"""Witness secret rotation: queued reports are re-signed at send time.

- The outbox never stores the HMAC secret (sign-at-send, not sign-at-queue).
- After a rotation, flushing the same queued entry with the NEW secret delivers;
  with the OLD secret it fails 401 with a clear message containing
  "witness secret changed — update EPI_WITNESS_SECRET" (never a silent failure).
- Failure logs never contain the secret.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from typer.testing import CliRunner

from epi_cli.main import app as cli_app

runner = CliRunner()
ROT_MSG = "witness secret changed — update EPI_WITNESS_SECRET"


def _hermetic(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("EPI_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("EPI_KEYS_DIR", str(tmp_path / "home" / "keys"))
    monkeypatch.setenv("EPI_NOTARIZE", "0")
    monkeypatch.setenv("EPI_CHECKPOINTS_ENABLED", "0")
    for key in ("EPI_WITNESS_URL", "EPI_WITNESS_SECRET"):
        monkeypatch.delenv(key, raising=False)


def _payload(workflow_id: str = "wf-rotate-1") -> dict:
    from epi_core.webhook import build_witness_payload

    return build_witness_payload(
        workflow_id=workflow_id,
        manifest_hash="a" * 64,
        file_sha256="b" * 64,
        public_key=None,
        content_digest="c" * 64,
        key_fingerprint=None,
        steps=1,
        sealed_at="2026-10-17T00:00:00+00:00",
        seal_timestamp={"source": "local"},
    )


def _hmac_server(secret_holder: dict, log_path: Path):
    """Minimal HMAC-checking witness receiver (like cloud /w/:inboxId)."""

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length)
            sig = self.headers.get("X-EPI-Signature", "")
            want = (
                "sha256="
                + hmac.new(secret_holder["secret"].encode(), raw, hashlib.sha256).hexdigest()
            )
            if not hmac.compare_digest(sig, want):
                self.send_response(401)
                self.end_headers()
                self.wfile.write(b"Bad or missing X-EPI-Signature HMAC.")
                return
            with open(log_path, "ab") as f:
                f.write(raw + b"\n")
            self.send_response(202)
            self.end_headers()
            self.wfile.write(b'{"accepted": true}')

        def log_message(self, *args):  # silence stdlib logging
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    return server


def test_queued_report_resigned_at_send_time(monkeypatch, tmp_path, caplog):
    """Queue with old secret, rotate, flush with new secret delivers."""
    import threading

    _hermetic(monkeypatch, tmp_path)
    from epi_core import webhook as wh

    log_path = tmp_path / "received.jsonl"
    holder = {"secret": "old-secret-AAAA"}
    server = _hmac_server(holder, log_path)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_port}/"
    try:
        # Stage (queue) while the old secret is active. The entry must not
        # embed the secret: HMAC is computed at send time.
        entry = wh.append_outbox_entry(_payload(), [url], path=wh.outbox_path())
        assert entry["payload"]["workflow_id"] == "wf-rotate-1"
        stored = wh.read_outbox(wh.outbox_path())[0]
        blob = json.dumps(stored)
        assert "old-secret-AAAA" not in blob
        assert "new-secret-BBBB" not in blob

        # Old secret still delivers before rotation.
        with caplog.at_level(logging.WARNING, logger="epi.witness"):
            res_old = wh.deliver_entry(entry, secret="old-secret-AAAA", path=wh.outbox_path())
        assert res_old["delivered"] == [url]
        assert len(log_path.read_bytes().splitlines()) == 1

        # Queue another report, then rotate the receiver secret.
        entry2 = wh.append_outbox_entry(_payload("wf-rotate-2"), [url], path=wh.outbox_path())
        holder["secret"] = "new-secret-BBBB"

        # Flushing with the STALE secret fails 401 (clear message, no silence).
        with caplog.at_level(logging.WARNING, logger="epi.witness"):
            stale = wh.deliver_entry(entry2, secret="old-secret-AAAA", path=wh.outbox_path())
        assert stale["delivered"] == []
        assert len(stale["failed"]) == 1
        err = next(iter(stale["failed"].values()))
        assert "401" in err

        # CLI flush surfaces the rotation hint without leaking the secret.
        monkeypatch.setenv("EPI_WITNESS_SECRET", "old-secret-AAAA")
        result = runner.invoke(cli_app, ["witness", "flush"])
        assert result.exit_code == 1
        assert ROT_MSG in result.output
        assert "old-secret-AAAA" not in result.output
        assert "new-secret-BBBB" not in result.output

        # Flushing with the NEW secret delivers the same queued entry.
        with caplog.at_level(logging.WARNING, logger="epi.witness"):
            last = wh.read_outbox(wh.outbox_path())[-1]
            fresh = wh.deliver_entry(last, secret="new-secret-BBBB", path=wh.outbox_path())
        assert fresh["delivered"] == [url]
        assert len(log_path.read_bytes().splitlines()) == 2

        # No log record ever contained either secret.
        for rec in caplog.records:
            text = rec.getMessage()
            assert "old-secret-AAAA" not in text
            assert "new-secret-BBBB" not in text
    finally:
        server.shutdown()
        server.server_close()


def test_flush_logs_never_contain_secret(monkeypatch, tmp_path, caplog):
    """Force delivery errors; assert logs contain no secret/key/token."""
    import threading

    _hermetic(monkeypatch, tmp_path)
    from epi_core import webhook as wh

    secret = "super-secret-XYZ-123"
    log_path = tmp_path / "received.jsonl"
    holder = {"secret": "different-secret"}
    server = _hmac_server(holder, log_path)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_port}/"
    try:
        wh.append_outbox_entry(_payload(), [url], path=wh.outbox_path())
        with caplog.at_level(logging.WARNING, logger="epi.witness"):
            summary = wh.flush_outbox(secret=secret, path=wh.outbox_path())
        # 401 is recorded, never silently dropped.
        assert len(summary["failed"]) == 1
        assert "401" in next(iter(summary["failed"].values()))
        blob = "\n".join(r.getMessage() for r in caplog.records)
        assert secret not in blob
        # The persisted outbox error also never embeds the secret.
        stored_blob = json.dumps(wh.read_outbox(wh.outbox_path()))
        assert secret not in stored_blob
    finally:
        server.shutdown()
        server.server_close()


def test_seal_outcome_hint_names_rotation(monkeypatch, tmp_path, capsys):
    """record() QUEUED line tells the user to update EPI_WITNESS_SECRET."""
    _hermetic(monkeypatch, tmp_path)
    from epi_recorder.api import _print_witness_outcome

    _print_witness_outcome(
        {"_outcome": {"failed": {"http://witness.test/": "HTTP Error 401: Unauthorized"}}}
    )
    err = capsys.readouterr().err
    assert ROT_MSG in err
    assert "EPI_WITNESS_SECRET" in err
