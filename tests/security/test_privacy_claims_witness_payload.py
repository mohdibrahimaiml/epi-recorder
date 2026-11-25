"""P3 privacy claim: witness reports carry hashes, never file contents.

Claim (website/privacy.html): "If you set up a witness or EPI Cloud, a
hash-only fingerprint of each sealed record goes to the log you configured."

Enforced by epi_core/webhook.py:build_witness_payload /
build_heartbeat_payload. These tests pin the payload shape so a new field
cannot quietly start shipping prompts or step content.
"""
from __future__ import annotations

import inspect
import json
import re
from pathlib import Path

import pytest

from epi_core.container import EPIContainer
from epi_core.webhook import build_heartbeat_payload, build_witness_payload

REPO = Path(__file__).resolve().parents[2]
SAMPLE = REPO / "website" / "assets" / "sample.epi"

# Every key the sealed-evidence report is allowed to carry today. Adding a key
# here is a deliberate privacy decision, not an accident.
ALLOWED_SEAL_KEYS = {
    "schema",
    "type",
    "workflow_id",
    "manifest_hash",
    "file_sha256",
    "steps",
    "sealed_at",
    "seal_timestamp",
    "content_digest",
    "public_key",
    "key_fingerprint",
    "goal",
    "case_id",
    "seal_seq",
    "ledger_id",
    "prev_seq",
    "prev_content_digest",
    "audience",
    "nonce",
}

ALLOWED_HEARTBEAT_KEYS = {
    "schema",
    "type",
    "ledger_id",
    "key_fingerprint",
    "last_seq",
    "at",
    "last_content_digest",
    "burned_seqs",
    "public_key",
}

_HEX64 = re.compile(r"^[0-9a-f]{64}$")


def _payload(**overrides) -> dict:
    base = dict(
        workflow_id="wf-1",
        manifest_hash="a" * 64,
        file_sha256="b" * 64,
        public_key="c" * 64,
        key_fingerprint="d" * 16,
        steps=3,
        sealed_at="2026-11-25T00:00:00Z",
        seal_timestamp={"status": "none", "gen_time": None},
    )
    base.update(overrides)
    return build_witness_payload(**base)


def _step_strings() -> list[str]:
    """Every long string in the sample's sealed steps (prompts, outputs)."""
    raw = EPIContainer.read_member_bytes(SAMPLE, "steps.jsonl")
    out: list[str] = []
    for line in raw.decode("utf-8").splitlines():
        if not line.strip():
            continue
        try:
            step = json.loads(line)
        except json.JSONDecodeError:
            continue
        for value in step.values():
            if isinstance(value, str) and len(value) >= 20:
                out.append(value)
    return out


def test_seal_payload_has_no_unexpected_keys() -> None:
    payload = _payload(content_digest="e" * 64, case_id="case_1", audience="cloud:inb_1")
    assert set(payload) <= ALLOWED_SEAL_KEYS, (
        f"new witness payload keys not reviewed for privacy: {set(payload) - ALLOWED_SEAL_KEYS}"
    )


def test_seal_payload_digests_are_sha256_hex() -> None:
    payload = _payload(
        content_digest="e" * 64,
        prev_content_digest="f" * 64,
        prev_seq=1,
        ledger_id="led_1",
    )
    for key in ("manifest_hash", "file_sha256", "content_digest", "prev_content_digest"):
        assert _HEX64.match(payload[key]), f"{key} is not a SHA-256 hex digest"


def test_seal_payload_carries_no_step_content() -> None:
    manifest = EPIContainer.read_manifest(SAMPLE)
    payload = _payload(
        workflow_id=str(getattr(manifest, "workflow_id", "wf")),
        content_digest="e" * 64,
    )
    serialized = json.dumps(payload, ensure_ascii=False)
    leaked = [text for text in _step_strings() if text in serialized]
    assert leaked == [], f"witness payload contains step content: {leaked[:2]}"


def test_seal_payload_omits_goal_by_default() -> None:
    payload = _payload()
    assert "goal" not in payload


def test_recorder_does_not_send_the_goal_unless_asked() -> None:
    from epi_recorder.api import record

    default = inspect.signature(record).parameters["witness_include_goal"].default
    assert default is False, (
        "witness_include_goal must default to False: the goal is free text and "
        "the privacy page promises a hash-only fingerprint"
    )


def test_goal_is_sent_only_when_explicitly_opted_in() -> None:
    payload = _payload(goal="refund ORD-9001")
    assert payload["goal"] == "refund ORD-9001"


def test_heartbeat_payload_is_hash_only() -> None:
    payload = build_heartbeat_payload(
        ledger_id="led_1",
        key_fingerprint="d" * 16,
        last_seq=42,
        last_content_digest="a" * 64,
    )
    assert set(payload) <= ALLOWED_HEARTBEAT_KEYS
    assert _HEX64.match(payload["last_content_digest"])
    serialized = json.dumps(payload)
    for text in _step_strings():
        assert text not in serialized


def test_seal_payload_contains_no_file_bytes_or_member_paths() -> None:
    payload = _payload(content_digest="e" * 64)
    serialized = json.dumps(payload)
    # Member names are not content, but they are not sent either.
    members = EPIContainer.list_members(SAMPLE)
    assert not any(name in serialized for name in members)
