#!/usr/bin/env python3
"""
Scenario 04 — Customer Refund: Compliant (Identity Verified First)
Support agent processes an $8,500 refund with proper identity verification.
Policy R002 requires identity check before refund.
Policy R005 threshold is $10,000 — no human approval needed here.
Expected result: PASS, both R002 and R005 satisfied.
"""
from pathlib import Path
from epi_recorder.api import EpiRecorderSession

OUTPUT = Path(__file__).parent / "output" / "04_refund_compliant.epi"
OUTPUT.parent.mkdir(parents=True, exist_ok=True)

def main():
    with EpiRecorderSession(
        output_path=str(OUTPUT),
        workflow_name="refund-TICKET-2026-7734",
        goal="Process customer refund with full identity verification and audit trail",
        notes="High-value refund. Defective product — customer provided purchase receipt and photos.",
        tags=["support", "refund", "identity-verified", "simulation"],
        metrics={"refund_amount": 8500, "verification_score": 0.97},
        auto_sign=True,
    ) as epi:

        epi.log_step("ticket.intake", {
            "ticket_id": "TICKET-2026-7734",
            "customer_id": "CUST-88221",
            "refund_reason": "defective_product",
            "product_sku": "LAPTOP-PRO-15-2025",
            "purchase_date": "2026-02-10",
            "days_since_purchase": 81,
            "evidence_provided": ["purchase_receipt", "defect_photos", "shipping_return_label"],
        })

        # R002: identity must be verified BEFORE refund.processed
        epi.log_step("identity.verified", {
            "method": "document_id_plus_last4_card",
            "customer_id": "CUST-88221",
            "verification_score": 0.97,
            "result": "VERIFIED",
            "verified_at": "2026-05-02T09:01:00Z",
        })

        epi.log_step("llm.request", {
            "model": "claude-3-5-sonnet",
            "messages": [
                {"role": "system", "content": "You are a customer support agent. Evaluate refund eligibility and determine approval or denial with reasoning."},
                {"role": "user",   "content": "Refund request: $8,500 laptop, defective within 81 days of purchase. Customer verified. Evidence: receipt + photos. Policy allows refunds within 90 days."},
            ],
        })

        epi.log_step("llm.response", {
            "model": "claude-3-5-sonnet",
            "output": "DECISION: APPROVE REFUND. Reasoning: Within 90-day return window, documented defect with photo evidence, customer identity verified. Full refund of $8,500 is warranted under standard warranty policy.",
            "tokens_used": 134,
            "latency_ms": 920,
        })

        epi.log_step("policy.check", {
            "rule_id": "R002",
            "identity_verified": True,
            "verified_before_refund": True,
            "status": "compliant",
        })

        epi.log_step("policy.check", {
            "rule_id": "R005",
            "refund_amount": 8500,
            "threshold": 10000,
            "status": "not_triggered",
            "note": "Under $10K threshold — no human approval required.",
        })

        epi.log_step("refund.processed", {
            "refund_amount": 8500,
            "currency": "USD",
            "method": "original_payment_card",
            "transaction_id": "TXN-2026-REF-7734",
            "estimated_days": 3,
            "approved_by": "ai.support.agent@company.com",
        })

    print(f"[04] Refund compliant scenario recorded -> {OUTPUT}")

if __name__ == "__main__":
    main()
