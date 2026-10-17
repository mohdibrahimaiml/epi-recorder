"""`epi record` reports to the customer witness (like the Python API does).

Before this fix the CLI seal path never called report_seal: a vendor who
followed the dashboard's `epi record -- python app.py` step sent nothing
to the witness inbox, no matter what EPI_WITNESS_URL/SECRET said.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import sys
import threading
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

    return HTTPServer(("127.0.0.1", 0), Handler)


def _serve(secret: str, tmp_path: Path):
    log_path = tmp_path / "received.jsonl"
    server = _hmac_server({"secret": secret}, log_path)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_port}/"
    return server, url, log_path


def test_record_reports_to_witness(monkeypatch, tmp_path):
    _hermetic(monkeypatch, tmp_path)
    server, url, log_path = _serve("customer-secret", tmp_path)
    monkeypatch.setenv("EPI_WITNESS_URL", url)
    monkeypatch.setenv("EPI_WITNESS_SECRET", "customer-secret")
    try:
        epi = tmp_path / "run.epi"
        result = runner.invoke(
            cli_app,
            ["record", "--out", str(epi), "--", sys.executable, "-c", "pass"],
        )
        assert result.exit_code == 0, result.output
        assert "Witness: delivered to" in result.output
        lines = log_path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1
        assert json.loads(lines[0])["schema"] == "epi-witness/v1"
    finally:
        server.shutdown()
        server.server_close()


def test_record_stale_secret_hint_never_fails_seal(monkeypatch, tmp_path):
    _hermetic(monkeypatch, tmp_path)
    server, url, log_path = _serve("new-secret", tmp_path)
    monkeypatch.setenv("EPI_WITNESS_URL", url)
    monkeypatch.setenv("EPI_WITNESS_SECRET", "old-secret")
    try:
        epi = tmp_path / "run.epi"
        result = runner.invoke(
            cli_app,
            ["record", "--out", str(epi), "--", sys.executable, "-c", "pass"],
        )
        # The seal still succeeds (exit 0); the report stays queued with a
        # clear rotation hint instead of a silent failure.
        assert result.exit_code == 0, result.output
        assert ROT_MSG in result.output
        assert not log_path.exists()
    finally:
        server.shutdown()
        server.server_close()


def test_record_without_witness_env_stays_quiet(monkeypatch, tmp_path):
    _hermetic(monkeypatch, tmp_path)
    epi = tmp_path / "run.epi"
    result = runner.invoke(
        cli_app, ["record", "--out", str(epi), "--", sys.executable, "-c", "pass"]
    )
    assert result.exit_code == 0, result.output
    assert "Witness:" not in result.output
