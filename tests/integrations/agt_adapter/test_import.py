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


class TestImportMalformed:
    def test_malformed_entry(self, tmp_path, fixture_agt_malformed):
        source = tmp_path / "audit_bad.json"
        source.write_text(json.dumps(fixture_agt_malformed))

        # Should raise on missing required fields
        with pytest.raises(AGTArtifactError):
            import_agt(source, output_dir=tmp_path)
