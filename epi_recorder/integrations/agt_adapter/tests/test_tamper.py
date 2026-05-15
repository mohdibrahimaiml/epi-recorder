"""Tests for tamper detection on imported AGT evidence."""

import json
import zipfile
from pathlib import Path

import pytest

from epi_recorder.integrations.agt_adapter.importer import import_agt
from epi_core.container import EPIContainer


class TestTamperDetection:
    def test_tampered_agt_evidence_detected(self, tmp_path, fixture_agt_current):
        """If raw AGT evidence in .epi is tampered, verification must fail."""
        source = tmp_path / "audit.json"
        source.write_text(json.dumps(fixture_agt_current))

        epi_path, _ = import_agt(source, output_dir=tmp_path)

        # Tamper the raw evidence inside the .epi
        tampered_path = tmp_path / "tampered.epi"
        with zipfile.ZipFile(epi_path, 'r') as zin:
            with zipfile.ZipFile(tampered_path, 'w') as zout:
                for item in zin.infolist():
                    data = zin.read(item.filename)
                    if item.filename == "agt_evidence_raw.json":
                        # Modify the raw evidence
                        data = data.replace(b"acme corp", b"HACKED")
                    zout.writestr(item, data)

        # Verification should detect tampering
        ok, mismatches = EPIContainer.verify_integrity(tampered_path)
        assert not ok, "Tampered AGT evidence should be detected"
        assert "agt_evidence_raw.json" in mismatches

    def test_tampered_steps_detected(self, tmp_path, fixture_agt_current):
        """If mapped steps are tampered, verification must fail."""
        source = tmp_path / "audit.json"
        source.write_text(json.dumps(fixture_agt_current))

        epi_path, _ = import_agt(source, output_dir=tmp_path)

        tampered_path = tmp_path / "tampered.epi"
        with zipfile.ZipFile(epi_path, 'r') as zin:
            with zipfile.ZipFile(tampered_path, 'w') as zout:
                for item in zin.infolist():
                    data = zin.read(item.filename)
                    if item.filename == "steps.jsonl":
                        data = data.replace(b"tool.call", b"tool.HACKED")
                    zout.writestr(item, data)

        ok, mismatches = EPIContainer.verify_integrity(tampered_path)
        assert not ok, "Tampered steps should be detected"
