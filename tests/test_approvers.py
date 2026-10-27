"""Human-signed approvals (step 3a): registry, classification, verification.

These tests pin the two properties that matter most:

* a 1.2.0 approval must not look like tampering to an older (4.6.x) reader —
  the approval rides inside `reviews`, so the old content hash is unchanged;
* nothing is `human_signed` unless the key is pinned as an approver AND differs
  from the sealing key.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import zipfile
from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
import typer
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from typer.testing import CliRunner

from epi_cli.review import app as review_app
from epi_cli.verify import verify_command
from epi_core.approvers import ApproverRegistry, reserved_key_reason
from epi_core.container import EPIContainer
from epi_core.keys import KeyManager, key_fingerprint
from epi_core.review import (
    APPROVAL_ENTRY_TYPE,
    ReviewRecord,
    add_review_to_artifact,
    canonical_review_json,
    make_approval_entry,
    read_review_records,
    verify_human_approvals,
    verify_review_trust,
)
from epi_core.schemas import ManifestModel
from epi_core.time_utils import utc_now
from epi_core.trust import sign_manifest, verify_embedded_manifest_signature

runner = CliRunner()


@pytest.fixture(autouse=True)
def _isolate_epi_dirs(tmp_path, monkeypatch):
    """Never read the developer's real approver registry or agent keys."""
    monkeypatch.setenv("EPI_TRUSTED_APPROVERS_DIR", str(tmp_path / "trusted_approvers"))
    monkeypatch.setenv("EPI_APPROVER_KEYS_DIR", str(tmp_path / "approver_keys"))
    monkeypatch.setenv("EPI_NOTARIZE", "0")
    monkeypatch.delenv("EPI_KEYS_DIR", raising=False)


# ---------------------------------------------------------------------------
# Frozen 4.6.x reader — what an already-deployed verifier does with our record
# ---------------------------------------------------------------------------

_OLD_V11_FIELDS = (
    "review_id",
    "review_version",
    "reviewer_identity",
    "reviewed_by",
    "reviewed_at",
    "reviews",
    "artifact_binding",
    "previous_review_hash",
    "review_hash",
    "review_signature",
)


def _old_from_dict(data: dict) -> dict:
    """epi-recorder 4.6.x ReviewRecord.from_dict — silently drops unknown keys."""
    return {
        "reviewed_by": str(data.get("reviewed_by") or "reviewer"),
        "reviews": list(data.get("reviews") or []),
        "reviewed_at": data.get("reviewed_at"),
        "review_version": str(data.get("review_version") or "1.0.0"),
        "review_id": data.get("review_id"),
        "reviewer_identity": data.get("reviewer_identity"),
        "artifact_binding": data.get("artifact_binding"),
        "previous_review_hash": data.get("previous_review_hash"),
        "review_hash": data.get("review_hash"),
        "review_signature": data.get("review_signature"),
        "case_level_review": bool(data.get("case_level_review")),
        "certification_level": "audit",  # 4.6.x never reads the stored value
    }


def _old_to_dict(record: dict) -> dict:
    payload = {field: record.get(field) for field in _OLD_V11_FIELDS}
    if record.get("case_level_review"):
        payload["case_level_review"] = True
    payload["certification_level"] = record.get("certification_level", "audit")
    return payload


def _old_content_hash(record: dict) -> str:
    payload = _old_to_dict(record)
    payload.pop("review_hash", None)
    payload.pop("review_signature", None)
    return hashlib.sha256(canonical_review_json(payload).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _pub_hex(private_key) -> str:
    return private_key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    ).hex()


def _save_key(keys_dir: Path, name: str, private_key: Ed25519PrivateKey) -> None:
    manager = KeyManager(keys_dir=keys_dir)
    manager._key_file_path(name, ".key").write_bytes(
        private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    manager._key_file_path(name, ".pub").write_bytes(
        private_key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        )
    )


def _pin(tmp_path: Path, name: str, private_key) -> str:
    directory = tmp_path / "trusted_approvers"
    ApproverRegistry(directory).add(name, _pub_hex(private_key))
    return str(directory)


def _sealed_epi(
    tmp_path: Path, *, requests=(), name="case.epi"
) -> tuple[Path, Ed25519PrivateKey]:
    """A sealed artifact with a known sealing key and optional approval requests."""
    source = tmp_path / f"{name}.src"
    source.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps({"index": 0, "kind": "agent.decision", "content": {"result": "approved"}})]
    for offset, (approval_id, action) in enumerate(requests, start=1):
        lines.append(
            json.dumps(
                {
                    "index": offset,
                    "kind": "agent.approval.request",
                    "content": {"action": action, "approval_id": approval_id},
                }
            )
        )
    (source / "steps.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")

    sealing_key = Ed25519PrivateKey.generate()
    epi_path = tmp_path / name
    EPIContainer.pack(
        source,
        ManifestModel(workflow_id=uuid4(), created_at=utc_now(), cli_command="pytest"),
        epi_path,
        signer_function=lambda manifest: sign_manifest(manifest, sealing_key, "test"),
        preserve_generated=True,
        generate_analysis=False,
    )
    return epi_path, sealing_key


def _approval_record(
    *,
    signing_key,
    approval_id: str | None = "refund-7",
    decision: str = "approve",
    action: str = "refund REF-7",
    name: str = "alice@bank.com",
    fingerprint: str | None = None,
    case_level: bool = False,
) -> ReviewRecord:
    return ReviewRecord(
        reviewed_by=name,
        reviews=[
            make_approval_entry(
                approval_id=approval_id,
                decision=decision,
                action=action,
                reason="checked against ledger",
                approver_name=name,
                key_fingerprint_hex=(
                    fingerprint
                    if fingerprint is not None
                    else key_fingerprint(_pub_hex(signing_key), grouped=False)
                ),
                case_level=case_level,
            )
        ],
        reviewer_identity={
            "type": "email",
            "value": name,
            "role": "Approver",
            "org": "Unknown",
            "verified": False,
        },
    )


def _classifications(state: dict) -> list[str]:
    return [item["classification"] for item in state["approvals"]]


# ---------------------------------------------------------------------------
# BLOCKING: old readers must not see a false tamper alarm
# ---------------------------------------------------------------------------


def test_old_reader_hash_is_stable_for_1_2_0_approval(tmp_path):
    epi_path, _ = _sealed_epi(tmp_path, requests=[("refund-7", "refund REF-7")])
    approver = Ed25519PrivateKey.generate()
    _pin(tmp_path, "alice@bank.com", approver)

    record = _approval_record(signing_key=approver)
    add_review_to_artifact(epi_path, record, private_key=approver)

    stored = read_review_records(epi_path)[0]
    assert stored.review_version == "1.2.0"
    assert "approval" not in stored.to_dict()  # no top-level approval field
    assert stored.reviewer_identity["verified"] is False

    old_hash = _old_content_hash(dict(stored.to_dict()))
    assert old_hash == stored.review_hash == stored.content_hash()

    parts = stored.review_signature.split(":")
    Ed25519PublicKey.from_public_bytes(bytes.fromhex(parts[1])).verify(
        bytes.fromhex(parts[2]), bytes.fromhex(old_hash)
    )


def test_approval_never_adds_a_top_level_field(tmp_path):
    epi_path, _ = _sealed_epi(tmp_path, requests=[("refund-7", "refund REF-7")])
    approver = Ed25519PrivateKey.generate()
    add_review_to_artifact(epi_path, _approval_record(signing_key=approver), private_key=approver)
    payload = dict(read_review_records(epi_path)[0].to_dict())
    assert "approval" not in payload
    assert payload["reviews"][0]["entry_type"] == APPROVAL_ENTRY_TYPE
    assert payload["certification_level"] == "audit"


def test_sealed_evidence_unchanged_by_an_approval(tmp_path):
    epi_path, _ = _sealed_epi(tmp_path, requests=[("refund-7", "refund REF-7")])
    before = EPIContainer.read_manifest(epi_path).model_dump()
    approver = Ed25519PrivateKey.generate()
    add_review_to_artifact(epi_path, _approval_record(signing_key=approver), private_key=approver)
    after = EPIContainer.read_manifest(epi_path).model_dump()
    assert before == after
    ok, _, message = verify_embedded_manifest_signature(EPIContainer.read_manifest(epi_path))
    assert ok is True, message


# ---------------------------------------------------------------------------
# Classification shortcut matrix
# ---------------------------------------------------------------------------


def test_signed_by_a_pinned_approver_is_human_signed(tmp_path):
    epi_path, _ = _sealed_epi(tmp_path, requests=[("refund-7", "refund REF-7")])
    approver = Ed25519PrivateKey.generate()
    _pin(tmp_path, "alice@bank.com", approver)
    add_review_to_artifact(epi_path, _approval_record(signing_key=approver), private_key=approver)

    state = verify_human_approvals(epi_path)
    assert state["status"] == "verified"
    assert state["requirement_met"] is True
    assert _classifications(state) == ["human_signed"]
    assert state["approvals"][0]["approver_name"] == "alice@bank.com"
    assert state["approvals"][0]["approval_id_present"] is True


def test_unpinned_key_is_signed_unknown_key(tmp_path):
    epi_path, _ = _sealed_epi(tmp_path, requests=[("refund-7", "refund REF-7")])
    approver = Ed25519PrivateKey.generate()
    add_review_to_artifact(epi_path, _approval_record(signing_key=approver), private_key=approver)

    state = verify_human_approvals(epi_path)
    assert state["status"] == "unverified"
    assert state["requirement_met"] is False
    assert _classifications(state) == ["signed_unknown_key"]


def test_pinned_signer_is_not_an_approver(tmp_path, monkeypatch):
    epi_path, _ = _sealed_epi(tmp_path, requests=[("refund-7", "refund REF-7")])
    vendor = Ed25519PrivateKey.generate()
    trusted_keys = tmp_path / "trusted_keys"
    trusted_keys.mkdir()
    vendor_pub = tmp_path / "vendor.pub"
    vendor_pub.write_text(_pub_hex(vendor), encoding="utf-8")
    KeyManager().trust_key(vendor_pub, trusted_keys_dir=trusted_keys, trusted_name="vendor")
    monkeypatch.setenv("EPI_TRUSTED_KEYS_DIR", str(trusted_keys))

    add_review_to_artifact(epi_path, _approval_record(signing_key=vendor), private_key=vendor)
    state = verify_human_approvals(epi_path)
    assert state["status"] == "unverified"
    assert _classifications(state) == ["signed_unknown_key"]


def test_sealing_key_signed_approval_is_not_independent(tmp_path):
    epi_path, sealing_key = _sealed_epi(tmp_path, requests=[("refund-7", "refund REF-7")])
    # The sealing key is also pinned as an approver: the sealing-key rule wins.
    _pin(tmp_path, "the-agent", sealing_key)
    add_review_to_artifact(
        epi_path,
        _approval_record(signing_key=sealing_key, name="the-agent"),
        private_key=sealing_key,
    )
    state = verify_human_approvals(epi_path)
    assert _classifications(state) == ["signed_by_sealing_key"]
    assert state["status"] == "unverified"


def test_tampered_approval_is_invalid(tmp_path):
    epi_path, _ = _sealed_epi(tmp_path, requests=[("refund-7", "refund REF-7")])
    approver = Ed25519PrivateKey.generate()
    _pin(tmp_path, "alice@bank.com", approver)
    add_review_to_artifact(epi_path, _approval_record(signing_key=approver), private_key=approver)

    member = _ledger_member(epi_path)
    payload = EPIContainer.read_member_json(epi_path, member)
    payload["reviews"][0]["decision"] = "deny"
    _replace_members(epi_path, {member: json.dumps(payload)})

    state = verify_human_approvals(epi_path)
    assert state["status"] == "failed"
    assert "review_hash" in state["detail"]


def test_fingerprint_claim_mismatch_is_invalid(tmp_path):
    epi_path, _ = _sealed_epi(tmp_path, requests=[("refund-7", "refund REF-7")])
    approver = Ed25519PrivateKey.generate()
    other = Ed25519PrivateKey.generate()
    _pin(tmp_path, "alice@bank.com", approver)
    add_review_to_artifact(
        epi_path,
        _approval_record(
            signing_key=approver, fingerprint=key_fingerprint(_pub_hex(other), grouped=False)
        ),
        private_key=approver,
    )
    state = verify_human_approvals(epi_path)
    assert state["status"] == "failed"
    assert "key_fingerprint" in state["detail"]


def test_unsigned_approval_is_unsigned(tmp_path):
    epi_path, _ = _sealed_epi(tmp_path, requests=[("refund-7", "refund REF-7")])
    approver = Ed25519PrivateKey.generate()
    _pin(tmp_path, "alice@bank.com", approver)
    add_review_to_artifact(epi_path, _approval_record(signing_key=approver))  # no private key
    assert _classifications(verify_human_approvals(epi_path)) == ["unsigned"]


def test_approval_copied_to_another_file_is_invalid(tmp_path):
    source, _ = _sealed_epi(tmp_path, requests=[("refund-7", "refund REF-7")], name="source.epi")
    target, _ = _sealed_epi(tmp_path, requests=[("refund-7", "refund REF-7")], name="target.epi")
    approver = Ed25519PrivateKey.generate()
    _pin(tmp_path, "alice@bank.com", approver)
    add_review_to_artifact(source, _approval_record(signing_key=approver), private_key=approver)
    _copy_review_members(source, target)
    state = verify_human_approvals(target)
    assert state["status"] == "failed"
    assert "binding" in state["detail"]


def test_broken_chain_makes_the_approval_invalid(tmp_path):
    epi_path, _ = _sealed_epi(tmp_path, requests=[("refund-7", "refund REF-7")])
    approver = Ed25519PrivateKey.generate()
    _pin(tmp_path, "alice@bank.com", approver)
    add_review_to_artifact(epi_path, _approval_record(signing_key=approver), private_key=approver)
    add_review_to_artifact(
        epi_path, _approval_record(signing_key=approver, decision="deny"), private_key=approver
    )
    member = _ledger_member(epi_path)
    payload = EPIContainer.read_member_json(epi_path, member)
    payload["previous_review_hash"] = "0" * 64
    _replace_members(epi_path, {member: json.dumps(payload)})

    state = verify_human_approvals(epi_path)
    assert state["status"] == "failed"
    assert "chain" in state["detail"].lower()


def test_approver_name_comes_from_the_verifiers_registry(tmp_path):
    epi_path, _ = _sealed_epi(tmp_path, requests=[("refund-7", "refund REF-7")])
    approver = Ed25519PrivateKey.generate()
    _pin(tmp_path, "alice@bank.com", approver)
    # The record claims to be the CEO; the verifier's registry says otherwise.
    add_review_to_artifact(
        epi_path,
        _approval_record(signing_key=approver, name="ceo@bank.com"),
        private_key=approver,
    )
    state = verify_human_approvals(epi_path)
    assert state["status"] == "verified"
    assert state["approvals"][0]["approver_name"] == "alice@bank.com"
    assert state["approvals"][0]["claimed_approver_name"] == "ceo@bank.com"
    assert state["warnings"]


# ---------------------------------------------------------------------------
# --require-human-approval: per request, not "latest decision overall"
# ---------------------------------------------------------------------------


def test_require_human_approval_is_per_request(tmp_path):
    epi_path, _ = _sealed_epi(
        tmp_path, requests=[("refund-7", "refund REF-7"), ("refund-8", "refund REF-8")]
    )
    approver = Ed25519PrivateKey.generate()
    _pin(tmp_path, "alice@bank.com", approver)

    add_review_to_artifact(
        epi_path,
        _approval_record(signing_key=approver, approval_id="refund-7"),
        private_key=approver,
    )
    state = verify_human_approvals(epi_path)
    assert [item["status"] for item in state["requests"]] == ["approved", "missing"]
    assert state["requirement_met"] is False
    with pytest.raises(typer.Exit):
        verify_command(ctx=MagicMock(), epi_file=epi_path, require_human_approval=True)

    add_review_to_artifact(
        epi_path,
        _approval_record(signing_key=approver, approval_id="refund-8"),
        private_key=approver,
    )
    state = verify_human_approvals(epi_path)
    assert [item["status"] for item in state["requests"]] == ["approved", "approved"]
    assert state["requirement_met"] is True
    verify_command(ctx=MagicMock(), epi_file=epi_path, require_human_approval=True)


def test_deny_on_a_request_fails_the_requirement(tmp_path):
    epi_path, _ = _sealed_epi(tmp_path, requests=[("refund-7", "refund REF-7")])
    approver = Ed25519PrivateKey.generate()
    _pin(tmp_path, "alice@bank.com", approver)
    add_review_to_artifact(
        epi_path,
        _approval_record(signing_key=approver, decision="deny"),
        private_key=approver,
    )
    state = verify_human_approvals(epi_path)
    assert state["status"] == "verified"  # a person really signed it
    assert state["requirement_met"] is False
    with pytest.raises(typer.Exit):
        verify_command(ctx=MagicMock(), epi_file=epi_path, require_human_approval=True)


def test_case_level_approval_satisfies_a_run_with_requests(tmp_path):
    epi_path, _ = _sealed_epi(tmp_path, requests=[("refund-7", "refund REF-7")])
    approver = Ed25519PrivateKey.generate()
    _pin(tmp_path, "alice@bank.com", approver)
    add_review_to_artifact(
        epi_path,
        _approval_record(signing_key=approver, approval_id=None, case_level=True, action=""),
        private_key=approver,
    )
    assert verify_human_approvals(epi_path)["requirement_met"] is True
    verify_command(ctx=MagicMock(), epi_file=epi_path, require_human_approval=True)


def test_no_requests_and_no_approval_fails_the_requirement(tmp_path):
    epi_path, _ = _sealed_epi(tmp_path)
    state = verify_human_approvals(epi_path)
    assert state["status"] == "none"
    assert state["requirement_met"] is False
    with pytest.raises(typer.Exit):
        verify_command(ctx=MagicMock(), epi_file=epi_path, require_human_approval=True)


def test_agent_reported_only_is_never_verified(tmp_path):
    epi_path, _ = _sealed_epi(tmp_path, requests=[("refund-7", "refund REF-7")])
    _append_step(
        epi_path,
        {
            "index": 99,
            "kind": "agent.approval.response",
            "content": {"action": "refund REF-7", "approved": True, "reviewer": "ceo@bank.com"},
        },
    )
    state = verify_human_approvals(epi_path)
    assert state["status"] == "none"
    assert state["agent_reported_approvals"] == 1
    assert "agent" in state["detail"]


def test_approval_id_not_a_sealed_request_does_not_satisfy(tmp_path):
    epi_path, _ = _sealed_epi(tmp_path, requests=[("refund-7", "refund REF-7")])
    approver = Ed25519PrivateKey.generate()
    _pin(tmp_path, "alice@bank.com", approver)
    add_review_to_artifact(
        epi_path,
        _approval_record(signing_key=approver, approval_id="not-a-request"),
        private_key=approver,
    )
    state = verify_human_approvals(epi_path)
    assert state["approvals"][0]["approval_id_present"] is False
    assert state["requirement_met"] is False


def test_verify_is_silent_for_a_run_with_no_approvals(tmp_path, capsys):
    epi_path, _ = _sealed_epi(tmp_path)
    verify_command(ctx=MagicMock(), epi_file=epi_path)
    assert "Human approval" not in capsys.readouterr().out


def test_verify_prints_the_approvers_own_clock(tmp_path, capsys):
    epi_path, _ = _sealed_epi(tmp_path, requests=[("refund-7", "refund REF-7")])
    approver = Ed25519PrivateKey.generate()
    _pin(tmp_path, "alice@bank.com", approver)
    add_review_to_artifact(epi_path, _approval_record(signing_key=approver), private_key=approver)
    verify_command(ctx=MagicMock(), epi_file=epi_path)
    out = capsys.readouterr().out
    assert "Human approval: VERIFIED" in out
    assert "approver's clock" in out
    assert "refund REF-7" in out


# ---------------------------------------------------------------------------
# Approver registry + `epi approvers add` refuses reserved keys (item 7)
# ---------------------------------------------------------------------------


def test_registry_add_list_remove(tmp_path):
    registry = ApproverRegistry(tmp_path / "approvers")
    key = Ed25519PrivateKey.generate()
    registry.add("alice@bank.com", _pub_hex(key), roles=["approver"])
    entries = registry.list()
    assert [entry["name"] for entry in entries] == ["alice@bank.com"]
    assert entries[0]["key_fingerprint"] == key_fingerprint(_pub_hex(key), grouped=False)
    assert registry.get_by_key(_pub_hex(key))["name"] == "alice@bank.com"
    assert registry.remove("alice@bank.com") is True
    assert registry.list() == []


def test_registry_refuses_name_collision_with_a_different_key(tmp_path):
    registry = ApproverRegistry(tmp_path / "approvers")
    registry.add("alice@bank.com", _pub_hex(Ed25519PrivateKey.generate()))
    with pytest.raises(FileExistsError):
        registry.add("alice@bank.com", _pub_hex(Ed25519PrivateKey.generate()))


def test_registry_refuses_a_name_that_is_not_a_file_stem(tmp_path):
    registry = ApproverRegistry(tmp_path / "approvers")
    with pytest.raises(ValueError):
        registry.add("..", _pub_hex(Ed25519PrivateKey.generate()))


def test_reserved_key_reason_flags_agent_and_pinned_signer(tmp_path, monkeypatch):
    agent_dir = tmp_path / "agent_keys"
    monkeypatch.setenv("EPI_KEYS_DIR", str(agent_dir))
    agent_key = Ed25519PrivateKey.generate()
    _save_key(agent_dir, "default", agent_key)
    assert reserved_key_reason(_pub_hex(agent_key)) is not None

    trusted = tmp_path / "trusted_keys"
    trusted.mkdir()
    monkeypatch.setenv("EPI_TRUSTED_KEYS_DIR", str(trusted))
    vendor = Ed25519PrivateKey.generate()
    (trusted / "vendor.pub").write_text(_pub_hex(vendor), encoding="utf-8")
    assert reserved_key_reason(_pub_hex(vendor)) is not None

    assert reserved_key_reason(_pub_hex(Ed25519PrivateKey.generate())) is None


def test_approvers_add_refuses_a_reserved_key(tmp_path, monkeypatch):
    monkeypatch.setenv("EPI_TRUSTED_APPROVERS_DIR", str(tmp_path / "target_approvers"))
    agent_dir = tmp_path / "agent_keys"
    monkeypatch.setenv("EPI_KEYS_DIR", str(agent_dir))
    agent_key = Ed25519PrivateKey.generate()
    _save_key(agent_dir, "default", agent_key)
    pub_file = tmp_path / "agent.pub"
    pub_file.write_text(_pub_hex(agent_key), encoding="utf-8")

    from epi_cli.approvers import app as approvers_app

    agent_fp = key_fingerprint(_pub_hex(agent_key))
    result = runner.invoke(
        approvers_app,
        ["add", str(pub_file), "--name", "the-agent", "--fingerprint", agent_fp],
    )
    assert result.exit_code == 1
    assert "Refusing" in result.output
    assert ApproverRegistry(tmp_path / "target_approvers").list() == []

    forced = runner.invoke(
        approvers_app,
        [
            "add", str(pub_file), "--name", "the-agent",
            "--fingerprint", agent_fp, "--force",
        ],
    )
    assert forced.exit_code == 0
    assert len(ApproverRegistry(tmp_path / "target_approvers").list()) == 1


def test_approvers_add_requires_a_matching_fingerprint(tmp_path, monkeypatch):
    monkeypatch.setenv("EPI_TRUSTED_APPROVERS_DIR", str(tmp_path / "target_approvers"))
    key = Ed25519PrivateKey.generate()
    pub_file = tmp_path / "alice.pub"
    pub_file.write_text(_pub_hex(key), encoding="utf-8")

    from epi_cli.approvers import app as approvers_app

    refused = runner.invoke(
        approvers_app,
        ["add", str(pub_file), "--name", "alice@bank.com", "--fingerprint", "deadbeef"],
    )
    assert refused.exit_code == 1
    assert ApproverRegistry(tmp_path / "target_approvers").list() == []

    accepted = runner.invoke(
        approvers_app,
        [
            "add", str(pub_file), "--name", "alice@bank.com",
            "--fingerprint", key_fingerprint(_pub_hex(key)),
        ],
    )
    assert accepted.exit_code == 0, accepted.output


# ---------------------------------------------------------------------------
# Browser-shaped records (epi_viewer_static/crypto.js epiBuildSignedReviewRecord)
# ---------------------------------------------------------------------------


def _browser_review(approver, *, with_approval: bool) -> ReviewRecord:
    if with_approval:
        entries = [
            make_approval_entry(
                approval_id="refund-7",
                decision="approve",
                action="refund REF-7",
                reason="ok",
                approver_name="browser",
                key_fingerprint_hex=key_fingerprint(_pub_hex(approver), grouped=False),
            )
        ]
    else:
        entries = [
            {
                "fault_step": None,
                "rule_id": None,
                "fault_type": None,
                "outcome": "dismissed",
                "notes": "browser review",
                "reviewer": "browser",
                "timestamp": utc_now().isoformat(),
            }
        ]
    return ReviewRecord(
        reviewed_by="browser",
        reviews=entries,
        review_version="1.1.0",  # crypto.js EPI_REVIEW_VERSION
        case_level_review=True,
    )


def test_browser_review_record_is_not_an_approval(tmp_path):
    epi_path, _ = _sealed_epi(tmp_path, requests=[("refund-7", "refund REF-7")])
    browser_key = Ed25519PrivateKey.generate()
    add_review_to_artifact(
        epi_path, _browser_review(browser_key, with_approval=False), private_key=browser_key
    )
    assert verify_human_approvals(epi_path)["status"] == "none"


def test_browser_approval_counts_only_when_pinned_and_not_the_sealer(tmp_path):
    epi_path, _ = _sealed_epi(tmp_path, requests=[("refund-7", "refund REF-7")])
    browser_key = Ed25519PrivateKey.generate()
    add_review_to_artifact(
        epi_path, _browser_review(browser_key, with_approval=True), private_key=browser_key
    )
    assert _classifications(verify_human_approvals(epi_path)) == ["signed_unknown_key"]

    _pin(tmp_path, "browser", browser_key)
    assert _classifications(verify_human_approvals(epi_path)) == ["human_signed"]

    sealing_epi, sealing_key = _sealed_epi(
        tmp_path, requests=[("refund-7", "refund REF-7")], name="sealed.epi"
    )
    _pin(tmp_path, "sealer", sealing_key)
    add_review_to_artifact(
        sealing_epi, _browser_review(sealing_key, with_approval=True), private_key=sealing_key
    )
    assert _classifications(verify_human_approvals(sealing_epi)) == ["signed_by_sealing_key"]


# ---------------------------------------------------------------------------
# `epi review approve` end to end
# ---------------------------------------------------------------------------


def _approver_env(tmp_path, monkeypatch, name="alice@bank.com", *, private_key=None):
    keys_dir = tmp_path / "approver_keys"
    monkeypatch.setenv("EPI_APPROVER_KEYS_DIR", str(keys_dir))
    key = private_key or Ed25519PrivateKey.generate()
    _save_key(keys_dir, name, key)
    monkeypatch.setenv("EPI_TRUSTED_APPROVERS_DIR", _pin(tmp_path, name, key))
    return key


def test_review_approve_end_to_end(tmp_path, monkeypatch):
    epi_path, _ = _sealed_epi(tmp_path, requests=[("refund-7", "refund REF-7")])
    _approver_env(tmp_path, monkeypatch)
    manifest_before = EPIContainer.read_manifest(epi_path).model_dump()

    result = runner.invoke(
        review_app,
        [
            str(epi_path), "approve",
            "--approval-id", "refund-7",
            "--decision", "approve",
            "--as", "alice@bank.com",
            "--yes",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "Signed approval written" in result.output

    state = verify_human_approvals(epi_path)
    assert state["status"] == "verified"
    assert state["requirement_met"] is True
    assert state["approvals"][0]["approval_id_present"] is True

    assert EPIContainer.read_manifest(epi_path).model_dump() == manifest_before
    ok, _, message = verify_embedded_manifest_signature(EPIContainer.read_manifest(epi_path))
    assert ok is True, message


def test_review_approve_refuses_unknown_approval_id(tmp_path, monkeypatch):
    epi_path, _ = _sealed_epi(tmp_path, requests=[("refund-7", "refund REF-7")])
    _approver_env(tmp_path, monkeypatch)
    result = runner.invoke(
        review_app,
        [str(epi_path), "approve", "--approval-id", "nope", "--as", "alice@bank.com", "--yes"],
    )
    assert result.exit_code == 1
    assert "No agent.approval.request" in result.output


def test_review_approve_refuses_self_approval(tmp_path, monkeypatch):
    epi_path, sealing_key = _sealed_epi(tmp_path, requests=[("refund-7", "refund REF-7")])
    _approver_env(tmp_path, monkeypatch, "the-agent", private_key=sealing_key)
    result = runner.invoke(
        review_app,
        [str(epi_path), "approve", "--approval-id", "refund-7", "--as", "the-agent", "--yes"],
    )
    assert result.exit_code == 1
    assert "separation of duties" in result.output


def test_review_approve_refuses_bad_decision(tmp_path, monkeypatch):
    epi_path, _ = _sealed_epi(tmp_path, requests=[("refund-7", "refund REF-7")])
    _approver_env(tmp_path, monkeypatch)
    result = runner.invoke(
        review_app,
        [str(epi_path), "approve", "--approval-id", "refund-7", "--decision", "maybe", "--as",
         "alice@bank.com", "--yes"],
    )
    assert result.exit_code == 1
    assert "approve or deny" in result.output


def test_review_approve_writes_a_claim_not_a_verdict(tmp_path, monkeypatch):
    epi_path, _ = _sealed_epi(tmp_path, requests=[("refund-7", "refund REF-7")])
    _approver_env(tmp_path, monkeypatch)
    runner.invoke(
        review_app,
        [str(epi_path), "approve", "--approval-id", "refund-7", "--as", "alice@bank.com", "--yes"],
    )
    identity = read_review_records(epi_path)[0].reviewer_identity
    assert identity["verified"] is False
    assert identity["role"] == "Approver"


def test_bind_does_not_copy_an_approval_into_an_agent_signed_record(tmp_path, monkeypatch):
    """`epi review bind` re-signs with the agent key; it must not carry an approval."""
    epi_path, sealing_key = _sealed_epi(tmp_path, requests=[("refund-7", "refund REF-7")])
    approver = Ed25519PrivateKey.generate()
    _pin(tmp_path, "alice@bank.com", approver)
    add_review_to_artifact(epi_path, _approval_record(signing_key=approver), private_key=approver)

    agent_dir = tmp_path / "agent_keys"
    monkeypatch.setenv("EPI_KEYS_DIR", str(agent_dir))
    _save_key(agent_dir, "default", sealing_key)

    result = runner.invoke(
        review_app,
        [str(epi_path), "bind", "--reviewer", "qa@example.com", "--key", "default"],
    )
    assert result.exit_code == 0, result.output
    assert "Nothing to bind" in result.output

    # The approval is untouched and the file is not poisoned into FAILED.
    state = verify_human_approvals(epi_path)
    assert state["status"] == "verified"
    assert _classifications(state) == ["human_signed"]


def test_plain_fault_review_never_reports_human_approval(tmp_path):
    epi_path, sealing_key = _sealed_epi(tmp_path, requests=[("refund-7", "refund REF-7")])
    _pin(tmp_path, "sealer", sealing_key)
    record = ReviewRecord(
        reviewed_by="qa@example.com",
        reviews=[{"outcome": "dismissed", "notes": "fault review", "reviewer": "qa@example.com"}],
    )
    add_review_to_artifact(epi_path, record, private_key=sealing_key)
    assert verify_review_trust(epi_path)["human_approval"]["status"] == "none"


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def _ledger_member(epi_path: Path) -> str:
    names = sorted(
        name for name in EPIContainer.list_members(epi_path)
        if name.startswith("reviews/") and name.endswith(".json")
    )
    assert names
    return names[-1]


def _replace_members(epi_path: Path, replacements: dict[str, str | bytes]) -> None:
    container_format = EPIContainer.detect_container_format(epi_path)
    temp_dir = EPIContainer._make_temp_dir("test_approvers_")
    payload_path = temp_dir / "payload.zip"
    next_payload = temp_dir / "next.zip"
    try:
        EPIContainer.extract_inner_payload(epi_path, payload_path)
        with zipfile.ZipFile(payload_path, "r") as src, zipfile.ZipFile(next_payload, "w") as dst:
            for item in src.infolist():
                if item.filename in replacements:
                    continue
                dst.writestr(item, src.read(item.filename))
            for name, value in replacements.items():
                data = value.encode("utf-8") if isinstance(value, str) else value
                dst.writestr(name, data)
        EPIContainer.write_from_payload(next_payload, epi_path, container_format=container_format)
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def _copy_review_members(source: Path, dest: Path) -> None:
    replacements: dict[str, bytes] = {}
    for name in EPIContainer.list_members(source):
        if name in ("review.json", "review_index.json") or name.startswith("reviews/"):
            replacements[name] = EPIContainer.read_member_bytes(source, name)
    _replace_members(dest, replacements)


def _append_step(epi_path: Path, step: dict) -> None:
    raw = EPIContainer.read_member_text(epi_path, "steps.jsonl")
    _replace_members(epi_path, {"steps.jsonl": raw + json.dumps(step) + "\n"})
