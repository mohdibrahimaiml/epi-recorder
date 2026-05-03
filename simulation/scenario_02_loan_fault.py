#!/usr/bin/env python3
"""
Scenario 02 — Loan Approval: Policy Fault
A loan officer approves a $250,000 loan WITHOUT logging manager approval.
Policy R001 requires manager sign-off for loans over $200,000.
Expected result: FAULT — R001 violation detected by policy engine.
"""
from pathlib import Path
from epi_recorder.api import EpiRecorderSession

OUTPUT = Path(__file__).parent / "output" / "02_loan_fault.epi"
OUTPUT.parent.mkdir(parents=True, exist_ok=True)

def main():
    with EpiRecorderSession(
        output_path=str(OUTPUT),
        workflow_name="loan-approval-APP-2026-0099",
        goal="Evaluate high-value home loan application",
        notes="Applicant is a premium customer. Loan officer fast-tracked without manager review.",
        tags=["loan", "finance", "policy-violation", "simulation"],
        metrics={"loan_amount": 250000, "credit_score": 760, "dti": 0.27},
        auto_sign=True,
    ) as epi:

        epi.log_step("application.intake", {
            "applicant_id": "APP-2026-0099",
            "loan_amount": 250000,
            "loan_purpose": "home_purchase",
            "property_address": "88 Riverside Drive, Capital City",
        })

        epi.log_step("credit.check", {
            "credit_score": 760,
            "debt_to_income": 0.27,
            "derogatory_marks": 0,
            "result": "PASS",
        })

        epi.log_step("llm.request", {
            "model": "gpt-4o",
            "messages": [
                {"role": "system", "content": "You are a loan risk assessor."},
                {"role": "user",   "content": "Assess: $250,000 home loan. Credit 760, DTI 0.27, premium customer."},
            ],
        })

        epi.log_step("llm.response", {
            "model": "gpt-4o",
            "output": "RISK_LEVEL: VERY LOW. Strong credit profile. Recommend approval with preferred rate.",
            "tokens_used": 98,
        })

        # NOTE: Manager approval step intentionally OMITTED — this triggers R001
        # In a compliant workflow: epi.log_step("agent.approval.response", {...})

        epi.log_step("agent.decision", {
            "decision": "APPROVED",
            "loan_amount": 250000,
            "interest_rate": "6.25%",
            "term_years": 30,
            "rationale": "Strong credit profile — officer approved without escalation.",
        })

    print(f"[02] Loan fault scenario recorded -> {OUTPUT}")
    print("     Expected: R001 policy fault (missing manager approval for loan > $200K)")

if __name__ == "__main__":
    main()
