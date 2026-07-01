"""Tests for epi_core.annex_schemas."""
from __future__ import annotations
import sys; sys.path.insert(0,".")
from epi_core.annex_schemas import *

def test_annex_iv_technical_file_creation():
    tf = AnnexIVTechnicalFile(
        section_01=Section01System(
            system_description=SystemDescription(
                system_name="Test", version="1.0", intended_purpose="Testing"
            )
        ),
        section_08=Section08Declaration(
            manufacturer=ManufacturerInfo(name="Acme"),
            system_name="Test", system_version="1.0",
            declares_under_sole_responsibility="yes",
            signatory=Signatory(name="J", role="CCO"),
        ),
    )
    assert tf.meta["schema"] == "EU AI Act Annex IV"
    assert tf.section_01.system_description.system_name == "Test"

def test_risk_entry_rpn_computation():
    r = RiskEntry(
        id="R-001", risk_description="Bias risk",
        category="discrimination", probability=3, severity=4
    )
    assert r.rpn_score == 12
    assert r.risk_level == "high"

def test_datasheet_creation():
    ds = DatasetDatasheet(
        dataset_name="train-v1", dataset_type="training",
        collection_date="2025-01-01"
    )
    assert ds.dataset_name == "train-v1"
    assert ds.dataset_type == "training"
    assert ds.status == "draft"

def test_compliance_summary_defaults():
    cs = AnnexComplianceSummary(
        system_name="Test", system_version="1.0"
    )
    assert cs.total_sections == 9
    assert cs.sections == []

def test_all_section_models_exist():
    tf = AnnexIVTechnicalFile(
        section_01=Section01System(
            system_description=SystemDescription(
                system_name="X", version="1", intended_purpose="T"
            )
        ),
        section_08=Section08Declaration(
            manufacturer=ManufacturerInfo(name="M"),
            system_name="X", system_version="1",
            declares_under_sole_responsibility="y",
            signatory=Signatory(name="J", role="C"),
        ),
    )
    fields = tf.model_dump()
    for s in ["section_01","section_02","section_03","section_04",
              "section_05","section_06","section_07","section_08","section_09"]:
        assert s in fields, f"Missing {s}"
