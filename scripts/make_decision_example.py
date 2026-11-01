#!/usr/bin/env python3
"""Seal the example decision records shown on the homepage.

Three outcomes, three real artifacts: a denial, an approval and an escalation.
The provider responses are scripted (no API key), so each file says so in its
notes. Everything else is real: the tool calls are recorded by the OpenAI
wrapper, each decision carries its reasons and the rules it relied on, the
approval is signed by a throwaway demo key, and each seal is a normal Ed25519
seal.

    python scripts/make_decision_example.py
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "website" / "assets" / "demo"

MODEL = "gpt-4o"
SERVED = "gpt-4o-2024-08-06"
APPROVER = "DEMO KEY - Claims Adjuster (not a real person)"

# One entry per card on the homepage. The page is asserted against these files
# by tests/test_homepage_example.py, so the card cannot describe a record the
# site does not ship.
VARIANTS = [
    {
        "file": "decision-example.epi",
        "case": "CLM-1001",
        "goal": "Adjudicate claim CLM-1001",
        "user_input": "Claim CLM-1001: burst pipe, kitchen. Policy HO3-4.2.",
        "lookup": {"claim_id": "CLM-1001", "peril": "water damage",
                   "policy": "HO3-4.2", "amount_usd": 4820},
        "policy_result": {"covered": False, "clause": "HO3-4.2",
                          "text": "Water damage from plumbing is excluded."},
        "tool": "deny_claim",
        "tool_args": ('{"claim_id": "CLM-1001", "decision": "deny", "reason": '
                      '"Water damage exclusion HO3-4.2 applies to this peril."}'),
        "tool_description": "Deny a claim with the policy clause relied on",
        "decision_output": {"claim_id": "CLM-1001", "payable_usd": 0},
        "rationale": "Water damage exclusion HO3-4.2 applies to this peril.",
        "basis": {"policy": "HO3-4.2",
                  "data": ["claim:CLM-1001", "policy:HO3-4.2#exclusion", "peril:water damage"]},
        "approval_id": "denial-CLM-1001",
        "approval_action": "issue denial notice",
        "approval_reason": "Checked against policy HO3-4.2; the exclusion applies.",
    },
    {
        "file": "decision-example-approved.epi",
        "case": "CLM-1002",
        "goal": "Approve claim CLM-1002",
        "user_input": "Claim CLM-1002: sudden pipe failure, bathroom. Policy HO3-2.0.",
        "lookup": {"claim_id": "CLM-1002", "peril": "sudden pipe failure",
                   "policy": "HO3-2.0", "amount_usd": 4820},
        "policy_result": {"covered": True, "clause": "HO3-2.0",
                          "text": "Sudden and accidental discharge is covered up to the limit."},
        "tool": "approve_claim",
        "tool_args": ('{"claim_id": "CLM-1002", "decision": "approve", "amount_usd": 4820, '
                      '"reason": "Covered peril under HO3-2.0 and the invoice is inside the limit."}'),
        "tool_description": "Approve a claim with the amount and the clause relied on",
        "decision_output": {"claim_id": "CLM-1002", "payable_usd": 4820},
        "rationale": "Covered peril under HO3-2.0 and the invoice is inside the limit.",
        "basis": {"policy": "HO3-2.0",
                  "data": ["claim:CLM-1002", "policy:HO3-2.0#covered", "invoice:INV-8841"]},
        "approval_id": "payment-CLM-1002",
        "approval_action": "release payment",
        "approval_reason": "Coverage and amount checked against HO3-2.0 and the invoice.",
    },
    {
        "file": "decision-example-escalated.epi",
        "case": "CLM-1003",
        "goal": "Escalate claim CLM-1003",
        "user_input": "Claim CLM-1003: slow leak behind a wall, damage over months. Policy HO3-4.2.",
        "lookup": {"claim_id": "CLM-1003", "peril": "slow leak",
                   "policy": "HO3-4.2", "amount_usd": 11840},
        "policy_result": {"covered": None, "clause": "HO3-4.2 vs 3.1",
                          "text": "Seepage over weeks is excluded; sudden discharge is covered."},
        "tool": "escalate_claim",
        "tool_args": ('{"claim_id": "CLM-1003", "route": "senior adjuster", "reason": '
                      '"Coverage is ambiguous: the loss sits between the seepage exclusion '
                      'and the sudden-discharge wording."}'),
        "tool_description": "Escalate a claim to a human when the wording does not settle it",
        "decision_output": {"claim_id": "CLM-1003", "payable_usd": None,
                            "route": "senior adjuster"},
        "rationale": "Coverage is ambiguous: the loss sits between the seepage exclusion and the sudden-discharge wording.",
        "basis": {"policy": "HO3-4.2 / HO3-3.1",
                  "data": ["claim:CLM-1003", "policy:HO3-4.2#seepage",
                           "policy:HO3-3.1#sudden-discharge", "inspection:INS-2207"]},
        "approval_id": "escalation-CLM-1003",
        "approval_action": "assign to a senior adjuster",
        "approval_reason": "The wording does not settle coverage; a person decides.",
    },
]


def _scripted_response(variant: dict) -> SimpleNamespace:
    call = SimpleNamespace(
        id=f"call_{variant['case'].lower().replace('-', '')}",
        type="function",
        function=SimpleNamespace(name=variant["tool"], arguments=variant["tool_args"]),
    )
    return SimpleNamespace(
        id=f"chatcmpl-{variant['case'].lower()}",
        model=SERVED,
        created=1761900000,
        system_fingerprint="fp_demo",
        usage=SimpleNamespace(prompt_tokens=412, completion_tokens=38, total_tokens=450),
        choices=[
            SimpleNamespace(
                index=0,
                finish_reason="tool_calls",
                message=SimpleNamespace(
                    role="assistant", content=None, tool_calls=[call], refusal=None
                ),
            )
        ],
    )


def _seal(variant: dict) -> Path:
    from epi_recorder import record
    from epi_recorder.wrappers.openai import TracedCompletions

    out = OUT_DIR / variant["file"]
    response = _scripted_response(variant)
    case = variant["case"]

    with record(
        str(out),
        workflow_name="claims-agent",
        goal=variant["goal"],
        case_id=case,
        notes=(
            "SIMULATED DEMO - the model response is scripted; the record format, "
            "hashes, signature and approval are real."
        ),
        with_viewer=False,
        # Keep the demo seals local: no hash-only report to a cloud witness.
        witness_url="",
    ) as epi:
        with epi.agent_run("claims-agent", user_input=variant["user_input"]) as agent:
            agent.tool_call("lookup_claim", {"claim_id": case})
            agent.tool_result("lookup_claim", variant["lookup"])
            agent.tool_call("check_policy", {"policy": variant["lookup"]["policy"]})
            agent.tool_result("check_policy", variant["policy_result"])
            TracedCompletions(SimpleNamespace(create=lambda *a, **k: response)).create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": "You adjudicate insurance claims."},
                    {"role": "user", "content": variant["user_input"]},
                ],
                temperature=0.0,
                tools=[
                    {
                        "type": "function",
                        "function": {
                            "name": variant["tool"],
                            "description": variant["tool_description"],
                        },
                    }
                ],
            )
            agent.decision(
                variant["tool"],
                output=variant["decision_output"],
                confidence=0.93 if variant["tool"] == "deny_claim" else 0.88,
                rationale=variant["rationale"],
                basis=variant["basis"],
            )
            epi.log(
                "agent.approval.request",
                {"action": variant["approval_action"], "approval_id": variant["approval_id"]},
            )
        epi.log("agent.run.end", {"status": "completed", "claim_id": case})
    return out


def _sign_off(variant: dict, out: Path) -> dict:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    from epi_core.keys import key_fingerprint
    from epi_core.review import ReviewRecord, add_review_to_artifact, make_approval_entry

    key = Ed25519PrivateKey.generate()
    public_hex = key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    ).hex()
    record_obj = ReviewRecord(
        reviewed_by=APPROVER,
        reviews=[
            make_approval_entry(
                approval_id=variant["approval_id"],
                decision="approve",
                action=variant["approval_action"],
                reason=variant["approval_reason"],
                approver_name=APPROVER,
                key_fingerprint_hex=key_fingerprint(public_hex, grouped=False),
                demo_key=True,
            )
        ],
        reviewer_identity={
            "type": "name",
            "value": APPROVER,
            "role": "Approver",
            "org": "EPI demo (synthetic)",
            "verified": False,
        },
    )
    stamp = add_review_to_artifact(out, record_obj, private_key=key, timestamp=True) or {}
    return {"fingerprint": key_fingerprint(public_hex), "stamp": stamp}


def main() -> int:
    os.environ.setdefault("EPI_NOTARIZE", "0")
    os.environ.setdefault("EPI_QUIET", "1")
    os.environ["EPI_OVERWRITE"] = "1"
    # A throwaway EPI_HOME keeps the demo seals off any configured cloud
    # witness: the seal falls back to $EPI_HOME/cloud.json, and there is none.
    os.environ.setdefault("EPI_HOME", tempfile.mkdtemp(prefix="epi_demo_home_"))

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for variant in VARIANTS:
        out = _seal(variant)
        signed = _sign_off(variant, out)
        stamp = signed["stamp"]
        print(f"sealed {out.relative_to(ROOT)}")
        print(f"  approver fingerprint: {signed['fingerprint']}")
        print(f"  independent time: {stamp.get('status')} {stamp.get('gen_time') or ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
