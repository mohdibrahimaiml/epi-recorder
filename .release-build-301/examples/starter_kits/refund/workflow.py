"""
EPI Starter Kit: Refund Approval Agent
---------------------------------------
A realistic refund decision agent with human approval, policy enforcement,
and full audit trail in a signed .epi case file.

Requirements:
    pip install epi-recorder

Optional (for real LLM calls):
    pip install openai
    export OPENAI_API_KEY=sk-...

Run:
    python workflow.py
    epi view refund_case.epi
    epi verify refund_case.epi
"""

import os
import time
import os
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

# ── Mock LLM — runs without any API key ──────────────────────────────────────

class _MockLLM:
    """Drop-in mock that simulates an OpenAI response. No API key required."""

    def __init__(self, decision_text: str):
        self._decision_text = decision_text

    def decide(self, order: dict) -> str:
        time.sleep(0.2)  # simulate network latency
        return self._decision_text


def _get_llm_decision(order: dict) -> tuple[str, str, dict]:
    """
    Returns (model_name, decision_text, usage_dict).
    Uses real OpenAI if OPENAI_API_KEY is set, otherwise uses mock.
    """
    use_real = bool(os.getenv("OPENAI_API_KEY"))

    if use_real:
        try:
            from openai import OpenAI
            from epi_recorder import wrap_openai

            client = wrap_openai(OpenAI())
            prompt = (
                f"You are a refund decision agent. Be concise (one sentence).\n"
                f"Order: {order['order_id']}, ${order['amount_usd']}, "
                f"{order['customer_tier']} customer, {order['days_since_purchase']} days since purchase.\n"
                f"Should we approve this refund? Answer: APPROVE or REJECT, then explain why."
            )
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a concise refund decision agent."},
                    {"role": "user", "content": prompt},
                ],
            )
            text = resp.choices[0].message.content
            usage = {
                "prompt_tokens": resp.usage.prompt_tokens,
                "completion_tokens": resp.usage.completion_tokens,
                "total_tokens": resp.usage.total_tokens,
            }
            return "gpt-4o-mini", text, usage
        except Exception as e:
            print(f"[warn] OpenAI call failed ({e}), falling back to mock.")

    decision = (
        f"APPROVE. Order {order['order_id']} qualifies: {order['customer_tier'].upper()} customer, "
        f"${order['amount_usd']}, {order['days_since_purchase']} days since purchase (within 30-day window). "
        f"Risk: low."
    )
    return "mock-llm", decision, {"prompt_tokens": 42, "completion_tokens": 30, "total_tokens": 72}


# ── Agent logic ───────────────────────────────────────────────────────────────

def run_refund_agent(
    order_id: str = "ORD-9001",
    reviewer_email: str = "manager@company.com",
    output_file: str = "refund_case.epi",
) -> dict:
    """
    Process a refund request with full EPI evidence capture.

    Returns the final decision dict.
    """
    output_path = Path(output_file)
    display_path = _display_output_path(output_file)

    with record(str(output_path), goal=f"Process refund for {order_id}") as epi:

        # Step 1: Agent starts
        epi.log_step("agent.run.start", {
            "agent_name": "RefundApprovalAgent",
            "agent_version": "1.0",
            "user_input": f"Process refund for order {order_id}",
            "goal": "Determine whether to approve or reject the refund request",
            "policy_file": "epi_policy.json",
        })

        # Step 2: Look up the order
        print(f"Looking up order {order_id}...")
        epi.log_step("tool.call", {
            "tool": "lookup_order",
            "input": {"order_id": order_id},
        })

        # Simulate order lookup (replace with real DB/API call)
        order = {
            "order_id": order_id,
            "amount_usd": 900,
            "customer_tier": "gold",
            "days_since_purchase": 12,
            "product": "Wireless Headphones Pro",
            "payment_method": "credit_card",
            "return_reason": "Defective - no sound from left ear",
        }

        epi.log_step("tool.response", {
            "tool": "lookup_order",
            "status": "success",
            "output": order,
        })

        # Step 3: LLM decision
        print("Consulting AI decision engine...")
        model_name, decision_text, usage = _get_llm_decision(order)

        epi.log_step("llm.request", {
            "provider": "openai",
            "model": model_name,
            "messages": [
                {"role": "system", "content": "You are a refund decision agent."},
                {"role": "user", "content": f"Evaluate refund for {order_id}"},
            ],
        })

        epi.log_step("llm.response", {
            "provider": "openai",
            "model": model_name,
            "choices": [{"message": {"role": "assistant", "content": decision_text}, "finish_reason": "stop"}],
            "usage": usage,
        })

        # Step 4: Human approval (required by policy rule refund-001 for amounts > $500)
        print(f"Requesting human approval from {reviewer_email}...")
        epi.log_step("agent.approval.request", {
            "approval_id": f"approval-{order_id}",
            "reason": f"Amount ${order['amount_usd']} exceeds $500 auto-approval threshold (policy: refund-001)",
            "requested_from": reviewer_email,
            "timeout_minutes": 60,
        })

        # Simulate approval response (in production: real workflow/webhook)
        epi.log_step("agent.approval.response", {
            "approval_id": f"approval-{order_id}",
            "approved": True,
            "reviewer": reviewer_email,
            "reviewer_note": "Verified: defective product confirmed by support ticket #SUP-4421.",
        })

        # Step 5: Final decision
        approved = "APPROVE" in decision_text.upper()
        confidence = 0.94

        decision = {
            "decision": "approve_refund" if approved else "reject_refund",
            "order_id": order_id,
            "amount_usd": order["amount_usd"],
            "action": "APPROVE" if approved else "REJECT",
            "confidence": confidence,
            "rationale": decision_text,
            "review_required": False,  # already reviewed above
        }

        epi.log_step("agent.decision", decision)

        # Step 6: Execute the refund
        print(f"Executing refund: ${order['amount_usd']} to {order['payment_method']}...")
        epi.log_step("tool.call", {
            "tool": "execute_refund",
            "input": {"order_id": order_id, "amount_usd": order["amount_usd"], "method": order["payment_method"]},
        })

        epi.log_step("tool.response", {
            "tool": "execute_refund",
            "status": "success",
            "output": {
                "refund_id": f"REF-{order_id}-001",
                "amount_usd": order["amount_usd"],
                "estimated_days": 3,
            },
        })

        epi.log_step("agent.run.end", {
            "agent_name": "RefundApprovalAgent",
            "success": True,
            "outcome": decision["action"],
        })

        print(f"\nDecision: {decision['action']} ${order['amount_usd']} refund for {order_id}")

    print(f"\nCase file: {display_path.resolve()}")
    print(f"  epi view    {output_path}   # open in browser")
    print(f"  epi verify  {output_path}   # cryptographic integrity check")
    print(f"  epi share   {output_path}   # get a hosted share link")
    print(f"  epi review  {output_path}   # add human review notes")

    return decision


if __name__ == "__main__":
    run_refund_agent()
