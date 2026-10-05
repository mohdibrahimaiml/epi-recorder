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
                        "epi_compare_runs",
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
    # Unauthenticated /mcp is challenged so hosts (ChatGPT) start OAuth.
    r = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "ping"})
    assert r.status_code == 401
    assert "resource_metadata=" in r.headers["www-authenticate"]
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


def test_seal_summary_counts_are_server_computed(isolated_keys, tmp_path):
    from epi_mcp.tools import epi_seal_record_tool

    events = [
        {"kind": "user.message", "content": {"text": "hi"}},
        {"kind": "tool.call", "content": {"tool": "x"}},
        {"kind": "tool.response", "content": {"tool": "x", "output": "ok"}},
        {"kind": "artifact.produced", "content": {"file": "r.pdf"}},
        {"kind": "agent.decision",
         "content": {"decision": "go", "key": "[REDACTED]", "nested": {"k": "[REDACTED]"}}},
    ]
    result = epi_seal_record_tool(events, output_path=str(tmp_path / "c.epi"))
    counts = result["summary_counts"]
    assert counts["events"] == 5
    assert counts["tool_calls"] == 2
    assert counts["artifacts"] == 1
    assert counts["redactions"] == 2
    assert counts["by_kind"]["user.message"] == 1


def test_compare_runs_finds_decision_divergence(isolated_keys, tmp_path):
    from epi_mcp.tools import compare_runs, epi_seal_record_tool

    base = [
        {"kind": "tool.call", "content": {"tool": "lookup"}},
        {"kind": "agent.decision", "content": {"decision": "approve"}},
    ]
    other = [
        {"kind": "tool.call", "content": {"tool": "lookup"}},
        {"kind": "tool.call", "content": {"tool": "extra_check"}},
        {"kind": "agent.decision", "content": {"decision": "reject"}},
    ]
    a = epi_seal_record_tool(base, output_path=str(tmp_path / "a.epi"))
    b = epi_seal_record_tool(other, output_path=str(tmp_path / "b.epi"))
    diff = compare_runs(a["epi_path"], b["epi_path"])
    assert diff["delta_steps"] == 1
    assert diff["decisions_match"] is False
    assert diff["run_a"]["decisions"] == ["approve"]
    assert diff["run_b"]["decisions"] == ["reject"]
    assert diff["first_divergence_index"] == 1
    assert "record" in diff["scope_note"]


def test_compare_identical_runs_match(isolated_keys, tmp_path):
    from epi_mcp.tools import compare_runs, epi_seal_record_tool

    a = epi_seal_record_tool(
        [{"kind": "agent.decision", "content": {"decision": "go"}}],
        output_path=str(tmp_path / "a.epi"),
    )
    b = epi_seal_record_tool(
        [{"kind": "agent.decision", "content": {"decision": "go"}}],
        output_path=str(tmp_path / "b.epi"),
    )
    diff = compare_runs(a["epi_path"], b["epi_path"])
    assert diff["decisions_match"] is True
    assert diff["delta_steps"] == 0
    assert diff["first_divergence_index"] is None


def test_oauth_code_flow_seals(tmp_path, monkeypatch):
    """Register -> approve -> token -> seal bound to the OAuth subject."""
    import base64 as _b64
    import hashlib as _hl

    import pytest as _pytest

    starlette_test = _pytest.importorskip("starlette.testclient")
    monkeypatch.setenv("EPI_MCP_TOKEN", "s3cret")
    monkeypatch.setenv("EPI_MCP_PUBLIC_URL", "https://epi-mcp.onrender.com")
    monkeypatch.setenv("EPI_MCP_KEYS_DIR", str(tmp_path / "keys"))

    from epi_mcp.http import build_app

    client = starlette_test.TestClient(build_app(), raise_server_exceptions=False)

    meta = client.get("/.well-known/oauth-authorization-server").json()
    assert meta["token_endpoint"].endswith("/oauth/token")

    reg = client.post("/oauth/register", json={"redirect_uris": ["https://chat.example/cb"]}).json()
    assert reg["client_id"].startswith("epi-client-")

    verifier = "test-verifier-1234567890"
    challenge = _b64.urlsafe_b64encode(_hl.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    form = client.get("/oauth/authorize", params={
        "client_id": reg["client_id"], "redirect_uri": "https://chat.example/cb",
        "state": "s1", "code_challenge": challenge, "code_challenge_method": "S256"})
    assert form.status_code == 200 and "Approve" in form.text

    redir = client.post(
        "/oauth/approve?client_id=" + reg["client_id"]
        + "&redirect_uri=https://chat.example/cb&state=s1"
        + f"&code_challenge={challenge}&code_challenge_method=S256",
        data={"decision": "approve"}, follow_redirects=False)
    assert redir.status_code in (302, 303, 307)
    code = [kv.split("=")[1] for kv in redir.headers["location"].split("?")[1].split("&")
            if kv.startswith("code=")][0]

    tok = client.post("/oauth/token", data={
        "grant_type": "authorization_code", "code": code,
        "client_id": reg["client_id"], "redirect_uri": "https://chat.example/cb",
        "code_verifier": verifier}).json()
    assert tok["token_type"] == "Bearer"

    from epi_mcp.auth import verify_bearer_token

    subject = verify_bearer_token(tok["access_token"])
    assert subject and subject.startswith("chatgpt-")

    # Wrong verifier on a fresh code must fail at the PKCE check.
    redir2 = client.post(
        "/oauth/approve?client_id=" + reg["client_id"]
        + "&redirect_uri=https://chat.example/cb&state=s2"
        + f"&code_challenge={challenge}&code_challenge_method=S256",
        data={"decision": "approve"}, follow_redirects=False)
    code2 = [kv.split("=")[1] for kv in redir2.headers["location"].split("?")[1].split("&")
             if kv.startswith("code=")][0]
    bad = client.post("/oauth/token", data={
        "grant_type": "authorization_code", "code": code2,
        "client_id": reg["client_id"], "redirect_uri": "https://chat.example/cb",
        "code_verifier": "wrong"})
    assert bad.status_code == 400

def test_oauth_metadata_path_variants(monkeypatch):
    import pytest as _pytest
    starlette_test = _pytest.importorskip('starlette.testclient')
    monkeypatch.setenv('EPI_MCP_PUBLIC_URL', 'https://epi-mcp.onrender.com')
    monkeypatch.delenv('EPI_MCP_TOKEN', raising=False)
    from epi_mcp.http import build_app
    client = starlette_test.TestClient(build_app(), raise_server_exceptions=False)
    for path in ('/.well-known/oauth-authorization-server',
                 '/.well-known/oauth-authorization-server/mcp'):
        r = client.get(path)
        assert r.status_code == 200, path
        assert r.json()['token_endpoint'].endswith('/oauth/token')


def test_oauth_protected_resource_metadata(monkeypatch):
    import pytest as _pytest
    starlette_test = _pytest.importorskip("starlette.testclient")
    monkeypatch.setenv("EPI_MCP_PUBLIC_URL", "https://epi-mcp.onrender.com")
    monkeypatch.delenv("EPI_MCP_TOKEN", raising=False)
    from epi_mcp.http import build_app
    client = starlette_test.TestClient(build_app(), raise_server_exceptions=False)
    for path in ("/.well-known/oauth-protected-resource",
                 "/.well-known/oauth-protected-resource/mcp"):
        r = client.get(path)
        assert r.status_code == 200, path
        body = r.json()
        assert body["resource"].endswith("/mcp")
        assert body["authorization_servers"] == ["https://epi-mcp.onrender.com"]


def test_oauth_redirect_uri_must_be_registered(monkeypatch):
    starlette_test = pytest.importorskip("starlette.testclient")
    monkeypatch.setenv("EPI_OAUTH_SECRET", "x" * 32)

    from epi_mcp.http import build_app

    client = starlette_test.TestClient(build_app(), raise_server_exceptions=False)
    reg = client.post(
        "/oauth/register", json={"redirect_uris": ["https://chatgpt.com/cb"]}
    ).json()
    q = {"client_id": reg["client_id"], "state": "s", "response_type": "code"}
    ok = client.get("/oauth/authorize", params={**q, "redirect_uri": "https://chatgpt.com/cb"})
    assert ok.status_code == 200
    bad = client.get("/oauth/authorize", params={**q, "redirect_uri": "https://evil.example/cb"})
    assert bad.status_code == 400
    xss = client.get(
        "/oauth/authorize",
        params={**q, "state": '"><script>1</script>', "redirect_uri": "https://chatgpt.com/cb"},
    )
    assert "<script>1</script>" not in xss.text
