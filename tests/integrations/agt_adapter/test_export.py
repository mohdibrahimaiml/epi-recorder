"""Tests for EPI → evidence receipt export."""

import json
from pathlib import Path

import pytest

from epi_recorder.integrations.agt_adapter.importer import import_agt
from epi_recorder.integrations.agt_adapter.exporter import (
    export_evidence_receipt,
    verify_evidence_receipt,
    build_agt_log_data,
)


class TestExportReceipt:
    def test_receipt_generation(self, tmp_path, fixture_agt_current):
        source = tmp_path / "audit.json"
        source.write_text(json.dumps(fixture_agt_current))

        epi_path, _ = import_agt(source, output_dir=tmp_path)
        receipt = export_evidence_receipt(epi_path)

        assert isinstance(receipt, bytes)
        assert len(receipt) > 50  # COSE Sign1 header + payload + sig

    def test_receipt_verification(self, tmp_path, fixture_agt_current):
        source = tmp_path / "audit.json"
        source.write_text(json.dumps(fixture_agt_current))

        epi_path, _ = import_agt(source, output_dir=tmp_path)
        receipt = export_evidence_receipt(epi_path)

        assert verify_evidence_receipt(receipt, epi_path) is True

    def test_build_agt_log_data(self, tmp_path, fixture_agt_current):
        source = tmp_path / "audit.json"
        source.write_text(json.dumps(fixture_agt_current))

        epi_path, _ = import_agt(source, output_dir=tmp_path)
        receipt = export_evidence_receipt(epi_path)
        log_data = build_agt_log_data(receipt, epi_path)

        assert "epi_evidence_hex" in log_data
        assert len(log_data["epi_evidence_hex"]) > 0
        assert log_data["evidence_type"] == "epi_signed_receipt"
        assert "epi_artifact_hash" in log_data
        assert "epi_workflow_id" in log_data

    def test_build_agt_log_data_reports_bad_signature_invalid(
        self, tmp_path, fixture_agt_current, monkeypatch
    ):
        """Finding 1: presence must not count as validity."""
        import epi_recorder.integrations.agt_adapter.exporter as exporter_mod
        from epi_core.container import EPIContainer

        source = tmp_path / "audit.json"
        source.write_text(json.dumps(fixture_agt_current))

        epi_path, _ = import_agt(source, output_dir=tmp_path)
        receipt = export_evidence_receipt(epi_path)

        real_read = EPIContainer.read_manifest

        def _bad_manifest(path):
            m = real_read(path)
            d = m.model_dump()
            d["signature"] = "00" * 128
            from epi_core.schemas import ManifestModel

            return ManifestModel(**d)

        monkeypatch.setattr(EPIContainer, "read_manifest", staticmethod(_bad_manifest))
        log_data = exporter_mod.build_agt_log_data(receipt, epi_path)

        assert log_data["epi_signature_present"] is True
        assert log_data["epi_signature_valid"] is False
