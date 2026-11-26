"""The frozen (Windows installer) build must not re-enter itself.

In a PyInstaller build ``sys.executable`` is ``epi.exe``. Spawning
``[sys.executable, "-m", "epi_cli", ...]`` or ``[sys.executable, script]``
therefore runs the CLI with a path where a command belongs, and the demo fails
with "No such command '...demo_refund.py'". These tests pin the two paths that
broke, without needing a frozen build.
"""

from __future__ import annotations

import pathlib
import sys

import epi_cli.dev as dev

REPO = pathlib.Path(__file__).resolve().parents[1]


def test_epi_argv_uses_module_in_source_checkout(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    argv = dev._epi_argv("verify", "--json", "f.epi")
    assert argv == [sys.executable, "-m", "epi_cli", "verify", "--json", "f.epi"]


def test_epi_argv_drops_the_module_flag_when_frozen(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    argv = dev._epi_argv("verify", "--json", "f.epi")
    assert argv == [sys.executable, "verify", "--json", "f.epi"]
    assert "-m" not in argv


def test_demo_script_runs_in_process_when_frozen(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    called = {}

    def fake_in_process(script_path, child_env):
        called["path"] = script_path
        called["env"] = child_env
        return True

    monkeypatch.setattr(dev, "_run_demo_script_in_process", fake_in_process)

    def no_subprocess(*a, **k):  # pragma: no cover - must not run
        raise AssertionError("frozen build spawned a subprocess for the demo script")

    monkeypatch.setattr(dev.subprocess, "run", no_subprocess)
    script = tmp_path / "demo.py"
    script.write_text("print('ok')", encoding="utf-8")

    assert dev._run_demo_script(script, {}) is True
    assert called["path"] == script


def test_no_frozen_unsafe_invocation_remains():
    """Guard: every self-invocation goes through _epi_argv or the frozen branch."""
    text = (REPO / "epi_cli" / "dev.py").read_text(encoding="utf-8")
    assert text.count('"-m", "epi_cli"') == 1, (
        "the only -m epi_cli invocation must be inside _epi_argv()"
    )
    assert text.count("[sys.executable, str(script_path)]") == 1, (
        "the script spawn must stay in the non-frozen branch of _run_demo_script"
    )
    frozen_branch = text.index('if getattr(sys, "frozen", False):\n        return _run_demo_script_in_process')
    spawn = text.index("[sys.executable, str(script_path)]")
    assert frozen_branch < spawn, "the frozen branch must return before the subprocess spawn"
