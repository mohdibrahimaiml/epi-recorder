"""Tests for verify_portal admin telemetry metrics and auth endpoints."""

from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from epi_core import telemetry


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> TestClient:
    monkeypatch.setenv("EPI_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("EPI_STORAGE_DIR", str(tmp_path / "storage"))
    monkeypatch.setenv("EPI_ADMIN_API_KEY", "admin-secret")
    monkeypatch.setenv("GITHUB_CLIENT_ID", "")
    monkeypatch.setenv("GITHUB_CLIENT_SECRET", "")
    key_bytes = b"\x00" * 32
    monkeypatch.setenv("EPI_SCITT_SERVICE_PRIVATE_KEY", base64.b64encode(key_bytes).decode())
    att_key = "not-used"
    monkeypatch.setenv("EPI_ATTESTATION_PRIVATE_KEY", base64.b64encode(b"x" * 32).decode())
    from verify_portal.main import app
    return TestClient(app)


def _event(
    install_id: str,
    event_name: str,
    timestamp: str = "2026-06-19T00:00:00Z",
    metadata: dict | None = None,
) -> dict:
    return {
        "schema_version": telemetry.TELEMETRY_SCHEMA_VERSION,
        "install_id": install_id,
        "event_name": event_name,
        "timestamp": timestamp,
        "epi_version": "4.2.0",
        "python_version": "3.11",
        "os": "Linux",
        "environment": "local",
        "ci": False,
        "metadata": metadata or {"command": event_name.replace(".", "_"), "success": True},
    }


def _write_events(storage_dir: Path, events: list[dict]) -> None:
    path = storage_dir / "telemetry" / "events.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for payload in events:
            f.write(json.dumps({"ts": payload["timestamp"], "payload": payload}) + "\n")


def test_admin_metrics_requires_key(client: TestClient) -> None:
    response = client.get("/api/admin/telemetry/metrics")
    assert response.status_code == 403

    response = client.get("/api/admin/telemetry/metrics", headers={"X-Admin-Key": "wrong"})
    assert response.status_code == 403


def test_admin_metrics_returns_aggregates(client: TestClient, tmp_path: Path) -> None:
    storage_dir = tmp_path / "storage"
    _write_events(storage_dir, [
        _event("install-a", "cli_started"),
        _event("install-a", "epi.record.completed", metadata={"command": "record", "success": True, "email_domain": "acme.com"}),
        _event("install-b", "cli_started", metadata={"github_org": "openai"}),
    ])

    response = client.get("/api/admin/telemetry/metrics", headers={"X-Admin-Key": "admin-secret"})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["total_installs"] == 2
    assert data["organizations_detected"]["email_domains"] == ["acme.com"]
    assert data["organizations_detected"]["github_orgs"] == ["openai"]
    assert "cli_started" in data["top_commands"]
    assert data["version_distribution"]["4.2.0"] == 3


def test_auth_me_rejects_missing_token(client: TestClient) -> None:
    response = client.get("/api/auth/me")
    assert response.status_code == 401


def test_auth_logout_succeeds_without_token(client: TestClient) -> None:
    response = client.post("/api/auth/logout")
    assert response.status_code == 200
    assert response.json()["ok"] is True
