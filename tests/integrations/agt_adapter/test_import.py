"""Tests for AGT → EPI import with various fixture types."""

import json
import zipfile
from pathlib import Path

import pytest

from epi_recorder.integrations.agt_adapter.importer import import_agt
from epi_recorder.integrations.agt_adapter.errors import AGTArtifactError


class TestImportCurrent:
    def test_all_event_types_imported(self, tmp_path, fixture_agt_current):
        source = tmp_path / "audit.json"
        source.write_text(json.dumps(fixture_agt_current))

        epi_path, report = import_agt(source, output_dir=tmp_path)

        with zipfile.ZipFile(epi_path) as zf:
            steps = [json.loads(l) for l in zf.read("steps.jsonl").decode().strip().split("\n")]

        assert len(steps) == 6
        kinds = [s["kind"] for s in steps]
        assert "tool.call" in kinds
        assert "tool.blocked" in kinds
        assert "policy.violation" in kinds
        assert "policy.eval" in kinds
        assert "security.alert" in kinds
        assert "agent.delegate" in kinds

    def test_epifact_verifies(self, tmp_path, fixture_agt_current):
        source = tmp_path / "audit.json"
        source.write_text(json.dumps(fixture_agt_current))

        epi_path, report = import_agt(source, output_dir=tmp_path)

        from epi_core.container import EPIContainer
        ok, mismatches = EPIContainer.verify_integrity(epi_path)
        assert ok, f"Integrity check failed: {mismatches}"


class TestImportOldFormat:
    def test_old_format_without_policy_decision(self, tmp_path, fixture_agt_old):
        source = tmp_path / "audit_old.json"
        source.write_text(json.dumps(fixture_agt_old))

        epi_path, report = import_agt(source, output_dir=tmp_path)

        assert report.agt_version_detected == "4.0"

        with zipfile.ZipFile(epi_path) as zf:
            steps = [json.loads(l) for l in zf.read("steps.jsonl").decode().strip().split("\n")]
        assert len(steps) == 1
        assert steps[0]["kind"] == "tool.call"


class TestImportExtraFields:
    def test_forward_compatibility(self, tmp_path, fixture_agt_extra):
        source = tmp_path / "audit_extra.json"
        source.write_text(json.dumps(fixture_agt_extra))

        epi_path, report = import_agt(source, output_dir=tmp_path)

        # Should not raise — extra fields preserved
        assert report.preserved_count >= 3  # federation_context, data_classification, etc.


class TestImportCloudEvents:
    def test_cloudevents_envelope_imports(self, tmp_path, fixture_agt_cloudevents):
        source = tmp_path / "cloudevents.json"
        source.write_text(json.dumps(fixture_agt_cloudevents))

        epi_path, report = import_agt(source, output_dir=tmp_path)

        with zipfile.ZipFile(epi_path) as zf:
            steps = [json.loads(l) for l in zf.read("steps.jsonl").decode().strip().split("\n")]

        assert len(steps) == len(fixture_agt_cloudevents)
        first = steps[0]
        assert first["governance"]["agent_did"] == fixture_agt_cloudevents[0]["source"]
        assert first["content"]["agt_entry_id"] == fixture_agt_cloudevents[0]["id"]
        # The envelope itself is carried, not replaced by the mapped fields.
        assert first["content"]["agt_unknown_fields"]["cloudevent"]["specversion"] == "1.0"
        # No AGT version exists in a CloudEvents envelope; do not invent one.
        assert report.agt_version_detected == "unknown"

    def test_cloudevents_action_and_outcome_are_kept_when_present(self, tmp_path):
        events = [
            {
                "specversion": "1.0",
                "type": "ai.agentmesh.policy.evaluated",
                "source": "did:web:refund-agent.example.com",
                "id": "ce-100",
                "time": "2026-05-15T10:00:00Z",
                "data": {"action": "deny", "outcome": "denied", "policy_name": "refunds"},
            }
        ]
        source = tmp_path / "cloudevents.json"
        source.write_text(json.dumps(events))

        epi_path, report = import_agt(source, output_dir=tmp_path)

        with zipfile.ZipFile(epi_path) as zf:
            steps = [json.loads(l) for l in zf.read("steps.jsonl").decode().strip().split("\n")]

        assert steps[0]["governance"]["action"] == "denied"
        assert steps[0]["governance"]["outcome"] == "blocked"

    def test_cloudevent_without_time_is_rejected(self, tmp_path):
        events = [
            {
                "specversion": "1.0",
                "type": "ai.agentmesh.tool.invoked",
                "source": "did:web:agent.example.com",
                "id": "ce-101",
                "data": {"tool": "crm_lookup"},
            }
        ]
        source = tmp_path / "cloudevents.json"
        source.write_text(json.dumps(events))

        with pytest.raises(AGTArtifactError):
            import_agt(source, output_dir=tmp_path)


class TestImportMalformed:
    def test_malformed_entry(self, tmp_path, fixture_agt_malformed):
        source = tmp_path / "audit_bad.json"
        source.write_text(json.dumps(fixture_agt_malformed))

        # Should raise on missing required fields
        with pytest.raises(AGTArtifactError):
            import_agt(source, output_dir=tmp_path)
