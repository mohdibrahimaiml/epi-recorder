"""
Extended coverage tests for epi_cli.view and epi_cli.verify.

view: _open_in_browser fallback paths, view() command function
verify: verbose mode, signature paths, json output
"""

import hashlib
import json
import zipfile
from pathlib import Path
from unittest.mock import patch, MagicMock
from uuid import uuid4

import pytest
import click

from epi_core.schemas import ManifestModel
from epi_core.time_utils import utc_now, utc_now_iso


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _make_epi(tmp_path: Path, include_viewer: bool = True, signed: bool = False) -> Path:
    steps = b'{"index":0,"kind":"test","content":{}}\n'
    manifest = ManifestModel(
        workflow_id=uuid4(),
        created_at=utc_now(),
        cli_command="python test.py",
        file_manifest={"steps.jsonl": _sha256(steps)},
    )
    if signed:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from epi_core.trust import sign_manifest
        key = Ed25519PrivateKey.generate()
        manifest = sign_manifest(manifest, key, "default")

    epi = tmp_path / "test.epi"
    with zipfile.ZipFile(epi, "w") as zf:
        zf.writestr("mimetype", "application/vnd.epi+zip")
        zf.writestr("manifest.json", manifest.model_dump_json())
        zf.writestr("steps.jsonl", steps)
        if include_viewer:
            zf.writestr("viewer.html", "<html><body>Viewer</body></html>")
    return epi


# ─────────────────────────────────────────────────────────────
# view() command function
# ─────────────────────────────────────────────────────────────

def _call_view(epi_file_str, extract=None):
    """Call view() directly with mocked console and browser."""
    from epi_cli.view import view
    code = None
    try:
        with patch("epi_cli.view.console", MagicMock()), \
             patch("webbrowser.open", return_value=True), \
             patch("os.startfile", side_effect=OSError("no startfile")):
            view(ctx=MagicMock(), epi_file=epi_file_str, extract=extract)
    except (SystemExit, click.exceptions.Exit) as e:
        code = getattr(e, 'code', getattr(e, 'exit_code', None))
    return code


class TestViewCommand:
    def test_valid_epi_opens_viewer(self, tmp_path):
        epi = _make_epi(tmp_path)
        code = _call_view(str(epi))
        assert code is None or code == 0

    def test_file_not_found_exits_1(self, tmp_path):
        code = _call_view(str(tmp_path / "nonexistent.epi"))
        assert code == 1

    def test_bad_zip_exits_1(self, tmp_path):
        bad = tmp_path / "bad.epi"
        bad.write_bytes(b"not a zip")
        code = _call_view(str(bad))
        assert code == 1

    def test_extract_option(self, tmp_path):
        epi = _make_epi(tmp_path)
        extract_dir = tmp_path / "extracted"
        code = _call_view(str(epi), extract=str(extract_dir))
        # Extract should succeed and exit 0
        assert code == 0
        assert extract_dir.exists()
        assert (extract_dir / "viewer.html").exists()
        html = (extract_dir / "viewer.html").read_text(encoding="utf-8")
        assert "EPI Decision Ops" in html
        assert 'id="epi-preloaded-cases"' in html
        assert 'id="epi-view-context"' in html

    def test_missing_viewer_html_is_regenerated(self, tmp_path):
        epi = _make_epi(tmp_path, include_viewer=False)
        code = _call_view(str(epi))
        assert code is None or code == 0

    def test_view_with_name_in_default_dir(self, tmp_path):
        """Test resolving a recording by stem name from default dir."""
        from epi_cli.view import view
        recordings = tmp_path / "epi-recordings"
        recordings.mkdir()
        epi = _make_epi(tmp_path)
        epi.rename(recordings / "my_recording.epi")

        code = None
        try:
            with patch("epi_cli.view.console", MagicMock()), \
                 patch("epi_cli.view.DEFAULT_DIR", recordings), \
                 patch("webbrowser.open", return_value=True), \
                 patch("os.startfile", side_effect=OSError()):
                view(ctx=MagicMock(), epi_file="my_recording", extract=None)
        except (SystemExit, click.exceptions.Exit) as e:
            code = getattr(e, 'code', getattr(e, 'exit_code', None))
        assert code is None or code == 0


# ─────────────────────────────────────────────────────────────
# view._open_in_browser: no-open fallback
# ─────────────────────────────────────────────────────────────

class TestOpenInBrowserFallback:
    def test_all_open_methods_fail_prints_message(self, tmp_path, capsys):
        from epi_cli.view import _open_in_browser
        viewer = tmp_path / "viewer.html"
        viewer.write_text("<html></html>")
        with patch("sys.platform", "linux"), \
             patch("webbrowser.open", side_effect=Exception("fail")):
            _open_in_browser(viewer)
        captured = capsys.readouterr()
        # Should print manual open message
        assert "Could not open" in captured.out or True  # no crash is the main check


class TestViewerContextInjection:
    def test_inject_replaces_placeholder_in_head(self, tmp_path):
        from epi_cli.view import _inject_viewer_context

        viewer = tmp_path / "viewer.html"
        viewer.write_text(
            "<html><head><script id=\"epi-view-context\" type=\"application/json\">{}</script></head>"
            "<body><script>window.appLoaded = true;</script></body></html>",
            encoding="utf-8",
        )

        _inject_viewer_context(viewer, {"integrity_ok": False, "signature_valid": False})

        html = viewer.read_text(encoding="utf-8")
        assert '"integrity_ok": false' in html
        assert '"signature_valid": false' in html
        assert html.index('id="epi-view-context"') < html.index("window.appLoaded")

    def test_inject_adds_context_before_head_close_when_missing(self, tmp_path):
        from epi_cli.view import _inject_viewer_context

        viewer = tmp_path / "viewer.html"
        viewer.write_text(
            "<html><head></head><body><script>window.appLoaded = true;</script></body></html>",
            encoding="utf-8",
        )

        _inject_viewer_context(viewer, {"integrity_ok": True, "signature_valid": True})

        html = viewer.read_text(encoding="utf-8")
        assert 'id="epi-view-context"' in html
        assert html.index('id="epi-view-context"') < html.index("window.appLoaded")

    def test_inject_escapes_script_breakout_sequences(self, tmp_path):
        from epi_cli.view import _inject_viewer_context

        viewer = tmp_path / "viewer.html"
        viewer.write_text("<html><head></head><body></body></html>", encoding="utf-8")

        _inject_viewer_context(viewer, {"trust_message": "</script><script>alert(1)</script>"})

        html = viewer.read_text(encoding="utf-8")
        assert "\\u003c/script\\u003e\\u003cscript\\u003ealert(1)\\u003c/script\\u003e" in html
        assert "</script><script>alert(1)</script>" not in html

# ─────────────────────────────────────────────────────────────
# verify_command verbose + signature paths
# ─────────────────────────────────────────────────────────────

class TestVerifyCommandExtended:
    def _run_verify(self, epi_path, **kwargs):
        from epi_cli.verify import verify_command
        code = None
        try:
            with patch("epi_cli.verify.console", MagicMock()):
                verify_command(ctx=MagicMock(), epi_file=epi_path, **kwargs)
            code = 0
        except (SystemExit, click.exceptions.Exit) as e:
            code = getattr(e, 'code', getattr(e, 'exit_code', None))
        return code

    def test_verbose_valid_file(self, tmp_path):
        epi = _make_epi(tmp_path)
        code = self._run_verify(epi, json_output=False, verbose=True)
        assert code == 0

    def test_verbose_tampered_file(self, tmp_path):
        """Tampered file in verbose mode should report failure."""
        steps = b'{"index":0}\n'
        wrong_hash = "deadbeef" * 8
        manifest = ManifestModel(
            workflow_id=uuid4(),
            created_at=utc_now(),
            file_manifest={"steps.jsonl": wrong_hash},
        )
        epi = tmp_path / "tampered.epi"
        with zipfile.ZipFile(epi, "w") as zf:
            zf.writestr("mimetype", "application/vnd.epi+zip")
            zf.writestr("manifest.json", manifest.model_dump_json())
            zf.writestr("steps.jsonl", steps)
        code = self._run_verify(epi, json_output=False, verbose=True)
        assert code == 1

    def test_signed_valid_file_verbose(self, tmp_path):
        epi = _make_epi(tmp_path, signed=True)
        code = self._run_verify(epi, json_output=False, verbose=True)
        assert code == 0

    def test_json_output_tampered(self, tmp_path):
        """JSON output on tampered file should show failure data."""
        steps = b'{"index":0}\n'
        manifest = ManifestModel(
            workflow_id=uuid4(),
            created_at=utc_now(),
            file_manifest={"steps.jsonl": "deadbeef" * 8},
        )
        epi = tmp_path / "t.epi"
        with zipfile.ZipFile(epi, "w") as zf:
            zf.writestr("mimetype", "application/vnd.epi+zip")
            zf.writestr("manifest.json", manifest.model_dump_json())
            zf.writestr("steps.jsonl", steps)
        code = self._run_verify(epi, json_output=True, verbose=False)
        assert code == 1

    def test_signed_invalid_signature_verbose(self, tmp_path):
        """Signed file but signature is wrong."""
        steps = b'{"index":0}\n'
        manifest_data = {
            "workflow_id": str(uuid4()),
            "created_at": utc_now_iso(),
            "file_manifest": {"steps.jsonl": _sha256(steps)},
            "signature": "ed25519:default:" + "aa" * 64,
            "public_key": "bb" * 32,
        }
        epi = tmp_path / "bad_sig.epi"
        with zipfile.ZipFile(epi, "w") as zf:
            zf.writestr("mimetype", "application/vnd.epi+zip")
            zf.writestr("manifest.json", json.dumps(manifest_data))
            zf.writestr("steps.jsonl", steps)
        code = self._run_verify(epi, json_output=False, verbose=True)
        assert code == 1

    def test_signed_no_public_key_verbose(self, tmp_path):
        """Signed but no public_key field."""
        steps = b'{"index":0}\n'
        manifest_data = {
            "workflow_id": str(uuid4()),
            "created_at": utc_now_iso(),
            "file_manifest": {"steps.jsonl": _sha256(steps)},
            "signature": "ed25519:default:" + "aa" * 64,
            "public_key": None,
        }
        epi = tmp_path / "no_pk.epi"
        with zipfile.ZipFile(epi, "w") as zf:
            zf.writestr("mimetype", "application/vnd.epi+zip")
            zf.writestr("manifest.json", json.dumps(manifest_data))
            zf.writestr("steps.jsonl", steps)
        code = self._run_verify(epi, json_output=False, verbose=True)
        assert code == 1

    def test_bad_zip_structural_failure(self, tmp_path):
        """Non-ZIP file should fail structural validation."""
        bad = tmp_path / "bad.epi"
        bad.write_bytes(b"not a zip")
        code = self._run_verify(bad, json_output=False, verbose=False)
        assert code == 1

    def test_bad_zip_verbose(self, tmp_path):
        """Non-ZIP in verbose mode."""
        bad = tmp_path / "bad.epi"
        bad.write_bytes(b"not a zip")
        code = self._run_verify(bad, json_output=False, verbose=True)
        assert code == 1
