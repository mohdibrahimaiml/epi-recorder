#!/usr/bin/env python3
"""Seal the auto-claim decision record shown on the NAIC vendor page.

The scenario is invented: a homeowners water-damage claim where the AI
recommends a denial on a named exclusion and the adjuster overrides it to a
partial payment. The data is fake and the file says so in its notes.

Everything else is real. The steps are recorded during the run, each decision
carries the reasons and the policy clause it relied on, the approval is signed
by a throwaway demo key, and the seal is a normal Ed25519 seal.

    python scripts/make_naic_claim_override_example.py
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "website" / "assets" / "demo"
OUT = OUT_DIR / "naic-claim-override.epi"

MODEL = "gpt-4o"
SERVED = "gpt-4o-2024-08-06"
APPROVER = "Dana Whitfield, Claims Adjuster (demo key, invented person)"
CASE = "CLM-2026-04417"
POLICY = "HO3-5510287"
POLICY_REV = "rev-2024-07"  # the form version in force on the date of loss
CLAUSE = "Section I - E.2(c), constant or repeated seepage over 14 days"

USER_INPUT = (
    "Claim CLM-2026-04417: water damage in the finished basement. "
    f"Policy {POLICY}, loss date 19 October 2026, estimate $9,400."
)

LOOKUP = {
    "claim_id": CASE,
    "policy": POLICY,
    "policy_revision": POLICY_REV,
    "date_of_loss": "2026-10-19",
    "peril": "water damage",
    "estimate_usd": 9400,
    "adjuster_report": {
        "report_id": "PLB-7731",
        "finding": "Supply line ruptured suddenly on 18 October 2026; no long-term seepage observed.",
    },
}

POLICY_RESULT = {
    "covered": False,
    "clause": CLAUSE,
    "policy_revision": POLICY_REV,
    "text": "Constant or repeated seepage over a period of 14 days or more is excluded.",
}

AI_TOOL_ARGS = (
    '{"claim_id": "CLM-2026-04417", "decision": "deny", "reason": '
    '"Water damage exclusion E.2(c) applies: records show moisture present over '
    'at least three weeks."}'
)


def _scripted_response() -> SimpleNamespace:
    call = SimpleNamespace(
        id="call_claim04417",
        type="function",
        function=SimpleNamespace(name="deny_claim", arguments=AI_TOOL_ARGS),
    )
    return SimpleNamespace(
        id="chatcmpl-claim04417",
        model=SERVED,
        created=1761206400,
        system_fingerprint="fp_demo",
        usage=SimpleNamespace(prompt_tokens=612, completion_tokens=41, total_tokens=653),
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


def _seal() -> Path:
    from epi_recorder import record
    from epi_recorder.wrappers.openai import TracedCompletions

    response = _scripted_response()

    with record(
        str(OUT),
        workflow_name="claims-agent",
        goal="Adjudicate claim CLM-2026-04417",
        case_id=CASE,
        notes=(
            "INVENTED EXAMPLE - fake claim, fake policy, fake people. The model "
            "response is scripted; the record format, timestamps, signature and "
            "approval are real."
        ),
        with_viewer=False,
        witness_url="",
    ) as epi:
        with epi.agent_run("claims-agent", user_input=USER_INPUT) as agent:
            agent.tool_call("lookup_claim", {"claim_id": CASE})
            agent.tool_result("lookup_claim", LOOKUP)

            agent.tool_call("check_policy", {"policy": POLICY, "revision": POLICY_REV})
            agent.tool_result("check_policy", POLICY_RESULT)

            TracedCompletions(SimpleNamespace(create=lambda *a, **k: response)).create(
                model=MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": "You adjudicate homeowners insurance claims.",
                    },
                    {"role": "user", "content": USER_INPUT},
                ],
                temperature=0.0,
                tools=[
                    {
                        "type": "function",
                        "function": {
                            "name": "deny_claim",
                            "description": "Deny a claim, citing the policy exclusion relied on",
                        },
                    }
                ],
            )

            agent.decision(
                "deny_claim",
                output={"claim_id": CASE, "payable_usd": 0},
                confidence=0.81,
                rationale=(
                    "Water damage exclusion E.2(c) applies: records show moisture "
                    "present over at least three weeks."
                ),
                basis={
                    "policy": f"{POLICY}#{POLICY_REV}#E.2(c)",
                    "data": [
                        f"claim:{CASE}",
                        f"policy:{POLICY}#{POLICY_REV}#E.2(c)",
                        "peril:water damage",
                        "report:PLB-7731",
                        "estimate:EST-9021",
                    ],
                },
            )

            epi.log(
                "agent.approval.request",
                {
                    "action": "issue denial notice",
                    "approval_id": f"denial-{CASE}",
                    "claim_id": CASE,
                    "ai_recommendation": "deny",
                },
            )

            epi.log(
                "agent.reviewer.override",
                {
                    "claim_id": CASE,
                    "reviewer": "Dana Whitfield, Claims Adjuster",
                    "ai_recommendation": "deny",
                    "reviewer_action": "approve partial payment",
                    "gross_estimate_usd": 9400,
                    "deductible_usd": 1000,
                    "payable_usd": 8400,
                    "reason": (
                        "Plumber report PLB-7731 shows the supply line ruptured "
                        "suddenly on 18 October, so the 14-day seepage exclusion "
                        "does not cover the whole loss. The AI relied on moisture "
                        "records only and did not read the report."
                    ),
                    "policy_revision_in_force": POLICY_REV,
                },
            )

            # The outcome that actually took effect. The earlier agent.decision
            # above is the AI's recommendation, not what was paid.
            agent.decision(
                "partial payment",
                output={
                    "claim_id": CASE,
                    "payable_usd": 8400,
                    "overrides_ai_recommendation": "deny",
                },
                rationale=(
                    "Adjuster override: plumber report PLB-7731 shows a sudden "
                    "supply-line rupture on 18 October, so exclusion E.2(c) does "
                    "not cover the whole loss. Partial payment of $8,400 after the "
                    "$1,000 deductible."
                ),
                basis={
                    "policy": f"{POLICY}#{POLICY_REV}#E.2(c)",
                    "data": [
                        f"claim:{CASE}",
                        "report:PLB-7731",
                        "estimate:EST-9021",
                        f"review:override-{CASE}",
                    ],
                },
                decided_by="human",
                ai_recommendation="deny",
                reviewer="Dana Whitfield, Claims Adjuster",
            )

        epi.log("agent.run.end", {"status": "completed", "claim_id": CASE})
    return OUT


def _sign_off(out: Path) -> dict:
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
                approval_id=f"override-{CASE}",
                decision="approve",
                action="override AI recommendation: approve partial payment of $8,400",
                reason=(
                    "Plumber report PLB-7731 shows a sudden supply-line rupture, so "
                    "exclusion E.2(c) does not apply to the whole loss. Partial "
                    "payment approved after the $1,000 deductible."
                ),
                approver_name=APPROVER,
                key_fingerprint_hex=key_fingerprint(public_hex, grouped=False),
                demo_key=True,
            )
        ],
        reviewer_identity={
            "type": "name",
            "value": APPROVER,
            "role": "Claims Adjuster",
            "org": "Invented insurer (synthetic)",
            "verified": False,
        },
    )
    stamp = add_review_to_artifact(out, record_obj, private_key=key, timestamp=True) or {}
    return {"fingerprint": key_fingerprint(public_hex), "stamp": stamp}


def main() -> int:
    os.environ.setdefault("EPI_NOTARIZE", "0")
    os.environ.setdefault("EPI_QUIET", "1")
    os.environ["EPI_OVERWRITE"] = "1"
    os.environ.setdefault("EPI_HOME", tempfile.mkdtemp(prefix="epi_naic_home_"))

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = _seal()
    signed = _sign_off(out)
    stamp = signed["stamp"]
    print(f"sealed {out.relative_to(ROOT)}")
    print(f"  approver fingerprint: {signed['fingerprint']}")
    print(f"  independent time: {stamp.get('status')} {stamp.get('gen_time') or ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
