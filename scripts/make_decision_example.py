#!/usr/bin/env python3
"""Seal the example decision record shown on the homepage.

The provider response is scripted (no API key), so the file says so in its notes.
Everything else is real: the tool call is recorded by the OpenAI wrapper, the
decision carries its reasons and the rules it relied on, the approval is signed
by a throwaway demo key, and the seal is a normal Ed25519 seal.

    python scripts/make_decision_example.py
"""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "website" / "assets" / "demo" / "decision-example.epi"

MODEL = "gpt-4o"
SERVED = "gpt-4o-2024-08-06"
APPROVER = "DEMO KEY - Claims Adjuster (not a real person)"


def main() -> int:
    os.environ.setdefault("EPI_NOTARIZE", "0")
    os.environ.setdefault("EPI_QUIET", "1")
    os.environ["EPI_OVERWRITE"] = "1"

    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    from epi_core.keys import key_fingerprint
    from epi_core.review import ReviewRecord, add_review_to_artifact, make_approval_entry
    from epi_recorder import record
    from epi_recorder.wrappers.openai import TracedCompletions

    call = SimpleNamespace(
        id="call_9f21",
        type="function",
        function=SimpleNamespace(
            name="deny_claim",
            arguments=(
                '{"claim_id": "CLM-1001", "decision": "deny", '
                '"reason": "Water damage exclusion HO3-4.2 applies to this peril."}'
            ),
        ),
    )
    response = SimpleNamespace(
        id="chatcmpl-7c1e",
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

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with record(
        str(OUT),
        workflow_name="claims-agent",
        goal="Adjudicate claim CLM-1001",
        case_id="CLM-1001",
        notes=(
            "SIMULATED DEMO - the model response is scripted; the record format, "
            "hashes, signature and approval are real."
        ),
        with_viewer=False,
    ) as epi:
        with epi.agent_run("claims-agent", user_input="Claim CLM-1001: burst pipe, kitchen") as agent:
            agent.tool_call("lookup_claim", {"claim_id": "CLM-1001"})
            agent.tool_result(
                "lookup_claim",
                {"claim_id": "CLM-1001", "peril": "water damage", "policy": "HO3-4.2"},
            )
            agent.tool_call("check_policy", {"policy": "HO3-4.2"})
            agent.tool_result(
                "check_policy",
                {"covered": False, "clause": "HO3-4.2", "text": "Water damage from plumbing is excluded."},
            )
            TracedCompletions(SimpleNamespace(create=lambda *a, **k: response)).create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": "You adjudicate insurance claims."},
                    {"role": "user", "content": "Claim CLM-1001: burst pipe, kitchen. Policy HO3-4.2."},
                ],
                temperature=0.0,
                tools=[
                    {
                        "type": "function",
                        "function": {
                            "name": "deny_claim",
                            "description": "Deny a claim with the policy clause relied on",
                        },
                    }
                ],
            )
            agent.decision(
                "deny_claim",
                output={"claim_id": "CLM-1001", "payable_usd": 0},
                confidence=0.93,
                rationale="Water damage exclusion HO3-4.2 applies to this peril.",
                basis={
                    "policy": "HO3-4.2",
                    "data": ["claim:CLM-1001", "policy:HO3-4.2#exclusion", "peril:water damage"],
                },
            )
            epi.log(
                "agent.approval.request",
                {"action": "issue denial notice", "approval_id": "denial-CLM-1001"},
            )
        epi.log("agent.run.end", {"status": "completed", "claim_id": "CLM-1001"})

    key = Ed25519PrivateKey.generate()
    public_hex = key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    ).hex()
    record_obj = ReviewRecord(
        reviewed_by=APPROVER,
        reviews=[
            make_approval_entry(
                approval_id="denial-CLM-1001",
                decision="approve",
                action="issue denial notice",
                reason="Checked against policy HO3-4.2; the exclusion applies.",
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
    stamp = add_review_to_artifact(OUT, record_obj, private_key=key, timestamp=True) or {}
    print(f"sealed {OUT}")
    print(f"  approver fingerprint: {key_fingerprint(public_hex)}")
    print(f"  independent time: {stamp.get('status')} {stamp.get('gen_time') or ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
