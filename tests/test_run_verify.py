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
                "spec_version": "4.1.0",
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


# ─────────────────────────────────────────────────────────────
# Tests: prev_hash chain verification
# ─────────────────────────────────────────────────────────────

class TestPrevHashChainVerification:
    """Tests for prev_hash chain integrity."""

    def _make_step_dicts(self, tamper_step_index: int | None = None) -> list[dict]:
        """Build a list of 3 step dicts with a valid JSON-hashed prev_hash chain."""
        from epi_core.serialize import get_canonical_hash
        from epi_core.schemas import StepModel

        steps = []
        prev_hash = "CHAIN_START"
        for i in range(3):
            step = StepModel(
                index=i,
                timestamp=utc_now(),
                kind="test.step",
                content={"msg": f"step-{i}"},
                prev_hash=prev_hash,
            )
            steps.append(step)
            prev_hash = get_canonical_hash(step, format="json")

        if tamper_step_index is not None:
            steps[tamper_step_index].content["tampered"] = True

        return [s.model_dump(mode="json") for s in steps]

    def test_intact_chain_passes(self):
        """A valid chain should verify cleanly."""
        from epi_cli.verify import _verify_step_chain

        step_dicts = self._make_step_dicts()
        ok, breaks = _verify_step_chain(step_dicts)
        assert ok is True
        assert breaks == []

    def test_tampered_chain_detected(self):
        """Modifying a step's content should break the prev_hash chain."""
        from epi_cli.verify import _verify_step_chain

        step_dicts = self._make_step_dicts(tamper_step_index=1)
        ok, breaks = _verify_step_chain(step_dicts)
        assert ok is False
        assert any("prev_hash mismatch" in b for b in breaks)

    def test_single_step_no_chain(self):
        """A single step has no chain to verify — should pass."""
        from epi_cli.verify import _verify_step_chain

        ok, breaks = _verify_step_chain([{"index": 0, "kind": "test"}])
        assert ok is True
        assert breaks == []

    def test_empty_steps_no_chain(self):
        """Empty step list should pass."""
        from epi_cli.verify import _verify_step_chain

        ok, breaks = _verify_step_chain([])
        assert ok is True
        assert breaks == []

    def test_genesis_step_skipped(self):
        """Steps with prev_hash='CHAIN_START' are skipped."""
        from epi_cli.verify import _verify_step_chain

        step_dicts = [
            {"index": 0, "kind": "start", "prev_hash": "CHAIN_START"},
            {"index": 1, "kind": "middle", "prev_hash": "CHAIN_START"},
        ]
        ok, breaks = _verify_step_chain(step_dicts)
        assert ok is True
        assert breaks == []

    def test_old_cbor_artifact_graceful(self):
        """Steps with CBOR-hashed prev_hash should not crash (graceful degradation)."""
        from epi_cli.verify import _verify_step_chain

        # Simulate an old artifact: prev_hash is a CBOR hash that won't match JSON
        step_dicts = [
            {"index": 0, "kind": "test", "content": {"a": 1}},
            {"index": 1, "kind": "test", "content": {"b": 2}, "prev_hash": "deadbeef" * 8},
        ]
        ok, breaks = _verify_step_chain(step_dicts)
        # Should detect the mismatch, not crash
        assert ok is False
        assert any("prev_hash mismatch" in b for b in breaks)


class TestStepSequenceCompleteness:
    """Tests for AUD-CO-01 step sequence completeness."""

    def test_complete_sequence_passes(self):
        from epi_cli.verify import _audit_step_sequence_completeness

        steps = [
            {"index": 0, "kind": "llm.request", "span_id": "span-1"},
            {"index": 1, "kind": "llm.response", "span_id": "span-1"},
            {"index": 2, "kind": "tool.call", "content": {"call_id": "call-1"}},
            {"index": 3, "kind": "tool.response", "content": {"call_id": "call-1"}},
            {"index": 4, "kind": "agent.approval.request", "content": {"action": "approve"}},
            {"index": 5, "kind": "agent.approval.response", "content": {"action": "approve"}},
        ]
        ok, gaps = _audit_step_sequence_completeness(steps)
        assert ok is True
        assert not gaps

    def test_missing_tool_response(self):
        from epi_cli.verify import _audit_step_sequence_completeness

        steps = [
            {"index": 0, "kind": "tool.call", "content": {"call_id": "call-1"}},
            {"index": 1, "kind": "tool.call", "content": {"call_id": "call-2"}},
            {"index": 2, "kind": "tool.response", "content": {"call_id": "call-2"}},
        ]
        ok, gaps = _audit_step_sequence_completeness(steps)
        assert ok is False
        assert len(gaps) == 1
        assert "tool.call at step 0 is missing a corresponding tool.response" in gaps[0]

    def test_missing_llm_response(self):
        from epi_cli.verify import _audit_step_sequence_completeness

        steps = [
            {"index": 0, "kind": "llm.request", "span_id": "span-1"},
            {"index": 1, "kind": "llm.request", "span_id": "span-2"},
            {"index": 2, "kind": "llm.error", "span_id": "span-2"},
        ]
        ok, gaps = _audit_step_sequence_completeness(steps)
        assert ok is False
        assert len(gaps) == 1
        assert "llm.request at step 0 is missing a corresponding response or error" in gaps[0]

    def test_missing_approval_response(self):
        from epi_cli.verify import _audit_step_sequence_completeness

        steps = [
            {"index": 0, "kind": "agent.approval.request", "content": {"action": "action-1"}},
            {"index": 1, "kind": "agent.approval.request", "content": {"action": "action-2"}},
            {"index": 2, "kind": "agent.approval.response", "content": {"action": "action-2"}},
        ]
        ok, gaps = _audit_step_sequence_completeness(steps)
        assert ok is False
        assert len(gaps) == 1
        assert "agent.approval.request for 'action-1' at step 0 is missing a response" in gaps[0]

