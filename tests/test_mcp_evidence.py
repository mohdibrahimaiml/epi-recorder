"""Tests for the EPI evidence MCP package (seal/verify/export)."""

from __future__ import annotations

import pytest

from epi_mcp import export_summary, seal_record, verify_artifact


@pytest.fixture
def isolated_keys(tmp_path, monkeypatch):
    monkeypatch.setenv("EPI_MCP_KEYS_DIR", str(tmp_path / "keys"))
    monkeypatch.delenv("EPI_MCP_TOKEN", raising=False)
    from epi_mcp.tools import _current_subject

    _current_subject.set("test-user")
    yield tmp_path
    _current_subject.set(None)


def _events():
    return [
        {"kind": "user.task", "content": {"text": "Refund order ORD-9001?"}},
        {"kind": "tool.call", "content": {"tool": "lookup_order", "input": {"order": "ORD-9001"}}},
        {"kind": "agent.decision", "content": {"decision": "escalate"}},
    ]


def test_seal_then_verify_round_trip(isolated_keys, tmp_path):
    sealed = seal_record(_events(), goal="test refund", output_path=tmp_path / "r.epi")
    assert sealed["steps_sealed"] == 3
    assert sealed["scope"] == "caller-provided"

    report = verify_artifact(sealed["epi_path"])
    assert report["integrity_ok"] is True
    assert report["signature_valid"] is True


def test_seal_rejects_empty(isolated_keys):
    with pytest.raises(ValueError):
        seal_record([])


def test_seal_rejects_non_object_event(isolated_keys, tmp_path):
    with pytest.raises(ValueError):
        seal_record(["not-an-object"], output_path=tmp_path / "x.epi")


def test_export_summary_reads_timeline(isolated_keys, tmp_path):
    sealed = seal_record(_events(), output_path=tmp_path / "r.epi")
    summary = export_summary(sealed["epi_path"])
    assert summary["steps_total"] == 3
    assert [s["kind"] for s in summary["timeline"]] == ["user.task", "tool.call", "agent.decision"]


def test_verify_missing_file():
    with pytest.raises(FileNotFoundError):
        verify_artifact("does-not-exist.epi")


def test_server_tools_registered():
    pytest.importorskip("mcp.server.mcpserver")
    import epi_mcp.server as srv

    registered = {fn.__name__ for fn in (srv.epi_seal_record, srv.epi_verify, srv.epi_export_summary)}
    assert registered == {"epi_seal_record", "epi_verify", "epi_export_summary"}


def test_seal_tool_returns_file_bytes(isolated_keys, tmp_path):
    import base64

    from epi_mcp.tools import epi_seal_record_tool

    result = epi_seal_record_tool(_events(), goal="bytes check", output_path=str(tmp_path / "b.epi"))
    raw = base64.b64decode(result["epi_b64"])
    assert raw[:4] == b"<!--"  # envelope-v2 polyglot magic
    assert result["filename"] == "b.epi"
    assert result["scope"] == "caller-provided"
    assert result["seal_check"]["signature_valid"] is True
    assert "hidden reasoning" in " ".join(result["not_captured"])


def test_http_lists_and_seals(isolated_keys, tmp_path):
    uvicorn = pytest.importorskip("uvicorn")
    httpx = pytest.importorskip("httpx")
    from mcp.client.streamable_http import streamable_http_client
    from mcp.client.session import ClientSession

    import threading

    from epi_mcp.http import build_app

    port = 18791
    server = uvicorn.Server(uvicorn.Config(build_app(), host="127.0.0.1", port=port, log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        import asyncio
        import time

        async def _run():
            async with streamable_http_client(f"http://127.0.0.1:{port}/mcp") as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    tools = await session.list_tools()
                    assert sorted(t.name for t in tools.tools) == [
                        "epi_export_summary",
                        "epi_seal_record",
                        "epi_verify",
                    ]
                    sealed = await session.call_tool(
                        "epi_seal_record",
                        {"events": _events(), "goal": "http check",
                         "output_path": str(tmp_path / "h.epi")},
                    )
                    import json as _json

                    payload = _json.loads(sealed.content[0].text)
                    assert payload["seal_check"]["signature_valid"] is True
                    assert payload["epi_b64"]

                    # Artifact-return path: the delivered bytes must BE the
                    # sealed file — decodable, hash-matching, verifiable.
                    import base64 as _b64
                    import hashlib as _hl

                    raw = _b64.b64decode(payload["epi_b64"])
                    assert raw[:4] == b"<!--"
                    assert _hl.sha256(raw).hexdigest() == payload["sha256"]
                    delivered = tmp_path / payload["filename"]
                    delivered.write_bytes(raw)
                    from epi_mcp.records import verify_artifact as _verify

                    check = _verify(delivered)
                    assert check["integrity_ok"] is True
                    assert check["signature_valid"] is True

        for _ in range(100):
            try:
                httpx.get(f"http://127.0.0.1:{port}/mcp", timeout=1)
                break
            except Exception:
                time.sleep(0.1)
        asyncio.run(_run())
    finally:
        server.should_exit = True
        thread.join(timeout=20)


def test_http_bearer_auth_enforced(monkeypatch):
    starlette_test = pytest.importorskip("starlette.testclient")
    monkeypatch.setenv("EPI_MCP_TOKEN", "s3cret")

    from epi_mcp.http import build_app

    client = starlette_test.TestClient(build_app(), raise_server_exceptions=False)
    # /mcp stays open (handshake + verify/export need no identity).
    r = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "ping"})
    assert r.status_code != 401
    # Sealed downloads still require the token.
    assert client.get("/artifacts/anything").status_code == 401
    r2 = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "ping"},
        headers={"Authorization": "Bearer s3cret"},
    )
    assert r2.status_code != 401


def test_http_bind_guard():
    import pytest as _pytest

    from epi_mcp.http import is_loopback_host, main
    import epi_mcp.http as httpmod

    assert is_loopback_host("127.0.0.1") and is_loopback_host("localhost") and is_loopback_host("::1")
    assert not is_loopback_host("0.0.0.0")

    import sys

    argv, sys.argv = sys.argv, ["epi-mcp-http", "--host", "0.0.0.0"]
    try:
        with _pytest.raises(SystemExit):
            httpmod.os.environ.pop("EPI_MCP_TOKEN", None)
            main()
    finally:
        sys.argv = argv


def test_artifact_download_serves_sealed_bytes(isolated_keys, tmp_path, monkeypatch):
    starlette_test = pytest.importorskip("starlette.testclient")
    monkeypatch.delenv("EPI_MCP_TOKEN", raising=False)

    from epi_mcp.http import build_app
    from epi_mcp.tools import epi_seal_record_tool

    sealed = epi_seal_record_tool(_events(), output_path=str(tmp_path / "d.epi"))
    client = starlette_test.TestClient(build_app(), raise_server_exceptions=False)

    r = client.get(sealed["download_path"])
    assert r.status_code == 200
    import base64 as _b64

    assert r.content == _b64.b64decode(sealed["epi_b64"])

    missing = client.get("/artifacts/nope-not-here")
    assert missing.status_code == 404
    traversal = client.get("/artifacts/..%2F..%2Fsecret")
    assert traversal.status_code in (404, 400)


def test_artifact_download_requires_token(monkeypatch):
    starlette_test = pytest.importorskip("starlette.testclient")
    monkeypatch.setenv("EPI_MCP_TOKEN", "s3cret")

    from epi_mcp.http import build_app

    client = starlette_test.TestClient(build_app(), raise_server_exceptions=False)
    assert client.get("/artifacts/anything").status_code == 401


def test_favicon_served_from_plugin_host(monkeypatch):
    starlette_test = pytest.importorskip("starlette.testclient")
    monkeypatch.delenv("EPI_MCP_TOKEN", raising=False)

    from epi_mcp.http import build_app

    client = starlette_test.TestClient(build_app(), raise_server_exceptions=False)
    r = client.get("/favicon.ico")
    assert r.status_code == 200
    assert r.content[:4] in (b"\x00\x00\x01\x00", b"\x89PNG")


def test_public_host_allowed_via_public_url(monkeypatch):
    """Regression: SDK DNS-rebinding guard rejected the public Host (421)."""
    monkeypatch.setenv("EPI_MCP_PUBLIC_URL", "https://epi-mcp.onrender.com")

    from epi_mcp.http import _transport_security

    ts = _transport_security()
    assert ts is not None
    assert "epi-mcp.onrender.com" in ts.allowed_hosts


def test_per_user_keys_differ_per_subject(isolated_keys, tmp_path, monkeypatch):
    from epi_mcp.tools import _current_subject, epi_seal_record_tool

    _current_subject.set("alice")
    a = epi_seal_record_tool(_events(), output_path=str(tmp_path / "a.epi"))
    _current_subject.set("bob")
    b = epi_seal_record_tool(_events(), output_path=str(tmp_path / "b.epi"))
    from epi_mcp.records import verify_artifact

    assert verify_artifact(a["epi_path"])["signer"] != verify_artifact(b["epi_path"])["signer"]
    assert a["sealed_for_subject"] != b["sealed_for_subject"]


def test_anonymous_seal_refused(tmp_path, monkeypatch):
    """No subject bound -> seal refuses instead of sealing anonymously."""
    import pytest as _pytest

    monkeypatch.setenv("EPI_MCP_KEYS_DIR", str(tmp_path / "keys"))
    from epi_mcp.tools import _current_subject, epi_seal_record_tool

    _current_subject.set(None)
    with _pytest.raises(PermissionError):
        epi_seal_record_tool(_events(), output_path=str(tmp_path / "anon.epi"))


def test_oidc_malformed_token_rejected(monkeypatch):
    monkeypatch.setenv("EPI_OIDC_JWKS_URL", "https://example.com/.well-known/jwks.json")
    monkeypatch.setenv("EPI_OIDC_ISSUER", "https://example.com")
    monkeypatch.delenv("EPI_MCP_TOKEN", raising=False)

    from epi_mcp.auth import verify_bearer_token

    assert verify_bearer_token("not-a-jwt") is None
    assert verify_bearer_token("") is None
