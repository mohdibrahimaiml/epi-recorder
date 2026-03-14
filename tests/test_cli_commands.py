"""
Tests for CLI command callbacks using typer.testing.CliRunner.

Covers:
- epi_cli.ls: ls callback (empty dir, recordings found)
- epi_cli.debug: debug callback (mocked MistakeDetector)
- epi_cli.verify: verify_command (valid, tampered, missing)
- epi_cli.view: view (resolve, open, extract)
"""

import hashlib
import json
import zipfile
from datetime import datetime
from pathlib import Path
from unittest.mock import patch, MagicMock
from uuid import uuid4

import pytest
from typer.testing import CliRunner

from epi_core.schemas import ManifestModel


runner = CliRunner()


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _make_epi(tmp_path: Path, include_viewer: bool = True,
              signed: bool = False, tamper: bool = False) -> Path:
    steps = b'{"index":0,"kind":"test","content":{}}\n'
    steps_hash = _sha256(steps)
    if tamper:
        steps_hash = "deadbeef" * 8  # wrong hash

    manifest = ManifestModel(
        workflow_id=uuid4(),
        created_at=datetime.utcnow(),
        cli_command="python test_script.py",
        file_manifest={"steps.jsonl": steps_hash},
    )
    epi = tmp_path / "test.epi"
    with zipfile.ZipFile(epi, "w") as zf:
        zf.writestr("mimetype", "application/vnd.epi+zip")
        zf.writestr("manifest.json", manifest.model_dump_json())
        zf.writestr("steps.jsonl", steps)
        if include_viewer:
            zf.writestr("viewer.html", "<html><body>Viewer</body></html>")
    return epi


# ─────────────────────────────────────────────────────────────
# ls callback tests
# ─────────────────────────────────────────────────────────────

class TestLsCallback:
    def test_no_recordings_message(self, tmp_path):
        from epi_cli.ls import app
        with patch("epi_cli.ls.DEFAULT_DIR", tmp_path / "epi-recordings"), \
             patch("epi_cli.ls.console", _mock_console()):
            result = runner.invoke(app, [])
        assert result.exit_code == 0

    def test_shows_recordings(self, tmp_path):
        from epi_cli.ls import ls
        recordings = tmp_path / "epi-recordings"
        recordings.mkdir()
        epi = _make_epi(tmp_path)
        epi.rename(recordings / "my_recording.epi")
        mock_console = _mock_console()
        with patch("epi_cli.ls.DEFAULT_DIR", recordings), \
             patch("epi_cli.ls.console", mock_console):
            ls()
        # console.print was called (recording was found)
        mock_console.print.assert_called()

    def test_all_flag_includes_current_dir(self, tmp_path):
        from epi_cli.ls import ls
        import os
        epi = _make_epi(tmp_path)
        original_cwd = os.getcwd()
        mock_console = _mock_console()
        try:
            os.chdir(tmp_path)
            with patch("epi_cli.ls.DEFAULT_DIR", tmp_path / "epi-recordings"), \
                 patch("epi_cli.ls.console", mock_console):
                ls(all_dirs=True)
        finally:
            os.chdir(original_cwd)
        mock_console.print.assert_called()

    def test_no_recordings_when_dir_missing(self, tmp_path):
        from epi_cli.ls import ls
        mock_console = _mock_console()
        with patch("epi_cli.ls.DEFAULT_DIR", tmp_path / "nonexistent"), \
             patch("epi_cli.ls.console", mock_console):
            ls()
        # At minimum, "No recordings found" is printed
        mock_console.print.assert_called()


# ─────────────────────────────────────────────────────────────
# debug callback tests (mocked MistakeDetector)
# ─────────────────────────────────────────────────────────────

def _mock_console():
    """Return a MagicMock console that silently eats all output."""
    return MagicMock()


def _call_debug(epi_path, output_json=False, export=None, verbose=False,
                mock_mistakes=None, mock_summary="OK"):
    """Call debug() directly with mocked detector and console."""
    import typer, click
    from epi_cli.debug import debug
    mock_detector = MagicMock()
    mock_detector.analyze.return_value = mock_mistakes or []
    mock_detector.get_summary.return_value = mock_summary
    ctx = MagicMock()
    try:
        with patch("epi_cli.debug.MistakeDetector", return_value=mock_detector), \
             patch("epi_cli.debug.console", _mock_console()):
            debug(ctx=ctx, epi_file=epi_path, output_json=output_json,
                  export=export, verbose=verbose)
        return 0
    except (SystemExit, click.exceptions.Exit) as e:
        return getattr(e, 'code', getattr(e, 'exit_code', 1))


class TestDebugCallback:
    def test_no_mistakes_exits_0(self, tmp_path):
        epi = _make_epi(tmp_path)
        code = _call_debug(epi, mock_mistakes=[], mock_summary="No mistakes.")
        assert code == 0

    def test_critical_mistake_exits_1(self, tmp_path):
        epi = _make_epi(tmp_path)
        mistakes = [{"type": "loop", "step": 1, "severity": "CRITICAL"}]
        code = _call_debug(epi, mock_mistakes=mistakes, mock_summary="1 critical issue.")
        assert code == 1

    def test_json_output_no_crash(self, tmp_path):
        epi = _make_epi(tmp_path)
        code = _call_debug(epi, output_json=True, mock_mistakes=[], mock_summary="OK")
        assert code == 0

    def test_file_not_found_exits_2(self, tmp_path):
        import typer, click
        from epi_cli.debug import debug
        ctx = MagicMock()
        with patch("epi_cli.debug.MistakeDetector",
                   side_effect=FileNotFoundError("not found")), \
             patch("epi_cli.debug.console", _mock_console()):
            try:
                debug(ctx=ctx, epi_file=tmp_path / "ghost.epi",
                      output_json=False, export=None, verbose=False)
                code = 0
            except (SystemExit, click.exceptions.Exit) as e:
                code = getattr(e, 'code', getattr(e, 'exit_code', 1))
        assert code == 2

    def test_verbose_with_mistakes_no_crash(self, tmp_path):
        epi = _make_epi(tmp_path)
        mistakes = [{"type": "loop", "step": 1, "severity": "MEDIUM", "detail": "info"}]
        code = _call_debug(epi, verbose=True, mock_mistakes=mistakes, mock_summary="1 issue.")
        assert code == 0

    def test_export_writes_file(self, tmp_path):
        epi = _make_epi(tmp_path)
        export_file = tmp_path / "report.txt"
        code = _call_debug(epi, export=export_file, mock_mistakes=[], mock_summary="No mistakes.")
        assert code == 0
        assert export_file.exists()


# ─────────────────────────────────────────────────────────────
# verify_command tests
# ─────────────────────────────────────────────────────────────

class TestVerifyCommand:
    def _run_verify(self, epi_path, **kwargs):
        """Invoke verify_command, return exit code (0 = success)."""
        from epi_cli.verify import verify_command
        import click
        ctx = MagicMock()
        try:
            verify_command(ctx=ctx, epi_file=epi_path, **kwargs)
            return 0
        except (SystemExit, click.exceptions.Exit) as e:
            return getattr(e, 'code', getattr(e, 'exit_code', 1))

    def test_valid_file_exits_0(self, tmp_path):
        epi = _make_epi(tmp_path)
        with patch("epi_cli.verify.console", _mock_console()):
            code = self._run_verify(epi, json_output=False, verbose=False)
        assert code == 0

    def test_missing_file_exits_1(self, tmp_path):
        with patch("epi_cli.verify.console", _mock_console()):
            code = self._run_verify(tmp_path / "ghost.epi",
                                    json_output=False, verbose=False)
        assert code == 1

    def test_tampered_file_exits_1(self, tmp_path):
        epi = _make_epi(tmp_path, tamper=True)
        with patch("epi_cli.verify.console", _mock_console()):
            code = self._run_verify(epi, json_output=False, verbose=False)
        assert code == 1

    def test_verbose_mode_no_crash(self, tmp_path):
        epi = _make_epi(tmp_path)
        with patch("epi_cli.verify.console", _mock_console()):
            code = self._run_verify(epi, json_output=False, verbose=True)
        # Valid file in verbose mode should exit 0
        assert code == 0

    def test_json_output_valid_file(self, tmp_path):
        epi = _make_epi(tmp_path)
        with patch("epi_cli.verify.console", _mock_console()):
            code = self._run_verify(epi, json_output=True, verbose=False)
        assert code == 0


# ─────────────────────────────────────────────────────────────
# view._open_in_browser edge cases
# ─────────────────────────────────────────────────────────────

class TestViewEdgeCases:
    def test_resolve_with_epi_in_default_dir(self, tmp_path):
        """_resolve_epi_file with exact epi extension in default dir."""
        from epi_cli.view import _resolve_epi_file
        recordings = tmp_path / "epi-recordings"
        recordings.mkdir()
        epi = recordings / "recording.epi"
        epi.write_bytes(b"dummy")
        with patch("epi_cli.view.DEFAULT_DIR", recordings):
            result = _resolve_epi_file("recording.epi")
        assert result == epi

    def test_open_in_browser_startfile_fallback(self, tmp_path):
        """If startfile fails on Windows, fallback to webbrowser."""
        from epi_cli.view import _open_in_browser
        viewer = tmp_path / "viewer.html"
        viewer.write_text("<html></html>")
        with patch("sys.platform", "win32"), \
             patch("os.startfile", side_effect=OSError("permission denied")), \
             patch("webbrowser.open") as mock_wb:
            _open_in_browser(viewer)
        mock_wb.assert_called_once()
