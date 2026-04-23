"""
Tests for epi_cli.run — _gen_auto_name, _verify_recording, _open_viewer.
Tests for epi_cli.verify — print_trust_report, verify_command logic.
"""

import json
import zipfile
from pathlib import Path
from uuid import uuid4
from unittest.mock import patch


from epi_core.schemas import ManifestModel
from epi_core.time_utils import utc_now, utc_now_iso


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

def _make_minimal_epi(tmp_path: Path, signed: bool = False, include_viewer: bool = True) -> Path:
    """Create a minimal valid .epi file for testing."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from epi_core.trust import sign_manifest

    epi_path = tmp_path / "test.epi"
    steps_content = json.dumps({
        "index": 0, "kind": "test.step",
        "timestamp": utc_now_iso(),
        "content": {"msg": "hello"}
    }) + "\n"

    import hashlib
    steps_hash = hashlib.sha256(steps_content.encode()).hexdigest()

    manifest = ManifestModel(
        workflow_id=uuid4(),
        created_at=utc_now(),
        cli_command="python test.py",
        file_manifest={"steps.jsonl": steps_hash},
    )

    if signed:
        private_key = Ed25519PrivateKey.generate()
        manifest = sign_manifest(manifest, private_key, "test")

    mimetype = "application/vnd.epi+zip"
    with zipfile.ZipFile(epi_path, "w") as zf:
        zf.writestr("mimetype", mimetype)
        zf.writestr("manifest.json", manifest.model_dump_json(indent=2))
        zf.writestr("steps.jsonl", steps_content)
        if include_viewer:
            zf.writestr("viewer.html", "<html><body>Viewer</body></html>")

    return epi_path


# ─────────────────────────────────────────────────────────────
# Tests: _gen_auto_name
# ─────────────────────────────────────────────────────────────

class TestGenAutoName:
    def test_name_contains_script_stem(self, tmp_path):
        from epi_cli.run import _gen_auto_name
        with patch("epi_cli.run.DEFAULT_DIR", tmp_path / "epi-recordings"):
            result = _gen_auto_name(Path("my_script.py"))
        assert "my_script" in result.name

    def test_name_has_timestamp(self, tmp_path):
        from epi_cli.run import _gen_auto_name
        with patch("epi_cli.run.DEFAULT_DIR", tmp_path / "epi-recordings"):
            result = _gen_auto_name(Path("demo.py"))
        # timestamp format: YYYYMMDD_HHMMSS
        parts = result.stem.split("_")
        assert len(parts) >= 3

    def test_name_has_epi_extension(self, tmp_path):
        from epi_cli.run import _gen_auto_name
        with patch("epi_cli.run.DEFAULT_DIR", tmp_path / "epi-recordings"):
            result = _gen_auto_name(Path("run.py"))
        assert result.suffix == ".epi"

    def test_dash_script_becomes_recording(self, tmp_path):
        from epi_cli.run import _gen_auto_name
        with patch("epi_cli.run.DEFAULT_DIR", tmp_path / "epi-recordings"):
            result = _gen_auto_name(Path("-"))
        assert "recording" in result.name

    def test_creates_output_directory(self, tmp_path):
        from epi_cli.run import _gen_auto_name
        recordings_dir = tmp_path / "epi-recordings"
        assert not recordings_dir.exists()
        with patch("epi_cli.run.DEFAULT_DIR", recordings_dir):
            _gen_auto_name(Path("script.py"))
        assert recordings_dir.exists()


# ─────────────────────────────────────────────────────────────
# Tests: _verify_recording
# ─────────────────────────────────────────────────────────────

class TestVerifyRecording:
    def test_unsigned_valid_file_returns_ok(self, tmp_path):
        from epi_cli.run import _verify_recording
        epi = _make_minimal_epi(tmp_path, signed=False)
        success, msg = _verify_recording(epi)
        assert success
        assert "OK" in msg

    def test_signed_valid_file_returns_verified(self, tmp_path):
        from epi_cli.run import _verify_recording
        epi = _make_minimal_epi(tmp_path, signed=True)
        success, msg = _verify_recording(epi)
        assert success
        assert "verified" in msg.lower() or "OK" in msg

    def test_nonexistent_file_returns_failure(self, tmp_path):
        from epi_cli.run import _verify_recording
        success, msg = _verify_recording(tmp_path / "nonexistent.epi")
        assert not success

    def test_tampered_file_returns_failure(self, tmp_path):
        from epi_cli.run import _verify_recording
        epi = _make_minimal_epi(tmp_path, signed=False)

        # Tamper: modify steps.jsonl
        with zipfile.ZipFile(epi, "r") as zin:
            files = {n: zin.read(n) for n in zin.namelist()}
        files["steps.jsonl"] = b'{"tampered": true}\n'
        tampered = tmp_path / "tampered.epi"
        with zipfile.ZipFile(tampered, "w") as zout:
            for name, data in files.items():
                zout.writestr(name, data)

        success, msg = _verify_recording(tampered)
        assert not success
        assert "mismatch" in msg.lower() or "fail" in msg.lower() or "integrity" in msg.lower()


# ─────────────────────────────────────────────────────────────
# Tests: _open_viewer
# ─────────────────────────────────────────────────────────────

class TestOpenViewer:
    def test_opens_viewer_when_present(self, tmp_path):
        from epi_cli.run import _open_viewer
        epi = _make_minimal_epi(tmp_path, signed=False)
        with patch("webbrowser.open", return_value=True) as mock_open:
            result = _open_viewer(epi)
        assert result is True
        mock_open.assert_called_once()

    def test_regenerates_viewer_when_no_viewer_html(self, tmp_path):
        from epi_cli.run import _open_viewer
        epi = _make_minimal_epi(tmp_path, include_viewer=False)
        with patch("webbrowser.open", return_value=True) as mock_open:
            result = _open_viewer(epi)
        assert result is True
        mock_open.assert_called_once()

    def test_returns_false_on_bad_zip(self, tmp_path):
        from epi_cli.run import _open_viewer
        bad = tmp_path / "bad.epi"
        bad.write_bytes(b"not a zip file")
        result = _open_viewer(bad)
        assert result is False


# ─────────────────────────────────────────────────────────────
# Tests: verify CLI print_trust_report
# ─────────────────────────────────────────────────────────────

class TestPrintTrustReport:
    def _make_report(self, trust_level="HIGH", integrity=True,
                     sig_valid=True, mismatches=None):
        return {
            "facts": {
                "integrity_ok": integrity,
                "signature_valid": sig_valid,
                "sequence_ok": True,
                "completeness_ok": True,
                "mismatches": mismatches or {},
                "has_signature": sig_valid is not None,
            },
            "identity": {
                "status": "KNOWN" if sig_valid else "UNKNOWN",
                "name": "default",
                "detail": "Test source",
            },
            "decision": {
                "status": "PASS" if (integrity and sig_valid) else "FAIL",
                "policy": "standard",
                "reason": "Test decision"
            },
            "metadata": {
                "workflow_id": str(uuid4()),
                "created_at": utc_now_iso(),
                "spec_version": "4.0.1",
                "files_checked": 2,
            },
            # Legacy fields for backward compatibility
            "trust_level": trust_level,
            "integrity_ok": integrity,
            "signature_valid": sig_valid,
            "signer": "default",
            "workflow_id": str(uuid4()),
            "created_at": utc_now_iso(),
            "spec_version": "4.0.1",
            "files_checked": 2,
            "mismatches_count": len(mismatches or {}),
        }

    def test_high_trust_no_exception(self, tmp_path):
        from epi_cli.verify import print_trust_report
        report = self._make_report("HIGH")
        print_trust_report(report, tmp_path / "test.epi")

    def test_medium_trust_no_exception(self, tmp_path):
        from epi_cli.verify import print_trust_report
        report = self._make_report("MEDIUM", sig_valid=None)
        print_trust_report(report, tmp_path / "test.epi")

    def test_none_trust_no_exception(self, tmp_path):
        from epi_cli.verify import print_trust_report
        report = self._make_report("NONE", integrity=False,
                                   sig_valid=False,
                                   mismatches={"steps.jsonl": "Hash mismatch"})
        print_trust_report(report, tmp_path / "test.epi")

    def test_verbose_mode_no_exception(self, tmp_path):
        from epi_cli.verify import print_trust_report
        report = self._make_report("HIGH")
        print_trust_report(report, tmp_path / "test.epi", verbose=True)
