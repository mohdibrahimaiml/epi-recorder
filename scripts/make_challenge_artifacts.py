#!/usr/bin/env python3
"""Build the "Break the seal" challenge artifacts reproducibly.

Writes into challenge/:
  challenge-original.epi        a refund decision with two approval requests,
                                sealed with the challenge signing key and
                                approved by the challenge approver key
  challenge-signing-key.pub     the sealing key (public only)
  challenge-approver-key.pub    the approver key (public only)

The PRIVATE keys are written to a fresh temp directory OUTSIDE the repo and
printed. Move them offline (or destroy them — they are not needed to run the
challenge; they are needed to re-issue artifacts). Nothing in challenge/ may
contain private key material; tests/test_challenge_artifacts.py enforces it.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from epi_core.container import EPIContainer
from epi_core.keys import key_fingerprint
from epi_core.review import ReviewRecord, add_review_to_artifact, make_approval_entry
from epi_core.schemas import ManifestModel
from epi_core.trust import sign_manifest

CHALLENGE = REPO / "challenge"


def _pub_hex(key: Ed25519PrivateKey) -> str:
    return key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    ).hex()


def _write_private(path: Path, key: Ed25519PrivateKey) -> None:
    path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )


def _steps() -> list[dict]:
    return [
        {"index": 0, "kind": "session.start", "content": {"workflow_name": "refund review"}},
        {"index": 1, "kind": "tool.call", "content": {"tool": "lookup_ledger", "id": "REF-7"}},
        {"index": 2, "kind": "tool.response", "content": {"tool": "lookup_ledger", "ok": True, "balance": 250}},
        {
            "index": 3,
            "kind": "agent.approval.request",
            "content": {"action": "refund REF-7", "approval_id": "refund-7", "reason": "high-value refund"},
        },
        {
            "index": 4,
            "kind": "agent.approval.request",
            "content": {"action": "refund REF-8", "approval_id": "refund-8", "reason": "high-value refund"},
        },
        {"index": 5, "kind": "agent.decision", "content": {"decision": "approve", "reason": "within limit"}},
        {"index": 6, "kind": "session.end", "content": {"success": True}},
    ]


def build(out_dir: Path | None = None) -> dict:
    """Generate everything. Returns the fingerprints and the private-key location."""
    CHALLENGE.mkdir(parents=True, exist_ok=True)
    private_dir = Path(
        out_dir or tempfile.mkdtemp(prefix="epi-challenge-keys-", dir=tempfile.gettempdir())
    )
    signing = Ed25519PrivateKey.generate()
    approver = Ed25519PrivateKey.generate()
    _write_private(private_dir / "challenge-signing-key.key", signing)
    _write_private(private_dir / "challenge-approver-key.key", approver)

    source = private_dir / "artifact-src"
    source.mkdir(parents=True, exist_ok=True)
    (source / "steps.jsonl").write_text(
        "\n".join(json.dumps(step, sort_keys=True) for step in _steps()) + "\n",
        encoding="utf-8",
    )
    artifact = CHALLENGE / "challenge-original.epi"
    EPIContainer.pack(
        source,
        ManifestModel(
            workflow_id=uuid4(),
            created_at=datetime.now(UTC),
            cli_command="scripts/make_challenge_artifacts.py",
            goal="Refund decision with two human approvals (challenge artifact)",
        ),
        artifact,
        signer_function=lambda manifest: sign_manifest(manifest, signing, "challenge-sealing-key"),
        preserve_generated=True,
        generate_analysis=False,
    )

    for approval_id, action in (("refund-7", "refund REF-7"), ("refund-8", "refund REF-8")):
        entry = make_approval_entry(
            approval_id=approval_id,
            decision="approve",
            action=action,
            reason="checked against the ledger",
            approver_name="challenge-approver",
            key_fingerprint_hex=key_fingerprint(_pub_hex(approver), grouped=False),
        )
        record = ReviewRecord(
            reviewed_by="challenge-approver",
            reviews=[entry],
            reviewer_identity={
                "type": "name",
                "value": "challenge-approver",
                "role": "Approver",
                "org": "EPI",
                "verified": False,
            },
        )
        add_review_to_artifact(artifact, record, private_key=approver)

    (CHALLENGE / "challenge-signing-key.pub").write_text(_pub_hex(signing) + "\n", encoding="utf-8")
    (CHALLENGE / "challenge-approver-key.pub").write_text(_pub_hex(approver) + "\n", encoding="utf-8")

    return {
        "artifact": artifact,
        "private_dir": private_dir,
        "signing_fingerprint": key_fingerprint(_pub_hex(signing)),
        "approver_fingerprint": key_fingerprint(_pub_hex(approver)),
    }


def main() -> int:
    os.environ.setdefault("EPI_NOTARIZE", "0")
    result = build()
    print(f"Wrote {result['artifact']}")
    print(f"  signing key fingerprint : {result['signing_fingerprint']}")
    print(f"  approver key fingerprint: {result['approver_fingerprint']}")
    print()
    print(f"PRIVATE keys are in {result['private_dir']}")
    print("MOVE THEM OFFLINE (or destroy them) — they must never be committed.")
    print("Without them nobody can re-issue the artifacts, which is the point.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
