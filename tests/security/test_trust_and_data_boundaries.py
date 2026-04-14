from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from epi_cli.main import app as cli_app
from epi_core import telemetry
from epi_core.container import EPIContainer
from epi_core.redactor import REDACTION_PLACEHOLDER, Redactor
from epi_core.trust import verify_embedded_manifest_signature
from epi_gateway.main import GatewayRuntimeSettings, create_app
from epi_gateway.worker import EvidenceWorker
from tests.helpers.artifacts import (
    make_decision_epi,
    read_legacy_member_json,
    rewrite_legacy_member,
)


pytestmark = pytest.mark.security
runner = CliRunner()


def test_ed25519_rfc8032_shape_and_embedded_verification(tmp_path: Path):
    artifact, key = make_decision_epi(tmp_path, signed=True)
    assert isinstance(key, Ed25519PrivateKey)

    manifest = EPIContainer.read_manifest(artifact)
    assert manifest.public_key is not None
    assert manifest.signature is not None
    assert len(bytes.fromhex(manifest.public_key)) == 32
    assert len(bytes.fromhex(manifest.signature.split(":", 2)[2])) == 64
    assert verify_embedded_manifest_signature(manifest)[0] is True


def test_tampered_artifact_fails_verify_offline(tmp_path: Path):
    artifact, _ = make_decision_epi(tmp_path, signed=True)
    rewrite_legacy_member(
        artifact,
        "steps.jsonl",
        b'{"index":0,"kind":"test","content":{"tampered":true}}\n',
    )

    integrity_ok, mismatches = EPIContainer.verify_integrity(artifact)
    cli = runner.invoke(cli_app, ["verify", "--json", str(artifact)])

    assert integrity_ok is False
    assert "steps.jsonl" in mismatches
    assert cli.exit_code == 1
    assert json.loads(cli.stdout)["integrity_ok"] is False


def test_signature_replay_attack_fails_with_copied_signature(tmp_path: Path):
    key = Ed25519PrivateKey.generate()
    first, _ = make_decision_epi(tmp_path, name="first.epi", signed=True, private_key=key)
    second, _ = make_decision_epi(
        tmp_path,
        name="second.epi",
        signed=True,
        private_key=key,
        prompt="A different prompt changes the manifest hash",
    )
    first_manifest = read_legacy_member_json(first, "manifest.json")
    second_manifest = read_legacy_member_json(second, "manifest.json")
    second_manifest["signature"] = first_manifest["signature"]
    rewrite_legacy_member(
        second,
        "manifest.json",
        json.dumps(second_manifest, indent=2).encode("utf-8"),
    )

    signature_valid, _, message = verify_embedded_manifest_signature(EPIContainer.read_manifest(second))

    assert signature_valid is False
    assert "invalid" in message.lower() or "tamper" in message.lower()


def test_signature_timestamp_is_immutable(tmp_path: Path):
    artifact, _ = make_decision_epi(tmp_path, signed=True)
    manifest = read_legacy_member_json(artifact, "manifest.json")
    manifest["created_at"] = "2099-01-01T00:00:00Z"
    rewrite_legacy_member(
        artifact,
        "manifest.json",
        json.dumps(manifest, indent=2).encode("utf-8"),
    )

    signature_valid, _, _ = verify_embedded_manifest_signature(EPIContainer.read_manifest(artifact))

    assert signature_valid is False


def test_private_key_never_serialized_into_artifact(tmp_path: Path):
    artifact, key = make_decision_epi(tmp_path, signed=True)
    assert key is not None
    private_hex = key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    ).hex()
    public_hex = EPIContainer.read_manifest(artifact).public_key

    artifact_text = artifact.read_bytes().hex()
    assert private_hex not in artifact_text
    assert public_hex is not None


def test_remote_telemetry_payloads_never_accept_prompts_paths_or_keys(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("EPI_HOME", str(tmp_path))
    telemetry.enable()

    assert telemetry.track_event("epi.verify.completed", {"prompt": "raw prompt"}) is False
    assert telemetry.track_event("epi.verify.completed", {"path": "C:/private/file.epi"}) is False
    assert telemetry.track_event("epi.verify.completed", {"api_key": "sk-" + "a" * 48}) is False
    assert not telemetry.telemetry_queue_path().exists()


def test_api_keys_and_pii_redaction_work():
    payload = {
        "message": "Contact alice@example.com or +1 415-555-0123",
        "api_key": "sk-" + "a" * 48,
        "nested": {"Authorization": "Bearer abc123def456ghi789jkl012"},
    }

    redacted, count = Redactor().redact(payload)

    assert count >= 4
    assert "alice@example.com" not in json.dumps(redacted)
    assert "415-555-0123" not in json.dumps(redacted)
    assert redacted["api_key"] == REDACTION_PLACEHOLDER
    assert REDACTION_PLACEHOLDER in redacted["nested"]["Authorization"]


def test_gateway_capture_redacts_remote_prompt_bodies_by_default(tmp_path: Path):
    worker = EvidenceWorker(storage_dir=tmp_path / "worker", batch_size=1, batch_timeout=0.1)
    gateway = create_app(
        worker=worker,
        settings=GatewayRuntimeSettings(storage_dir=str(tmp_path), retention_mode="redacted_hashes"),
    )

    with TestClient(gateway) as client:
        response = client.post(
            "/capture/llm",
            json={
                "provider": "openai-compatible",
                "request": {
                    "model": "gpt-4o-mini",
                    "messages": [{"role": "user", "content": "Approve refund REF-100 for $900"}],
                },
                "response": {
                    "model": "gpt-4o-mini",
                    "choices": [{"message": {"role": "assistant", "content": "Escalate it"}}],
                },
                "meta": {"decision_id": "decision-sec", "workflow_name": "Refund approvals"},
            },
        )
        assert response.status_code == 202

        detail = None
        deadline = time.time() + 2.0
        while time.time() < deadline:
            cases = client.get("/api/cases").json()["cases"]
            if cases:
                detail = client.get(f"/api/cases/{cases[0]['id']}").json()["case"]
                if len(detail.get("steps") or []) >= 3:
                    break
            time.sleep(0.05)

    assert detail is not None
    serialized = json.dumps(detail)
    assert "Approve refund REF-100 for $900" not in serialized
    assert "Escalate it" not in serialized
    assert "[redacted sha256=" in serialized
