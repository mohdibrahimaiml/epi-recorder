"""Customer witness on every seal (WP1b). Local HTTP servers only, no external network."""

from __future__ import annotations

import hashlib
import hmac
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest
from typer.testing import CliRunner

from epi_cli.main import app as cli_app

runner = CliRunner()

SECRET = "customer-shared-secret"


class CaptureHandler(BaseHTTPRequestHandler):
    received: list = []

    def do_POST(self):  # noqa: N802 (http.server convention)
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            CaptureHandler.received.append(
                {"path": self.path, "headers": dict(self.headers), "body": body}
            )
            self.send_response(200)
            self.end_headers()
        except Exception:
            self.send_response(500)
            self.end_headers()

    def log_message(self, *args):
        pass


def _serve() -> tuple[HTTPServer, str]:
    CaptureHandler.received = []
    server = HTTPServer(("127.0.0.1", 0), CaptureHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, f"http://127.0.0.1:{server.server_port}/witness"


def _hermetic(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("EPI_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("EPI_KEYS_DIR", str(tmp_path / "home" / "keys"))
    monkeypatch.setenv("EPI_NOTARIZE", "0")
    monkeypatch.setenv("EPI_CHECKPOINTS_ENABLED", "0")


def _seal(monkeypatch, tmp_path: Path, out: Path, **kwargs) -> Path:
    from epi_recorder import record

    with record(str(out), **kwargs) as epi:
        epi.log_step("llm.request", {"content": "hello"})
    return out


def test_payload_hashes_and_both_signatures(monkeypatch, tmp_path: Path) -> None:
    _hermetic(monkeypatch, tmp_path)
    server, url = _serve()
    try:
        out = tmp_path / "run.epi"
        _seal(monkeypatch, tmp_path, out, witness_url=url, witness_secret=SECRET)
        assert len(CaptureHandler.received) == 1
        raw = CaptureHandler.received[0]["body"]
        headers = {k.lower(): v for k, v in CaptureHandler.received[0]["headers"].items()}
        payload = json.loads(raw.decode("utf-8"))

        from epi_core.container import EPIContainer
        from epi_core.keys import KeyManager
        from epi_core.serialize import get_canonical_hash

        manifest = EPIContainer.read_manifest(out)
        assert payload["schema"] == "epi-witness/v1"
        assert payload["type"] == "epi.sealed"
        assert payload["workflow_id"] == str(manifest.workflow_id)
        assert payload["manifest_hash"] == get_canonical_hash(
            manifest, exclude_fields=["signature"]
        )
        assert payload["file_sha256"] == hashlib.sha256(out.read_bytes()).hexdigest()
        assert payload["public_key"] == manifest.public_key
        assert payload["key_fingerprint"] == hashlib.sha256(
            str(manifest.public_key).encode()
        ).hexdigest()[:16]
        assert payload["steps"] == manifest.total_steps
        assert "goal" not in payload  # omitted by default
        assert payload["seal_timestamp"]["status"] == "none"  # EPI_NOTARIZE=0 here

        # HMAC header verifies.
        want_hmac = hmac.new(SECRET.encode(), raw, hashlib.sha256).hexdigest()
        assert headers["x-epi-signature"] == f"sha256={want_hmac}"

        # Ed25519 seal-signature header verifies with the vendor key.
        seal_header = headers["x-epi-seal-signature"]
        assert seal_header.startswith("ed25519:default:")
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

        public = Ed25519PublicKey.from_public_bytes(
            KeyManager().load_public_key("default")
        )
        public.verify(bytes.fromhex(seal_header.rsplit(":", 1)[1]), raw)
    finally:
        server.shutdown()


def test_endpoint_down_seal_succeeds_and_flush_delivers(monkeypatch, tmp_path: Path) -> None:
    _hermetic(monkeypatch, tmp_path)
    from epi_core.webhook import outbox_path, read_outbox

    # Reserve a port, then close it: connection refused.
    import socket

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    dead_url = f"http://127.0.0.1:{sock.getsockname()[1]}/witness"
    sock.close()

    out = tmp_path / "run.epi"
    _seal(monkeypatch, tmp_path, out, witness_url=dead_url, witness_secret=SECRET)
    assert out.is_file()  # seal succeeded despite the dead endpoint
    entries = [e for e in read_outbox() if e.get("pending")]
    assert len(entries) == 1
    assert entries[0]["pending"] == [dead_url]

    server, live_url = _serve()
    try:
        # Point the pending entry at the live server, then flush via CLI.
        target = outbox_path()
        text = target.read_text(encoding="utf-8").replace(dead_url, live_url)
        target.write_text(text, encoding="utf-8")
        result = runner.invoke(cli_app, ["witness", "flush"])
        assert result.exit_code == 0, result.output
        assert len(CaptureHandler.received) == 1
        assert not [e for e in read_outbox() if e.get("pending")]
    finally:
        server.shutdown()


def test_witness_log_verdicts(monkeypatch, tmp_path: Path) -> None:
    _hermetic(monkeypatch, tmp_path)
    server, url = _serve()
    try:
        out = tmp_path / "run.epi"
        _seal(monkeypatch, tmp_path, out, witness_url=url, witness_secret=SECRET)
        assert len(CaptureHandler.received) == 1

        received = tmp_path / "received.jsonl"
        received.write_text(
            json.dumps(
                {**json.loads(CaptureHandler.received[0]["body"].decode()),
                 "received_at": "2026-10-11T00:00:00+00:00"}
            )
            + "\n",
            encoding="utf-8",
        )

        # WITNESSED.
        result = runner.invoke(
            cli_app, ["verify", str(out), "--json", "--witness-log", str(received)]
        )
        assert result.exit_code == 0, result.output
        report = json.loads(result.output)
        assert report["witness"]["status"] == "WITNESSED"
        assert report["witness"]["received_at"] == "2026-10-11T00:00:00+00:00"

        # NOT IN WITNESS LOG (different workflow id).
        other = tmp_path / "other.jsonl"
        other.write_text('{"workflow_id": "nope", "manifest_hash": "x"}\n', encoding="utf-8")
        result = runner.invoke(
            cli_app, ["verify", str(out), "--json", "--witness-log", str(other)]
        )
        assert result.exit_code == 0, result.output
        assert json.loads(result.output)["witness"]["status"] == "NOT IN WITNESS LOG"

        # MISMATCH: alter the goal and re-sign with the same key.
        import copy

        from epi_core.container import EPIContainer
        from epi_core.keys import KeyManager
        from epi_core.trust import sign_manifest

        ws = tmp_path / "ws"
        EPIContainer.unpack(out, ws)
        manifest = EPIContainer.read_manifest(out)
        manifest2 = copy.deepcopy(manifest)
        manifest2.goal = "a different goal"
        km = KeyManager()
        out2 = tmp_path / "altered.epi"
        monkeypatch.setenv("EPI_CHECKPOINTS_ENABLED", "0")
        EPIContainer.pack(
            ws,
            manifest2,
            out2,
            signer_function=lambda current: sign_manifest(
                current, km.load_private_key("default"), "default"
            ),
            preserve_generated=True,
        )
        result = runner.invoke(
            cli_app, ["verify", str(out2), "--json", "--witness-log", str(received)]
        )
        assert result.exit_code == 1, result.output
        report = json.loads(result.output)
        assert report["decision"]["status"] == "FAIL"
        assert report["witness"]["status"] == "MISMATCH"

        # Human output carries the verdict.
        result = runner.invoke(
            cli_app, ["verify", str(out), "--witness-log", str(received)]
        )
        assert "WITNESSED" in result.output
    finally:
        server.shutdown()


def test_payload_carries_no_step_content(monkeypatch, tmp_path: Path) -> None:
    _hermetic(monkeypatch, tmp_path)
    server, url = _serve()
    try:
        from epi_recorder import record

        marker = "sk-super-secret-marker-xyz-12345"
        out = tmp_path / "run.epi"
        with record(str(out), witness_url=url) as epi:
            epi.log_step("llm.request", {"content": f"key {marker} inside"})
        assert len(CaptureHandler.received) == 1
        body = CaptureHandler.received[0]["body"].decode("utf-8")
        assert marker not in body
        # Receiver-side: outbox file holds hashes only too.
        from epi_core.webhook import read_outbox

        blob = json.dumps(read_outbox())
        assert marker not in blob
    finally:
        server.shutdown()


def test_concurrent_appends_lose_no_entries(tmp_path: Path) -> None:
    import threading

    from epi_core.webhook import append_outbox_entry, read_outbox

    target = tmp_path / "outbox.jsonl"

    def _worker(n: int) -> None:
        for i in range(10):
            append_outbox_entry({"i": n * 10 + i}, ["http://x/"], path=target)

    threads = [threading.Thread(target=_worker, args=(n,)) for n in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(read_outbox(target)) == 80


def test_witness_status_lists_entries(monkeypatch, tmp_path: Path) -> None:
    _hermetic(monkeypatch, tmp_path)
    server, url = _serve()
    try:
        out = tmp_path / "run.epi"
        _seal(monkeypatch, tmp_path, out, witness_url=url)
        result = runner.invoke(cli_app, ["witness", "status"])
        assert result.exit_code == 0, result.output
        assert "pending" in result.output.lower()
    finally:
        server.shutdown()


def test_gateway_export_witnesses(monkeypatch, tmp_path: Path) -> None:
    """Case export with witness settings delivers a seal report."""
    from fastapi.testclient import TestClient

    from epi_gateway.main import GatewayRuntimeSettings, create_app
    from epi_gateway.worker import EvidenceWorker

    monkeypatch.setenv("EPI_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("EPI_NOTARIZE", "0")
    server, url = _serve()
    try:
        worker = EvidenceWorker(storage_dir=tmp_path, batch_size=1, batch_timeout=0.1)
        settings = GatewayRuntimeSettings(
            storage_dir=str(tmp_path),
            witness_url=url,
            witness_secret=SECRET,
        )
        app = create_app(worker=worker, settings=settings)
        worker.store_items(
            [
                {
                    "case_id": "case-wit-1",
                    "workflow_id": "wf-wit-1",
                    "kind": "agent.run.start",
                    "content": {"goal": "witness me"},
                }
            ]
        )
        with TestClient(app) as client:
            response = client.post("/api/cases/case-wit-1/export")
        assert response.status_code == 200, response.text
        # Delivery is backgrounded; the outbox entry must exist regardless.
        from epi_core.webhook import read_outbox

        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and not CaptureHandler.received:
            time.sleep(0.05)
        assert len(CaptureHandler.received) == 1
        payload = json.loads(CaptureHandler.received[0]["body"].decode())
        assert payload["schema"] == "epi-witness/v1"
        assert payload["workflow_id"]
        assert not [e for e in read_outbox() if e.get("pending")]
    finally:
        server.shutdown()


def test_register_after_witness_is_still_witnessed(monkeypatch, tmp_path: Path) -> None:
    """`epi-register` re-packages the file after the witness; the evidence is unchanged."""
    _hermetic(monkeypatch, tmp_path)
    server, url = _serve()
    try:
        out = tmp_path / "run.epi"
        _seal(monkeypatch, tmp_path, out, witness_url=url, witness_secret=SECRET)
        payload = json.loads(CaptureHandler.received[0]["body"].decode())
        assert payload["content_digest"]
        received = tmp_path / "received.jsonl"
        received.write_text(
            json.dumps({**payload, "received_at": "2026-10-11T00:00:00+00:00"}) + "\n",
            encoding="utf-8",
        )
        before = hashlib.sha256(out.read_bytes()).hexdigest()

        result = runner.invoke(cli_app, ["scitt", "register", str(out), "--local"])
        assert result.exit_code == 0, result.output
        assert hashlib.sha256(out.read_bytes()).hexdigest() != before

        result = runner.invoke(
            cli_app, ["verify", str(out), "--json", "--witness-log", str(received)]
        )
        report = json.loads(result.output)
        assert report["witness"]["status"] == "WITNESSED", report["witness"]
        assert report["witness"].get("repackaged") is True
        assert report["decision"]["status"] != "FAIL"
    finally:
        server.shutdown()

def test_edited_evidence_against_the_customers_log_is_not_called_repackaged(
    monkeypatch, tmp_path: Path
) -> None:
    """A forgery shares the manifest with the real run; only the members differ.

    "Re-packaged" reads as harmless, so a tampered file must never earn it: the
    customer's log has to reject the copy, not reassure the forger.
    """
    import zipfile

    _hermetic(monkeypatch, tmp_path)
    server, url = _serve()
    try:
        out = tmp_path / "run.epi"
        _seal(monkeypatch, tmp_path, out, witness_url=url, witness_secret=SECRET)
        payload = json.loads(CaptureHandler.received[0]["body"].decode())
        received = tmp_path / "received.jsonl"
        received.write_text(
            json.dumps({**payload, "received_at": "2026-10-11T00:00:00+00:00"}) + "\n",
            encoding="utf-8",
        )

        from epi_core.container import EPIContainer

        original_manifest = EPIContainer.read_manifest(out)
        inner = tmp_path / "payload.zip"
        EPIContainer.extract_inner_payload(out, inner)
        with zipfile.ZipFile(inner, "r") as archive:
            order = [info.filename for info in archive.infolist()]
            members = {name: archive.read(name) for name in order}
        forged = members["steps.jsonl"].replace(b"hello", b"forged")
        assert forged != members["steps.jsonl"]
        members["steps.jsonl"] = forged
        with zipfile.ZipFile(inner, "w", zipfile.ZIP_DEFLATED) as archive:
            for name in order:
                compress = (
                    zipfile.ZIP_STORED if name == "mimetype" else zipfile.ZIP_DEFLATED
                )
                archive.writestr(name, members[name], compress_type=compress)
        EPIContainer._write_envelope_from_payload(
            inner, out, manifest=original_manifest
        )

        result = runner.invoke(
            cli_app, ["verify", str(out), "--json", "--witness-log", str(received)]
        )
        report = json.loads(result.output)
        assert report["decision"]["status"] == "FAIL", report["decision"]
        assert report["witness"]["status"] == "MISMATCH", report["witness"]
        assert not report["witness"].get("repackaged")
        assert "altered after the report" in report["witness"]["detail"]
    finally:
        server.shutdown()
