from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from epi_core import telemetry
from epi_gateway.main import GatewayRuntimeSettings, create_app
from epi_gateway.worker import EvidenceWorker


pytestmark = pytest.mark.unit


def _event_payload() -> dict:
    return {
        "schema_version": telemetry.TELEMETRY_SCHEMA_VERSION,
        "install_id": "install-1",
        "event_name": "epi.verify.completed",
        "timestamp": "2026-04-12T00:00:00Z",
        "epi_version": "4.0.1",
        "python_version": "3.11",
        "os": "Linux",
        "environment": "ci",
        "ci": True,
        "metadata": {"command": "verify", "artifact_bytes": 123, "success": True},
    }


def test_gateway_health_ready_and_disabled_telemetry_default(tmp_path: Path):
    worker = EvidenceWorker(storage_dir=tmp_path / "worker", batch_size=1, batch_timeout=0.1)
    app = create_app(worker=worker, settings=GatewayRuntimeSettings(storage_dir=str(tmp_path)))

    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/ready").status_code == 200
        response = client.post("/api/telemetry/events", json=_event_payload())

    assert response.status_code == 404
    assert not (tmp_path / "telemetry" / "events.jsonl").exists()


def test_gateway_accepts_telemetry_events_and_pilot_signups_when_enabled(tmp_path: Path):
    worker = EvidenceWorker(storage_dir=tmp_path / "worker", batch_size=1, batch_timeout=0.1)
    app = create_app(
        worker=worker,
        settings=GatewayRuntimeSettings(storage_dir=str(tmp_path), telemetry_enabled=True),
    )

    with TestClient(app) as client:
        event_response = client.post("/api/telemetry/events", json=_event_payload())
        pilot_response = client.post(
            "/api/telemetry/pilot-signups",
            json={
                "schema_version": telemetry.PILOT_SIGNUP_SCHEMA_VERSION,
                "email": "pilot@example.com",
                "org": "EPI Labs",
                "role": "reviewer",
                "use_case": "governance",
                "consent_to_contact": True,
                "link_telemetry": False,
                "created_at": "2026-04-12T00:00:00Z",
            },
        )

    assert event_response.status_code == 202, event_response.text
    assert pilot_response.status_code == 202, pilot_response.text
    event = json.loads((tmp_path / "telemetry" / "events.jsonl").read_text(encoding="utf-8"))
    signup = json.loads((tmp_path / "telemetry" / "pilot_signups.jsonl").read_text(encoding="utf-8"))
    assert event["metadata"]["artifact_bytes"] == 123
    assert signup["email"] == "pilot@example.com"


def test_gateway_rejects_prompt_key_path_and_repo_metadata(tmp_path: Path):
    worker = EvidenceWorker(storage_dir=tmp_path / "worker", batch_size=1, batch_timeout=0.1)
    app = create_app(
        worker=worker,
        settings=GatewayRuntimeSettings(storage_dir=str(tmp_path), telemetry_enabled=True),
    )

    with TestClient(app) as client:
        for banned_key in ("prompt", "api_key", "repo_name", "path"):
            payload = _event_payload()
            payload["metadata"][banned_key] = "secret"
            response = client.post("/api/telemetry/events", json=payload)
            assert response.status_code == 400
