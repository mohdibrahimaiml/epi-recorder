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

    pytest.importorskip("epi_enterprise.gateway.main")
    from epi_enterprise.gateway.main import GatewayRuntimeSettings, create_app
    from epi_enterprise.gateway.worker import EvidenceWorker

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

# ---------------------------------------------------------------------------
# Step 1: seal sequence numbers, audit, heartbeat, re-sign rules
# ---------------------------------------------------------------------------
import zipfile  # noqa: E402

def _payload_at(index: int) -> dict:

    return json.loads(CaptureHandler.received[index]["body"].decode("utf-8"))


def _write_log(path: Path, payloads: list[dict]) -> None:
    path.write_text(
        "".join(
            json.dumps({**payload, "received_at": "2026-11-01T00:00:0%d+00:00" % i})
            + "\n"
            for i, payload in enumerate(payloads)
        ),
        encoding="utf-8",
    )


def _resign_with_other_key(tmp_path: Path, source: Path, key_name: str) -> Path:
    from epi_core.container import EPIContainer
    from epi_core.keys import KeyManager
    from epi_core.trust import sign_manifest

    km = KeyManager()
    if not km.has_key(key_name):
        km.generate_keypair(key_name)
    manifest = EPIContainer.read_manifest(source)
    workspace = tmp_path / f"ws-{key_name}"
    EPIContainer.unpack(source, workspace)
    target = tmp_path / f"resigned-{key_name}.epi"
    EPIContainer.pack(
        workspace,
        manifest,
        target,
        signer_function=lambda current: sign_manifest(
            current, km.load_private_key(key_name), key_name
        ),
        preserve_generated=True,
    )
    return target


def _edit_seal_chain(epi_path: Path) -> None:
    from epi_core.container import EPIContainer

    original = EPIContainer.read_manifest(epi_path)
    inner = epi_path.with_suffix(".inner.zip")
    EPIContainer.extract_inner_payload(epi_path, inner)
    with zipfile.ZipFile(inner, "r") as archive:
        order = [info.filename for info in archive.infolist()]
        members = {name: archive.read(name) for name in order}
    manifest = json.loads(members["manifest.json"])
    chain = json.loads(members["artifacts/seal_chain.json"])
    chain["seal_chain"]["seq"] = int(chain["seal_chain"]["seq"]) + 1
    members["artifacts/seal_chain.json"] = json.dumps(chain, indent=2).encode("utf-8")
    with zipfile.ZipFile(inner, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in order:
            compress = (
                zipfile.ZIP_STORED if name == "mimetype" else zipfile.ZIP_DEFLATED
            )
            archive.writestr(name, members[name], compress_type=compress)
    EPIContainer._write_envelope_from_payload(inner, epi_path, manifest=original)


def test_payload_carries_seal_chain_fields(monkeypatch, tmp_path: Path) -> None:

    _hermetic(monkeypatch, tmp_path)
    server, url = _serve()
    try:
        first = _seal(
            monkeypatch, tmp_path, tmp_path / "one.epi",
            witness_url=url, witness_secret=SECRET,
        )
        second = _seal(
            monkeypatch, tmp_path, tmp_path / "two.epi",
            witness_url=url, witness_secret=SECRET,
        )
        one = _payload_at(0)
        two = _payload_at(1)

        from epi_core.container import EPIContainer

        manifest = EPIContainer.read_manifest(first)
        assert manifest.seal_chain is not None
        assert one["seal_seq"] == manifest.seal_chain.seq == 1
        assert one["ledger_id"] == manifest.seal_chain.ledger_id
        assert one["prev_seq"] == 0
        assert one["prev_content_digest"] == "genesis"

        manifest_two = EPIContainer.read_manifest(second)
        assert two["seal_seq"] == manifest_two.seal_chain.seq == 2
        assert two["ledger_id"] == one["ledger_id"]
        assert two["prev_seq"] == 1
        assert two["prev_content_digest"] == one["content_digest"]
    finally:
        server.shutdown()


def test_editing_seal_chain_breaks_integrity(monkeypatch, tmp_path: Path) -> None:

    _hermetic(monkeypatch, tmp_path)
    sealed = _seal(monkeypatch, tmp_path, tmp_path / "run.epi")
    _edit_seal_chain(sealed)

    from epi_core.container import EPIContainer

    # The chain is a member listed in file_manifest. Editing it changes the
    # member hash, so integrity fails even though the manifest signature (over
    # file_manifest) is unchanged. Both old and new verifiers must catch it.
    ok, mismatches = EPIContainer.verify_integrity(sealed)
    assert ok is False
    assert "artifacts/seal_chain.json" in mismatches


def test_audit_reports_a_missing_number_and_exits_1(
    monkeypatch, tmp_path: Path
) -> None:

    _hermetic(monkeypatch, tmp_path)
    server, url = _serve()
    try:
        for name in ("one.epi", "two.epi", "three.epi"):
            _seal(
                monkeypatch, tmp_path, tmp_path / name,
                witness_url=url, witness_secret=SECRET,
            )
        log = tmp_path / "received.jsonl"
        _write_log(log, [_payload_at(0), _payload_at(1), _payload_at(2)])

        clean = runner.invoke(cli_app, ["witness", "audit", str(log)])
        assert clean.exit_code == 0, clean.output
        assert "MISSING" not in clean.output

        lines = log.read_text(encoding="utf-8").splitlines()
        log.write_text("\n".join([lines[0], lines[2]]) + "\n", encoding="utf-8")

        result = runner.invoke(cli_app, ["witness", "audit", str(log)])
        assert result.exit_code == 1, result.output
        assert "MISSING #2" in result.output
    finally:
        server.shutdown()


def test_verify_shows_the_sequence_and_old_files_are_unsequenced(
    monkeypatch, tmp_path: Path
) -> None:

    _hermetic(monkeypatch, tmp_path)
    server, url = _serve()
    try:
        sealed = _seal(
            monkeypatch, tmp_path, tmp_path / "run.epi",
            witness_url=url, witness_secret=SECRET,
        )
        log = tmp_path / "received.jsonl"
        _write_log(log, [_payload_at(0)])

        result = runner.invoke(
            cli_app, ["verify", str(sealed), "--json", "--witness-log", str(log)]
        )
        assert result.exit_code == 0, result.output
        sequence = json.loads(result.output)["witness"]["sequence"]
        assert sequence["present"] is True
        assert sequence["seq"] == 1
        assert sequence["in_log"] is True
        assert sequence["contiguous"] is True

        human = runner.invoke(
            cli_app, ["verify", str(sealed), "--witness-log", str(log)]
        )
        assert "Sequence:" in human.output
        assert "#1 of chain" in human.output

        # An old artifact has no chain: display says so, verdict is unchanged.
        from epi_cli.verify import _check_witness_log, _format_sequence_line
        from epi_core.container import EPIContainer

        golden = (
            Path(__file__).resolve().parent / "goldens" / "legacy-spec-4.4.0.epi"
        )
        golden_manifest = EPIContainer.read_manifest(golden)
        check = _check_witness_log(golden, golden_manifest, log)
        assert check["sequence"]["present"] is False
        assert "not present" in _format_sequence_line(check["sequence"])
        assert check["status"] == "NOT IN WITNESS LOG"
    finally:
        server.shutdown()


def test_heartbeat_is_signed_accepted_and_reveals_a_tail_gap(
    monkeypatch, tmp_path: Path
) -> None:

    _hermetic(monkeypatch, tmp_path)
    server, url = _serve()
    try:
        _seal(
            monkeypatch, tmp_path, tmp_path / "run.epi",
            witness_url=url, witness_secret=SECRET,
        )
        monkeypatch.setenv("EPI_WITNESS_URL", url)
        monkeypatch.setenv("EPI_WITNESS_SECRET", SECRET)

        result = runner.invoke(cli_app, ["witness", "heartbeat", "--key", "default"])
        assert result.exit_code == 0, result.output
        payloads = [_payload_at(i) for i in range(len(CaptureHandler.received))]
        heartbeat = next(p for p in payloads if p.get("type") == "epi.heartbeat")
        assert heartbeat["schema"] == "epi-witness/v1"
        assert heartbeat["last_seq"] == 1
        assert heartbeat["ledger_id"]
        assert heartbeat["key_fingerprint"]

        seal_report = next(p for p in payloads if p.get("type") == "epi.sealed")
        # The heartbeat alone reveals a tail the customer never received.
        heartbeat["last_seq"] = 3
        log = tmp_path / "received.jsonl"
        _write_log(log, [seal_report, heartbeat])
        audit = runner.invoke(cli_app, ["witness", "audit", str(log)])
        assert audit.exit_code == 1, audit.output
        assert "TAIL GAP" in audit.output
    finally:
        server.shutdown()


def _received_bodies() -> list:

    return CaptureHandler.received


def test_heartbeat_to_an_older_receiver_is_not_retried_forever(
    monkeypatch, tmp_path: Path
) -> None:
    from tests.test_seal_witness import SECRET, _hermetic, _seal

    _hermetic(monkeypatch, tmp_path)
    _seal(monkeypatch, tmp_path, tmp_path / "run.epi")

    class OldReceiver(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802 (http.server convention)
            length = int(self.headers.get("Content-Length", 0))
            self.rfile.read(length)
            self.send_response(400)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), OldReceiver)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_port}/witness"
        result = runner.invoke(
            cli_app,
            ["witness", "heartbeat", "--url", url, "--secret", SECRET, "--timeout", "5"],
        )
        assert result.exit_code == 1, result.output
        assert "doesn't accept heartbeats yet" in result.output

        from epi_core.webhook import read_outbox

        assert not [entry for entry in read_outbox() if entry.get("pending")]
    finally:
        server.shutdown()


def test_resigning_with_a_different_key_allocates_a_new_chain(
    monkeypatch, tmp_path: Path
) -> None:

    _hermetic(monkeypatch, tmp_path)
    sealed = _seal(monkeypatch, tmp_path, tmp_path / "run.epi")

    from epi_core.container import EPIContainer
    from epi_core.keys import KeyManager, key_fingerprint

    original = EPIContainer.read_manifest(sealed)
    resigned = _resign_with_other_key(tmp_path, sealed, "other")
    manifest = EPIContainer.read_manifest(resigned)
    fingerprint = key_fingerprint(
        KeyManager().load_public_key("other").hex(), grouped=False
    )

    assert manifest.seal_chain is not None
    assert original.seal_chain is not None
    assert manifest.seal_chain.key_fingerprint == fingerprint
    assert manifest.seal_chain.key_fingerprint != original.seal_chain.key_fingerprint
    assert manifest.seal_chain.ledger_id != original.seal_chain.ledger_id
    assert manifest.seal_chain.seq == 1


def test_same_key_reseal_of_altered_content_surfaces_as_fork(
    monkeypatch, tmp_path: Path
) -> None:

    _hermetic(monkeypatch, tmp_path)
    server, url = _serve()
    try:
        sealed = _seal(
            monkeypatch, tmp_path, tmp_path / "run.epi",
            witness_url=url, witness_secret=SECRET,
        )
        genuine = _payload_at(0)

        from epi_core.container import EPIContainer
        from epi_core.keys import KeyManager
        from epi_core.trust import sign_manifest
        from epi_core.webhook import report_seal

        km = KeyManager()
        manifest = EPIContainer.read_manifest(sealed)
        manifest.goal = "a different decision"
        workspace = tmp_path / "ws-fork"
        EPIContainer.unpack(sealed, workspace)
        altered = tmp_path / "altered.epi"
        EPIContainer.pack(
            workspace,
            manifest,
            altered,
            signer_function=lambda current: sign_manifest(
                current, km.load_private_key("default"), "default"
            ),
            preserve_generated=True,
        )
        # Same key, same seal number, different content: reported as a seal.
        report_seal(
            altered,
            urls=[url],
            secret=SECRET,
            key_name="default",
            signer=km.load_private_key("default"),
        )
        altered_report = _payload_at(1)
        assert altered_report["seal_seq"] == genuine["seal_seq"]
        assert altered_report["content_digest"] != genuine["content_digest"]

        log = tmp_path / "received.jsonl"
        _write_log(log, [genuine, altered_report])
        audit = runner.invoke(cli_app, ["witness", "audit", str(log)])
        assert audit.exit_code == 1, audit.output
        assert "FORK at #1" in audit.output
    finally:
        server.shutdown()


def test_audit_json_and_strict_burn_exit_codes(monkeypatch, tmp_path: Path) -> None:
    log = tmp_path / "received.jsonl"
    report = {
        "schema": "epi-witness/v1",
        "type": "epi.sealed",
        "seal_seq": 1,
        "ledger_id": "led-1",
        "key_fingerprint": "kf",
        "prev_seq": 0,
        "prev_content_digest": "genesis",
        "content_digest": "d1",
        "workflow_id": "w1",
    }
    heartbeat = {
        "schema": "epi-witness/v1",
        "type": "epi.heartbeat",
        "ledger_id": "led-1",
        "key_fingerprint": "kf",
        "last_seq": 2,
        "burned_seqs": [2],
    }
    log.write_text(
        json.dumps(report) + "\n" + json.dumps(heartbeat) + "\n", encoding="utf-8"
    )

    default = runner.invoke(cli_app, ["witness", "audit", str(log)])
    assert default.exit_code == 0, default.output
    assert "BURNED #2" in default.output

    strict = runner.invoke(cli_app, ["witness", "audit", str(log), "--strict"])
    assert strict.exit_code == 1, strict.output

    machine = runner.invoke(cli_app, ["witness", "audit", str(log), "--json"])
    assert machine.exit_code == 0, machine.output
    parsed = json.loads(machine.output)
    assert parsed["warnings"]["burned"] == 1
    assert parsed["chains"][0]["burned"] == [2]
