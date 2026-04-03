"""
EPI Starter Kit: Insurance Claim Denial — Offline / Simulated Approval
-----------------------------------------------------------------------
Generates a complete, signed .epi artifact from a deterministic claim denial
workflow. Human approval is SIMULATED inline — no gateway or network required.

Use this script to:
  - demonstrate artifact generation and tamper-evidence (epi verify)
  - show the Decision Record export (epi export-summary)
  - run in environments without a live gateway

For a demo that pauses for a REAL human approval click, use agent_live_approval.py.

Run:
    python agent.py
    epi view insurance_claim_case.epi
    epi verify insurance_claim_case.epi
    epi export-summary summary insurance_claim_case.epi
"""

from __future__ import annotations

import os
import time
from pathlib import Path

from epi_recorder import record


def _display_output_path(output_file: str) -> Path:
    path = Path(output_file)
    if path.suffix != ".epi":
        path = path.with_suffix(".epi")
    if path.is_absolute():
        return path
    recordings_dir = Path(os.getenv("EPI_RECORDINGS_DIR", "epi-recordings"))
    if path.parts and path.parts[0] == recordings_dir.name:
        return path
    return recordings_dir / path


def _mock_claim_ai(claim: dict) -> tuple[str, str, dict]:
    """Return a deterministic denial recommendation without requiring an API key."""
    time.sleep(0.15)
    recommendation = (
        "DENY. The reported water damage falls under an excluded cause of loss "
        "for this policy and the documented evidence does not support an exception."
    )
    usage = {"prompt_tokens": 68, "completion_tokens": 32, "total_tokens": 100}
    return "mock-claims-model", recommendation, usage


def run_claim_denial_demo(
    claim_id: str = "CLM-48219",
    reviewer_email: str = "claims.manager@carrier.com",
    output_file: str = "insurance_claim_case.epi",
) -> dict:
    """
    Simulate a realistic claim denial workflow and seal it into a `.epi` file.
    """
    output_path = Path(output_file)
    display_path = _display_output_path(output_file)

    with record(str(output_path), goal=f"Review and decide claim {claim_id}") as epi:
        epi.log_step(
            "agent.run.start",
            {
                "agent_name": "InsuranceClaimDenialAgent",
                "agent_version": "1.0",
                "workflow": "claim-denial",
                "user_input": f"Review claim {claim_id}",
                "goal": "Determine whether the claim should be paid or denied with defensible evidence.",
                "policy_file": "epi_policy.json",
            },
        )

        print(f"Loading claim {claim_id}...")
        epi.log_step("tool.call", {"tool": "load_claim", "input": {"claim_id": claim_id}})
        claim = {
            "claim_id": claim_id,
            "claim_amount": 1200,
            "policy_number": "POL-77192",
            "line_of_business": "homeowners",
            "loss_type": "water damage",
            "reported_cause": "groundwater seepage",
            "coverage_summary": "Groundwater seepage is excluded under section HO-7.2.",
        }
        epi.log_step("tool.response", {"tool": "load_claim", "status": "success", "output": claim})

        print("Running fraud check...")
        epi.log_step("tool.call", {"tool": "run_fraud_check", "input": {"claim_id": claim_id}})
        epi.log_step(
            "tool.response",
            {
                "tool": "run_fraud_check",
                "status": "success",
                "output": {"risk_level": "low", "score": 0.08, "watchlist_match": False},
            },
        )

        print("Checking coverage...")
        epi.log_step(
            "tool.call",
            {"tool": "check_coverage", "input": {"claim_id": claim_id, "policy_number": claim["policy_number"]}},
        )
        epi.log_step(
            "tool.response",
            {
                "tool": "check_coverage",
                "status": "success",
                "output": {
                    "claim_amount": claim["claim_amount"],
                    "coverage_status": "excluded",
                    "policy_clause": "HO-7.2",
                    "summary": "Groundwater seepage exclusion applies to this loss type.",
                },
            },
        )

        print(f"Requesting human approval from {reviewer_email}...")
        epi.log_step(
            "agent.approval.request",
            {
                "approval_id": f"approval-{claim_id}",
                "action": "deny_claim",
                "reason": (
                    f"Claim amount ${claim['claim_amount']} exceeds the $500 review threshold and the decision "
                    "is a denial that must be approved by a human reviewer."
                ),
                "requested_from": reviewer_email,
                "reviewer_role": "manager",
                "timeout_minutes": 120,
            },
        )
        epi.log_step(
            "agent.approval.response",
            {
                "approval_id": f"approval-{claim_id}",
                "action": "deny_claim",
                "approved": True,
                "reviewer": reviewer_email,
                "role": "manager",
                "reason": "Coverage exclusion confirmed and denial notice language reviewed.",
            },
        )

        print("Documenting denial reason...")
        denial_reason = (
            "Claim denied because the reported groundwater seepage is excluded under policy section HO-7.2."
        )
        epi.log_step(
            "tool.call",
            {
                "tool": "record_denial_reason",
                "input": {"claim_id": claim_id, "reason_code": "coverage-exclusion"},
            },
        )
        epi.log_step(
            "tool.response",
            {
                "tool": "record_denial_reason",
                "status": "success",
                "output": {"claim_id": claim_id, "reason_code": "coverage-exclusion", "summary": denial_reason},
            },
        )

        print("Consulting the claims AI...")
        model_name, ai_recommendation, usage = _mock_claim_ai(claim)
        epi.log_step(
            "llm.request",
            {
                "provider": "mock",
                "model": model_name,
                "messages": [
                    {"role": "system", "content": "You summarize insurer claim decisions in one paragraph."},
                    {"role": "user", "content": f"Explain the recommended outcome for claim {claim_id}."},
                ],
            },
        )
        epi.log_step(
            "llm.response",
            {
                "provider": "mock",
                "model": model_name,
                "choices": [{"message": {"role": "assistant", "content": ai_recommendation}, "finish_reason": "stop"}],
                "usage": usage,
            },
        )

        decision = {
            "decision": "deny_claim",
            "claim_id": claim_id,
            "claim_amount": claim["claim_amount"],
            "coverage_status": "excluded",
            "policy_clause": "HO-7.2",
            "denial_reason": denial_reason,
            "confidence": 0.93,
        }
        epi.log_step("agent.decision", decision)

        print("Issuing denial notice...")
        epi.log_step(
            "tool.call",
            {"tool": "issue_denial_notice", "input": {"claim_id": claim_id, "delivery_channel": "letter"}},
        )
        epi.log_step(
            "tool.response",
            {
                "tool": "issue_denial_notice",
                "status": "success",
                "output": {"notice_id": f"DEN-{claim_id}", "delivery_channel": "letter"},
            },
        )

        epi.log_step(
            "agent.run.end",
            {
                "agent_name": "InsuranceClaimDenialAgent",
                "success": True,
                "outcome": "DENY",
            },
        )

    print(f"\nCase file: {display_path.resolve()}")
    print(f"  epi view {output_path}                    # open the Decision Summary in the browser")
    print(f"  epi verify {output_path}                  # verify tamper evidence")
    print(f"  epi share {output_path}                   # get a hosted share link")
    print(f"  epi export-summary summary {output_path}  # export the Decision Record")
    return decision


if __name__ == "__main__":
    run_claim_denial_demo()
