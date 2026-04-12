import json

from fastapi.testclient import TestClient

from epi_core import telemetry
from epi_gateway.main import GatewayRuntimeSettings, create_app
from epi_gateway.worker import EvidenceWorker


def _event_payload():
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


def test_gateway_telemetry_disabled_by_default(tmp_path):
    worker = EvidenceWorker(storage_dir=tmp_path / "worker", batch_size=1, batch_timeout=0.1)
    app = create_app(worker=worker, settings=GatewayRuntimeSettings(storage_dir=str(tmp_path)))

    with TestClient(app) as client:
        response = client.post("/api/telemetry/events", json=_event_payload())

    assert response.status_code == 404
    assert not (tmp_path / "telemetry" / "events.jsonl").exists()


def test_gateway_accepts_enabled_telemetry_event(tmp_path):
    worker = EvidenceWorker(storage_dir=tmp_path / "worker", batch_size=1, batch_timeout=0.1)
    settings = GatewayRuntimeSettings(storage_dir=str(tmp_path), telemetry_enabled=True)
    app = create_app(worker=worker, settings=settings)

    with TestClient(app) as client:
        response = client.post("/api/telemetry/events", json=_event_payload())

    assert response.status_code == 202, response.text
    output = tmp_path / "telemetry" / "events.jsonl"
    record = json.loads(output.read_text(encoding="utf-8").strip())
    assert record["event_name"] == "epi.verify.completed"
    assert record["metadata"]["artifact_bytes"] == 123


def test_gateway_rejects_banned_telemetry_fields(tmp_path):
    worker = EvidenceWorker(storage_dir=tmp_path / "worker", batch_size=1, batch_timeout=0.1)
    settings = GatewayRuntimeSettings(storage_dir=str(tmp_path), telemetry_enabled=True)
    app = create_app(worker=worker, settings=settings)
    payload = _event_payload()
    payload["metadata"]["repo_name"] = "private/repo"

    with TestClient(app) as client:
        response = client.post("/api/telemetry/events", json=payload)

    assert response.status_code == 400


def test_gateway_accepts_pilot_signup_separately(tmp_path):
    worker = EvidenceWorker(storage_dir=tmp_path / "worker", batch_size=1, batch_timeout=0.1)
    settings = GatewayRuntimeSettings(storage_dir=str(tmp_path), telemetry_enabled=True)
    app = create_app(worker=worker, settings=settings)

    with TestClient(app) as client:
        response = client.post(
            "/api/telemetry/pilot-signups",
            json={
                "schema_version": telemetry.PILOT_SIGNUP_SCHEMA_VERSION,
                "email": "pilot@example.com",
                "org": "EPI Labs",
                "role": "founder",
                "use_case": "agt integration",
                "consent_to_contact": True,
                "link_telemetry": False,
                "created_at": "2026-04-12T00:00:00Z",
            },
        )

    assert response.status_code == 202, response.text
    output = tmp_path / "telemetry" / "pilot_signups.jsonl"
    record = json.loads(output.read_text(encoding="utf-8").strip())
    assert record["email"] == "pilot@example.com"
    assert record["use_case"] == "agt integration"
