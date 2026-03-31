import hashlib
import json
import zipfile
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from epi_core.schemas import ManifestModel
from epi_core.time_utils import utc_now
from epi_core.trust import sign_manifest
from epi_gateway.main import GatewayRuntimeSettings, create_app
from epi_gateway.worker import EvidenceWorker


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _make_epi(
    tmp_path: Path,
    *,
    name: str = "sample.epi",
    signed: bool = False,
    include_manifest: bool = True,
    include_steps: bool = True,
    integrity_ok: bool = True,
    invalid_signature: bool = False,
) -> Path:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    expected_steps = b'{"index":0,"kind":"test","content":{"ok":true}}\n'
    stored_steps = expected_steps if integrity_ok else b'{"index":0,"kind":"test","content":{"ok":false}}\n'
    manifest = ManifestModel(
        workflow_id=uuid4(),
        created_at=utc_now(),
        cli_command="python demo.py",
        file_manifest={"steps.jsonl": _sha256(expected_steps)} if include_steps else {},
    )

    if signed:
        key = Ed25519PrivateKey.generate()
        manifest = sign_manifest(manifest, key, "default")

    if invalid_signature:
        manifest = ManifestModel(
            **{
                **manifest.model_dump(),
                "signature": "ed25519:default:" + ("aa" * 64),
                "public_key": "bb" * 32,
            }
        )

    artifact = tmp_path / name
    with zipfile.ZipFile(artifact, "w") as archive:
        archive.writestr("mimetype", "application/vnd.epi+zip")
        if include_manifest:
            archive.writestr("manifest.json", manifest.model_dump_json())
        if include_steps:
            archive.writestr("steps.jsonl", stored_steps)
        archive.writestr("viewer.html", "<html></html>")
    return artifact


def _share_settings(tmp_path: Path, **overrides) -> GatewayRuntimeSettings:
    base = {
        "storage_dir": str(tmp_path),
        "share_enabled": True,
        "share_ip_hmac_secret": "test-share-secret",
        "share_site_base_url": "https://epilabs.org",
        "share_api_base_url": "https://api.epilabs.org",
    }
    base.update(overrides)
    return GatewayRuntimeSettings(**base)


def test_gateway_share_upload_unsigned_and_signed(tmp_path):
    worker = EvidenceWorker(storage_dir=tmp_path / "worker", batch_size=1, batch_timeout=0.1)
    app = create_app(worker=worker, settings=_share_settings(tmp_path / "share"))

    unsigned = _make_epi(tmp_path, name="unsigned.epi", signed=False)
    signed = _make_epi(tmp_path, name="signed.epi", signed=True)

    with TestClient(app) as client:
        unsigned_response = client.post(
            "/api/share",
            content=unsigned.read_bytes(),
            headers={"Content-Type": "application/vnd.epi+zip", "X-EPI-Filename": "unsigned.epi"},
        )
        assert unsigned_response.status_code == 201
        unsigned_payload = unsigned_response.json()
        assert unsigned_payload["signature_status"] == "unsigned"
        assert unsigned_payload["url"].startswith("https://epilabs.org/cases/?id=")

        signed_response = client.post(
            "/api/share",
            content=signed.read_bytes(),
            headers={"Content-Type": "application/vnd.epi+zip", "X-EPI-Filename": "signed.epi"},
        )
        assert signed_response.status_code == 201
        signed_payload = signed_response.json()
        assert signed_payload["signature_status"] == "verified"
        assert signed_payload["steps_count"] == 1


def test_gateway_share_rejects_bad_zip_and_missing_required_files(tmp_path):
    worker = EvidenceWorker(storage_dir=tmp_path / "worker", batch_size=1, batch_timeout=0.1)
    app = create_app(worker=worker, settings=_share_settings(tmp_path / "share"))
    bad_zip = tmp_path / "bad.epi"
    bad_zip.write_text("not-a-zip", encoding="utf-8")
    missing_manifest = _make_epi(tmp_path, name="missing_manifest.epi", include_manifest=False)
    missing_steps = _make_epi(tmp_path, name="missing_steps.epi", include_steps=False)

    with TestClient(app) as client:
        response = client.post("/api/share", content=bad_zip.read_bytes(), headers={"Content-Type": "application/vnd.epi+zip"})
        assert response.status_code == 400
        assert "zip" in response.json()["detail"].lower()

        response = client.post("/api/share", content=missing_manifest.read_bytes(), headers={"Content-Type": "application/vnd.epi+zip"})
        assert response.status_code == 400
        assert "manifest.json" in response.json()["detail"].lower()

        response = client.post("/api/share", content=missing_steps.read_bytes(), headers={"Content-Type": "application/vnd.epi+zip"})
        assert response.status_code == 400
        assert "steps.jsonl" in response.json()["detail"].lower()


def test_gateway_share_rejects_integrity_and_signature_failures(tmp_path):
    worker = EvidenceWorker(storage_dir=tmp_path / "worker", batch_size=1, batch_timeout=0.1)
    app = create_app(worker=worker, settings=_share_settings(tmp_path / "share"))
    bad_integrity = _make_epi(tmp_path, name="bad_integrity.epi", integrity_ok=False)
    bad_signature = _make_epi(tmp_path, name="bad_signature.epi", signed=True, invalid_signature=True)

    with TestClient(app) as client:
        response = client.post("/api/share", content=bad_integrity.read_bytes(), headers={"Content-Type": "application/vnd.epi+zip"})
        assert response.status_code == 400
        assert "integrity" in response.json()["detail"].lower()

        response = client.post("/api/share", content=bad_signature.read_bytes(), headers={"Content-Type": "application/vnd.epi+zip"})
        assert response.status_code == 400
        assert "signature" in response.json()["detail"].lower()


def test_gateway_share_enforces_size_limit(tmp_path):
    worker = EvidenceWorker(storage_dir=tmp_path / "worker", batch_size=1, batch_timeout=0.1)
    settings = _share_settings(tmp_path / "share", share_max_upload_bytes=1024)
    app = create_app(worker=worker, settings=settings)

    with TestClient(app) as client:
        response = client.post(
            "/api/share",
            content=b"x" * 2048,
            headers={"Content-Type": "application/octet-stream", "Content-Length": "2048"},
        )
        assert response.status_code == 413


def test_gateway_share_enforces_rate_limit(tmp_path):
    worker = EvidenceWorker(storage_dir=tmp_path / "worker", batch_size=1, batch_timeout=0.1)
    settings = _share_settings(tmp_path / "share", share_rate_limit_per_hour=10)
    app = create_app(worker=worker, settings=settings)
    artifact = _make_epi(tmp_path, name="rate.epi")

    with TestClient(app) as client:
        for _ in range(10):
            response = client.post("/api/share", content=artifact.read_bytes(), headers={"Content-Type": "application/vnd.epi+zip"})
            assert response.status_code == 201

        response = client.post("/api/share", content=artifact.read_bytes(), headers={"Content-Type": "application/vnd.epi+zip"})
        assert response.status_code == 429


def test_gateway_share_enforces_quota(tmp_path):
    artifact = _make_epi(tmp_path, name="quota.epi")
    artifact_size = artifact.stat().st_size
    worker = EvidenceWorker(storage_dir=tmp_path / "worker", batch_size=1, batch_timeout=0.1)
    settings = _share_settings(
        tmp_path / "share",
        share_max_upload_bytes=1024,
        share_rate_limit_per_hour=20,
        share_quota_bytes_per_30d=2048,
    )
    app = create_app(worker=worker, settings=settings)

    with TestClient(app) as client:
        first = client.post("/api/share", content=artifact.read_bytes(), headers={"Content-Type": "application/vnd.epi+zip"})
        second = client.post("/api/share", content=artifact.read_bytes(), headers={"Content-Type": "application/vnd.epi+zip"})
        third = client.post("/api/share", content=artifact.read_bytes(), headers={"Content-Type": "application/vnd.epi+zip"})

        assert first.status_code == 201
        assert second.status_code == 201
        assert third.status_code == 429
        assert "quota" in third.json()["detail"].lower()


def test_gateway_share_meta_download_and_expiry(tmp_path):
    worker = EvidenceWorker(storage_dir=tmp_path / "worker", batch_size=1, batch_timeout=0.1)
    share_storage = tmp_path / "share"
    app = create_app(worker=worker, settings=_share_settings(share_storage))
    artifact = _make_epi(tmp_path, name="meta.epi", signed=True)

    with TestClient(app) as client:
        response = client.post(
            "/api/share",
            content=artifact.read_bytes(),
            headers={"Content-Type": "application/vnd.epi+zip", "X-EPI-Filename": "meta.epi"},
        )
        assert response.status_code == 201
        payload = response.json()
        share_id = payload["id"]

        meta_response = client.get(f"/api/share/{share_id}/meta")
        assert meta_response.status_code == 200
        meta = meta_response.json()
        assert meta["filename"] == "meta.epi"
        assert meta["signature_status"] == "verified"

        download_response = client.get(f"/api/share/{share_id}")
        assert download_response.status_code == 200
        assert download_response.headers["content-type"].startswith("application/vnd.epi+zip")
        assert download_response.content == artifact.read_bytes()

        stored_path = share_storage / "shared-objects" / "cases" / f"{share_id}.epi"
        assert stored_path.exists()

        share_db = app.state.share_service.metadata_store.db_path
        with zipfile.ZipFile(stored_path, "r") as archive:
            assert "manifest.json" in archive.namelist()

        import sqlite3

        with sqlite3.connect(share_db) as connection:
            connection.execute(
                "UPDATE shares SET expires_at = ?, deleted_at = NULL WHERE share_id = ?",
                ("2000-01-01T00:00:00Z", share_id),
            )
            connection.commit()

        expired_meta = client.get(f"/api/share/{share_id}/meta")
        expired_download = client.get(f"/api/share/{share_id}")
        assert expired_meta.status_code == 410
        assert expired_download.status_code == 410


def test_gateway_share_remains_auth_free_when_case_api_requires_auth(tmp_path):
    worker = EvidenceWorker(storage_dir=tmp_path / "worker", batch_size=1, batch_timeout=0.1)
    settings = _share_settings(tmp_path / "share", access_token="shared-secret")
    app = create_app(worker=worker, settings=settings)
    artifact = _make_epi(tmp_path, name="authfree.epi")

    with TestClient(app) as client:
        share_response = client.post("/api/share", content=artifact.read_bytes(), headers={"Content-Type": "application/vnd.epi+zip"})
        assert share_response.status_code == 201

        cases_response = client.get("/api/cases")
        assert cases_response.status_code == 401
