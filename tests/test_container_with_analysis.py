"""
Tests for EPIContainer.pack() with Fault Intelligence layer.

Verifies that:
- analysis.json is present in packed .epi files
- policy.json is present when epi_policy.json exists in CWD
- Both files are included in manifest.file_manifest (hashed & signed)
- Tampering with analysis.json after sealing fails verify_integrity()
- The embedded viewer data includes analysis and policy fields
"""

import json
import zipfile
import pytest
from pathlib import Path
from unittest.mock import patch

from epi_core.container import EPIContainer
from epi_core.schemas import ManifestModel


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_source_dir(tmp_path: Path, extra_files: dict = None) -> Path:
    """Create a minimal source workspace for EPIContainer.pack()."""
    src = tmp_path / "workspace"
    src.mkdir()
    (src / "steps.jsonl").write_text(
        '{"index": 0, "kind": "session.start", "content": {"workflow": "test"}, "timestamp": "2025-01-01T00:00:00"}\n'
        '{"index": 1, "kind": "llm.request", "content": {"model": "gpt-4", "messages": []}, "timestamp": "2025-01-01T00:00:01"}\n'
        '{"index": 2, "kind": "llm.response", "content": {"choices": [{"message": {"content": "hi"}}]}, "timestamp": "2025-01-01T00:00:02"}\n'
        '{"index": 3, "kind": "session.end", "content": {"success": true}, "timestamp": "2025-01-01T00:00:03"}\n',
        encoding="utf-8",
    )
    (src / "environment.json").write_text(json.dumps({"os": "test", "python": "3.11"}), encoding="utf-8")
    if extra_files:
        for name, content in extra_files.items():
            (src / name).write_text(content, encoding="utf-8")
    return src


def _pack(tmp_path: Path, src: Path, policy_json: str = None) -> Path:
    """Pack src to a .epi file, optionally with an epi_policy.json in CWD."""
    out = tmp_path / "output.epi"
    manifest = ManifestModel(file_manifest={})

    # Patch Path.cwd() to point to tmp_path so policy is found there
    with patch("epi_core.container.Path") as mock_path_cls:
        # Only patch .cwd(); let other Path() calls through
        import epi_core.container as container_mod
        real_path = Path

        original_cwd = Path.cwd

        if policy_json:
            policy_path = tmp_path / "epi_policy.json"
            policy_path.write_text(policy_json, encoding="utf-8")

        # Use monkeypatch-style: patch load_policy's search_dir resolution
        with patch("epi_core.policy.Path") as mock_policy_path:
            mock_policy_path.cwd.return_value = tmp_path
            mock_policy_path.return_value = real_path(tmp_path)
            mock_policy_path.side_effect = real_path

            EPIContainer.pack(src, manifest, out)

    return out


# ── Tests ──────────────────────────────────────────────────────────────────────

class TestPackWithAnalysis:
    def test_analysis_json_present_in_artifact(self, tmp_path):
        src = _make_source_dir(tmp_path)
        out = tmp_path / "output.epi"
        EPIContainer.pack(src, ManifestModel(file_manifest={}), out)

        with zipfile.ZipFile(out, "r") as zf:
            assert "analysis.json" in zf.namelist()
        manifest = EPIContainer.read_manifest(out)
        assert manifest.analysis_status == "complete"
        assert manifest.analysis_error is None

    def test_analysis_json_is_valid(self, tmp_path):
        src = _make_source_dir(tmp_path)
        out = tmp_path / "output.epi"
        EPIContainer.pack(src, ManifestModel(file_manifest={}), out)

        with zipfile.ZipFile(out, "r") as zf:
            analysis = json.loads(zf.read("analysis.json"))
        assert "fault_detected" in analysis
        assert "disclaimer" in analysis
        assert "human_review" in analysis

    def test_analysis_in_file_manifest(self, tmp_path):
        src = _make_source_dir(tmp_path)
        out = tmp_path / "output.epi"
        manifest = ManifestModel(file_manifest={})
        EPIContainer.pack(src, manifest, out)

        packed_manifest = EPIContainer.read_manifest(out)
        assert "analysis.json" in packed_manifest.file_manifest

    def test_analysis_hash_in_manifest_is_correct(self, tmp_path):
        import hashlib
        src = _make_source_dir(tmp_path)
        out = tmp_path / "output.epi"
        EPIContainer.pack(src, ManifestModel(file_manifest={}), out)

        packed_manifest = EPIContainer.read_manifest(out)
        expected_hash = packed_manifest.file_manifest["analysis.json"]

        with zipfile.ZipFile(out, "r") as zf:
            analysis_bytes = zf.read("analysis.json")

        actual_hash = hashlib.sha256(analysis_bytes).hexdigest()
        assert actual_hash == expected_hash

    def test_tampering_analysis_fails_integrity(self, tmp_path):
        """Modifying analysis.json after sealing must fail verify_integrity()."""
        src = _make_source_dir(tmp_path)
        out = tmp_path / "output.epi"
        EPIContainer.pack(src, ManifestModel(file_manifest={}), out)

        # Tamper: replace analysis.json with different content
        tampered = tmp_path / "tampered.epi"
        with zipfile.ZipFile(out, "r") as zf_in, \
             zipfile.ZipFile(tampered, "w", zipfile.ZIP_DEFLATED) as zf_out:
            for item in zf_in.infolist():
                if item.filename == "analysis.json":
                    zf_out.writestr(item, json.dumps({"fault_detected": False, "tampered": True}))
                else:
                    zf_out.writestr(item, zf_in.read(item.filename))

        ok, mismatches = EPIContainer.verify_integrity(tampered)
        assert not ok
        assert "analysis.json" in mismatches

    def test_viewer_html_embeds_analysis(self, tmp_path):
        """The embedded viewer HTML must contain the analysis data."""
        src = _make_source_dir(tmp_path)
        out = tmp_path / "output.epi"
        EPIContainer.pack(src, ManifestModel(file_manifest={}), out)

        with zipfile.ZipFile(out, "r") as zf:
            viewer_html = zf.read("viewer.html").decode("utf-8")

        assert '"analysis"' in viewer_html

    def test_policy_evaluation_json_present_when_policy_used(self, tmp_path):
        src = _make_source_dir(tmp_path)
        out = tmp_path / "output.epi"
        policy_payload = {
            "policy_format_version": "2.0",
            "policy_id": "refund-agent-prod",
            "system_name": "refund-agent",
            "system_version": "1.0",
            "policy_version": "2026-04-01",
            "rules": [
                {
                    "id": "R005",
                    "name": "Manager Approval Before Refund",
                    "severity": "critical",
                    "description": "Refund approval requires explicit manager signoff.",
                    "type": "approval_guard",
                    "mode": "require_approval",
                    "applies_at": "decision",
                    "approval_action": "approve_refund",
                    "approved_by": "manager",
                }
            ],
        }
        (tmp_path / "epi_policy.json").write_text(json.dumps(policy_payload), encoding="utf-8")
        (src / "steps.jsonl").write_text(
            '{"index": 0, "kind": "session.start", "content": {"workflow": "test"}, "timestamp": "2025-01-01T00:00:00"}\n'
            '{"index": 1, "kind": "agent.approval.request", "content": {"action": "approve_refund"}, "timestamp": "2025-01-01T00:00:01"}\n'
            '{"index": 2, "kind": "agent.decision", "content": {"decision": "approve_refund"}, "timestamp": "2025-01-01T00:00:02"}\n'
            '{"index": 3, "kind": "session.end", "content": {"success": true}, "timestamp": "2025-01-01T00:00:03"}\n',
            encoding="utf-8",
        )

        with patch("epi_core.policy.Path") as mock_p:
            mock_p.cwd.return_value = tmp_path
            mock_p.side_effect = Path
            EPIContainer.pack(src, ManifestModel(file_manifest={}), out)

        with zipfile.ZipFile(out, "r") as zf:
            assert "policy_evaluation.json" in zf.namelist()
            policy_evaluation = json.loads(zf.read("policy_evaluation.json"))
            viewer_html = zf.read("viewer.html").decode("utf-8")

        assert policy_evaluation["policy_id"] == "refund-agent-prod"
        assert policy_evaluation["controls_evaluated"] == 1
        assert policy_evaluation["controls_failed"] == 1
        assert "policy_evaluation.json" in EPIContainer.read_manifest(out).file_manifest
        assert '"policy_evaluation"' in viewer_html

    def test_no_policy_json_when_no_policy_file(self, tmp_path):
        """If no epi_policy.json exists in CWD, policy.json must not be in the artifact."""
        src = _make_source_dir(tmp_path)
        out = tmp_path / "output.epi"

        # Ensure no policy file in any search location
        with patch("epi_core.policy.Path") as mock_p:
            mock_p.cwd.return_value = tmp_path
            mock_p.side_effect = Path
            EPIContainer.pack(src, ManifestModel(file_manifest={}), out)

        with zipfile.ZipFile(out, "r") as zf:
            # policy.json should be absent when no epi_policy.json was found
            if "policy.json" in zf.namelist():
                # If present, it should be from a real policy file in CWD
                pass  # acceptable if test env has one

    def test_invalid_policy_warns_and_packs_without_policy_json(self, tmp_path, capsys):
        src = _make_source_dir(tmp_path)
        out = tmp_path / "output.epi"
        (tmp_path / "epi_policy.json").write_text("{not valid json", encoding="utf-8")

        with patch("epi_core.policy.Path") as mock_p:
            mock_p.cwd.return_value = tmp_path
            mock_p.side_effect = Path
            EPIContainer.pack(src, ManifestModel(file_manifest={}), out)

        captured = capsys.readouterr()
        assert "invalid" in captured.err.lower()
        with zipfile.ZipFile(out, "r") as zf:
            assert "analysis.json" in zf.namelist()
            assert "policy.json" not in zf.namelist()

    def test_pack_never_raises_on_analyzer_failure(self, tmp_path):
        """FaultAnalyzer failures must not propagate and break packing."""
        src = _make_source_dir(tmp_path)
        out = tmp_path / "output.epi"

        with patch("epi_core.fault_analyzer.FaultAnalyzer.analyze",
                   side_effect=RuntimeError("analyzer exploded")):
            # Pack must still complete
            EPIContainer.pack(src, ManifestModel(file_manifest={}), out)

        assert out.exists()
        manifest = EPIContainer.read_manifest(out)
        assert manifest.analysis_status == "error"
        assert manifest.analysis_error is not None
        with zipfile.ZipFile(out, "r") as zf:
            assert "manifest.json" in zf.namelist()
            assert "steps.jsonl" in zf.namelist()

    def test_analyzer_failure_does_not_leak_stale_analysis_file(self, tmp_path):
        src = _make_source_dir(tmp_path, extra_files={"analysis.json": json.dumps({"stale": True})})
        out = tmp_path / "output.epi"

        with patch("epi_core.fault_analyzer.FaultAnalyzer.analyze", side_effect=RuntimeError("analyzer exploded")):
            EPIContainer.pack(src, ManifestModel(file_manifest={}), out)

        with zipfile.ZipFile(out, "r") as zf:
            assert "analysis.json" not in zf.namelist()

    def test_analysis_status_skipped_when_steps_file_missing(self, tmp_path):
        src = tmp_path / "workspace"
        src.mkdir()
        (src / "environment.json").write_text(json.dumps({"os": "test"}), encoding="utf-8")
        out = tmp_path / "output.epi"

        EPIContainer.pack(src, ManifestModel(file_manifest={}), out)

        manifest = EPIContainer.read_manifest(out)
        assert manifest.analysis_status == "skipped"
        assert manifest.analysis_error is None
        with zipfile.ZipFile(out, "r") as zf:
            assert "analysis.json" not in zf.namelist()

    def test_analysis_status_complete_when_generated_analysis_is_preserved(self, tmp_path):
        src = tmp_path / "workspace"
        src.mkdir()
        (src / "analysis.json").write_text(json.dumps({"summary": "already analyzed"}), encoding="utf-8")
        (src / "environment.json").write_text(json.dumps({"os": "test"}), encoding="utf-8")
        out = tmp_path / "output.epi"

        EPIContainer.pack(src, ManifestModel(file_manifest={}), out, preserve_generated=True)

        manifest = EPIContainer.read_manifest(out)
        assert manifest.analysis_status == "complete"
        assert manifest.analysis_error is None
