from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from epi_core.container import EPIContainer, EPI_CONTAINER_FORMAT_LEGACY
from epi_core.schemas import ManifestModel
from epi_core.trust import sign_manifest


FIXED_TS = "2026-04-12T00:00:00Z"


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def make_decision_workspace(tmp_path: Path, *, prompt: str = "Approve refund REF-100?") -> Path:
    workspace = tmp_path / "decision_workspace"
    workspace.mkdir(parents=True, exist_ok=True)

    steps = [
        {
            "index": 0,
            "timestamp": FIXED_TS,
            "kind": "llm.request",
            "content": {
                "provider": "local-fake",
                "model": "offline-test-model",
                "messages": [{"role": "user", "content": prompt}],
            },
        },
        {
            "index": 1,
            "timestamp": "2026-04-12T00:00:01Z",
            "kind": "tool.call",
            "content": {"tool": "check_refund_policy", "input": {"amount": 900}},
        },
        {
            "index": 2,
            "timestamp": "2026-04-12T00:00:02Z",
            "kind": "policy.check",
            "content": {
                "rule_id": "HUMAN_REVIEW_HIGH_VALUE_REFUND",
                "allowed": False,
                "status": "failed",
            },
        },
        {
            "index": 3,
            "timestamp": "2026-04-12T00:00:03Z",
            "kind": "agent.approval.response",
            "content": {
                "reviewer": "qa@example.com",
                "approved": True,
                "action": "refund escalation",
                "reason": "High-value refund reviewed.",
            },
        },
        {
            "index": 4,
            "timestamp": "2026-04-12T00:00:04Z",
            "kind": "agent.decision",
            "content": {"decision": "escalate for human review"},
        },
    ]
    (workspace / "steps.jsonl").write_text(
        "\n".join(json.dumps(step, sort_keys=True) for step in steps) + "\n",
        encoding="utf-8",
    )

    _write_json(workspace / "environment.json", {"python": "test", "offline": True})
    _write_json(
        workspace / "analysis.json",
        {"summary": {"headline": "High-value refund requires human review"}, "review_required": True},
    )
    _write_json(
        workspace / "policy.json",
        {
            "policy_id": "refund-policy",
            "profile_id": "refunds",
            "rules": [{"id": "HUMAN_REVIEW_HIGH_VALUE_REFUND", "name": "Human review"}],
        },
    )
    _write_json(
        workspace / "policy_evaluation.json",
        {
            "policy_id": "refund-policy",
            "controls_evaluated": 1,
            "controls_failed": 1,
            "artifact_review_required": True,
            "results": [
                {
                    "rule_id": "HUMAN_REVIEW_HIGH_VALUE_REFUND",
                    "name": "High-value refund needs review",
                    "rule_type": "approval_guard",
                    "status": "failed",
                    "plain_english": "Refunds over the threshold must be reviewed.",
                }
            ],
        },
    )
    _write_json(
        workspace / "review.json",
        {
            "review_version": "1.0.0",
            "reviewed_by": "qa@example.com",
            "reviewed_at": "2026-04-12T00:05:00Z",
            "reviews": [
                {
                    "outcome": "dismissed",
                    "notes": "Human reviewer approved the escalation.",
                    "reviewer": "qa@example.com",
                    "timestamp": "2026-04-12T00:05:00Z",
                }
            ],
        },
    )
    return workspace


def make_decision_epi(
    tmp_path: Path,
    *,
    name: str = "decision.epi",
    signed: bool = True,
    private_key: Ed25519PrivateKey | None = None,
    prompt: str = "Approve refund REF-100?",
    container_format: str = EPI_CONTAINER_FORMAT_LEGACY,
) -> tuple[Path, Ed25519PrivateKey | None]:
    workspace = make_decision_workspace(tmp_path, prompt=prompt)
    output_path = tmp_path / name
    manifest = ManifestModel(
        cli_command="pytest helper",
        goal="Capture a high-value refund decision",
        notes="Offline deterministic test artifact",
        tags=["test", "offline"],
    )

    key = private_key or (Ed25519PrivateKey.generate() if signed else None)
    signer = (lambda item: sign_manifest(item, key, "test")) if key is not None else None
    EPIContainer.pack(
        workspace,
        manifest,
        output_path,
        signer_function=signer,
        preserve_generated=True,
        container_format=container_format,
        generate_analysis=False,
    )
    return output_path, key


def rewrite_legacy_member(epi_path: Path, member: str, payload: bytes) -> None:
    with zipfile.ZipFile(epi_path, "r") as archive:
        members = {name: archive.read(name) for name in archive.namelist()}
    members[member] = payload
    with zipfile.ZipFile(epi_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in members.items():
            compress_type = zipfile.ZIP_STORED if name == "mimetype" else zipfile.ZIP_DEFLATED
            archive.writestr(name, content, compress_type=compress_type)


def read_legacy_member_json(epi_path: Path, member: str) -> dict[str, Any]:
    with zipfile.ZipFile(epi_path, "r") as archive:
        payload = json.loads(archive.read(member).decode("utf-8"))
    assert isinstance(payload, dict)
    return payload
