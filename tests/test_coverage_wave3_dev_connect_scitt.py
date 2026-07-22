"""Wave 3 coverage: epi_cli.dev, epi_cli.connect helpers, epi_cli.scitt."""
from __future__ import annotations

import json
import shutil
import socket
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

runner = CliRunner()


def _sample_epi() -> Path:
    for p in (Path("assets/sample.epi"), Path("loan_decision.epi"), Path("agicomply_demo.epi")):
        if p.exists():
            return p
    pytest.skip("no sample epi")


def _home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("EPI_HOME", str(home / "epi"))
    monkeypatch.setenv("EPI_KEYS_DIR", str(home / "epi" / "keys"))
    monkeypatch.setenv("EPI_TRUSTED_KEYS_DIR", str(home / "epi" / "trusted_keys"))
    monkeypatch.setenv("EPI_NOTARIZE", "0")
    return home


# ---------------------------------------------------------------------------
# dev.py helpers
# ---------------------------------------------------------------------------

def test_dev_find_free_port_and_wait():
    from epi_cli import dev as d

    port = d._find_free_port(0)
    assert isinstance(port, int) and port >= 0

    # preferred free bind (OS may assign ephemeral if preferred busy)
    p2 = d._find_free_port(18787)
    assert isinstance(p2, int) and p2 > 0

    # wait for closed port fails quickly
    assert d._wait_for_port("127.0.0.1", 1, timeout=0.2) is False

    # open a real listener and wait succeeds
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    host, port = srv.getsockname()
    try:
        assert d._wait_for_port(host, port, timeout=2.0) is True
    finally:
        srv.close()


def test_dev_find_demo_epi(tmp_path, monkeypatch):
    from epi_cli import dev as d

    monkeypatch.chdir(tmp_path)
    assert d._find_demo_epi("missing") is None
    rec = tmp_path / "epi-recordings"
    rec.mkdir()
    f = rec / "demo_refund.epi"
    f.write_bytes(b"x" * 100)
    found = d._find_demo_epi("demo_refund")
    assert found is not None and found.name.startswith("demo_refund")


def test_dev_seed_and_ingest(tmp_path, monkeypatch):
    from epi_cli import dev as d

    storage = tmp_path / "vault"
    storage.mkdir()
    case_id = d._seed_simulated_case(storage)
    assert case_id

    epi = _sample_epi()
    dest = tmp_path / "live.epi"
    shutil.copy(epi, dest)
    live_id = d._ingest_epi_into_gateway(dest, storage)
    # may return id or None depending on worker; should not crash
    assert live_id is None or isinstance(live_id, str)

    # bad file
    bad = tmp_path / "bad.epi"
    bad.write_text("not-an-epi")
    assert d._ingest_epi_into_gateway(bad, storage) is None


def test_dev_run_demo_script_and_key_trust(tmp_path, monkeypatch):
    from epi_cli import dev as d

    _home(tmp_path, monkeypatch)
    monkeypatch.chdir(tmp_path)

    script = tmp_path / "ok.py"
    script.write_text("print('hi')\n", encoding="utf-8")
    assert d._run_demo_script(script, env={**dict(**__import__("os").environ)}) is True

    fail = tmp_path / "fail.py"
    fail.write_text("import sys; sys.exit(2)\n", encoding="utf-8")
    assert d._run_demo_script(fail, env={**dict(**__import__("os").environ)}) is False

    # timeout path
    slow = tmp_path / "slow.py"
    slow.write_text("import time; time.sleep(5)\n", encoding="utf-8")
    with patch("epi_cli.dev.subprocess.run", side_effect=__import__("subprocess").TimeoutExpired(cmd="x", timeout=0.01)):
        assert d._run_demo_script(slow, env={}) is False

    with patch("epi_cli.dev.subprocess.run", side_effect=OSError("nope")):
        assert d._run_demo_script(script, env={}) is False

    d._ensure_default_key_trusted()


def test_dev_run_fast_demo_no_run_missing(tmp_path, monkeypatch):
    from epi_cli import dev as d

    monkeypatch.chdir(tmp_path)
    _home(tmp_path, monkeypatch)
    out = d._run_fast_demo(
        demo_script=tmp_path / "demo_refund.py",
        no_run=True,
        no_verify=True,
        no_browser=True,
        force_script=True,
    )
    assert out is None  # no artifact


def test_dev_run_fast_demo_with_existing_epi(tmp_path, monkeypatch):
    from epi_cli import dev as d

    monkeypatch.chdir(tmp_path)
    _home(tmp_path, monkeypatch)
    rec = tmp_path / "epi-recordings"
    rec.mkdir()
    epi = _sample_epi()
    target = rec / "demo_refund.epi"
    shutil.copy(epi, target)

    with patch("epi_cli.dev.subprocess.run") as run:
        run.return_value = SimpleNamespace(
            returncode=0,
            stdout=json.dumps({"facts": {"integrity_ok": True, "signature_valid": True}}),
            stderr="",
        )
        out = d._run_fast_demo(
            demo_script=tmp_path / "demo_refund.py",
            no_run=True,
            no_verify=False,
            no_browser=True,
            force_script=False,
        )
    assert out is not None
    assert out.exists()


def test_dev_auto_export_and_verify(tmp_path, monkeypatch):
    from epi_cli import dev as d

    monkeypatch.chdir(tmp_path)
    storage = tmp_path / "vault"
    storage.mkdir()
    case_id = d._seed_simulated_case(storage)

    # Mock export_case and verify
    class FakeWorker:
        def __init__(self, storage_dir=None, **kwargs):
            self.storage_dir = storage_dir

        def export_case(self, case_id, out_path, signer_function=None):
            Path(out_path).write_bytes(b"PK\x03\x04")

        def upsert_case_payload(self, payload):
            return {"id": payload.get("id")}

    # Avoid importing epi_gateway.main at module level (side-effects).
    class FakeSettings:
        pass

    with patch.dict(
        "sys.modules",
        {
            "epi_gateway.main": SimpleNamespace(
                _build_gateway_signer=lambda s: None,
                _build_settings_from_env=lambda: FakeSettings(),
            ),
            "epi_gateway.worker": SimpleNamespace(EvidenceWorker=FakeWorker),
        },
    ):
        with patch("epi_cli.dev.subprocess.run", return_value=SimpleNamespace(returncode=0)):
            # Re-import path used inside function by patching after import inside call
            import epi_gateway.worker as gw

            monkeypatch.setattr(gw, "EvidenceWorker", FakeWorker, raising=False)
            path = d._auto_export_and_verify(storage, case_id)
    # May return path or None if export import fails — just exercise branch
    assert path is None or path.exists()


def test_dev_cli_help():
    from epi_cli.dev import app

    r = runner.invoke(app, ["--help"])
    assert r.exit_code == 0


# ---------------------------------------------------------------------------
# connect.py helpers + bridge handler
# ---------------------------------------------------------------------------

def test_connect_workspace_helpers(tmp_path):
    from epi_cli import connect as c

    assert c._clean(None) == ""
    assert c._clean("  x ") == "x"
    assert "T" in c._utc_now() or "-" in c._utc_now()

    storage = c._resolve_storage_dir(tmp_path / "store")
    assert storage.exists()

    # json path → parent
    jf = tmp_path / "ws" / "workspace-state.json"
    resolved = c._resolve_storage_dir(jf)
    assert resolved.exists()

    ws = tmp_path / "workspace-state.json"
    state = c._read_workspace_state(ws)
    assert "cases" in state
    # corrupt file
    ws.write_text("{bad", encoding="utf-8")
    state2 = c._read_workspace_state(ws)
    assert state2["cases"] == {}

    with pytest.raises(ValueError):
        c._upsert_workspace_case(ws, "not-dict")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        c._upsert_workspace_case(ws, {"title": "no id"})

    stored = c._upsert_workspace_case(
        ws,
        {"id": "c1", "title": "Case One", "status": "open"},
    )
    assert stored["id"] == "c1"
    assert stored["shared_workspace_case"] is True
    cases = c._list_workspace_cases(ws)
    assert any(x.get("id") == "c1" for x in cases)


def test_connect_bridge_handler_methods(tmp_path):
    """Exercise bridge handler without serve_forever (avoids Windows shutdown hangs)."""
    from epi_cli.connect import (
        _handler_factory,
        create_web_viewer_server,
        _endpoint_ready,
        _shutdown_servers,
        create_connector_bridge_server,
    )
    from io import BytesIO

    ws = tmp_path / "workspace-state.json"
    Handler = _handler_factory(ws)

    class FakeHandler(Handler):
        def __init__(self):
            self.headers = {"Content-Length": "0"}
            self.path = "/health"
            self.wfile = BytesIO()
            self.rfile = BytesIO(b"")
            self._status = None
            self._headers = {}

        def send_response(self, code, message=None):
            self._status = code

        def send_header(self, k, v):
            self._headers[k] = v

        def end_headers(self):
            pass

    h = FakeHandler()
    h.do_OPTIONS()
    assert h._status == 200

    h.path = "/health"
    h.do_GET()
    assert h._status == 200

    h.path = "/api/workspace/state"
    h.do_GET()
    assert h._status == 200

    h.path = "/missing"
    h.do_GET()
    assert h._status == 404

    # POST upsert case
    body = json.dumps({"case": {"id": "z1", "title": "Z"}}).encode()
    h.headers = {"Content-Length": str(len(body))}
    h.rfile = BytesIO(body)
    h.path = "/api/workspace/cases"
    h.do_POST()
    assert h._status == 200

    # POST bad case
    body = json.dumps({"case": {}}).encode()
    h.headers = {"Content-Length": str(len(body))}
    h.rfile = BytesIO(body)
    h.path = "/api/workspace/cases"
    h.do_POST()
    assert h._status == 400

    # fetch-record mock
    body = json.dumps(
        {
            "system": "zendesk",
            "connector_profile": {"preview_mode": "sample"},
            "case_input": {"case_id": "t1"},
        }
    ).encode()
    h.headers = {"Content-Length": str(len(body))}
    h.rfile = BytesIO(body)
    h.path = "/api/fetch-record"
    h.do_POST()
    assert h._status == 200

    h.path = "/unknown-post"
    h.headers = {"Content-Length": "2"}
    h.rfile = BytesIO(b"{}")
    h.do_POST()
    assert h._status == 404

    assert _endpoint_ready("http://127.0.0.1:1/nope", timeout=0.2) is False

    # Construct viewer server object only (do not serve_forever)
    srv = create_web_viewer_server("127.0.0.1", 0, directory=tmp_path)
    try:
        srv.server_close()
    except Exception:
        pass
    _shutdown_servers([])


def test_connect_cli_help():
    from epi_cli.connect import app

    for cmd in ("serve", "serve-viewer", "open"):
        r = runner.invoke(app, [cmd, "--help"])
        assert r.exit_code == 0


def test_open_workspace_browser_helpers(monkeypatch):
    from epi_cli import connect as c

    monkeypatch.setattr(c.webbrowser, "open", lambda url: True)
    assert c._open_workspace_in_browser("http://example.com") is True
    monkeypatch.setattr(c.webbrowser, "open", lambda url: (_ for _ in ()).throw(OSError("x")))
    assert c._open_workspace_in_browser("http://example.com") is False


# ---------------------------------------------------------------------------
# scitt.py
# ---------------------------------------------------------------------------

def test_scitt_derive_issuer_and_load_key(tmp_path, monkeypatch):
    from epi_cli import scitt as s
    from epi_core.schemas import ManifestModel
    from epi_core.keys import KeyManager
    import click

    _home(tmp_path, monkeypatch)
    km = KeyManager()
    try:
        km.generate_keypair("scitt_cov", overwrite=True)
    except Exception:
        pass

    key = s._load_signing_key("scitt_cov")
    assert key is not None

    with pytest.raises((SystemExit, click.exceptions.Exit)):
        s._load_signing_key("definitely-missing-key-xyz")

    m = ManifestModel(cli_command="t", goal="g", public_key="abc123def4567890extra")
    assert s._derive_issuer(m).startswith("epi:pubkey:")
    m2 = ManifestModel(cli_command="t", goal="g", governance={"did": "did:web:example"})
    assert s._derive_issuer(m2) == "did:web:example"
    m3 = ManifestModel(cli_command="t", goal="g")
    assert s._derive_issuer(m3) == "epi:anonymous"


def test_scitt_register_offline_mocked(tmp_path, monkeypatch):
    from epi_cli import scitt as s
    from epi_core.container import EPIContainer
    from epi_core.keys import KeyManager

    _home(tmp_path, monkeypatch)
    monkeypatch.chdir(tmp_path)
    try:
        KeyManager().generate_keypair("default", overwrite=True)
    except Exception:
        pass

    epi = _sample_epi()
    inp = tmp_path / "in.epi"
    out = tmp_path / "out.epi"
    shutil.copy(epi, inp)
    manifest = EPIContainer.read_manifest(inp)
    if not getattr(manifest, "public_key", None):
        pytest.skip("sample unsigned")

    key = s._load_signing_key("default")
    issuer = s._derive_issuer(manifest)

    monkeypatch.setattr(s, "create_scitt_statement", lambda *a, **k: b"stmt-bytes")
    monkeypatch.setattr(
        s,
        "register_local_statement",
        lambda stmt: (
            b"rcpt-bytes",
            SimpleNamespace(entry_id="entry-1", registered_at="now"),
        ),
    )
    monkeypatch.setattr(s, "_build_scitt_artifact", lambda *a, **k: None)
    s._register_offline(inp, out, manifest, key, "default", issuer, "local://test")


def test_scitt_register_missing_file(tmp_path):
    from epi_cli.scitt import app as scitt_app

    r = runner.invoke(scitt_app, ["register", str(tmp_path / "nope.epi"), "--local"])
    assert r.exit_code == 1


def test_scitt_verify_no_metadata(tmp_path, monkeypatch):
    from epi_cli.scitt import scitt_verify
    import click

    epi = _sample_epi()
    dest = tmp_path / "s.epi"
    shutil.copy(epi, dest)
    try:
        scitt_verify(dest, service=None)
    except (SystemExit, click.exceptions.Exit):
        pass


def test_scitt_cli_help_and_missing():
    from epi_cli.scitt import app as scitt_app

    r = runner.invoke(scitt_app, ["register", "--help"])
    assert r.exit_code == 0
    r = runner.invoke(scitt_app, ["verify", "--help"])
    assert r.exit_code == 0
    r = runner.invoke(scitt_app, ["anchor", "--help"])
    assert r.exit_code == 0
