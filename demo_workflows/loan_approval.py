#!/usr/bin/env python3
"""
Realistic financial workflow: Loan Approval Decision Support
A loan officer uses an AI system to evaluate a loan application.
"""
import json

from epi_recorder.api import EpiRecorderSession

# Simulated loan application
APPLICATION = {
    "applicant_id": "APP-2025-8842",
    "name": "Jane Doe",
    "ssn": "123-45-6789",  # This should be redacted
    "credit_score": 720,
    "annual_income": 85000,
    "loan_amount": 250000,
    "loan_purpose": "home_purchase",
    "debt_to_income": 0.32,
}

def main():
    with EpiRecorderSession(
        output_path="loan_decision.epi",
        workflow_name="loan-approval-APP-2025-8842",
        goal="Evaluate loan application and document decision rationale",
        notes="High-value loan requiring documented AI-assisted review",
        tags=["finance", "loan", "high-value", "compliance-required"],
        auto_sign=True,
    ) as epi:
        # Step 1: Application intake
        epi.log_step("application.intake", {
            "applicant_id": APPLICATION["applicant_id"],
            "loan_amount": APPLICATION["loan_amount"],
            "loan_purpose": APPLICATION["loan_purpose"],
        })

        # Step 2: Credit check (with PII that should be redacted)
        epi.log_step("credit.check", {
            "credit_score": APPLICATION["credit_score"],
            "debt_to_income": APPLICATION["debt_to_income"],
            "raw_report": f"SSN {APPLICATION['ssn']} score {APPLICATION['credit_score']}",
        })

        # Step 3: LLM risk assessment
        epi.log_step("llm.request", {
            "model": "gpt-4",
            "prompt": f"Assess loan risk: ${APPLICATION['loan_amount']} home loan, DTI {APPLICATION['debt_to_income']}, credit {APPLICATION['credit_score']}",
            "system_prompt": "You are a conservative loan risk assessor. Respond with RISK_LEVEL and REASON.",
        })

        # Step 4: LLM response
        epi.log_step("llm.response", {
            "output": "RISK_LEVEL: LOW. REASON: Credit score above 700, DTI below 36%, stable income. Recommend approval with standard terms.",
            "model": "gpt-4",
            "tokens_used": 145,
        })

        # Step 5: Policy guard check
        epi.log_step("policy.check", {
            "rule_id": "LOAN_AMOUNT_OVER_200K_REQUIRES_MANAGER_REVIEW",
            "loan_amount": APPLICATION["loan_amount"],
            "threshold": 200000,
            "status": "triggered",
            "required_approver": "branch_manager",
        })

        # Step 6: Human manager approval
        epi.log_step("agent.approval.response", {
            "reviewer": "mgr.smith@bank.com",
            "approved": True,
            "reason": "AI assessment aligns with manual review. Applicant has strong credit history.",
            "timestamp": "2025-01-15T14:30:00Z",
        })

        # Step 7: Final decision
        epi.log_step("agent.decision", {
            "decision": "APPROVED",
            "loan_amount": APPLICATION["loan_amount"],
            "interest_rate": "6.75%",
            "term_years": 30,
            "conditions": ["standard_title_search", "home_appraisal"],
            "rationale": "Low risk profile per AI and manual review.",
        })

        print(f"Loan decision recorded: loan_decision.epi")


if __name__ == "__main__":
    main()
