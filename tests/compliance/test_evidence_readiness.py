from __future__ import annotations

import json
from pathlib import Path

import pytest

from epi_core.container import EPIContainer
from epi_core.trust import verify_embedded_manifest_signature
from tests.helpers.artifacts import make_decision_epi


pytestmark = pytest.mark.compliance
REPO_ROOT = Path(__file__).resolve().parents[2]


def test_artifact_meets_evidence_readiness_checklist(tmp_path: Path):
    artifact, _ = make_decision_epi(tmp_path, signed=True)
    members = set(EPIContainer.list_members(artifact))
    manifest = EPIContainer.read_manifest(artifact)
    steps = EPIContainer.read_steps(artifact)
    policy_eval = EPIContainer.read_member_json(artifact, "policy_evaluation.json")
    review = EPIContainer.read_member_json(artifact, "review.json")
    integrity_ok, mismatches = EPIContainer.verify_integrity(artifact)
    signature_valid, signer, _ = verify_embedded_manifest_signature(manifest)

    assert "steps.jsonl" in members
    assert "policy_evaluation.json" in members
    assert "review.json" in members
    assert steps
    assert all(step.get("timestamp") for step in steps)
    assert policy_eval["controls_evaluated"] >= 1
    assert review["reviews"][0]["reviewer"] == "qa@example.com"
    assert integrity_ok is True
    assert mismatches == {}
    assert signature_valid is True
    assert signer == "test"


def test_eu_evidence_prep_guide_uses_non_legal_advice_boundary():
    guide = (REPO_ROOT / "docs" / "EU-AI-ACT-EVIDENCE-PREP.md").read_text(encoding="utf-8")

    assert "not legal advice" in guide.lower()
    assert "does not guarantee regulatory compliance" in guide.lower()
    assert "captured execution trace" in guide
    assert "event timestamps present" in guide
    assert "artifact integrity verified" in guide
    assert "signature state reviewed" in guide


def test_readme_avoids_unqualified_regulatory_compliance_claims():
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")

    banned_phrases = [
        "Compliance | Yes - EU AI Act, FDA, SEC",
        "litigation-grade evidence",
        "guarantees regulator approval",
    ]
    for phrase in banned_phrases:
        assert phrase not in readme
    assert "not a compliance guarantee" in readme
    assert "does not provide legal advice" in readme


def test_decision_record_contains_regulator_review_inputs(tmp_path: Path):
    artifact, _ = make_decision_epi(tmp_path, signed=True)

    summary = {
        "trace_present": EPIContainer.count_steps(artifact) > 0,
        "policy_present": "policy_evaluation.json" in EPIContainer.list_members(artifact),
        "review_present": "review.json" in EPIContainer.list_members(artifact),
        "signature_present": EPIContainer.read_manifest(artifact).signature is not None,
        "offline_verifiable": EPIContainer.verify_integrity(artifact)[0],
    }

    assert json.loads(json.dumps(summary)) == {
        "trace_present": True,
        "policy_present": True,
        "review_present": True,
        "signature_present": True,
        "offline_verifiable": True,
    }
