"""Gateway exports carry the did:web identity and report to the customer witness,
the same way the SDK record() path does. Local HTTP servers only (no external network)."""

from __future__ import annotations

import json
import os
import re
import socket
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from typer.testing import CliRunner

from epi_cli.main import app

runner = CliRunner()

_GATEWAY_IDENTITY_ENV = (
    "EPI_DID",
    "EPI_GATEWAY_DID",
    "EPI_WITNESS_URL",
    "EPI_WITNESS_SECRET",
    "EPI_GATEWAY_WITNESS_URL",
    "EPI_GATEWAY_WITNESS_SECRET",
    "EPI_GATEWAY_DISABLE_SIGNING",
    "EPI_GATEWAY_SIGNING_KEY_NAME",
)


def _plain(output: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", output)


def _flat(output: str) -> str:
    """Plain output with terminal line wrapping undone."""
    return " ".join(_plain(output).split())


def _hermetic(monkeypatch, tmp_path, *, signed=False):
    for key in _GATEWAY_IDENTITY_ENV:
        monkeypatch.delenv(key, raising=False)
    home = tmp_path / "home"
    monkeypatch.setenv("EPI_HOME", str(home))
    monkeypatch.setenv("EPI_KEYS_DIR", str(home / "keys"))
    monkeypatch.setenv("EPI_GATEWAY_KEYS_DIR", str(home / "keys"))
    monkeypatch.setenv("EPI_NOTARIZE", "0")
    if signed:
        from epi_core.keys import KeyManager

        KeyManager(home / "keys").generate_keypair("default")


def _store_case(storage_dir):
    from epi_gateway.worker import EvidenceWorker

    worker = EvidenceWorker(storage_dir=storage_dir, batch_size=1, batch_timeout=0.1)
    return worker.store_items(
        [
            {
                "kind": "llm.request",
                "content": {"messages": [{"role": "user", "content": "Approve refund"}]},
                "meta": {"decision_id": "decision-identity", "workflow_name": "Refunds"},
            }
        ]
    )[0]


class _WitnessHandler(BaseHTTPRequestHandler):
    received: list = []

    def do_POST(self):  # noqa: N802 - http.server convention
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        headers = {key.lower(): value for key, value in self.headers.items()}
        _WitnessHandler.received.append({"headers": headers, "body": body})
        self.send_response(200)
        self.end_headers()

    def log_message(self, *args):  # noqa: ANN002
        pass


def _witness_server():
    _WitnessHandler.received = []
    server = HTTPServer(("127.0.0.1", 0), _WitnessHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_port}/witness"


def _export(case_id, out, storage_dir, *extra):
    return runner.invoke(
        app,
        [
            "gateway", "export", "--case-id", case_id, "--out", str(out),
            "--storage-dir", str(storage_dir), *extra,
        ],
    )


def test_export_binds_did_flag_into_manifest_governance(monkeypatch, tmp_path):
    from epi_core.container import EPIContainer

    _hermetic(monkeypatch, tmp_path, signed=True)
    storage_dir = tmp_path / "storage"
    case_id = _store_case(storage_dir)
    out = tmp_path / "case.epi"

    result = _export(case_id, out, storage_dir, "--did", "did:web:vendor.example")
    output = _plain(result.output)

    assert result.exit_code == 0, output
    manifest = EPIContainer.read_manifest(out)
    # Same field and shape as record(did=...): manifest.governance["did"].
    assert manifest.governance["did"] == "did:web:vendor.example"
    assert manifest.signature
    assert "DID: did:web:vendor.example" in output
    assert "Unsigned" not in output


def test_export_reads_epi_did_env_and_reports_none(monkeypatch, tmp_path):
    from epi_core.container import EPIContainer

    _hermetic(monkeypatch, tmp_path)
    storage_dir = tmp_path / "storage"
    case_id = _store_case(storage_dir)

    result = _export(case_id, tmp_path / "none.epi", storage_dir)
    assert result.exit_code == 0, result.output
    assert "DID: none" in _plain(result.output)
    assert not (EPIContainer.read_manifest(tmp_path / "none.epi").governance or {}).get("did")

    monkeypatch.setenv("EPI_DID", "did:web:env.example")
    result = _export(case_id, tmp_path / "env.epi", storage_dir)
    assert result.exit_code == 0, result.output
    assert "DID: did:web:env.example" in _plain(result.output)
    assert EPIContainer.read_manifest(tmp_path / "env.epi").governance["did"] == "did:web:env.example"


def test_export_rejects_non_did_web(monkeypatch, tmp_path):
    _hermetic(monkeypatch, tmp_path)
    storage_dir = tmp_path / "storage"
    case_id = _store_case(storage_dir)

    result = _export(case_id, tmp_path / "bad.epi", storage_dir, "--did", "vendor.example")

    assert result.exit_code == 1
    assert "did:web:" in _plain(result.output)
    assert not (tmp_path / "bad.epi").exists()


def test_export_unsigned_prints_keys_hint(monkeypatch, tmp_path):
    _hermetic(monkeypatch, tmp_path)  # no key in the keystore
    storage_dir = tmp_path / "storage"
    case_id = _store_case(storage_dir)

    result = _export(case_id, tmp_path / "case.epi", storage_dir)
    output = _plain(result.output)

    assert result.exit_code == 0, output
    assert "Signed: no" in output
    assert 'Unsigned — run "epi keys generate" first so exports are signed.' in output


def test_export_delivers_to_witness_from_env(monkeypatch, tmp_path):
    from epi_core.webhook import read_outbox

    _hermetic(monkeypatch, tmp_path, signed=True)
    storage_dir = tmp_path / "storage"
    case_id = _store_case(storage_dir)
    server, url = _witness_server()
    try:
        monkeypatch.setenv("EPI_WITNESS_URL", url)
        monkeypatch.setenv("EPI_WITNESS_SECRET", "env-secret")
        result = _export(case_id, tmp_path / "case.epi", storage_dir, "--did", "did:web:vendor.example")
    finally:
        server.shutdown()
    output = _plain(result.output)

    assert result.exit_code == 0, output
    assert f"Witness: delivered to {url}" in output
    assert "env-secret" not in output
    assert len(_WitnessHandler.received) == 1
    received = _WitnessHandler.received[0]
    payload = json.loads(received["body"])
    assert payload["schema"] == "epi-witness/v1"
    assert received["headers"].get("x-epi-signature", "").startswith("sha256=")
    assert received["headers"].get("x-epi-seal-signature", "").startswith("ed25519:")
    assert not [entry for entry in read_outbox() if entry.get("pending")]


def test_export_witness_flags_with_down_endpoint_queue_and_succeed(monkeypatch, tmp_path):
    from epi_core.webhook import read_outbox

    _hermetic(monkeypatch, tmp_path)
    storage_dir = tmp_path / "storage"
    case_id = _store_case(storage_dir)
    with socket.socket() as sock:  # bound then closed: connection refused
        sock.bind(("127.0.0.1", 0))
        dead_url = f"http://127.0.0.1:{sock.getsockname()[1]}/witness"

    result = _export(
        case_id, tmp_path / "case.epi", storage_dir,
        "--witness-url", dead_url, "--witness-secret", "flag-secret",
    )
    output = _plain(result.output)

    # Delivery failure never fails the export; the report stays in the outbox.
    assert result.exit_code == 0, output
    assert (tmp_path / "case.epi").exists()
    assert "Witness: QUEUED (Connection refused) — run epi witness flush" in _flat(result.output)
    assert "flag-secret" not in output
    assert [entry for entry in read_outbox() if dead_url in (entry.get("pending") or [])]


def test_export_refuses_storage_dir_without_case_store(monkeypatch, tmp_path):
    _hermetic(monkeypatch, tmp_path)
    empty = tmp_path / "not-a-vault"
    empty.mkdir()

    result = _export("any-case", tmp_path / "case.epi", empty)
    output = _plain(result.output)

    assert result.exit_code == 1
    assert "No gateway case store" in output
    assert not (empty / "cases.sqlite3").exists()
    assert not (tmp_path / "case.epi").exists()


def test_health_reports_did_and_witness_configured(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    from epi_gateway.main import GatewayRuntimeSettings, create_app
    from epi_gateway.worker import EvidenceWorker

    _hermetic(monkeypatch, tmp_path)
    settings = GatewayRuntimeSettings(
        storage_dir=str(tmp_path),
        did_web="did:web:vendor.example",
        witness_url="http://127.0.0.1:9/witness",
        witness_secret="health-secret",
    )
    app_ = create_app(worker=EvidenceWorker(storage_dir=tmp_path), settings=settings)
    with TestClient(app_) as client:
        body = client.get("/health").json()
    assert body["did"] == "did:web:vendor.example"
    assert body["witness_configured"] is True
    assert "health-secret" not in json.dumps(body)
    assert "127.0.0.1:9" not in json.dumps(body)

    plain_dir = tmp_path / "plain"
    plain = create_app(
        worker=EvidenceWorker(storage_dir=plain_dir),
        settings=GatewayRuntimeSettings(storage_dir=str(plain_dir)),
    )
    with TestClient(plain) as client:
        body = client.get("/health").json()
    assert body["did"] is None
    assert body["witness_configured"] is False


def test_api_export_binds_did_from_gateway_env(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    from epi_core.container import EPIContainer
    from epi_gateway.main import _build_settings_from_env, create_app
    from epi_gateway.worker import EvidenceWorker

    _hermetic(monkeypatch, tmp_path)
    monkeypatch.setenv("EPI_DID", "did:web:ignored.example")
    monkeypatch.setenv("EPI_GATEWAY_DID", "did:web:gateway.example")
    monkeypatch.setenv("EPI_GATEWAY_STORAGE_DIR", str(tmp_path / "storage"))
    case_id = _store_case(tmp_path / "storage")
    settings = _build_settings_from_env()
    assert settings.did_web == "did:web:gateway.example"

    app_ = create_app(worker=EvidenceWorker(storage_dir=tmp_path / "storage"), settings=settings)
    with TestClient(app_) as client:
        response = client.post(f"/api/cases/{case_id}/export")
    assert response.status_code == 200, response.text
    out = tmp_path / "api.epi"
    out.write_bytes(response.content)
    assert EPIContainer.read_manifest(out).governance["did"] == "did:web:gateway.example"


def test_serve_exports_did_and_witness_and_hides_secret(monkeypatch, tmp_path):
    _hermetic(monkeypatch, tmp_path)
    seen = {}

    def _fake_run(target, **kwargs):  # noqa: ANN001, ANN003 - monkeypatch stub
        from epi_gateway.main import _build_settings_from_env

        settings = _build_settings_from_env()
        seen["env_did"] = os.environ.get("EPI_GATEWAY_DID")
        seen["did"] = settings.did_web
        seen["witness_url"] = settings.witness_url
        seen["witness_secret"] = settings.witness_secret

    monkeypatch.setattr("uvicorn.run", _fake_run)
    result = runner.invoke(
        app,
        [
            "gateway", "serve", "--storage-dir", str(tmp_path),
            "--did", "did:web:vendor.example",
            "--witness-url", "http://127.0.0.1:8099/witness",
            "--witness-secret", "serve-secret",
        ],
    )
    output = _plain(result.output)

    assert result.exit_code == 0, output
    assert "DID: did:web:vendor.example" in output
    assert "Witness: http://127.0.0.1:8099/witness" in output
    assert "serve-secret" not in output
    assert seen == {
        "env_did": "did:web:vendor.example",
        "did": "did:web:vendor.example",
        "witness_url": "http://127.0.0.1:8099/witness",
        "witness_secret": "serve-secret",
    }
    # Restored after serve returns.
    assert os.environ.get("EPI_GATEWAY_DID") is None
