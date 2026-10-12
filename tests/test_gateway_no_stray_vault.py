"""`epi gateway serve/export` must not create ./evidence_vault in the cwd.

Regression: epi_gateway.main built a module-level ``app = create_app()`` at
import time with default settings (storage ``./evidence_vault``), so every
command that imported the module left cases.sqlite3, share.sqlite3, events/
and shared-objects/ in whatever directory the user ran it from.
"""

from __future__ import annotations

import importlib
import os
import subprocess
import sys
from pathlib import Path

from fastapi.testclient import TestClient
from typer.testing import CliRunner

REPO_ROOT = Path(__file__).resolve().parents[1]


def _fresh_gateway_import(monkeypatch):
    """Drop the cached module so the command imports it inside the temp cwd."""
    monkeypatch.delitem(sys.modules, "epi_gateway.main", raising=False)
    return importlib.import_module("epi_gateway.main")


def _clean_gateway_env(monkeypatch):
    for key in list(os.environ):
        if key.startswith("EPI_GATEWAY_") or key.startswith("EPI_WITNESS_"):
            monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("EPI_GATEWAY_DISABLE_SIGNING", "1")


def test_importing_gateway_main_touches_no_disk(tmp_path):
    """A fresh interpreter importing the module must leave the cwd empty."""
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    env = dict(os.environ)
    env["HOME"] = str(tmp_path / "home")
    env["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    env.pop("EPI_GATEWAY_STORAGE_DIR", None)
    code = (
        "import epi_gateway.main as m\n"
        "import epi_cli.gateway\n"
        "assert '_lazy_app' in vars(m) and m._lazy_app is None\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code], cwd=cwd, env=env, capture_output=True, text=True
    )
    assert proc.returncode == 0, proc.stderr
    assert list(cwd.iterdir()) == []


def test_module_level_app_is_lazy_and_cached(tmp_path, monkeypatch):
    _clean_gateway_env(monkeypatch)
    monkeypatch.setenv("EPI_GATEWAY_STORAGE_DIR", str(tmp_path / "vault"))
    import epi_gateway.main as gm

    monkeypatch.setattr(gm, "_lazy_app", None)
    first = gm.app
    assert first is gm.app
    from epi_gateway.main import app as imported

    assert imported is first
    # Built from the env at first access, not from import-time defaults.
    assert (tmp_path / "vault").is_dir()


def test_gateway_export_does_not_create_evidence_vault_in_cwd(tmp_path, monkeypatch):
    _clean_gateway_env(monkeypatch)
    from epi_gateway.worker import EvidenceWorker

    storage = tmp_path / "data"
    worker = EvidenceWorker(storage_dir=storage, batch_size=1, batch_timeout=0.1)
    touched = worker.store_items(
        [
            {
                "case_id": "case-stray-1",
                "workflow_id": "wf-stray",
                "kind": "llm.request",
                "content": {"messages": [{"role": "user", "content": "hi"}]},
            }
        ]
    )
    assert touched
    assert (storage / "cases.sqlite3").is_file()

    cwd = tmp_path / "cwd"
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    _fresh_gateway_import(monkeypatch)
    from epi_cli.gateway import app as gw_app

    out = tmp_path / "out.epi"
    result = CliRunner().invoke(
        gw_app,
        ["export", "--case-id", "case-stray-1", "--out", str(out), "--storage-dir", str(storage)],
    )
    assert result.exit_code == 0, result.output
    assert out.is_file()
    assert not (cwd / "evidence_vault").exists()
    assert list(cwd.iterdir()) == []


def test_gateway_serve_does_not_create_evidence_vault_in_cwd(tmp_path, monkeypatch):
    _clean_gateway_env(monkeypatch)
    import uvicorn

    from epi_cli.gateway import app as gw_app

    cwd = tmp_path / "cwd"
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    _fresh_gateway_import(monkeypatch)
    seen = {}

    def fake_run(target, **kwargs):
        module_name, attr = target.split(":")
        factory = getattr(importlib.import_module(module_name), attr)
        assert kwargs.get("factory") is True
        with TestClient(factory()) as client:
            seen["health"] = client.get("/health").json()

    monkeypatch.setattr(uvicorn, "run", fake_run)
    storage = tmp_path / ".epi-data"
    result = CliRunner().invoke(gw_app, ["serve", "--storage-dir", str(storage)])
    assert result.exit_code == 0, result.output
    assert seen["health"]["storage_dir"] == str(storage.resolve())
    assert storage.is_dir()
    assert not (cwd / "evidence_vault").exists()
    assert list(cwd.iterdir()) == []
