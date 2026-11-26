"""A bare `epi view` must not exit with a usage error.

The Windows package's Start-menu entry runs `epi view` with no argument
(`uap10:Parameters="view"`). Before this, that printed "Missing argument
'epi_file'" and exited 2, so the app window flashed and closed — exactly what
the Store rejects. With a keyboard it now offers the file dialog and falls back
to a prompt; without a terminal it keeps the old usage error so scripts and
tests behave the same.
"""
from __future__ import annotations

import subprocess
from types import SimpleNamespace

import pytest

from epi_cli import view as view_module
from epi_cli.main import app
from typer.testing import CliRunner

runner = CliRunner()


def test_picker_uses_a_windows_open_file_dialog(monkeypatch):
    calls = {}

    def fake_run(argv, **kwargs):
        calls["argv"] = argv
        calls["kwargs"] = kwargs
        return subprocess.CompletedProcess(argv, 0, stdout="C:\\records\\demo.epi\n", stderr="")

    monkeypatch.setattr(view_module.os, "name", "nt")
    monkeypatch.setattr(view_module.subprocess, "run", fake_run)

    assert view_module._windows_choose_file() == r"C:\records\demo.epi"
    script = calls["argv"][-1]
    assert "OpenFileDialog" in script
    assert "*.epi" in script


def test_picker_is_none_off_windows(monkeypatch):
    monkeypatch.setattr(view_module.os, "name", "posix")
    assert view_module._windows_choose_file() is None


def test_cancelled_dialog_is_none_not_an_error(monkeypatch):
    monkeypatch.setattr(view_module.os, "name", "nt")
    monkeypatch.setattr(
        view_module.subprocess,
        "run",
        lambda argv, **kw: subprocess.CompletedProcess(argv, 0, stdout="", stderr=""),
    )
    assert view_module._windows_choose_file() is None


def test_missing_powershell_does_not_raise(monkeypatch):
    def boom(argv, **kwargs):
        raise OSError("powershell not found")

    monkeypatch.setattr(view_module.os, "name", "nt")
    monkeypatch.setattr(view_module.subprocess, "run", boom)
    assert view_module._windows_choose_file() is None


def test_bare_view_without_a_terminal_keeps_the_usage_error(monkeypatch):
    # Never open a real dialog in a test run.
    monkeypatch.setattr(view_module, "_windows_choose_file", lambda: None)

    result = runner.invoke(app, ["view"])

    assert result.exit_code == 2
    assert "Missing argument 'epi_file'" in result.stdout


def test_prompt_is_used_when_the_dialog_cannot_open(monkeypatch):
    monkeypatch.setattr(view_module, "_windows_choose_file", lambda: None)
    monkeypatch.setattr(view_module.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt="": r' "C:\records\typed.epi" ')

    assert view_module._choose_epi_file() == r"C:\records\typed.epi"


def test_prompt_enter_quits(monkeypatch):
    monkeypatch.setattr(view_module, "_windows_choose_file", lambda: None)
    monkeypatch.setattr(view_module.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt="": "")

    assert view_module._choose_epi_file() is None


def test_view_signature_accepts_no_file(tmp_path):
    """The CLI must accept `epi view` with no argument at all."""
    from epi_cli.main import view as view_command

    param = view_command.__defaults__ or ()
    # Typer stores the argument object; the important part is that it is not
    # required any more. A required Argument would have default ... (Ellipsis).
    assert not any(value is ... for value in param), (
        "epi view still declares a required file argument"
    )
