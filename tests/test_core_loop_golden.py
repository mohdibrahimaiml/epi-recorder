"""Golden path: record → seal → verify → view assets (core loop).

This is the contract every release must keep boringly green.
"""

from __future__ import annotations

import json
import zipfile
from collections import Counter
from pathlib import Path

import pytest
from typer.testing import CliRunner

from epi_cli.main import app as cli_app
from epi_core.container import EPIContainer
from epi_core.trust import verify_embedded_manifest_signature
from epi_recorder import get_current_session, record

runner = CliRunner()


@pytest.fixture
def epi_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    home = tmp_path / "epi_home"
    home.mkdir()
    monkeypatch.setenv("EPI_HOME", str(home))
    monkeypatch.setenv("EPI_KEYS_DIR", str(home / "keys"))
    monkeypatch.setenv("EPI_TRUSTED_KEYS_DIR", str(home / "trusted_keys"))
    # Keep tests offline / fast
    monkeypatch.setenv("EPI_NOTARIZE", "0")
    return home


def test_record_seal_verify_no_duplicate_zip_members(epi_home, tmp_path: Path):
    out = tmp_path / "golden.epi"

    with record(str(out), goal="golden-path", workflow_name="golden"):
        s = get_current_session()
        assert s is not None
        s.log_step("tool.call", {"tool": "lookup_account", "args": {"id": "A-1"}})
        s.log("tool.response", {"tool": "lookup_account", "result": {"balance": 250}})
        s.log("decision", action="approve", reason="within policy")

    assert out.is_file()
    assert out.stat().st_size > 1000

    # Unique zip member names (no Duplicate name: VERIFY.txt)
    with EPIContainer._payload_zip_path(out) as payload:
        with zipfile.ZipFile(payload) as zf:
            names = zf.namelist()
    counts = Counter(names)
    dups = {n: c for n, c in counts.items() if c > 1}
    assert not dups, f"Duplicate archive members: {dups}"
    assert "VERIFY.txt" in counts and counts["VERIFY.txt"] == 1
    assert "manifest.json" in counts and counts["manifest.json"] == 1
    assert "viewer.html" in counts and counts["viewer.html"] == 1
    assert "steps.jsonl" in counts

    # Cryptographic verify via library
    manifest = EPIContainer.read_manifest(out)
    sig_result = verify_embedded_manifest_signature(manifest)
    # Returns (valid, signer_name, message)
    assert sig_result[0] is True, sig_result
    integrity_ok, mismatches = EPIContainer.verify_integrity(out)
    assert integrity_ok is True, mismatches

    # CLI verify
    result = runner.invoke(cli_app, ["verify", "--json", str(out)])
    assert result.exit_code == 0, result.output
    report = json.loads(result.stdout)
    assert report["facts"]["integrity_ok"] is True
    assert report["facts"]["signature_valid"] is True

    # CLI view should resolve without crash (open may launch browser — use --no-open if exists)
    help_r = runner.invoke(cli_app, ["view", "--help"])
    assert help_r.exit_code == 0
    # Extract embedded viewer for smoke check
    with EPIContainer._payload_zip_path(out) as payload:
        with zipfile.ZipFile(payload) as zf:
            html = zf.read("viewer.html").decode("utf-8", errors="replace")
    assert len(html) > 500
    assert "html" in html.lower()


def test_record_zero_config_and_verify(epi_home, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(tmp_path)
    with record(goal="zero-config"):
        s = get_current_session()
        assert s is not None
        s.log_step("custom.note", {"msg": "hello"})

    # zero-config writes under ./epi-recordings
    recordings = list((tmp_path / "epi-recordings").glob("*.epi"))
    assert recordings, "expected auto-generated .epi under epi-recordings/"
    artifact = recordings[0]

    result = runner.invoke(cli_app, ["verify", "--json", str(artifact)])
    assert result.exit_code == 0, result.output
    report = json.loads(result.stdout)
    assert report["facts"]["integrity_ok"] is True
