"""
SCITT + AIUC-1 smoke test.

Creates a complete EPI artifact, registers with a mock SCITT service
(Merkle-tree-backed), embeds the receipt, verifies it with inclusion proof,
and checks all 6 AIUC-1 trust domains pass with substantive evidence.

Usage:
    python _test_scitt_aiuc1.py
    epi verify epi-recordings/scitt_aiuc1_smoke.epi --aiuc1 --strict
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def _build_key():
    key_dir = Path.home() / ".epi" / "keys"
    key_dir.mkdir(parents=True, exist_ok=True)
    key = Ed25519PrivateKey.generate()
    from cryptography.hazmat.primitives import serialization
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    key_file = key_dir / "default.key"
    key_file.write_bytes(pem)
    return key


def _build_steps():
    """Realistic agent execution trace covering all 6 AIUC-1 domains."""
    import hmac, hashlib as hl

    secret = b"smoke-test-redaction-secret-32b"
    def redact(desc, val):
        h = hmac.new(secret, val.encode(), hl.sha256)
        return f"***REDACTED***:{desc}:HMAC-SHA256:{h.hexdigest()}***"

    now = datetime.now(UTC)

    def s(idx, offset, kind, content):
        return {
            "index": idx,
            "timestamp": (now.replace(second=offset)).isoformat(),
            "kind": kind,
            "span_id": f"span-{idx:03d}",
            "trace_id": "smoke-trace-001",
            "content": content,
        }

    steps = []
    steps.append(s(0, 0, "agent.plan", {"plan": "Process refund ORD-001", "reasoning": "Standard refund workflow"}))
    steps.append(s(1, 1, "agent.memory.read", {"key": "customer", "data": {"customer_id": "CUST-001"}}))
    steps.append(s(2, 2, "tool.call", {"tool": "verify_identity", "input": {"customer_id": "CUST-001"}}))
    steps.append(s(3, 3, "tool.response", {"tool": "verify_identity", "output": {"verified": True}}))
    steps.append(s(4, 4, "tool.call", {"tool": "lookup_order", "input": {"order_id": "ORD-001"}}))
    steps.append(s(5, 5, "tool.response", {"tool": "lookup_order", "output": {"amount": 299.99, "balance": 500.00}}))
    steps.append(s(6, 6, "llm.request", {"model": "claude-sonnet", "messages": [{"role": "user", "content": "Approve refund?"}]}))
    steps.append(s(7, 7, "llm.response", {"model": "claude-sonnet", "text": "Recommend approve. Balance sufficient."}))
    steps.append(s(8, 8, "agent.approval.request", {"action": "approve_refund", "amount": 299.99}))
    steps.append(s(9, 9, "agent.approval.response", {"action": "approve_refund", "approved": True, "reviewer": "manager"}))
    steps.append(s(10, 10, "agent.decision", {"decision": "approved", "confidence": 0.97, "amount": 299.99}))
    # Two redaction categories for completeness check
    steps.append(s(11, 11, "stdout.print", {
        "text": redact("OpenAI API key", "sk-test-key-123") + " " + redact("Email address", "user@test.com")
    }))
    steps.append(s(12, 12, "llm.error", {"error": "RateLimitError", "recoverable": True}))
    steps.append(s(13, 13, "tool.call", {"tool": "lookup_order", "input": {"order_id": "ORD-002"}}))
    steps.append(s(14, 14, "tool.response", {"tool": "lookup_order", "output": {"amount": 50.00}}))
    steps.append(s(15, 15, "session.end", {"status": "completed", "total_steps": 16}))

    # Build prev_hash chain
    from epi_core.schemas import StepModel
    from epi_core.serialize import get_canonical_hash

    for i, st in enumerate(steps):
        if i == 0:
            st["prev_hash"] = "CHAIN_START"
        else:
            prev = StepModel(**steps[i - 1])
            st["prev_hash"] = get_canonical_hash(prev, format="json")

    return steps


def _build_policy():
    return {
        "policy_format_version": "2.0",
        "policy_id": "smoke-refund-policy",
        "system_name": "Refund Agent Smoke",
        "system_version": "1.0",
        "policy_version": "1.0.0",
        "rules": [
            {"id": "R001", "name": "No Exceed Balance", "severity": "critical",
             "type": "constraint_guard", "mode": "block",
             "watch_for": ["balance", "available_balance"],
             "violation_if": "refund_amount > watched_value"},
            {"id": "R002", "name": "Verify Identity First", "severity": "critical",
             "type": "sequence_guard", "mode": "block",
             "required_before": "approve_refund", "must_call": "verify_identity"},
            {"id": "R003", "name": "No Secrets In Output", "severity": "critical",
             "type": "prohibition_guard", "mode": "block",
             "prohibited_pattern": r"(sk-[A-Za-z0-9]+|api[_-]?key)"},
        ],
    }


def run_smoke():
    print("=== SCITT + AIUC-1 Smoke Test ===")

    pk = _build_key()

    # 1. Build steps and analysis
    steps = _build_steps()
    print(f"[1/7] Built {len(steps)} steps with agent trace, redaction, error handling")

    from epi_core.fault_analyzer import FaultAnalyzer
    analyzer = FaultAnalyzer()
    steps_jsonl = "\n".join(json.dumps(s) for s in steps)
    analysis_result = analyzer.analyze(steps_jsonl)
    print(f"[2/7] Fault analyzer ran: fault_detected={analysis_result.fault_detected}")

    # 2. Pack into .epi
    from epi_core.container import EPIContainer
    from epi_core.schemas import ManifestModel
    from epi_core.trust import sign_manifest

    with tempfile.TemporaryDirectory() as tmpdir:
        src = Path(tmpdir) / "source"
        src.mkdir()

        (src / "steps.jsonl").write_text(steps_jsonl, encoding="utf-8")
        (src / "analysis.json").write_text(analysis_result.to_json(), encoding="utf-8")
        (src / "policy.json").write_text(json.dumps(_build_policy(), indent=2), encoding="utf-8")
        (src / "environment.json").write_text(json.dumps({"python": "3.12"}), encoding="utf-8")

        manifest = ManifestModel(
            workflow_id=uuid4(),
            created_at=datetime.now(UTC).isoformat(),
            cli_command="python _test_scitt_aiuc1.py",
            file_manifest={
                "steps.jsonl": "placeholder",
                "analysis.json": "placeholder",
                "policy.json": "placeholder",
                "environment.json": "placeholder",
            },
            total_steps=len(steps),
            goal="SCITT + AIUC-1 smoke test",
        )
        signed = sign_manifest(manifest, pk, "default")
        (src / "manifest.json").write_text(signed.model_dump_json(indent=2), encoding="utf-8")

        out_dir = Path("epi-recordings")
        out_dir.mkdir(exist_ok=True)
        out_path = out_dir / "scitt_aiuc1_smoke.epi"

        EPIContainer.pack(
            source_dir=src,
            manifest=signed,
            output_path=out_path,
            container_format="legacy-zip",
            preserve_generated=True,
        )
        print(f"[3/7] Packed artifact: {out_path}")

    # 3. Add signed review
    from epi_core.review import ReviewRecord, add_review_to_artifact
    review = ReviewRecord(
        reviewed_by="qa@epilabs.org",
        reviews=[{"outcome": "approved", "notes": "Smoke test review — all checks pass"}],
    )
    add_review_to_artifact(out_path, review, private_key=pk)
    print("[4/7] Signed review added to artifact")

    # 4. SCITT registration with mock Merkle-tree service
    import sys
    sys.path.insert(0, r"C:\Users\dell\epi-recorder")
    from tests.helpers.mock_scitt_service import MockSCITTService

    final_manifest = EPIContainer.read_manifest(out_path)
    from epi_core.scitt import create_scitt_statement
    statement_bytes = create_scitt_statement(final_manifest, pk, issuer="smoke-test")

    mock_svc = MockSCITTService()
    receipt_bytes, info = mock_svc.register(statement_bytes)
    print(f"[5/7] Registered with SCITT service: entry_id={info.entry_id}")

    # 5. Verify receipt with inclusion proof
    from epi_core.scitt import verify_scitt_receipt
    proof = mock_svc.get_proof(info.entry_id)
    assert proof is not None, "Inclusion proof missing"
    assert mock_svc.verify_with_proof(receipt_bytes, statement_bytes, proof), "Inclusion proof verification failed"
    assert verify_scitt_receipt(receipt_bytes, statement_bytes, mock_svc.public_key_bytes)
    print(f"[6/7] SCITT receipt verified with Merkle inclusion proof (tree_index={proof['tree_index']})")

    # 6. AIUC-1 mapping
    from epi_core.aiuc1_mapping import map_verification_to_aiuc1, aiuc1_summary

    report = {
        "facts": {
            "signature_valid": True,
            "integrity_ok": True,
            "chain_ok": True,
            "sequence_ok": True,
            "completeness_ok": True,
        },
        "identity": {
            "status": "KNOWN",
            "scitt": {"entry_id": info.entry_id},
        },
    }

    statuses = map_verification_to_aiuc1(report, final_manifest, steps, epi_path=out_path)
    summary = aiuc1_summary(statuses)

    print(f"[7/7] AIUC-1 result: overall={summary['overall']}")
    for dom_id in "ABCDEF":
        s = statuses[dom_id]
        print(f"  Domain {dom_id} ({s.label}): {s.status}  evidence={s.evidence}  missing={s.missing}")

    failures = [dom_id for dom_id in "ABCDEF" if statuses[dom_id].status != "PASS"]
    if failures:
        print(f"\n[FAIL] Domains not passing: {failures}")
        raise SystemExit(1)

    print("\n[PASS] All 6 AIUC-1 domains PASS with substantive evidence")
    print(f"       Artifact: {out_path.resolve()}")
    print(f"       SCITT entry: {info.entry_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(run_smoke())
