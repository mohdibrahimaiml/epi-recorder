"""End-to-end investor demo for EPI policy, fault analysis, and review.

Run this from the `examples/investor_demo` directory so `epi_policy.json`
is discovered automatically during packing.
"""

from __future__ import annotations

from pathlib import Path

from epi_recorder import record


def main() -> None:
    output = Path("investor_fault_demo.epi")

    with record(
        output,
        workflow_name="Investor Fault Intelligence Demo",
        goal="Demonstrate policy-grounded fault analysis and human review",
        notes="Intentional policy and heuristic violations for investor walkthrough",
        metrics={"expected_faults": 6},
        approved_by="investor-demo@epilabs.org",
        metadata_tags=["investor-demo", "fault-analysis", "policy"],
    ) as epi:
        # Establish an early identity and financial constraint.
        epi.log_step(
            "tool.response",
            {
                "tool": "fetch_account_context",
                "account_id": "ACC-4401",
                "customer_id": "CUST-9001",
                "balance": 500.0,
                "currency": "USD",
            },
        )

        # Error continuation heuristic: the next step ignores the error.
        epi.log_step(
            "llm.error",
            {
                "error": "Rate limit exceeded while fetching external sanctions data",
                "provider": "demo-llm",
            },
        )

        # Constraint violation against balance = 500.
        epi.log_step(
            "tool.call",
            {
                "tool": "approve_loan_disbursement",
                "amount": 2000.0,
                "account_id": "ACC-4401",
                "reason": "urgent disbursement",
            },
        )

        # Sequence violation: refund without verify_identity first.
        epi.log_step(
            "tool.call",
            {
                "tool": "process_refund",
                "amount": 200.0,
                "reference": "REF-2026-001",
            },
        )

        # Threshold violation: human approval is required above 10,000.
        epi.log_step(
            "tool.call",
            {
                "tool": "approve_wire_transfer",
                "amount": 15000.0,
                "destination": "vendor-settlement",
            },
        )

        # Prohibition violation: secret-like pattern in output.
        epi.log_step(
            "llm.response",
            {
                "text": "Escalation note: temporary key observed as sk-ABC123SECRET for retry flow.",
                "model": "demo-llm",
            },
        )

        # Final steps omit the original account/customer identifiers to trigger context drop.
        epi.log_step(
            "tool.response",
            {
                "tool": "create_case",
                "case_reference": "CASE-7702",
                "status": "pending_manual_review",
            },
        )
        epi.log_step(
            "file.write",
            {
                "path": "case_summary.txt",
                "operation": "write",
                "size_bytes": 128,
            },
        )

    print(f"Created demo artifact: {output.resolve()}")
    print("Next: run `epi view investor_fault_demo.epi` or `epi review investor_fault_demo.epi`.")


if __name__ == "__main__":
    main()
