#!/usr/bin/env python3
"""
Scenario 01 — Loan Approval: Happy Path
A loan officer uses an AI system to evaluate a $180,000 loan.
Policy is satisfied: amount is under $200K threshold, no manager approval needed.
Expected result: PASS, no policy faults.
"""
from pathlib import Path
from epi_recorder.api import EpiRecorderSession

OUTPUT = Path(__file__).parent / "output" / "01_loan_happy.epi"
OUTPUT.parent.mkdir(parents=True, exist_ok=True)

def main():
    with EpiRecorderSession(
        output_path=str(OUTPUT),
        workflow_name="loan-approval-APP-2026-0042",
        goal="Evaluate home loan application and document AI-assisted decision",
        notes="Standard home purchase. Amount below $200K threshold — no manager sign-off required.",
        tags=["loan", "finance", "happy-path", "simulation"],
        approved_by="branch.auto-approval@bank.com",
        metrics={"loan_amount": 180000, "credit_score": 735, "dti": 0.29},
        auto_sign=True,
    ) as epi:

        epi.log_step("application.intake", {
            "applicant_id": "APP-2026-0042",
            "loan_amount": 180000,
            "loan_purpose": "home_purchase",
            "property_address": "14 Elm Street, Springfield",
        })

        epi.log_step("credit.check", {
            "credit_score": 735,
            "debt_to_income": 0.29,
            "derogatory_marks": 0,
            "credit_history_years": 11,
            "result": "PASS",
        })

        epi.log_step("llm.request", {
            "model": "gpt-4o",
            "messages": [
                {"role": "system", "content": "You are a conservative loan risk assessor. Reply with RISK_LEVEL and REASON."},
                {"role": "user",   "content": "Assess: $180,000 home loan. Credit score 735, DTI 0.29, 11yr credit history, 0 derogatory marks."},
            ],
        })

        epi.log_step("llm.response", {
            "model": "gpt-4o",
            "output": "RISK_LEVEL: LOW. REASON: Credit score well above threshold (735 > 680), DTI comfortably below 36%, long clean credit history. Recommend approval at standard rate.",
            "tokens_used": 112,
            "latency_ms": 840,
        })

        epi.log_step("policy.check", {
            "rule_id": "R001",
            "loan_amount": 180000,
            "threshold": 200000,
            "status": "not_triggered",
            "note": "Amount below $200K threshold — auto-approval path.",
        })

        epi.log_step("agent.decision", {
            "decision": "APPROVED",
            "loan_amount": 180000,
            "interest_rate": "6.50%",
            "term_years": 30,
            "conditions": ["standard_title_search", "home_appraisal"],
            "rationale": "Low-risk profile confirmed by AI and automated policy check.",
        })

    print(f"[01] Loan happy path recorded -> {OUTPUT}")

if __name__ == "__main__":
    main()
