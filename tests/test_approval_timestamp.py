"""An approval must say when it was signed, and prove it independently.

`signed_at` is the approver's clock, inside the payload their key signs. The
question a dispute actually asks is "did a human approve before the payout went
out?", and only a third party can answer that: an RFC 3161 token over the
approval's review hash, from the same pinned authorities as the seal.
"""

from __future__ import annotations

import base64
import json

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from epi_core.container import EPIContainer
from epi_core.keys import key_fingerprint
from epi_core.review import (
    APPROVAL_TIMESTAMP_SCHEME,
    ReviewRecord,
    add_review_to_artifact,
    approval_timestamp_member,
    make_approval_entry,
    read_approval_timestamp,
    read_review,
    verify_approval_timestamp,
    verify_human_approvals,
)
from epi_core.schemas import ManifestModel
from epi_core.time_utils import utc_now
from epi_core.trust import sign_manifest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _seal(tmp_path, *, name="case.epi", approval_id="refund-7"):
    source = tmp_path / f"{name}.src"
    source.mkdir(parents=True, exist_ok=True)
    steps = [
        {"index": 0, "kind": "agent.decision", "content": {"result": "approved"}},
        {
            "index": 1,
            "kind": "agent.approval.request",
            "content": {"action": "refund REF-7", "approval_id": approval_id},
        },
    ]
    (source / "steps.jsonl").write_text(
        "\n".join(json.dumps(step) for step in steps) + "\n", encoding="utf-8"
    )
    sealing_key = Ed25519PrivateKey.generate()
    epi_path = tmp_path / name
    from uuid import uuid4

    EPIContainer.pack(
        source,
        ManifestModel(workflow_id=uuid4(), created_at=utc_now(), cli_command="pytest"),
        epi_path,
        signer_function=lambda manifest: sign_manifest(manifest, sealing_key, "test"),
        preserve_generated=True,
        generate_analysis=False,
    )
    return epi_path


def _record(key, *, name="alice@bank.com", approval_id="refund-7", signed_at=None):
    return ReviewRecord(
        reviewed_by=name,
        reviews=[
            make_approval_entry(
                approval_id=approval_id,
                decision="approve",
                action="refund REF-7",
                reason="checked against the ledger",
                approver_name=name,
                key_fingerprint_hex=key_fingerprint(_pub_hex(key), grouped=False),
                signed_at=signed_at,
            )
        ],
    )


@pytest.fixture
def pinned(tmp_path, monkeypatch):
    """Isolate the approver registry so no developer machine state leaks in."""
    monkeypatch.setenv("EPI_TRUSTED_APPROVERS_DIR", str(tmp_path / "trusted_approvers"))
    monkeypatch.setenv("EPI_APPROVER_KEYS_DIR", str(tmp_path / "approver_keys"))
    key = Ed25519PrivateKey.generate()
    from epi_core.approvers import ApproverRegistry

    ApproverRegistry(tmp_path / "trusted_approvers").add(
        "alice@bank.com", _pub_hex(key)
    )
    return key


def _pub_hex(key) -> str:
    from cryptography.hazmat.primitives import serialization

    return key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    ).hex()


def _fake_tsr(monkeypatch, token=b"\x30\x03\x02\x01\x00"):
    from epi_core import notarize

    monkeypatch.setattr(notarize, "_submit_rfc3161", lambda digest_hex, url: token)


# ---------------------------------------------------------------------------
# signed_at lives inside the signature
# ---------------------------------------------------------------------------

def test_approval_entry_carries_signed_at():
    entry = make_approval_entry(
        approval_id="refund-7",
        decision="approve",
        action="refund",
        reason="ok",
        approver_name="alice",
        key_fingerprint_hex="ab" * 32,
    )
    assert entry["approval_version"] == "1.1.0"
    assert entry["signed_at"], "the entry must say when it was signed"


def test_changing_signed_at_breaks_the_approvers_signature(tmp_path, pinned):
    """signed_at is inside the signed payload, so backdating it is detectable."""
    from epi_core.review import _verify_review_signature

    epi_path = _seal(tmp_path)
    add_review_to_artifact(
        epi_path, _record(pinned, signed_at="2026-01-01T00:00:00Z"), private_key=pinned
    )

    record = read_review(epi_path)
    assert record.reviews[0]["signed_at"] == "2026-01-01T00:00:00Z"

    # The signature covers the review hash, and the hash is computed over the
    # stored payload - so a different signed_at yields a different hash, which
    # the approver's key did not sign.
    ok, _detail = _verify_review_signature(record, record.review_hash)
    assert ok is True

    backdated = record.to_dict()
    backdated["reviews"][0]["signed_at"] = "2026-06-01T00:00:00Z"
    ok, detail = _verify_review_signature(record, ReviewRecord.from_dict(backdated).content_hash())
    assert ok is False, "a changed signed_at must not verify against the same signature"
    assert "does not match" in detail


# ---------------------------------------------------------------------------
# The independent timestamp
# ---------------------------------------------------------------------------

def test_stamp_is_stored_beside_the_approval_not_inside_the_hash(tmp_path, pinned, monkeypatch):
    _fake_tsr(monkeypatch)
    epi_path = _seal(tmp_path)

    stamp = add_review_to_artifact(
        epi_path, _record(pinned), private_key=pinned, timestamp=True
    )

    record = read_review(epi_path)
    assert stamp is not None
    assert stamp["scheme"] == APPROVAL_TIMESTAMP_SCHEME
    assert stamp["status"] == "stamped"
    assert stamp["review_hash"] == record.review_hash
    assert stamp["signed_at"] == record.reviews[0]["signed_at"]

    stored = read_approval_timestamp(epi_path, record.review_id)
    assert stored and base64.b64decode(stored["token_b64"])

    # Adding it must not have changed the approval's own hash, or the approver's
    # signature over it would no longer verify.
    state = verify_human_approvals(epi_path)
    assert state["approvals"][0]["classification"] == "human_signed"


def test_absent_timestamp_is_reported_as_absent(tmp_path, pinned):
    epi_path = _seal(tmp_path)
    add_review_to_artifact(epi_path, _record(pinned), private_key=pinned)  # no timestamp

    result = verify_approval_timestamp(epi_path, read_review(epi_path))
    assert result["status"] == "absent"


def test_unreachable_authority_is_recorded_not_hidden(tmp_path, pinned, monkeypatch):
    from epi_core import notarize

    def boom(digest_hex, url):
        raise OSError("no route to host")

    monkeypatch.setattr(notarize, "_submit_rfc3161", boom)
    epi_path = _seal(tmp_path)

    stamp = add_review_to_artifact(
        epi_path, _record(pinned), private_key=pinned, timestamp=True
    )

    assert stamp["status"] == "unavailable"
    assert "no route to host" in stamp["reason"] or "OSError" in stamp["reason"]

    # The approval itself still stands - only the time is uncorroborated.
    state = verify_human_approvals(epi_path)
    assert state["approvals"][0]["classification"] == "human_signed"
    assert verify_approval_timestamp(epi_path, read_review(epi_path))["status"] == "unavailable"


def test_timestamp_over_a_different_hash_is_a_mismatch(tmp_path, pinned, monkeypatch):
    _fake_tsr(monkeypatch)
    epi_path = _seal(tmp_path)
    add_review_to_artifact(epi_path, _record(pinned), private_key=pinned, timestamp=True)
    record = read_review(epi_path)

    member = approval_timestamp_member(record.review_id)
    stamp = read_approval_timestamp(epi_path, record.review_id)
    stamp["review_hash"] = "00" * 32
    _rewrite_member(epi_path, member, stamp)

    assert verify_approval_timestamp(epi_path, record)["status"] == "mismatch"


def test_verified_timestamp_exposes_its_independent_time(tmp_path, pinned, monkeypatch):
    _fake_tsr(monkeypatch)
    epi_path = _seal(tmp_path)
    add_review_to_artifact(epi_path, _record(pinned), private_key=pinned, timestamp=True)

    from epi_core import tsa_verify

    class _Ok:
        status = "valid"
        gen_time = "2026-10-30T09:15:00Z"
        detail = ""

    monkeypatch.setattr(tsa_verify, "validate_tsr", lambda *a, **k: _Ok())
    monkeypatch.setattr(tsa_verify, "load_pinned_tsa_roots", lambda: [])

    result = verify_approval_timestamp(epi_path, read_review(epi_path))
    assert result["status"] == "verified"
    assert result["gen_time"] == "2026-10-30T09:15:00Z"

    state = verify_human_approvals(epi_path)
    assert state["approvals"][0]["timestamp"]["status"] == "verified"


def test_old_1_0_0_approval_still_counts(tmp_path, pinned):
    """Entries sealed before signed_at existed must keep classifying cleanly."""
    epi_path = _seal(tmp_path)
    record = _record(pinned)
    entry = dict(record.reviews[0])
    entry["approval_version"] = "1.0.0"
    entry.pop("signed_at", None)
    record.reviews = [entry]
    add_review_to_artifact(epi_path, record, private_key=pinned)

    state = verify_human_approvals(epi_path)
    assert state["approvals"][0]["classification"] == "human_signed"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _rewrite_member(epi_path, member, payload):
    import zipfile

    from epi_core.container import EPIContainer as C

    tmp = epi_path.parent / "rewrite.zip"
    C.extract_inner_payload(epi_path, tmp)
    with zipfile.ZipFile(tmp) as zf:
        members = {name: zf.read(name) for name in zf.namelist()}
    members[member] = json.dumps(payload).encode("utf-8")
    with zipfile.ZipFile(tmp, "w") as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    C.write_from_payload(tmp, epi_path, container_format=C.detect_container_format(epi_path))

def test_pinning_from_the_artifact_finds_the_approval_key(tmp_path, pinned, monkeypatch):
    """`approvers add <file.epi>` must be able to pin the human, not just the sealer.

    The fingerprint read aloud is the check: the key is taken from the review
    signature only when its fingerprint matches the one supplied.
    """
    from typer.testing import CliRunner

    from epi_cli.main import app as cli_app
    from epi_core.review import verify_human_approvals

    _fake_tsr(monkeypatch)
    epi_path = _seal(tmp_path)
    approver = Ed25519PrivateKey.generate()  # deliberately not pinned yet
    add_review_to_artifact(
        epi_path, _record(approver, name="demo@bank.com"), private_key=approver, timestamp=True
    )

    before = verify_human_approvals(epi_path)["approvals"][0]["classification"]
    assert before == "signed_unknown_key"

    fingerprint = key_fingerprint(_pub_hex(approver))
    result = CliRunner().invoke(
        cli_app,
        ["approvers", "add", str(epi_path), "--name", "demo@bank.com", "--fingerprint", fingerprint],
    )
    assert result.exit_code == 0, result.output
    assert "Pinned approver" in result.output

    after = verify_human_approvals(epi_path)["approvals"][0]
    assert after["classification"] == "human_signed"
    assert after["key_fingerprint"].replace(" ", "") == fingerprint.replace(" ", "")
