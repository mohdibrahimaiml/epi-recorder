"""M4 customer-owned storage: SigV4 unit tests (botocore cross-check + stub).

Fail-first suite for epi_core/storage_sink.py. Interop against a real
S3-speaking server lives in tests/test_storage_interop.py (moto/MinIO).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


def _sigv4_key(secret: str, date: str, region: str, service: str = "s3") -> bytes:
    k_date = hmac.new(f"AWS4{secret}".encode(), date.encode(), hashlib.sha256).digest()
    k_region = hmac.new(k_date, region.encode(), hashlib.sha256).digest()
    k_service = hmac.new(k_region, service.encode(), hashlib.sha256).digest()
    return hmac.new(k_service, b"aws4_request", hashlib.sha256).digest()


class VerifyingStubState:
    """Independent SigV4 verifier (separate code path from the signer)."""

    def __init__(self, access: str, secret: str) -> None:
        self.access = access
        self.secret = secret
        self.objects: dict[str, bytes] = {}
        self.requests: list[dict] = []

    def verify(self, method: str, path: str, headers: dict, body: bytes) -> bool:
        auth = headers.get("authorization", "")
        if not auth.startswith("AWS4-HMAC-SHA256 "):
            return False
        parts = dict(
            p.split("=", 1) for p in auth[len("AWS4-HMAC-SHA256 "):].split(", ") if "=" in p
        )
        try:
            credential = parts["Credential"]
            signed_headers = parts["SignedHeaders"]
            signature = parts["Signature"]
        except KeyError:
            return False
        scope = credential.split("/")
        if len(scope) != 5 or scope[0] != self.access or scope[4] != "aws4_request":
            return False
        date, region, service = scope[1], scope[2], scope[3]
        names = signed_headers.split(";")
        canonical_headers = "".join(f"{n}:{headers[n].strip()}\n" for n in names)
        canonical = "\n".join([
            method, path, "", canonical_headers, signed_headers,
            hashlib.sha256(body).hexdigest(),
        ])
        string_to_sign = "\n".join([
            "AWS4-HMAC-SHA256", headers["x-amz-date"],
            f"{date}/{region}/{service}/aws4_request",
            hashlib.sha256(canonical.encode()).hexdigest(),
        ])
        want = hmac.new(
            _sigv4_key(self.secret, date, region, service),
            string_to_sign.encode(),
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(want, signature)


def _make_stub(state: VerifyingStubState):
    class Handler(BaseHTTPRequestHandler):
        def _reply(self, code: int, body: bytes = b"") -> None:
            self.send_response(code)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if body:
                self.wfile.write(body)

        def do_PUT(self) -> None:
            length = int(self.headers.get("Content-Length", 0) or 0)
            body = self.rfile.read(length) if length else b""
            headers = {k.lower(): v for k, v in dict(self.headers).items()}
            state.requests.append({"method": "PUT", "path": self.path, "headers": headers})
            if not state.verify("PUT", self.path.split("?")[0], headers, body):
                self._reply(403, b"bad signature")
                return
            state.objects[self.path] = body
            self._reply(200)

        def log_message(self, *args) -> None:
            pass

    return Handler


@pytest.fixture()
def stub():
    state = VerifyingStubState("AKID", "SECRET")
    server = ThreadingHTTPServer(("127.0.0.1", 0), _make_stub(state))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield state, f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


def test_parse_storage_url():
    from epi_core.storage_sink import parse_storage_url

    t = parse_storage_url("s3://mybucket/prefix/sub", region="eu-west-1")
    assert t.bucket == "mybucket" and t.prefix == "prefix/sub" and t.region == "eu-west-1"
    assert t.endpoint == "https://mybucket.s3.eu-west-1.amazonaws.com"
    t = parse_storage_url("s3://mybucket")
    assert t.prefix == "" and t.region == "us-east-1"
    assert t.endpoint == "https://mybucket.s3.amazonaws.com"
    t = parse_storage_url("s3://mybucket/p", endpoint="http://127.0.0.1:9000")
    assert t.endpoint == "http://127.0.0.1:9000" and t.bucket == "mybucket"
    with pytest.raises(ValueError, match="region"):
        parse_storage_url("s3://mybucket", region="no such region!!")
    with pytest.raises(ValueError, match="credentials"):
        parse_storage_url("s3://AKID:SECRET@mybucket/prefix")


def test_credentials_env_profile_missing(monkeypatch, tmp_path: Path):
    from epi_core import storage_sink as sink

    monkeypatch.delenv("AWS_ACCESS_KEY_ID", raising=False)
    monkeypatch.delenv("AWS_SECRET_ACCESS_KEY", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    with pytest.raises(LookupError, match="[Cc]redential"):
        sink.load_credentials()
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKID")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "SECRET")
    creds = sink.load_credentials()
    assert creds.access == "AKID" and creds.secret == "SECRET"
    assert "SECRET" not in repr(creds)


def test_sigv4_matches_botocore(monkeypatch):
    """Byte-identical Authorization header to AWS's own signer (frozen time)."""
    import datetime

    import botocore.auth

    from epi_core.storage_sink import sign_v4

    frozen = datetime.datetime(2026, 10, 16, 12, 0, 0)
    monkeypatch.setattr(botocore.auth, "get_current_datetime", lambda: frozen)
    from botocore.awsrequest import AWSRequest
    from botocore.credentials import Credentials

    url = "https://mybucket.s3.us-east-1.amazonaws.com/test.txt"
    headers = {"x-amz-content-sha256": "abc", "Content-Length": "5"}
    req = AWSRequest(method="PUT", url=url, data=b"hello", headers=dict(headers))
    botocore.auth.SigV4Auth(Credentials("AKID", "SECRET"), "s3", "us-east-1").add_auth(req)
    mine = sign_v4(
        "AKID", "SECRET", "us-east-1", "PUT", url, dict(headers), b"hello",
        amz_date="20261016T120000Z",
    )
    assert mine["Authorization"] == req.headers["Authorization"]
    assert mine["x-amz-date"] == "20261016T120000Z"


def test_put_roundtrip_against_verifying_stub(stub, monkeypatch):
    from epi_core import storage_sink as sink

    state, base = stub
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKID")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "SECRET")
    target = sink.parse_storage_url("s3://mybucket/prefix", endpoint=base)
    sink.put_object(b"hello world", "prefix/a.bin", target, sink.load_credentials())
    assert state.objects["/mybucket/prefix/a.bin"] == b"hello world"
    assert len(state.requests) == 1


def test_outbox_queues_offline_and_flushes_later(tmp_path: Path, monkeypatch):
    from epi_core import storage_sink as sink

    home = tmp_path / "home"
    monkeypatch.setenv("EPI_HOME", str(home))
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKID")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "SECRET")
    target = sink.parse_storage_url("s3://mybucket/p", endpoint="http://127.0.0.1:9")
    entry = sink.queue_storage_upload("/tmp/run.epi", "abc123", target)
    assert entry["pending"] is True
    outbox = (home / "storage_outbox.jsonl").read_text()
    assert "SECRET" not in outbox and "AKID" not in outbox
    assert sink.pending_uploads() != []
    # flush fails closed (endpoint dead) but keeps the entry
    assert sink.flush_storage_outbox() == {"delivered": 0, "failed": 1}
    assert sink.pending_uploads() != []


def test_heartbeat_has_no_file_data_or_secrets():
    from epi_core.storage_sink import heartbeat_payload

    hb = heartbeat_payload(ok=True, count=3, object_lock="unknown")
    assert hb["ok"] is True and hb["count"] == 3
    assert set(hb) <= {"ok", "count", "object_lock", "checked_at"}
    assert "SECRET" not in json.dumps(hb)


def test_redact_url():
    from epi_core.storage_sink import redact_url

    assert redact_url("https://AKID:SECRET@host.example/bkt") == "https://host.example/bkt"
    assert redact_url("https://host.example/bkt") == "https://host.example/bkt"


def _hermetic(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("EPI_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("EPI_KEYS_DIR", str(tmp_path / "home" / "keys"))
    monkeypatch.setenv("EPI_NOTARIZE", "0")
    monkeypatch.setenv("EPI_CHECKPOINTS_ENABLED", "0")


def _sealed_run(monkeypatch, tmp_path: Path, out: Path, **kwargs) -> Path:
    from epi_recorder import record

    with record(str(out), **kwargs) as epi:
        epi.log_step("llm.request", {"content": "hello"})
    return out


def test_record_uploads_when_configured(monkeypatch, tmp_path: Path):
    import hashlib

    _hermetic(monkeypatch, tmp_path)
    import threading
    from http.server import ThreadingHTTPServer

    state = VerifyingStubState("AKID", "SECRET")
    server = ThreadingHTTPServer(("127.0.0.1", 0), _make_stub(state))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        monkeypatch.setenv("EPI_STORAGE_URL", "s3://mybucket/runs")
        monkeypatch.setenv("EPI_STORAGE_ENDPOINT", f"http://127.0.0.1:{server.server_port}")
        monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKID")
        monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "SECRET")
        out = _sealed_run(monkeypatch, tmp_path, tmp_path / "run.epi")
        digest = hashlib.sha256(out.read_bytes()).hexdigest()
        assert state.objects[f"/mybucket/runs/{digest}.epi"] == out.read_bytes()
    finally:
        server.shutdown()


def test_record_is_noop_without_config(monkeypatch, tmp_path: Path):
    from epi_core import storage_sink as sink

    _hermetic(monkeypatch, tmp_path)
    monkeypatch.delenv("EPI_STORAGE_URL", raising=False)
    out = _sealed_run(monkeypatch, tmp_path, tmp_path / "run.epi")
    assert out.is_file()
    assert not sink.storage_outbox_path().exists()


def test_record_survives_dead_storage(monkeypatch, tmp_path: Path):
    from epi_core import storage_sink as sink

    _hermetic(monkeypatch, tmp_path)
    monkeypatch.setenv("EPI_STORAGE_URL", "s3://mybucket/runs")
    monkeypatch.setenv("EPI_STORAGE_ENDPOINT", "http://127.0.0.1:9")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKID")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "SECRET")
    monkeypatch.setenv("EPI_STORAGE_TIMEOUT", "3")
    out = _sealed_run(monkeypatch, tmp_path, tmp_path / "run.epi")
    assert out.is_file()  # seal succeeds; the upload waits in the outbox
    assert sink.pending_uploads() != []


def _sealed_bytes(out: Path) -> tuple[str, bytes]:
    import hashlib

    raw = out.read_bytes()
    return hashlib.sha256(raw).hexdigest(), raw


def test_queued_uploads_flush_on_next_healthy_seal(monkeypatch, tmp_path: Path):
    """Outage → 2 runs queued → storage back → 1 run → all 3 land, queue empty."""
    import socket
    import threading
    from http.server import ThreadingHTTPServer

    from epi_core import storage_sink as sink

    _hermetic(monkeypatch, tmp_path)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        port = int(s.getsockname()[1])
    base = f"http://127.0.0.1:{port}"
    monkeypatch.setenv("EPI_STORAGE_URL", "s3://mybucket/runs")
    monkeypatch.setenv("EPI_STORAGE_ENDPOINT", base)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKID")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "SECRET")
    monkeypatch.setenv("EPI_STORAGE_TIMEOUT", "5")

    # Storage down: two seals succeed and queue.
    sealed: list[tuple[str, bytes]] = []
    for i in range(2):
        out = _sealed_run(monkeypatch, tmp_path, tmp_path / f"down-{i}.epi")
        sealed.append(_sealed_bytes(out))
    assert len(sink.pending_uploads()) == 2

    # Storage back on the same endpoint: the next seal piggybacks the queue.
    state = VerifyingStubState("AKID", "SECRET")
    server = ThreadingHTTPServer(("127.0.0.1", port), _make_stub(state))
    server.allow_reuse_address = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        out = _sealed_run(monkeypatch, tmp_path, tmp_path / "up.epi")
        sealed.append(_sealed_bytes(out))
        for digest, raw in sealed:
            assert state.objects.get(f"/mybucket/runs/{digest}.epi") == raw
        assert sink.pending_uploads() == []
    finally:
        server.shutdown()
