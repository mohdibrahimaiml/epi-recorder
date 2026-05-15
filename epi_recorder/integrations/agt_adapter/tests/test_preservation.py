"""Tests for raw preservation and hash integrity."""

import json
import zipfile
from pathlib import Path

import pytest

from epi_recorder.integrations.agt_adapter.importer import import_agt


class TestRawPreservation:
    def test_raw_evidence_in_epifact(self, tmp_path, fixture_agt_current):
        """Raw AGT evidence must be preserved verbatim inside .epi artifact."""
        source = tmp_path / "audit.json"
        source.write_text(json.dumps(fixture_agt_current))

        epi_path, report = import_agt(source, output_dir=tmp_path)

        # Verify raw evidence is in the .epi ZIP
        with zipfile.ZipFile(epi_path) as zf:
            namelist = zf.namelist()
            assert "agt_evidence_raw.json" in namelist, \
                "Raw AGT evidence not found in .epi artifact"
            raw = zf.read("agt_evidence_raw.json")
            assert raw == source.read_bytes(), \
                "Raw evidence was modified during import"

    def test_entry_hash_preserved(self, tmp_path, fixture_agt_current):
        """AGT entry_hash must survive the import."""
        source = tmp_path / "audit.json"
        source.write_text(json.dumps(fixture_agt_current))

        epi_path, report = import_agt(source, output_dir=tmp_path)

        with zipfile.ZipFile(epi_path) as zf:
            steps_raw = zf.read("steps.jsonl").decode()
            steps = [json.loads(line) for line in steps_raw.strip().split("\n")]

            for i, step in enumerate(steps):
                agt_hash = fixture_agt_current["entries"][i]["entry_hash"]
                assert step["content"]["agt_entry_hash"] == agt_hash, \
                    f"Entry {i}: entry_hash not preserved"

    def test_unknown_fields_preserved(self, tmp_path, fixture_agt_extra):
        """Unknown future AGT fields must be preserved, not dropped."""
        source = tmp_path / "audit.json"
        source.write_text(json.dumps(fixture_agt_extra))

        epi_path, report = import_agt(source, output_dir=tmp_path)

        # Check mapping report
        assert "federation_context" in report.unknown_fields_preserved
        assert "data_classification" in report.unknown_fields_preserved

        # Check steps contain unknown fields
        with zipfile.ZipFile(epi_path) as zf:
            steps_raw = zf.read("steps.jsonl").decode()
            step = json.loads(steps_raw.strip().split("\n")[0])
            assert "agt_unknown_fields" in step["content"]
            assert step["content"]["agt_unknown_fields"]["federation_context"] == "eu-west-1"

    def test_mapping_report_complete(self, tmp_path, fixture_agt_current):
        """Mapping report must have entries for all transformed fields."""
        source = tmp_path / "audit.json"
        source.write_text(json.dumps(fixture_agt_current))

        epi_path, report = import_agt(source, output_dir=tmp_path)

        mapped_fields = [m.source_field for m in report.field_mappings]
        assert "event_type" in mapped_fields
        assert "action" in mapped_fields
        assert "outcome" in mapped_fields
        assert "agent_did" in mapped_fields

        # Report stored in artifact
        with zipfile.ZipFile(epi_path) as zf:
            assert "mapping_report.json" in zf.namelist()
