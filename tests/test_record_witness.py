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
REPO = Path(__file__).resolve().parents[1]


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


def test_flush_uses_saved_cloud_login_secret(monkeypatch, tmp_path):
    """Flush with no --secret/env secret delivers via the saved cloud-login secret."""
    from epi_core import webhook as _wh

    _hermetic(monkeypatch, tmp_path)
    server, url, _ = _serve("cloud-secret", tmp_path, "flush.jsonl")
    _write_cloud_json(tmp_path / "home", url, "cloud-secret")
    import shutil as _shutil

    f = tmp_path / "dummy.epi"
    _shutil.copyfile(REPO / "website" / "assets" / "sample.epi", f)
    try:
        _wh.report_seal(f, urls=[url], secret=None, path=_wh.outbox_path())
        result = runner.invoke(cli_app, ["witness", "flush"])
        assert result.exit_code == 0, result.output
        assert "Delivered:" in result.output, result.output
    finally:
        server.shutdown()
        server.server_close()


def test_flush_never_sends_saved_secret_elsewhere(monkeypatch):
    """The saved secret only goes to the saved URL; explicit secrets still win."""
    import urllib.request as _url

    from epi_core import webhook as _wh

    seen: dict = {}

    class _Resp:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def _fake(req, timeout=None):
        seen[req.full_url] = dict(req.header_items())
        return _Resp()

    monkeypatch.setattr(_url, "urlopen", _fake)
    entry = {
        "id": "e1",
        "pending": ["https://cloud.test/w/inb_saved", "https://other.example/w/inb_x"],
        "payload": {"schema": "epi-witness/v1"},
    }
    out = _wh.deliver_entry(entry, secret_for_url=lambda u: "saved-secret" if u == "https://cloud.test/w/inb_saved" else None)
    assert out["delivered"] == ["https://cloud.test/w/inb_saved", "https://other.example/w/inb_x"]
    saved_headers = {k.lower(): v for k, v in seen["https://cloud.test/w/inb_saved"].items()}
    other_headers = {k.lower(): v for k, v in seen["https://other.example/w/inb_x"].items()}
    assert saved_headers.get("x-epi-signature", "").startswith("sha256=")
    assert "x-epi-signature" not in other_headers
    # Explicit secret wins everywhere, resolver ignored.
    seen.clear()
    out = _wh.deliver_entry(entry, secret="explicit", secret_for_url=lambda u: "saved-secret")
    assert out["delivered"] == ["https://cloud.test/w/inb_saved", "https://other.example/w/inb_x"]
    for _u, _h in seen.items():
        assert {k.lower() for k in _h} >= {"x-epi-signature"}


def test_print_witness_outcome_401_403_hints(monkeypatch, tmp_path, capsys):
    """The exact terminal line from epi demo: relogin for cloud users, blocked for 403."""
    import sys as _sys

    from epi_recorder.api import _print_witness_outcome

    sys_path_home = tmp_path / "home"
    monkeypatch.setenv("EPI_HOME", str(sys_path_home))
    monkeypatch.delenv("EPI_WITNESS_URL", raising=False)
    _write_cloud_json(sys_path_home, "https://cloud.test/w/inb_tb", "cloud-secret")

    _print_witness_outcome({"_outcome": {"delivered": [], "failed": {"https://cloud.test/w/inb_tb": "HTTP Error 401: Unauthorized"}}})
    out = capsys.readouterr().err
    assert "re-run epi cloud login" in out, out
    assert "update EPI_WITNESS_SECRET" not in out

    _print_witness_outcome({"_outcome": {"delivered": [], "failed": {"https://cloud.test/w/inb_tb": "HTTP Error 403: Forbidden"}}})
    out = capsys.readouterr().err
    assert "blocked before reaching EPI Cloud" in out, out
    assert "secret changed" not in out
    assert "queued" in out.lower()

    # Env-configured users keep the existing secret hints on 401.
    monkeypatch.setenv("EPI_WITNESS_URL", "https://cloud.test/w/inb_tb")
    monkeypatch.setenv("EPI_WITNESS_SECRET", "s")
    _print_witness_outcome({"_outcome": {"delivered": [], "failed": {"https://cloud.test/w/inb_tb": "HTTP Error 401: Unauthorized"}}})
    out = capsys.readouterr().err
    assert "update EPI_WITNESS_SECRET" in out, out
    assert "re-run epi cloud login" not in out
    _sys.stdout.flush()


def test_build_witness_payload_omits_none_fields():
    """None-valued optional fields are omitted, never sent as JSON null."""
    from epi_core.webhook import build_witness_payload

    payload = build_witness_payload(
        workflow_id="wf-1",
        manifest_hash="mh",
        file_sha256="fs",
        public_key=None,
        content_digest=None,
        key_fingerprint=None,
        steps=3,
        sealed_at="t",
        seal_timestamp={"status": "none", "gen_time": None},
    )
    assert "public_key" not in payload
    assert "content_digest" not in payload
    assert "key_fingerprint" not in payload
    assert payload["workflow_id"] == "wf-1"
    assert payload["steps"] == 3
    payload2 = build_witness_payload(
        workflow_id="wf-1",
        manifest_hash="mh",
        file_sha256="fs",
        public_key="pk",
        content_digest="cd",
        key_fingerprint="fp",
        steps=1,
        sealed_at="t",
        seal_timestamp={"status": "none", "gen_time": None},
    )
    assert payload2["public_key"] == "pk"
    assert payload2["content_digest"] == "cd"
    assert payload2["key_fingerprint"] == "fp"


def test_stage_same_file_twice_reports_once(monkeypatch, tmp_path):
    """One sealed file stages exactly one pending entry, however often reported."""
    from epi_core import webhook as _wh

    _hermetic(monkeypatch, tmp_path)
    import shutil as _shutil

    f = tmp_path / "run.epi"
    _shutil.copyfile(REPO / "website" / "assets" / "sample.epi", f)
    url = "https://cloud.test/w/inb_tb"
    first = _wh.stage_seal_report(f, urls=[url], path=_wh.outbox_path())
    second = _wh.stage_seal_report(f, urls=[url], path=_wh.outbox_path())
    assert first is not None and second is not None
    assert first["id"] == second["id"]
    entries = [e for e in _wh.read_outbox(_wh.outbox_path()) if e.get("pending")]
    assert len(entries) == 1, entries


def _bad_schema_server(tmp_path: Path):
    """Always-400 receiver (malformed stamp, retrying can never help)."""

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            length = int(self.headers.get("Content-Length", "0"))
            self.rfile.read(length)
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"bad schema")

        def log_message(self, *args):  # silence stdlib logging
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_port}/"


def test_flush_400_says_drop_dont_retry(monkeypatch, tmp_path):
    """A 400 is malformed, not a secret problem: name the drop command with the id."""
    import re as _re

    from epi_core import webhook as _wh

    _hermetic(monkeypatch, tmp_path)
    server, url = _bad_schema_server(tmp_path)
    monkeypatch.setenv("EPI_WITNESS_URL", url)
    monkeypatch.setenv("EPI_WITNESS_SECRET", "s")
    try:
        import shutil as _shutil

        f = tmp_path / "dummy.epi"
        _shutil.copyfile(REPO / "website" / "assets" / "sample.epi", f)
        _wh.report_seal(f, urls=[url], secret="s", path=_wh.outbox_path())
        result = runner.invoke(cli_app, ["witness", "flush"])
        assert result.exit_code == 1, result.output
        assert "Rejected as malformed" in result.output, result.output
        assert _re.search(r"epi witness drop [0-9a-f]{16}", result.output), result.output
        assert "Fix the URL/secret" not in result.output
    finally:
        server.shutdown()
        server.server_close()


def test_compact_session_summary_skips_policy_detail(monkeypatch, tmp_path, capsys):
    """`epi demo` sets EPI_COMPACT_SUMMARY: no Policy/Issue/Finding lines, steps kept."""
    from epi_recorder import record as _record

    _hermetic(monkeypatch, tmp_path)
    monkeypatch.setenv("EPI_COMPACT_SUMMARY", "1")
    out = tmp_path / "compact.epi"
    with _record(str(out)) as epi:
        epi.log_step("llm.request", {"content": "hello"})
    err = capsys.readouterr().err
    assert "steps" in err and ".epi" in err, err
    for banned in ("Policy:", "Issue:", "Finding:", "Next:"):
        assert banned not in err, err
