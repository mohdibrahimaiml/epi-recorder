"""`epi witness serve` (installed receiver) and `epi witness drop`.

Local HTTP servers on 127.0.0.1 only, no external network.
"""

from __future__ import annotations

import json
import socket
import threading
import urllib.error
from pathlib import Path

import pytest
from typer.testing import CliRunner

from epi_cli.main import app as cli_app

runner = CliRunner()

SECRET = "customer-shared-secret"


def _hermetic(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("EPI_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("EPI_KEYS_DIR", str(tmp_path / "home" / "keys"))
    monkeypatch.setenv("EPI_NOTARIZE", "0")
    monkeypatch.setenv("EPI_CHECKPOINTS_ENABLED", "0")
    for key in ("EPI_WITNESS_URL", "EPI_WITNESS_SECRET"):
        monkeypatch.delenv(key, raising=False)


@pytest.fixture
def started(monkeypatch):
    """Run the real `epi witness serve` command; serve in a thread instead of blocking."""
    from epi_core import witness_receiver

    servers = []

    def fake_serve_forever(server):
        servers.append(server)
        threading.Thread(target=server.serve_forever, daemon=True).start()

    monkeypatch.setattr(witness_receiver, "serve_forever", fake_serve_forever)
    yield servers
    for server in servers:
        server.shutdown()
        server.server_close()


def _serve(started, out: Path, *extra: str):
    result = runner.invoke(
        cli_app,
        ["witness", "serve", "--host", "127.0.0.1", "--port", "0", "--out", str(out), *extra],
    )
    assert result.exit_code == 0, result.output
    assert started, result.output
    server = started[-1]
    return server, f"http://127.0.0.1:{server.server_port}/", result.output


def _payload(workflow_id: str = "wf-serve-1") -> dict:
    from epi_core.webhook import build_witness_payload

    return build_witness_payload(
        workflow_id=workflow_id,
        manifest_hash="a" * 64,
        file_sha256="b" * 64,
        public_key=None,
        content_digest="c" * 64,
        key_fingerprint=None,
        steps=1,
        sealed_at="2026-10-12T00:00:00+00:00",
        seal_timestamp={"source": "local"},
    )


def test_serve_accepts_signed_report_from_record(monkeypatch, tmp_path, started):
    _hermetic(monkeypatch, tmp_path)
    out_log = tmp_path / "received.jsonl"
    _server, url, output = _serve(started, out_log, "--secret", SECRET)
    assert f"EPI_WITNESS_URL={url}" in output
    assert f"--witness-log {out_log.resolve()}" in output

    from epi_recorder import record

    epi = tmp_path / "run.epi"
    with record(str(epi), witness_url=url, witness_secret=SECRET) as rec:
        rec.log_step("llm.request", {"content": "hello"})

    lines = out_log.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["schema"] == "epi-witness/v1"
    assert entry["received_at"]

    result = runner.invoke(cli_app, ["verify", str(epi), "--json", "--witness-log", str(out_log)])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["witness"]["status"] == "WITNESSED"


def test_serve_rejects_bad_hmac_with_401(monkeypatch, tmp_path, started, capsys):
    _hermetic(monkeypatch, tmp_path)
    from epi_core.webhook import _post_once

    out_log = tmp_path / "received.jsonl"
    _server, url, _ = _serve(started, out_log, "--secret", SECRET)

    with pytest.raises(urllib.error.HTTPError) as excinfo:
        _post_once(url, _payload(), secret="wrong-secret", extra_headers=None, timeout_seconds=5)
    assert excinfo.value.code == 401
    with pytest.raises(urllib.error.HTTPError) as excinfo:
        _post_once(url, _payload(), secret=None, extra_headers=None, timeout_seconds=5)
    assert excinfo.value.code == 401
    assert not out_log.exists()
    assert "rejected: bad or missing X-EPI-Signature HMAC" in capsys.readouterr().err

    _post_once(url, _payload(), secret=SECRET, extra_headers=None, timeout_seconds=5)
    assert len(out_log.read_text(encoding="utf-8").splitlines()) == 1


def test_serve_secret_from_env(monkeypatch, tmp_path, started):
    _hermetic(monkeypatch, tmp_path)
    monkeypatch.setenv("EPI_WITNESS_SECRET", SECRET)
    from epi_core.webhook import _post_once

    out_log = tmp_path / "received.jsonl"
    _server, url, _ = _serve(started, out_log)
    _post_once(url, _payload(), secret=SECRET, extra_headers=None, timeout_seconds=5)
    assert out_log.is_file()


def test_serve_refuses_without_secret(monkeypatch, tmp_path, started):
    _hermetic(monkeypatch, tmp_path)
    result = runner.invoke(cli_app, ["witness", "serve", "--port", "0"])
    assert result.exit_code == 2
    assert "--insecure-no-secret" in result.output
    assert not started


def test_serve_insecure_no_secret(monkeypatch, tmp_path, started):
    _hermetic(monkeypatch, tmp_path)
    from epi_core.webhook import _post_once

    out_log = tmp_path / "received.jsonl"
    _server, url, output = _serve(started, out_log, "--insecure-no-secret")
    assert "WARNING" in output
    _post_once(url, _payload(), secret=None, extra_headers=None, timeout_seconds=5)
    assert out_log.is_file()


def test_serve_port_in_use_is_friendly(monkeypatch, tmp_path, started):
    _hermetic(monkeypatch, tmp_path)
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen(1)
    try:
        port = sock.getsockname()[1]
        result = runner.invoke(
            cli_app, ["witness", "serve", "--port", str(port), "--secret", SECRET]
        )
    finally:
        sock.close()
    assert result.exit_code == 2
    assert "already in use" in result.output
    assert "Traceback" not in result.output


def test_example_receiver_is_thin_wrapper():
    import importlib.util

    path = Path(__file__).resolve().parents[1] / "examples" / "witness_receiver" / "receiver.py"
    spec = importlib.util.spec_from_file_location("example_witness_receiver", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    from epi_core import witness_receiver

    assert module.main is witness_receiver.main
    args = module.build_parser().parse_args([])
    assert (args.host, args.port, str(args.out)) == ("127.0.0.1", 8099, "received.jsonl")


# --------------------------------------------------------------------------- drop


def _dead_url() -> str:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    url = f"http://127.0.0.1:{sock.getsockname()[1]}/witness"
    sock.close()
    return url


def _ids():
    from epi_core.webhook import read_outbox

    return [e["id"] for e in read_outbox()]


def test_drop_by_status_prefix_clears_flush(monkeypatch, tmp_path):
    _hermetic(monkeypatch, tmp_path)
    from epi_core.webhook import append_outbox_entry

    entry = append_outbox_entry(_payload(), [_dead_url()])
    keep = append_outbox_entry(_payload("wf-keep"), [])

    result = runner.invoke(cli_app, ["witness", "flush", "--timeout", "2"])
    assert result.exit_code == 1
    assert "epi witness drop <id>" in result.output

    status = runner.invoke(cli_app, ["witness", "status"])
    short = entry["id"][:8]
    assert short in status.output

    result = runner.invoke(cli_app, ["witness", "drop", short])
    assert result.exit_code == 0, result.output
    assert "Dropped" in result.output
    assert _ids() == [keep["id"]]

    result = runner.invoke(cli_app, ["witness", "flush"])
    assert result.exit_code == 0, result.output


def test_drop_unknown_and_ambiguous_prefix(monkeypatch, tmp_path):
    _hermetic(monkeypatch, tmp_path)
    from epi_core.webhook import outbox_path

    target = outbox_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    entries = [
        {"id": "abc11111aaaa0000", "payload": {}, "pending": ["http://x/"], "delivered": {}},
        {"id": "abc22222bbbb0000", "payload": {}, "pending": ["http://y/"], "delivered": {}},
    ]
    target.write_text("".join(json.dumps(e) + "\n" for e in entries), encoding="utf-8")

    result = runner.invoke(cli_app, ["witness", "drop", "abc"])
    assert result.exit_code == 1
    assert "ambiguous" in result.output
    assert len(_ids()) == 2

    result = runner.invoke(cli_app, ["witness", "drop", "zzz"])
    assert result.exit_code == 1
    assert "No witness entry matches" in result.output

    result = runner.invoke(cli_app, ["witness", "drop"])
    assert result.exit_code == 2

    result = runner.invoke(cli_app, ["witness", "drop", "ABC2"])
    assert result.exit_code == 0, result.output
    assert _ids() == ["abc11111aaaa0000"]


def test_drop_all_failed_needs_yes(monkeypatch, tmp_path):
    _hermetic(monkeypatch, tmp_path)
    from epi_core.webhook import append_outbox_entry

    append_outbox_entry(_payload("wf-1"), ["http://127.0.0.1:9/a"])
    append_outbox_entry(_payload("wf-2"), ["http://127.0.0.1:9/b"])
    done = append_outbox_entry(_payload("wf-3"), [])

    result = runner.invoke(cli_app, ["witness", "drop", "--all-failed"])
    assert result.exit_code == 1
    assert "--yes" in result.output
    assert len(_ids()) == 3

    result = runner.invoke(cli_app, ["witness", "drop", "--all-failed", "--yes"])
    assert result.exit_code == 0, result.output
    assert _ids() == [done["id"]]

    result = runner.invoke(cli_app, ["witness", "drop", "--all-failed", "--yes"])
    assert result.exit_code == 0
    assert "nothing to drop" in result.output


def test_flush_auth_hint(monkeypatch, tmp_path, started):
    _hermetic(monkeypatch, tmp_path)
    from epi_core.webhook import append_outbox_entry

    _server, url, _ = _serve(started, tmp_path / "received.jsonl", "--secret", SECRET)
    append_outbox_entry(_payload(), [url])
    result = runner.invoke(cli_app, ["witness", "flush", "--secret", "wrong"])
    assert result.exit_code == 1
    flat = " ".join(result.output.split())
    assert (
        "The receiver rejected the secret (HTTP 401). Use the same secret as the "
        "receiver: EPI_WITNESS_SECRET or --secret." in flat
    )
    assert (
        "Still pending. Fix the URL/secret and flush again, or remove an entry with: "
        "epi witness drop <id>" in flat
    )

    result = runner.invoke(cli_app, ["witness", "flush", "--secret", SECRET])
    assert result.exit_code == 0, result.output


def test_windows_socket_errors_read_like_linux():
    """Windows words refused/busy sockets differently; users see one message."""
    import errno as _errno

    from epi_cli.gateway import _short_reason
    from epi_core.witness_receiver import bind_error_message

    win = (
        "http://x/: <urlopen error [WinError 10061] No connection could be made "
        "because the target machine actively refused it>"
    )
    assert _short_reason(win, ["http://x/"]) == "Connection refused"
    exc = OSError(_errno.EACCES, "forbidden")
    exc.winerror = 10013
    assert "already in use" in bind_error_message("127.0.0.1", 9, exc)
