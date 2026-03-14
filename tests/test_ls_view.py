"""
Tests for epi_cli.ls — _format_metrics, _get_recording_info
Tests for epi_cli.view — _resolve_epi_file, _make_temp_dir, _open_in_browser, _cleanup_after_delay
"""

import json
import hashlib
import time
import zipfile
from pathlib import Path
from datetime import datetime
from uuid import uuid4
from unittest.mock import patch, MagicMock

import pytest

from epi_core.schemas import ManifestModel


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _make_epi(tmp_path: Path, include_viewer: bool = True, signed: bool = False) -> Path:
    steps = b'{"index":0,"kind":"test","content":{}}\n'
    manifest = ManifestModel(
        workflow_id=uuid4(),
        created_at=datetime.utcnow(),
        cli_command="python test_script.py --arg",
        file_manifest={"steps.jsonl": _sha256(steps)},
        goal="Measure accuracy",
        metrics={"accuracy": 0.95, "loss": 0.05},
        tags=["test", "demo"],
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
# ls._format_metrics
# ─────────────────────────────────────────────────────────────

class TestFormatMetrics:
    def test_empty_dict_returns_empty(self):
        from epi_cli.ls import _format_metrics
        assert _format_metrics({}) == ""

    def test_none_returns_empty(self):
        from epi_cli.ls import _format_metrics
        assert _format_metrics(None) == ""

    def test_float_values_formatted(self):
        from epi_cli.ls import _format_metrics
        result = _format_metrics({"acc": 0.95678})
        assert "acc=0.96" in result

    def test_int_values_no_decimal(self):
        from epi_cli.ls import _format_metrics
        result = _format_metrics({"count": 42})
        assert "count=42" in result

    def test_multiple_metrics_joined(self):
        from epi_cli.ls import _format_metrics
        result = _format_metrics({"a": 1, "b": 2})
        assert "," in result


# ─────────────────────────────────────────────────────────────
# ls._get_recording_info
# ─────────────────────────────────────────────────────────────

class TestGetRecordingInfo:
    def test_returns_dict_for_valid_file(self, tmp_path):
        from epi_cli.ls import _get_recording_info
        epi = _make_epi(tmp_path)
        info = _get_recording_info(epi)
        assert isinstance(info, dict)
        assert info["name"] == "test.epi"

    def test_extracts_script_from_cli_command(self, tmp_path):
        from epi_cli.ls import _get_recording_info
        epi = _make_epi(tmp_path)
        info = _get_recording_info(epi)
        assert info["script"] == "test_script.py"

    def test_extracts_goal(self, tmp_path):
        from epi_cli.ls import _get_recording_info
        epi = _make_epi(tmp_path)
        info = _get_recording_info(epi)
        assert info["goal"] == "Measure accuracy"

    def test_extracts_metrics(self, tmp_path):
        from epi_cli.ls import _get_recording_info
        epi = _make_epi(tmp_path)
        info = _get_recording_info(epi)
        assert "accuracy" in info["metrics_summary"]

    def test_extracts_tags(self, tmp_path):
        from epi_cli.ls import _get_recording_info
        epi = _make_epi(tmp_path)
        info = _get_recording_info(epi)
        assert "test" in info["tags_summary"]

    def test_signed_field_no(self, tmp_path):
        from epi_cli.ls import _get_recording_info
        epi = _make_epi(tmp_path)
        info = _get_recording_info(epi)
        assert info["signed"] == "No"

    def test_status_ok_for_valid_file(self, tmp_path):
        from epi_cli.ls import _get_recording_info
        epi = _make_epi(tmp_path)
        info = _get_recording_info(epi)
        assert info["status"] == "[OK]"

    def test_error_on_bad_file(self, tmp_path):
        from epi_cli.ls import _get_recording_info
        bad = tmp_path / "bad.epi"
        bad.write_bytes(b"not a zip")
        info = _get_recording_info(bad)
        assert info["script"] == "Error"
        assert "ERR" in info["status"]

    def test_script_unknown_when_no_cli_command(self, tmp_path):
        from epi_cli.ls import _get_recording_info
        steps = b'{"index":0}\n'
        manifest = ManifestModel(file_manifest={"steps.jsonl": _sha256(steps)})
        epi = tmp_path / "noscript.epi"
        with zipfile.ZipFile(epi, "w") as zf:
            zf.writestr("mimetype", "application/vnd.epi+zip")
            zf.writestr("manifest.json", manifest.model_dump_json())
            zf.writestr("steps.jsonl", steps)
        info = _get_recording_info(epi)
        assert info["script"] == "Unknown"


# ─────────────────────────────────────────────────────────────
# view._resolve_epi_file
# ─────────────────────────────────────────────────────────────

class TestResolveEpiFile:
    def test_resolves_exact_path(self, tmp_path):
        from epi_cli.view import _resolve_epi_file
        epi = tmp_path / "test.epi"
        epi.write_bytes(b"dummy")
        result = _resolve_epi_file(str(epi))
        assert result == epi

    def test_adds_epi_extension(self, tmp_path):
        from epi_cli.view import _resolve_epi_file
        epi = tmp_path / "test.epi"
        epi.write_bytes(b"dummy")
        result = _resolve_epi_file(str(tmp_path / "test"))
        assert result == epi

    def test_searches_default_dir(self, tmp_path):
        from epi_cli.view import _resolve_epi_file
        recordings = tmp_path / "epi-recordings"
        recordings.mkdir()
        epi = recordings / "myfile.epi"
        epi.write_bytes(b"dummy")
        with patch("epi_cli.view.DEFAULT_DIR", recordings):
            result = _resolve_epi_file("myfile")
        assert result == epi

    def test_glob_stem_match(self, tmp_path):
        from epi_cli.view import _resolve_epi_file
        recordings = tmp_path / "epi-recordings"
        recordings.mkdir()
        epi = recordings / "myscript_20250101_120000.epi"
        epi.write_bytes(b"dummy")
        with patch("epi_cli.view.DEFAULT_DIR", recordings):
            result = _resolve_epi_file("myscript")
        assert result == epi

    def test_raises_when_not_found(self, tmp_path):
        from epi_cli.view import _resolve_epi_file
        with patch("epi_cli.view.DEFAULT_DIR", tmp_path / "epi-recordings"):
            with pytest.raises(FileNotFoundError):
                _resolve_epi_file("nonexistent")


# ─────────────────────────────────────────────────────────────
# view._make_temp_dir
# ─────────────────────────────────────────────────────────────

class TestMakeTempDir:
    def test_returns_path(self):
        from epi_cli.view import _make_temp_dir
        result = _make_temp_dir()
        assert result is not None
        assert result.exists()
        # Cleanup
        import shutil
        shutil.rmtree(result, ignore_errors=True)

    def test_returns_directory(self):
        from epi_cli.view import _make_temp_dir
        import shutil
        result = _make_temp_dir()
        assert result.is_dir()
        shutil.rmtree(result, ignore_errors=True)


# ─────────────────────────────────────────────────────────────
# view._open_in_browser
# ─────────────────────────────────────────────────────────────

class TestOpenInBrowser:
    def test_calls_webbrowser_open(self, tmp_path):
        from epi_cli.view import _open_in_browser
        viewer = tmp_path / "viewer.html"
        viewer.write_text("<html></html>")
        with patch("webbrowser.open") as mock_wb, \
             patch("sys.platform", "linux"):
            _open_in_browser(viewer)
        mock_wb.assert_called_once()

    def test_windows_uses_startfile(self, tmp_path):
        from epi_cli.view import _open_in_browser
        viewer = tmp_path / "viewer.html"
        viewer.write_text("<html></html>")
        with patch("sys.platform", "win32"), \
             patch("os.startfile") as mock_sf:
            _open_in_browser(viewer)
        mock_sf.assert_called_once_with(str(viewer))


# ─────────────────────────────────────────────────────────────
# view._cleanup_after_delay
# ─────────────────────────────────────────────────────────────

class TestCleanupAfterDelay:
    def test_removes_directory_after_delay(self, tmp_path):
        from epi_cli.view import _cleanup_after_delay
        target = tmp_path / "temp_viewer"
        target.mkdir()
        assert target.exists()
        _cleanup_after_delay(target, delay_seconds=0.05)
        time.sleep(0.2)  # wait for thread
        assert not target.exists()
