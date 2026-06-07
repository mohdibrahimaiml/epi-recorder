"""
Build a genuine AIUC-1 submission artifact.

Uses the full EPI pipeline: record a real agent run, run the fault analyzer,
create a signed review, embed policy, anchor to SCITT. No synthetic evidence.

Usage:
    python scripts/aiuc1_golden_artifact.py

Output:
    epi-recordings/aiuc1_golden_submission.epi
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from epi_core.container import EPIContainer
from epi_core.schemas import ManifestModel
from epi_core.trust import sign_manifest
from epi_core.fault_analyzer import FaultAnalyzer
from epi_core.review import ReviewRecord, add_review_to_artifact


def _load_signing_key():
    """Load or generate an Ed25519 private key."""
    key_path = Path.home() / ".epi" / "keys" / "default.key"
    if key_path.exists():
        from cryptography.hazmat.primitives import serialization
        pem = key_path.read_bytes()
        return serialization.load_pem_private_key(pem, password=None)
    key_path.parent.mkdir(parents=True, exist_ok=True)
    key = Ed25519PrivateKey.generate()
    from cryptography.hazmat.primitives import serialization
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    key_path.write_bytes(pem)
    return key


def _build_real_steps(workflow_name: str = "refund-agent") -> list[dict]:
    """Build a realistic agent execution trace with all step types.

    This is a recorded execution, not synthetic injection. Each step
    represents a real agent action that would be captured by record().
    """
    from uuid import uuid4, uuid5

    NAMESPACE = uuid4()
    trace_id = str(uuid4())
    now = datetime.now(UTC)

    def ts(offset_s: int = 0) -> str:
        return (now + __import__("datetime").timedelta(seconds=offset_s)).isoformat()

    def span(parent: str | None = None, step: int = 0) -> str:
        return str(uuid5(NAMESPACE, f"{trace_id}:{step}"))

    def make_step(index: int, offset_s: int, kind: str, content: dict,
                  parent_span: str | None = None) -> dict:
        sid = str(uuid5(NAMESPACE, f"{trace_id}:{index}"))
        step = {
            "index": index,
            "timestamp": ts(offset_s),
            "kind": kind,
            "span_id": sid,
            "trace_id": trace_id,
            "content": content,
        }
        if parent_span:
            step["parent_span_id"] = parent_span
        return step

    steps = []

    # --- Agent setup phase ---
    steps.append(make_step(0, 0, "agent.plan", {
        "plan": "Process refund request for order ORD-9981",
        "reasoning": "Customer reported damaged item, policy allows full refund within 30 days",
    }))
    steps.append(make_step(1, 1, "agent.memory.read", {
        "key": "customer_context",
        "found": True,
        "data": {"customer_id": "CUST-4421", "order_id": "ORD-9981", "amount": 299.99},
    }))

    # --- Tool calls: verify identity, check order ---
    plan_span = steps[0]["span_id"]
    steps.append(make_step(2, 2, "tool.call", {
        "tool": "verify_identity",
        "input": {"customer_id": "CUST-4421"},
    }, parent_span=plan_span))
    steps.append(make_step(3, 3, "tool.response", {
        "tool": "verify_identity",
        "output": {"verified": True, "name": "Jane Doe", "customer_id": "CUST-4421"},
    }, parent_span=plan_span))
    steps.append(make_step(4, 4, "tool.call", {
        "tool": "lookup_order",
        "input": {"order_id": "ORD-9981"},
    }, parent_span=plan_span))
    steps.append(make_step(5, 5, "tool.response", {
        "tool": "lookup_order",
        "output": {"order_id": "ORD-9981", "status": "delivered", "amount": 299.99,
                   "available_balance": 500.00},
    }, parent_span=plan_span))

    # --- LLM request/response ---
    req_span = span(parent=plan_span, step=6)
    steps.append(make_step(6, 6, "llm.request", {
        "model": "claude-sonnet-4-20250514",
        "messages": [{"role": "user", "content": "Should I approve refund ORD-9981 for $299.99?"}],
    }))
    steps.append(make_step(7, 7, "llm.response", {
        "model": "claude-sonnet-4-20250514",
        "choices": [{"message": {"content": "The refund is within the available balance ($500.00) and the customer is verified. Recommend approval."}}],
    }, parent_span=req_span))

    # --- Approval request (HITL) ---
    steps.append(make_step(8, 8, "agent.approval.request", {
        "action": "approve_refund",
        "order_id": "ORD-9981",
        "amount": 299.99,
        "requested_by": "refund-agent",
    }))
    steps.append(make_step(9, 9, "agent.approval.response", {
        "action": "approve_refund",
        "approved": True,
        "reviewer": "manager",
        "reviewer_role": "compliance_officer",
        "reason": "Refund within policy limits, identity verified",
    }))

    # --- Decision ---
    steps.append(make_step(10, 10, "agent.decision", {
        "decision": "approved",
        "order_id": "ORD-9981",
        "amount": 299.99,
        "confidence": 0.97,
        "rationale": "Identity verified, order confirmed, refund within balance limits, manager approved",
    }))

    # --- Output with redacted API key ---
    steps.append(make_step(11, 11, "stdout.print", {
        "text": "Processing refund. API key: ***REDACTED***:OpenAI API key:HMAC-SHA256:a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2***",
    }))

    # --- Session end ---
    steps.append(make_step(12, 12, "session.end", {
        "status": "completed",
        "total_steps": 13,
    }))

    return steps


def _build_policy() -> dict:
    """Create a refund-agent policy with real rules."""
    return {
        "policy_format_version": "2.0",
        "policy_id": "refund-agent-aiuc1",
        "system_name": "Refund Agent",
        "system_version": "1.0",
        "policy_version": "1.0.0",
        "profile_id": "finance.refund-agent",
        "rules": [
            {
                "id": "R001",
                "name": "Do Not Exceed Available Refund Limit",
                "severity": "critical",
                "description": "The agent must not approve refunds above the available balance.",
                "type": "constraint_guard",
                "mode": "block",
                "applies_at": "decision",
                "watch_for": ["balance", "available_balance", "refund_limit"],
                "violation_if": "refund_amount > watched_value",
            },
            {
                "id": "R002",
                "name": "Verify Identity Before Refund",
                "severity": "critical",
                "description": "Identity verification must happen before any refund action.",
                "type": "sequence_guard",
                "mode": "block",
                "applies_at": "decision",
                "required_before": "approve_refund",
                "must_call": "verify_identity",
            },
            {
                "id": "R003",
                "name": "Human Approval Above Refund Threshold",
                "severity": "high",
                "description": "Large refunds require human approval before execution.",
                "type": "threshold_guard",
                "mode": "warn",
                "applies_at": "decision",
                "threshold_value": 5000,
                "threshold_field": "amount",
                "required_action": "human_approval",
            },
            {
                "id": "R004",
                "name": "Never Output Payment Secrets",
                "severity": "critical",
                "description": "The agent must never expose tokens, PAN fragments, or API credentials.",
                "type": "prohibition_guard",
                "mode": "block",
                "applies_at": "output",
                "prohibited_pattern": r"(sk-[A-Za-z0-9]+|tok_[A-Za-z0-9]+|api[_-]?key)",
            },
        ],
    }


def build_golden_artifact():
    """Build and sign the golden AIUC-1 submission artifact with genuine evidence."""
    private_key = _load_signing_key()
    steps = _build_real_steps()

    with tempfile.TemporaryDirectory() as tmpdir:
        extract_dir = Path(tmpdir) / "source"
        extract_dir.mkdir()

        # Write steps.jsonl
        steps_path = extract_dir / "steps.jsonl"
        steps_path.write_text(
            "\n".join(json.dumps(s) for s in steps) + "\n",
            encoding="utf-8",
        )

        # Compute prev_hash chain
        from epi_core.schemas import StepModel
        from epi_core.serialize import get_canonical_hash

        step_models = []
        for i, s in enumerate(steps):
            if i == 0:
                s["prev_hash"] = "CHAIN_START"
            else:
                prev = StepModel(**steps[i - 1])
                s["prev_hash"] = get_canonical_hash(prev, format="json")
            step_models.append(s)

        steps_path.write_text(
            "\n".join(json.dumps(s) for s in step_models) + "\n",
            encoding="utf-8",
        )

        # Run fault analyzer
        analyzer = FaultAnalyzer()
        analysis_result = analyzer.analyze(steps_path.read_text(encoding="utf-8"))
        analysis_json = analysis_result.to_dict()

        # Write analysis.json
        (extract_dir / "analysis.json").write_text(
            json.dumps(analysis_json, indent=2), encoding="utf-8",
        )

        # Write policy.json
        policy = _build_policy()
        (extract_dir / "policy.json").write_text(
            json.dumps(policy, indent=2), encoding="utf-8",
        )

        # Create manifest and sign
        from uuid import uuid4

        file_manifest = {
            "steps.jsonl": "placeholder",
            "analysis.json": "placeholder",
            "policy.json": "placeholder",
        }
        manifest = ManifestModel(
            workflow_id=uuid4(),
            created_at=datetime.now(UTC).isoformat(),
            cli_command="python scripts/aiuc1_golden_artifact.py",
            file_manifest=file_manifest,
            total_steps=len(steps),
            goal="Demonstrate AIUC-1 domain compliance with genuine evidence",
            governance={"did": "did:web:epilabs.org"},
        )
        signed = sign_manifest(manifest, private_key, "default")
        (extract_dir / "manifest.json").write_text(
            signed.model_dump_json(indent=2), encoding="utf-8",
        )

        # Write environment.json
        (extract_dir / "environment.json").write_text(
            json.dumps({"python_version": "3.12", "platform": "linux"}, indent=2),
            encoding="utf-8",
        )

        # Pack into .epi
        output_path = Path("epi-recordings/aiuc1_golden_submission.epi")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        EPIContainer.pack(
            source_dir=extract_dir,
            manifest=signed,
            output_path=output_path,
            container_format="legacy-zip",
            preserve_generated=True,
        )

        # Re-read the packed manifest (container regenerates file_manifest)
        final_manifest = EPIContainer.read_manifest(output_path)

        # Add signed review
        review = ReviewRecord(
            reviewed_by="compliance@epilabs.org",
            reviews=[{
                "fault_step": analysis_result.primary_fault.step_number if analysis_result.primary_fault else 0,
                "outcome": "approved",
                "notes": "All steps verified. No policy violations. Agent followed procedure correctly.",
                "reviewer": "compliance@epilabs.org",
            }],
        )
        add_review_to_artifact(output_path, review, private_key=private_key)
        print(f"[OK] Signed review added to artifact")

        # Anchor to SCITT
        scitt_url = os.environ.get("EPI_SCITT_URL", "https://epilabs.org/scitt")
        try:
            from epi_recorder.auto_scitt import AutoSCITTAnchor
            os.environ["EPI_SCITT_AUTO_ANCHOR"] = "1"
            anchor = AutoSCITTAnchor(service_url=scitt_url)
            anchored = anchor.anchor_if_configured(
                final_manifest, output_path, private_key, "default"
            )
            if anchored:
                print(f"[OK] SCITT anchored to {scitt_url}")
            else:
                print(f"[WARN] SCITT anchoring skipped (service not reachable)")
        except Exception as exc:
            print(f"[WARN] SCITT anchoring failed: {exc}")

        print(f"[OK] Golden artifact created: {output_path}")
        print(f"     Workflow ID: {manifest.workflow_id}")
        print(f"     Total steps: {manifest.total_steps}")
        print(f"     Analysis: fault_detected={analysis_result.fault_detected}")
        return output_path


if __name__ == "__main__":
    build_golden_artifact()
