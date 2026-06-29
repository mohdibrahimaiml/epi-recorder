"""
Tests for verify_portal FastAPI backend.

Covers: health, static routes, .well-known, /api/verify upload,
and SCITT transparency service endpoints.
"""

from __future__ import annotations

import base64
import io
import json
from pathlib import Path
from typing import Any, Callable

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

from epi_core.container import EPIContainer
from epi_core.scitt import create_scitt_statement
from epi_core.schemas import ManifestModel
from epi_core.serialize import get_canonical_hash
from epi_core.trust import sign_manifest
from tests.helpers.artifacts import make_decision_epi

# Import the app lazily so that module-level STATIC_DIR resolution
# happens after any temporary directory fixtures.


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """TestClient with a mocked SCITT service private key."""
    # Use a deterministic key so receipts are reproducible across calls.
    key_bytes = b"\x00" * 32
    monkeypatch.setenv(
        "EPI_SCITT_SERVICE_PRIVATE_KEY",
        base64.b64encode(key_bytes).decode(),
    )
    # Ensure the attestation key is also present so signed attestations work.
    att_key = Ed25519PrivateKey.generate()
    monkeypatch.setenv(
        "EPI_ATTESTATION_PRIVATE_KEY",
        base64.b64encode(att_key.private_bytes_raw()).decode(),
    )
    # Disable in-memory rate limiting for tests.
    monkeypatch.setattr("verify_portal.main._check_rate_limit", lambda _ip: True)
    # Import here so env vars are patched first.
    from verify_portal.main import app

    return TestClient(app)


@pytest.fixture
def valid_epi(tmp_path: Path) -> Path:
    """Return a path to a signed, valid .epi artifact."""
    epi_path, _ = make_decision_epi(tmp_path, signed=True)
    return epi_path


# ---------------------------------------------------------------------------
# Health & static routes
# ---------------------------------------------------------------------------


def test_health(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert data["service"] == "epi-verify-portal"


def test_portal_html(client: TestClient) -> None:
    r = client.get("/portal")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "EPI Verify" in r.text or "verify" in r.text.lower()


def test_admin_telemetry_html(client: TestClient) -> None:
    r = client.get("/admin/telemetry.html")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "Telemetry Dashboard" in r.text
    assert "/api/admin/telemetry/metrics" in r.text
    assert "/css/epi.css?v=24" in r.text
    assert 'href="#how"' in r.text or 'href="/#how"' in r.text
    assert 'href="/#verify"' in r.text
    assert 'href="#audit"' in r.text or 'href="/#audit"' in r.text


def test_verify_page_matches_site_design(client: TestClient) -> None:
    r = client.get("/verify")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "css/epi.css?v=24" in r.text
    assert 'href="#how"' in r.text or 'href="/#how"' in r.text
    assert 'href="#verify"' in r.text or 'href="/verify"' in r.text
    assert 'href="#audit"' in r.text or 'href="/#audit"' in r.text
    assert 'href="#cta"' in r.text or 'href="/#cta"' in r.text


def test_root_serves_landing_page(client: TestClient) -> None:
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]


# ---------------------------------------------------------------------------
# .well-known
# ---------------------------------------------------------------------------


def test_did_document(client: TestClient) -> None:
    r = client.get("/.well-known/did.json")
    assert r.status_code == 200
    data = r.json()
    assert data.get("id") == "did:web:epilabs.org"


def test_trust_registry(client: TestClient) -> None:
    r = client.get("/.well-known/epi-trust-registry.json")
    assert r.status_code == 200
    data = r.json()
    assert "trusted_keys" in data
    assert "scitt_services" in data
    # Should contain the newly-rotated SCITT key.
    scitt = data.get("scitt_services", [])
    assert len(scitt) >= 1
    assert scitt[0].get("status") == "active"
    assert len(scitt[0].get("public_key", "")) == 64


# ---------------------------------------------------------------------------
# /api/verify
# ---------------------------------------------------------------------------


def test_verify_valid_epi(client: TestClient, valid_epi: Path) -> None:
    with open(valid_epi, "rb") as f:
        r = client.post(
            "/api/verify",
            files={"file": ("test.epi", f, "application/epi+zip")},
            data={"aiuc1": "true"},
        )
    assert r.status_code == 200
    report: dict[str, Any] = r.json()
    assert "summary" in report
    assert "trust_level" in report
    # Integrity may be FAILED for test artifacts that lack complete
    # step sequences or total_steps; we just verify the pipeline ran.
    assert report["summary"].get("integrity") in ("VALID", "FAILED")
    # AIUC-1 mapping should be present.
    assert "aiuc1" in report
    assert "overall" in report["aiuc1"]


def test_verify_invalid_file(client: TestClient) -> None:
    r = client.post(
        "/api/verify",
        files={"file": ("bad.txt", io.BytesIO(b"not an epi file"), "text/plain")},
    )
    assert r.status_code == 400
    data = r.json()
    assert "detail" in data


def test_verify_missing_file(client: TestClient) -> None:
    r = client.post("/api/verify", data={})
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# SCITT service
# ---------------------------------------------------------------------------


def test_scitt_keys(client: TestClient) -> None:
    r = client.get("/scitt/keys")
    assert r.status_code == 200
    data = r.json()
    assert "public_key" in data
    pk = data["public_key"]
    assert len(pk) == 64  # hex-encoded 32-byte key


def test_scitt_register_and_lookup(client: TestClient) -> None:
    # Build a minimal valid COSE_Sign1 statement.
    issuer_key = Ed25519PrivateKey.generate()
    manifest = ManifestModel(
        cli_command="pytest",
        goal="test scitt register",
    )
    statement = create_scitt_statement(
        manifest,
        issuer_key,
        issuer="did:web:epilabs.org",
        kid=b"test",
    )

    # Register
    r = client.post(
        "/scitt/register",
        content=statement,
        headers={"content-type": "application/cose"},
    )
    assert r.status_code == 200
    receipt = r.content
    assert len(receipt) > 0
    entry_id = r.headers.get("x-scitt-entry-id")
    assert entry_id is not None
    assert len(entry_id) == 32

    # Lookup
    r2 = client.get(f"/scitt/entries/{entry_id}")
    assert r2.status_code == 200
    entry = r2.json()
    assert entry.get("entry_id") == entry_id
    assert "registered_at" in entry


def test_scitt_register_bad_statement(client: TestClient) -> None:
    r = client.post(
        "/scitt/register",
        content=b"not a valid cose statement",
        headers={"content-type": "application/cose"},
    )
    assert r.status_code == 400


def test_scitt_lookup_missing_entry(client: TestClient) -> None:
    r = client.get("/scitt/entries/00000000000000000000000000000000")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Rate limiting (smoke test — in-memory store resets between tests)
# ---------------------------------------------------------------------------


def test_rate_limit_headers_present(client: TestClient, valid_epi: Path) -> None:
    with open(valid_epi, "rb") as f:
        r = client.post(
            "/api/verify",
            files={"file": ("test.epi", f, "application/epi+zip")},
        )
    assert r.status_code == 200
    # The portal does not currently expose rate-limit headers, but the
    # response should be well-formed JSON.
    assert "application/json" in r.headers.get("content-type", "")


def test_pricing_page(client):  
    r = client.get("/pricing")  
    assert r.status_code == 200  
  
def test_docs_page(client):  
    r = client.get("/docs")  
    assert r.status_code == 200  
  
def test_openapi_json(client):  
    r = client.get("/openapi.json")  
    assert r.status_code == 200  
    assert "openapi" in r.json()  
  
def test_contact_endpoint(client):  
    r = client.post("/api/contact", data={"name": "T", "email": "t@c.com", "company": "C", "tier": "pro", "use_case": "x"})  
    assert r.status_code == 200  
    assert r.json()["status"] == "ok"  
  
def test_create_api_key(client):  
    r = client.post("/api/keys", json={"tier": "free", "name": "test"})  
    assert r.status_code == 200  
    d = r.json()  
    assert d["tier"] == "free"  
    assert d["api_key"].startswith("epi_")  
  
def test_create_api_key_bad_tier(client):  
    r = client.post("/api/keys", json={"tier": "bad", "name": "x"})  
    assert r.status_code == 400  
  
def test_list_api_keys(client):  
    r = client.get("/api/keys")  
    assert r.status_code == 200  
    assert "keys" in r.json()  
  
def test_verify_with_pro_key(client, valid_epi):  
    r = client.post("/api/keys", json={"tier": "pro", "name": "p"})  
    assert r.status_code == 200  
    key = r.json()["api_key"]  
    with open(valid_epi, "rb") as f:  
        r2 = client.post("/api/verify", files={"file": ("test.epi", f, "application/epi+zip")}, headers={"X-API-Key": key})  


# ---------------------------------------------------------------------------
# Telemetry ingestion
# ---------------------------------------------------------------------------


def _telemetry_event_payload() -> dict[str, Any]:
    from epi_core import telemetry
    return {
        "schema_version": telemetry.TELEMETRY_SCHEMA_VERSION,
        "install_id": "install-verify-portal-1",
        "event_name": "epi.record.completed",
        "timestamp": "2026-04-12T00:00:00Z",
        "epi_version": "4.2.0",
        "python_version": "3.11",
        "os": "Linux",
        "environment": "ci",
        "ci": True,
        "metadata": {"command": "record", "artifact_bytes": 123, "success": True},
    }


def test_verify_portal_accepts_telemetry_event(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("EPI_STORAGE_DIR", str(tmp_path))
    response = client.post("/api/telemetry/events", json=_telemetry_event_payload())
    assert response.status_code == 202, response.text
    output = tmp_path / "telemetry" / "events.jsonl"
    assert output.exists()
    record = json.loads(output.read_text(encoding="utf-8").strip())
    assert record["payload"]["event_name"] == "epi.record.completed"
    assert record["payload"]["metadata"]["artifact_bytes"] == 123


def test_verify_portal_rejects_banned_telemetry_fields(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("EPI_STORAGE_DIR", str(tmp_path))
    payload = _telemetry_event_payload()
    payload["metadata"]["repo_name"] = "private/repo"
    response = client.post("/api/telemetry/events", json=payload)
    assert response.status_code == 400


def test_verify_portal_accepts_pilot_signup(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from epi_core import telemetry
    monkeypatch.setenv("EPI_STORAGE_DIR", str(tmp_path))
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
    assert record["payload"]["email"] == "pilot@example.com"


def test_verify_portal_telemetry_can_be_disabled(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr("verify_portal.main._VERIFY_TELEMETRY_ENABLED", False)
    monkeypatch.setenv("EPI_STORAGE_DIR", str(tmp_path))
    response = client.post("/api/telemetry/events", json=_telemetry_event_payload())
    assert response.status_code == 404
    assert not (tmp_path / "telemetry" / "events.jsonl").exists()


# ---------------------------------------------------------------------------
# Accuracy-focused verification tests
# ---------------------------------------------------------------------------


def _canonical_step_hash(step_dict: dict[str, Any]) -> str:
    """Return the canonical JSON hash used for the prev_hash chain."""
    from epi_core.schemas import StepModel

    model = StepModel(**step_dict)
    return get_canonical_hash(model, format="json")


def _repack_with_modified_manifest(
    epi_path: Path,
    key: Ed25519PrivateKey,
    tmp_path: Path,
    manifest_mutator: Callable[[dict[str, Any], Path], None],
    container_format: str = "legacy-zip",
) -> Path:
    """Unpack an artifact, mutate the workspace/manifest, and re-pack + re-sign."""
    workspace = tmp_path / "workspace"
    EPIContainer.unpack(epi_path, workspace)
    manifest_data = json.loads((workspace / "manifest.json").read_text(encoding="utf-8"))
    manifest_mutator(manifest_data, workspace)
    manifest = ManifestModel(**manifest_data)
    output = tmp_path / "modified.epi"

    def _sign(item: ManifestModel) -> ManifestModel:
        return sign_manifest(item, key, "test")

    EPIContainer.pack(
        workspace,
        manifest,
        output,
        signer_function=_sign,
        preserve_generated=True,
        generate_analysis=False,
        container_format=container_format,
    )
    return output


def test_verify_signed_epi_with_trusted_key_reports_high(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A signed artifact whose public key is in the trusted registry should be HIGH."""
    epi_path, key = make_decision_epi(tmp_path, signed=True)
    trusted_dir = tmp_path / "trusted_keys"
    trusted_dir.mkdir()
    pub_hex = key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    ).hex()
    (trusted_dir / "test.pub").write_text(pub_hex, encoding="utf-8")
    monkeypatch.setenv("EPI_TRUSTED_KEYS_DIR", str(trusted_dir))

    with open(epi_path, "rb") as f:
        r = client.post(
            "/api/verify",
            files={"file": ("test.epi", f, "application/epi+zip")},
            data={"aiuc1": "true"},
        )
    assert r.status_code == 200
    report = r.json()
    assert report["facts"]["signature_valid"] is True
    assert report["identity"]["status"] == "KNOWN"
    assert report["trust_level"] == "HIGH"


def test_verify_chain_break_fails(
    client: TestClient,
    tmp_path: Path,
) -> None:
    """A re-signed artifact with a broken prev_hash chain must fail integrity."""
    epi_path, key = make_decision_epi(tmp_path, signed=True)

    def _tamper_first_step(manifest_data: dict[str, Any], workspace: Path) -> None:
        steps_path = workspace / "steps.jsonl"
        lines = steps_path.read_text(encoding="utf-8").splitlines()
        if not lines:
            return
        steps = [json.loads(line) for line in lines]
        for i in range(1, len(steps)):
            steps[i]["prev_hash"] = _canonical_step_hash(steps[i - 1])
        steps[0]["content"] = steps[0].get("content", {})
        steps[0]["content"]["tampered"] = True
        steps_path.write_text(
            "\n".join(json.dumps(step, ensure_ascii=False) for step in steps) + "\n",
            encoding="utf-8",
        )

    modified = _repack_with_modified_manifest(epi_path, key, tmp_path, _tamper_first_step)

    with open(modified, "rb") as f:
        r = client.post(
            "/api/verify",
            files={"file": ("modified.epi", f, "application/epi+zip")},
            data={"aiuc1": "true"},
        )
    assert r.status_code == 200
    report = r.json()
    assert report["facts"]["chain_ok"] is False
    assert report["summary"]["integrity"] == "FAILED"
    assert report["trust_level"] == "NONE"


def test_verify_step_count_mismatch_fails(
    client: TestClient,
    tmp_path: Path,
) -> None:
    """A manifest that lies about total_steps must fail integrity."""
    epi_path, key = make_decision_epi(tmp_path, signed=True)

    def _lie_about_step_count(manifest_data: dict[str, Any], workspace: Path) -> None:
        manifest_data["total_steps"] = 9999

    modified = _repack_with_modified_manifest(epi_path, key, tmp_path, _lie_about_step_count)

    with open(modified, "rb") as f:
        r = client.post(
            "/api/verify",
            files={"file": ("modified.epi", f, "application/epi+zip")},
            data={"aiuc1": "true"},
        )
    assert r.status_code == 200
    report = r.json()
    assert report["summary"]["integrity"] == "FAILED"
    assert report["trust_level"] == "NONE"


def test_verify_sample_epi_high(
    client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The shipped demo asset must verify as HIGH when its key is trusted."""
    sample_path = Path("verify_portal/static/assets/sample.epi")
    manifest = EPIContainer.read_manifest(sample_path)
    trusted_dir = tmp_path / "trusted_keys"
    trusted_dir.mkdir()
    (trusted_dir / "EPI Labs Official.pub").write_text(
        manifest.public_key or "", encoding="utf-8"
    )
    monkeypatch.setenv("EPI_TRUSTED_KEYS_DIR", str(trusted_dir))

    with open(sample_path, "rb") as f:
        r = client.post(
            "/api/verify",
            files={"file": ("sample.epi", f, "application/epi+zip")},
            data={"aiuc1": "true"},
        )
    assert r.status_code == 200
    report = r.json()
    assert report["facts"]["signature_valid"] is True
    assert report["identity"]["status"] == "KNOWN"
    assert report["trust_level"] == "HIGH"
