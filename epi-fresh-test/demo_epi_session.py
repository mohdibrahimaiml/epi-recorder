"""
EPI Recorder Demo - installed from GitHub
Records a simulated AI loan decision agent and saves a .epi file to the Desktop.
"""

import sys
import os

print(f"Python:  {sys.executable}")

from epi_recorder import EpiRecorderSession

desktop = os.path.join(os.path.expanduser("~"), "Desktop")
output_path = os.path.join(desktop, "demo_loan_decision.epi")

print(f"Recording to: {output_path}\n")

with EpiRecorderSession(
    output_path=output_path,
    workflow_name="Loan Decision Agent — Demo",
    goal="Evaluate and disburse a $25,000 personal loan for CUST-4821",
    tags=["demo", "loan", "finance"],
    auto_sign=True,
) as session:

    # Step 1: Agent receives input
    session.log_step(
        kind="agent.input",
        content={
            "input": "Process loan application for customer CUST-4821",
            "applicant": {
                "id": "CUST-4821",
                "name": "Alice Johnson",
                "credit_score": 720,
                "annual_income": 85000,
                "requested_amount": 25000,
            }
        }
    )

    # Step 2: LLM request (underwriter evaluation)
    session.log_step(
        kind="llm.request",
        content={
            "provider": "openai",
            "model": "gpt-4",
            "messages": [
                {"role": "system", "content": "You are a loan underwriting assistant."},
                {"role": "user", "content": "Evaluate: credit_score=720, income=$85,000, requested=$25,000"}
            ]
        }
    )

    # Step 3: LLM response
    session.log_step(
        kind="llm.response",
        content={
            "provider": "openai",
            "model": "gpt-4",
            "choices": [{
                "finish_reason": "stop",
                "message": {
                    "role": "assistant",
                    "content": "Credit score 720 and DTI 29.4% qualify for APPROVAL at 6.5% APR."
                }
            }],
            "usage": {"prompt_tokens": 87, "completion_tokens": 52, "total_tokens": 139}
        }
    )

    # Step 4: Agent requests human approval
    session.log_step(
        kind="agent.approval.request",
        content={
            "action": "approve_loan",
            "amount": 25000,
            "customer_id": "CUST-4821",
            "reason": "Credit score 720, DTI 29.4% — within standard limits",
            "recommended_rate": "6.5% APR"
        }
    )

    # Step 5: Human approves
    session.log_step(
        kind="agent.approval.response",
        content={
            "action": "approve_loan",
            "approved": True,
            "reviewer": "loan_officer",
            "reviewer_role": "senior_underwriter",
            "reason": "Application meets all standard criteria",
        }
    )

    # Step 6: Tool call — disburse funds
    session.log_step(
        kind="tool.call",
        content={
            "tool": "disburse_funds",
            "customer_id": "CUST-4821",
            "amount": 25000,
            "rate": 0.065,
            "term_months": 60,
        }
    )

    # Step 7: Tool response — success
    session.log_step(
        kind="tool.response",
        content={
            "tool": "disburse_funds",
            "status": "success",
            "loan_id": "LOAN-2026-98741",
            "message": "Funds disbursed successfully to CUST-4821"
        }
    )

    # Step 8: Agent finishes
    session.log_step(
        kind="agent.finish",
        content={
            "outcome": "loan_approved_and_disbursed",
            "loan_id": "LOAN-2026-98741",
            "amount": 25000,
            "summary": "$25,000 disbursed to CUST-4821 at 6.5% APR over 60 months."
        }
    )

print(f"\n✅ .epi file saved to Desktop!")
print(f"   Path: {output_path}")
print(f"   Size: {os.path.getsize(output_path):,} bytes")
print(f"\nOpen it with:  epi view \"{output_path}\"")
