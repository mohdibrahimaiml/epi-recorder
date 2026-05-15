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
