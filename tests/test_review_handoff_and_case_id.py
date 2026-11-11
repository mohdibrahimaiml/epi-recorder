"""Two fixes: the case number is sealed, and a review handoff clears a threshold.

The starter demo approves a $900 refund and then hands it to a manager, because
the policy says refunds above $500 need review. The analyzer used to read the
$900 as a violation of the $500 threshold and the demo summary led with
"P2 (Constraint Violation)" and "Controls failed: 1" — on the first file a new
user ever opens.

The case number was accepted by ``record(case_id=...)`` and never written to the
signed manifest, so a reviewer could not find the record by order id.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

from epi_core.container import EPIContainer
from epi_core.fault_analyzer import FaultAnalyzer
from epi_core.schemas import ManifestModel


def _steps(*, handoff: bool) -> list[dict]:
    steps = [
        {
            "index": 0,
            "kind": "policy.check",
            "content": {
                "policy_name": "high_value_refund_review",
                "rule": "Refunds above $500 require human review before payout.",
                "result": "review_required",
                "evidence": {"review_threshold_usd": 500.0, "amount_usd": 900.0},
            },
        },
        {
            "index": 1,
            "kind": "tool.response",
            "content": {
                "tool": "lookup_order",
                "status": "success",
                "output": {
                    "order_id": "ORD-9001",
                    "amount_usd": 900.0,
                    "review_threshold_usd": 500.0,
                },
            },
        },
        {
            "index": 2,
            "kind": "agent.decision",
            "content": {
                "decision": "approve_refund",
                "output": {"order_id": "ORD-9001", "amount_usd": 900.0},
                "rationale": "Gold customer, inside the return window.",
            },
        },
    ]
    if handoff:
        steps.append(
            {
                "index": 3,
                "kind": "review.handoff",
                "content": {
                    "queue": "refund-managers",
                    "reason": "Human review required for refunds above $500.",
                    "requested_action": "Approve or reject the payout.",
                },
            }
        )
    return steps


def _fault_ids(steps: list[dict]) -> list[str]:
    # analyze() takes JSONL text, the same shape as steps.jsonl in an artifact.
    payload = "\n".join(json.dumps(step) for step in steps)
    result = FaultAnalyzer().analyze(payload)
    flags = ([result.primary_fault] if result.primary_fault else []) + list(
        result.secondary_flags
    )
    return [flag.rule_id or flag.fault_type for flag in flags]


def test_a_following_review_handoff_clears_the_threshold():
    assert "P2" not in _fault_ids(_steps(handoff=True)), (
        "a decision handed to human review is the control working, not a breach"
    )


def test_without_a_handoff_the_threshold_still_fires():
    assert "P2" in _fault_ids(_steps(handoff=False)), (
        "an unapproved commitment above the threshold must still be flagged"
    )


def test_case_id_is_sealed_and_round_trips(tmp_path: Path):
    source = tmp_path / "src"
    source.mkdir()
    (source / "steps.jsonl").write_text(
        json.dumps({"index": 0, "kind": "agent.decision", "content": {"decision": "ok"}}) + "\n",
        encoding="utf-8",
    )
    out = tmp_path / "case.epi"
    EPIContainer.pack(
        source,
        ManifestModel(cli_command="pytest", goal="refund", case_id="ORD-9001"),
        out,
        signer_function=None,
        generate_analysis=False,
        notarize=False,
        embed_viewer=False,
    )
    with zipfile.ZipFile(out) as zf:
        manifest = json.loads(zf.read("manifest.json"))
        case = json.loads(zf.read("artifacts/case_id.json"))
    # 4.10 keeps case_id out of the manifest top level for 4.9.0 verifiers.
    assert "case_id" not in manifest
    assert case["case_id"] == "ORD-9001"
    assert EPIContainer.read_manifest(out).case_id == "ORD-9001"


def test_case_id_is_absent_when_not_given(tmp_path: Path):
    source = tmp_path / "src2"
    source.mkdir()
    (source / "steps.jsonl").write_text(
        json.dumps({"index": 0, "kind": "agent.decision", "content": {"decision": "ok"}}) + "\n",
        encoding="utf-8",
    )
    out = tmp_path / "nocase.epi"
    EPIContainer.pack(
        source,
        ManifestModel(cli_command="pytest", goal="refund"),
        out,
        signer_function=None,
        generate_analysis=False,
        notarize=False,
        embed_viewer=False,
    )
    with zipfile.ZipFile(out) as zf:
        manifest = json.loads(zf.read("manifest.json"))
        names = zf.namelist()
    assert manifest.get("case_id") in (None, ""), (
        "records without a case number must stay byte-identical to older ones"
    )
    assert "artifacts/case_id.json" not in names
