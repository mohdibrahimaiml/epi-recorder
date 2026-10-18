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


def _serve(secret: str, tmp_path: Path, name: str = "received.jsonl"):
    log_path = tmp_path / name
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


def test_webhook_posts_carry_epi_user_agent(monkeypatch):
    """Cloudflare blocks bare urllib: every urllib POST must identify as epi-recorder."""
    import urllib.request as _url

    from epi_core import __version__ as _v
    from epi_core import webhook as _wh

    seen: dict = {}

    class _Resp:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def _fake(req, timeout=None):
        seen.update({k.lower(): v for k, v in req.header_items()})
        return _Resp()

    monkeypatch.setattr(_url, "urlopen", _fake)
    _wh._post_once(
        "http://127.0.0.1:9/w/inb_x", {"a": 1},
        secret="s", extra_headers=None, timeout_seconds=1,
    )
    assert seen.get("user-agent") == f"epi-recorder/{_v}", seen
    seen.clear()
    _wh.send_signed_webhook(
        "http://127.0.0.1:9/hook", {"a": 1}, secret="s", timeout_seconds=1
    )
    assert seen.get("user-agent") == f"epi-recorder/{_v}", seen


def _write_cloud_json(home: Path, url: str, secret: str | None) -> None:
    home.mkdir(parents=True, exist_ok=True)
    cfg = {
        "url": "https://cloud.test", "org_id": "org_1", "api_key": "epik_x",
        "customer": "Test Bank", "witness_url": url,
    }
    if secret is not None:
        cfg["witness_secret"] = secret
    (home / "cloud.json").write_text(json.dumps(cfg), encoding="utf-8")


def test_saved_witness_pair_ignores_stale_env_secret(monkeypatch, tmp_path):
    """Same-source rule: saved url pairs with the saved secret, never a stale env secret."""
    _hermetic(monkeypatch, tmp_path)
    server, url, log_path = _serve("cloud-secret", tmp_path)
    monkeypatch.setenv("EPI_WITNESS_SECRET", "stale-env-secret")
    _write_cloud_json(tmp_path / "home", url, "cloud-secret")
    try:
        epi = tmp_path / "run.epi"
        result = runner.invoke(
            cli_app, ["record", "--out", str(epi), "--", sys.executable, "-c", "pass"]
        )
        assert result.exit_code == 0, result.output
        assert "Witness: delivered to" in result.output, result.output
        assert json.loads(log_path.read_text(encoding="utf-8").splitlines()[0])["schema"] == "epi-witness/v1"
    finally:
        server.shutdown()
        server.server_close()


def test_explicit_env_url_uses_env_secret(monkeypatch, tmp_path):
    """Same-source rule: an explicit env url pairs with the env secret, ignoring cloud.json."""
    _hermetic(monkeypatch, tmp_path)
    server, env_url, log_path = _serve("env-secret", tmp_path, "env.jsonl")
    cloud_server, cloud_url, cloud_log = _serve("cloud-secret", tmp_path, "cloud.jsonl")
    monkeypatch.setenv("EPI_WITNESS_URL", env_url)
    monkeypatch.setenv("EPI_WITNESS_SECRET", "env-secret")
    _write_cloud_json(tmp_path / "home", cloud_url, "cloud-secret")
    try:
        epi = tmp_path / "run.epi"
        result = runner.invoke(
            cli_app, ["record", "--out", str(epi), "--", sys.executable, "-c", "pass"]
        )
        assert result.exit_code == 0, result.output
        assert f"Witness: delivered to {env_url}" in result.output, result.output
        assert log_path.exists()
        assert not cloud_log.exists()
    finally:
        server.shutdown()
        server.server_close()
        cloud_server.shutdown()
        cloud_server.server_close()


def test_cloud_login_401_hint_says_relogin(monkeypatch, tmp_path):
    """Cloud-login users with a rejected secret are told to re-run login, not hunt env vars."""
    _hermetic(monkeypatch, tmp_path)
    server, url, _ = _serve("server-secret", tmp_path)
    _write_cloud_json(tmp_path / "home", url, "rotated-secret")
    try:
        epi = tmp_path / "run.epi"
        result = runner.invoke(
            cli_app, ["record", "--out", str(epi), "--", sys.executable, "-c", "pass"]
        )
        assert result.exit_code == 0, result.output
        assert "re-run epi cloud login" in result.output, result.output
        assert "update EPI_WITNESS_SECRET" not in result.output
    finally:
        server.shutdown()
        server.server_close()


def _forbidden_server(tmp_path: Path):
    """Always-403 receiver (like an edge firewall, never the witness logic)."""

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            length = int(self.headers.get("Content-Length", "0"))
            self.rfile.read(length)
            self.send_response(403)
            self.end_headers()
            self.wfile.write(b"Forbidden")

        def log_message(self, *args):  # silence stdlib logging
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_port}/"


def test_forbidden_stamp_says_blocked_not_secret(monkeypatch, tmp_path):
    """A 403 was blocked before reaching EPI Cloud: say so, never blame the secret."""
    _hermetic(monkeypatch, tmp_path)
    server, url = _forbidden_server(tmp_path)
    monkeypatch.setenv("EPI_WITNESS_URL", url)
    monkeypatch.setenv("EPI_WITNESS_SECRET", "s")
    try:
        epi = tmp_path / "run.epi"
        result = runner.invoke(
            cli_app, ["record", "--out", str(epi), "--", sys.executable, "-c", "pass"]
        )
        assert result.exit_code == 0, result.output
        assert "blocked before reaching EPI Cloud" in result.output, result.output
        assert "secret changed" not in result.output
        assert "queued" in result.output.lower()
        flushed = runner.invoke(cli_app, ["witness", "flush"])
        assert "Blocked before reaching" in flushed.output, flushed.output
        assert "secret changed" not in flushed.output
    finally:
        server.shutdown()
        server.server_close()
