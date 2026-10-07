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

    from epi_mcp.tools import _current_subject, epi_seal_record_tool

    _current_subject.set("operator")  # choosing the output path is for the local operator only
    result = epi_seal_record_tool(_events(), goal="bytes check", output_path=str(tmp_path / "b.epi"))
    raw = base64.b64decode(result["epi_b64"])
    assert raw[:4] == b"<!--"  # envelope-v2 polyglot magic
    assert result["filename"] == "b.epi"
    assert result["scope"] == "caller-provided"
    assert result["seal_check"]["signature_valid"] is True
    assert "did not supply" in " ".join(result["not_captured"])


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
    diff = compare_runs(a["artifact_id"], b["artifact_id"])
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
    diff = compare_runs(a["artifact_id"], b["artifact_id"])
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


def _keys(monkeypatch, tmp_path):
    monkeypatch.setenv("EPI_MCP_KEYS_DIR", str(tmp_path / "keys"))


def test_seal_declares_caller_provided_scope(monkeypatch, tmp_path):
    _keys(monkeypatch, tmp_path)
    import json
    import json
    import zipfile

    from epi_mcp.records import seal_record

    r = seal_record([{"kind": "user.message", "content": "hi"}], goal="g")
    m = json.loads(zipfile.ZipFile(r["epi_path"]).read("artifacts/manifest.json"))
    assert m["capture_path"] == "caller_provided"
    assert m["instrumented_surfaces"] == []
    assert any("caller" in g for g in m["known_gaps"])
    assert not any("wrap_openai" in g for g in m["known_gaps"])


def test_timestamp_provenance_and_fidelity_warnings(monkeypatch, tmp_path):
    _keys(monkeypatch, tmp_path)
    import json
    import json
    import zipfile

    from epi_mcp.records import seal_record

    events = [
        {"kind": "user.message", "content": {"text": "a"},
         "timestamp": "2026-10-05T10:00:00Z", "fidelity": "verbatim"},
        {"kind": "assistant.message", "content": {"text": "b"}, "fidelity": "summary"},
        {"kind": "assistant.message", "content": {"text": "c"}},
    ]
    r = seal_record(events)
    f = r["fidelity"]
    assert f["caller_timestamps"] == 1 and f["server_assigned_timestamps"] == 2
    assert f["by_fidelity"] == {"verbatim": 1, "summary": 1, "unspecified": 1}
    text = " ".join(f["warnings"])
    assert "no caller timestamp" in text and "summaries" in text and "do not say" in text
    steps = [
        json.loads(line)
        for line in zipfile.ZipFile(r["epi_path"]).read("steps.jsonl").decode().splitlines()
    ]
    assert steps[0]["content"]["_epi_provenance"]["timestamp_source"] == "caller"
    assert steps[0]["timestamp"].startswith("2026-10-05T10:00:00")
    assert steps[1]["content"]["_epi_provenance"]["timestamp_source"] == "server_received"
    assert steps[0]["prev_hash"] == "CHAIN_START" and steps[1]["prev_hash"] != "CHAIN_START"
    # Warnings are declared inside the signed artifact, not only in chat.
    m = json.loads(zipfile.ZipFile(r["epi_path"]).read("artifacts/manifest.json"))
    assert any("no caller timestamp" in g for g in m["known_gaps"])


def test_all_same_timestamp_is_flagged(monkeypatch, tmp_path):
    _keys(monkeypatch, tmp_path)
    from epi_mcp.records import seal_record

    r = seal_record([{"kind": "user.message", "content": "a"},
                     {"kind": "assistant.message", "content": "b"}])
    assert any("share one timestamp" in w for w in r["fidelity"]["warnings"])


def test_download_link_works_in_browser_and_verify_by_artifact_id(monkeypatch, tmp_path):
    starlette_test = pytest.importorskip("starlette.testclient")
    _keys(monkeypatch, tmp_path)
    monkeypatch.setenv("EPI_MCP_TOKEN", "s3cret")
    monkeypatch.setenv("EPI_MCP_PUBLIC_URL", "https://example.test")

    from epi_mcp.http import build_app
    from epi_mcp.tools import _current_subject, epi_seal_record_tool, epi_verify_tool

    _current_subject.set("someone")
    try:
        sealed = epi_seal_record_tool(
            [{"kind": "user.message", "content": "x"}], include_bytes=False
        )
    finally:
        _current_subject.set(None)
    assert "epi_b64" not in sealed and sealed["warnings"]
    assert epi_verify_tool(sealed["artifact_id"])["signature_valid"] is True

    client = starlette_test.TestClient(build_app(), raise_server_exceptions=False)
    path = sealed["download_url"].replace("https://example.test", "")
    assert client.get(path).status_code == 200            # browser click
    bare = f"/artifacts/{sealed['artifact_id']}"
    assert client.get(bare).status_code == 401            # no secret, no file
    assert client.get(bare + "?t=wrong").status_code == 401


def test_chain_is_real_and_tamper_is_caught(monkeypatch, tmp_path):
    _keys(monkeypatch, tmp_path)
    import json
    import json
    import zipfile

    from epi_cli.verify import _verify_step_chain
    from epi_mcp.records import seal_record, verify_artifact

    r = seal_record([
        {"kind": "user.message", "content": {"text": "approve?"}, "timestamp": "2026-10-05T10:00:00Z"},
        {"kind": "assistant.message", "content": {"text": "yes"}, "timestamp": "2026-10-05T10:00:05Z"},
        {"kind": "agent.decision", "content": {"decision": "approve"}, "timestamp": "2026-10-05T10:00:06Z"},
    ])
    raw = zipfile.ZipFile(r["epi_path"]).read("steps.jsonl").decode().splitlines()
    steps = [json.loads(line) for line in raw]
    spec = json.loads(zipfile.ZipFile(r["epi_path"]).read("manifest.json"))["spec_version"]
    ok, breaks = _verify_step_chain(steps, spec)
    assert ok and not breaks
    steps[1]["content"]["text"] = "no"          # edit a middle step
    ok, breaks = _verify_step_chain(steps, spec)
    assert not ok and any("step 2" in b for b in breaks)
    assert verify_artifact(r["epi_path"])["integrity_ok"] is True


def test_unknown_event_fields_are_preserved_not_dropped(monkeypatch, tmp_path):
    _keys(monkeypatch, tmp_path)
    import json
    import json
    import zipfile

    from epi_mcp.records import seal_record

    r = seal_record([{"kind": "tool.call", "content": {"name": "x"}, "event_id": "e-7"}])
    step = json.loads(zipfile.ZipFile(r["epi_path"]).read("steps.jsonl").decode().splitlines()[0])
    assert step["content"]["_caller_fields"] == {"event_id": "e-7"}


def test_source_type_and_tool_name_and_omission_counts(monkeypatch, tmp_path):
    _keys(monkeypatch, tmp_path)
    import json
    import json
    import zipfile

    from epi_mcp.records import seal_record
    from epi_mcp.tools import summarize_steps

    events = [
        {"kind": "user.message", "content": {"text": "q"}, "fidelity": "verbatim"},
        {"kind": "tool.call", "content": {"text": "searched"}, "fidelity": "summary"},
        {"kind": "tool.call", "content": {"tool": "search", "input": {"q": "x"}}},
        {"kind": "redaction.omitted", "content": {"text": "OMITTED: third-party data"}},
        {"kind": "assistant.message", "content": {"text": "a"}, "fidelity": "verbatim"},
    ]
    r = seal_record(events)
    steps = [
        json.loads(line)
        for line in zipfile.ZipFile(r["epi_path"]).read("steps.jsonl").decode().splitlines()
    ]
    by_kind = {s["kind"]: s for s in steps}
    assert by_kind["user.message"]["source_type"] == "user"      # was "reasoning"
    assert by_kind["redaction.omitted"]["source_type"] == "system"
    assert any("1 tool.call events have no tool name" in w for w in r["fidelity"]["warnings"])
    counts = summarize_steps(events)
    assert counts["omissions_declared"] == 1 and counts["redactions"] == 0


def test_epi_view_payload_carries_capture_manifest(monkeypatch, tmp_path):
    """`epi view` must show the declared scope, not 'undeclared (pre-v artifact)'."""
    _keys(monkeypatch, tmp_path)
    import json
    import zipfile

    from pathlib import Path

    from epi_cli.view import _build_preloaded_case_payload
    from epi_mcp.records import seal_record

    r = seal_record([{"kind": "user.message", "content": {"text": "hi"}}])
    out = tmp_path / "x"
    zipfile.ZipFile(r["epi_path"]).extractall(out)
    payload = _build_preloaded_case_payload(out, Path(r["epi_path"]))
    assert payload["capture_manifest"]["capture_path"] == "caller_provided"
    assert payload["capture_manifest"]["known_gaps"]
    assert payload["checkpoints"] == []


def test_oauth_clients_and_refresh_survive_restart(monkeypatch):
    """Registrations and refresh tokens are signed, not stored: wipe memory, still valid."""
    pytest.importorskip("jwt")
    monkeypatch.setenv("EPI_OAUTH_SECRET", "s" * 40)
    monkeypatch.setenv("EPI_MCP_PUBLIC_URL", "https://example.test")
    from epi_mcp import oauth

    reg = oauth.register_client({"redirect_uris": ["https://claude.ai/api/mcp/auth_callback"]})
    access, refresh = oauth.mint_token("chatgpt-abc")
    oauth.CLIENTS.clear(); oauth.CODES.clear(); oauth.REFRESH.clear(); oauth.SUBJECTS.clear()  # "restart"

    assert oauth.redirect_allowed(reg["client_id"], "https://claude.ai/api/mcp/auth_callback")
    assert not oauth.redirect_allowed(reg["client_id"], "https://evil.example/cb")
    # Flip (not just rewrite) the last MAC char: [:-1] + "0" is a no-op 1/16
    # of the time when it already ends in "0", which made this test flaky.
    last, flipped = reg["client_id"][-1], "0"
    if last == "0":
        flipped = "1"
    assert not oauth.redirect_allowed(reg["client_id"][:-1] + flipped, "https://claude.ai/api/mcp/auth_callback")
    out = oauth.redeem_refresh(refresh)
    assert out and oauth.verify_own_token(out["access_token"]) == "chatgpt-abc"
    assert oauth.redeem_refresh(refresh) is None              # rotated
    assert oauth.redeem_refresh(access) is None               # access token is not a refresh token
    monkeypatch.setenv("EPI_OAUTH_SECRET", "t" * 40)          # different server secret
    assert not oauth.redirect_allowed(reg["client_id"], "https://claude.ai/api/mcp/auth_callback")


def test_signer_is_stable_across_restarts_when_seed_set(monkeypatch, tmp_path):
    from epi_mcp.records import derived_signing_key, seal_record, verify_artifact

    monkeypatch.setenv("EPI_SIGNING_SEED", "seed" * 12)
    monkeypatch.setenv("EPI_MCP_KEYS_DIR", str(tmp_path / "keys-a"))
    a = seal_record([{"kind": "user.message", "content": "x"}], key_name="user-1")
    monkeypatch.setenv("EPI_MCP_KEYS_DIR", str(tmp_path / "keys-b"))   # fresh disk
    b = seal_record([{"kind": "user.message", "content": "x"}], key_name="user-1")
    c = seal_record([{"kind": "user.message", "content": "x"}], key_name="user-2")
    sa, sb, sc = (verify_artifact(r["epi_path"])["signer"] for r in (a, b, c))
    assert sa == sb != sc                                              # same caller, same signer
    assert verify_artifact(a["epi_path"])["signature_valid"] is True
    monkeypatch.delenv("EPI_SIGNING_SEED"); monkeypatch.delenv("EPI_OAUTH_SECRET", raising=False)
    assert derived_signing_key("user-1") is None
    monkeypatch.setenv("EPI_MCP_TOKEN", "bearer-token")                # static token must not seed keys
    assert derived_signing_key("user-1") is None


def test_sealed_file_is_deleted_when_retention_ends(monkeypatch, tmp_path):
    _keys(monkeypatch, tmp_path)
    from pathlib import Path

    from epi_mcp import tools
    from epi_mcp.tools import _current_subject, epi_seal_record_tool, get_artifact_path, purge_expired_artifacts

    _current_subject.set("someone")
    try:
        sealed = epi_seal_record_tool([{"kind": "user.message", "content": "private"}])
    finally:
        _current_subject.set(None)
    aid = sealed["artifact_id"]
    f = Path(sealed["epi_path"])
    assert f.exists() and "deletes this file" in sealed["retention"]
    assert get_artifact_path(aid) is not None
    assert purge_expired_artifacts() == 0 and f.exists()            # not yet
    tools._ARTIFACT_EXPIRY[aid] = 0.0                                 # retention over
    assert get_artifact_path(aid) is None                             # served no more
    assert not f.exists() and not f.parent.exists()                   # file + temp dir gone


def test_operator_chosen_output_path_is_never_deleted(monkeypatch, tmp_path):
    _keys(monkeypatch, tmp_path)
    from epi_mcp import tools
    from epi_mcp.tools import _current_subject, epi_seal_record_tool, purge_expired_artifacts

    _current_subject.set("operator")
    try:
        out = tmp_path / "mine.epi"
        sealed = epi_seal_record_tool([{"kind": "user.message", "content": "x"}], output_path=str(out))
    finally:
        _current_subject.set(None)
    assert sealed["artifact_id"] not in tools._ARTIFACT_EXPIRY
    purge_expired_artifacts(now=10**12)
    assert out.exists()


def test_model_facing_text_avoids_trigger_phrases():
    """Tool text the host model reads must state scope without phrases that
    safety classifiers can misread as a request to expose reasoning."""
    import inspect

    import epi_mcp.server as srv
    from epi_mcp.records import SCOPE_NOTE
    from epi_mcp.tools import NOT_CAPTURED

    texts = [SCOPE_NOTE, " ".join(NOT_CAPTURED), srv.SEAL_GUIDE, inspect.getsource(srv)]
    for tool in srv.server._tool_manager.list_tools() if hasattr(srv.server, "_tool_manager") else []:
        texts.append(getattr(tool, "description", "") or "")
    blob = " ".join(texts).lower()
    for phrase in ("hidden reasoning", "model-internal", "chain-of-thought", "reasoning extraction"):
        assert phrase not in blob, phrase


def test_oversized_records_get_a_clear_way_forward(monkeypatch, tmp_path):
    _keys(monkeypatch, tmp_path)
    from epi_mcp.tools import _current_subject, epi_seal_record_tool

    _current_subject.set("someone")
    try:
        big = [{"kind": "tool.response", "content": {"result": "x" * (9 * 1024 * 1024)}}]
        with pytest.raises(ValueError, match="hash_only"):
            epi_seal_record_tool(big)
        many = [{"kind": "user.message", "content": "a"}] * 5001
        with pytest.raises(ValueError, match="in parts"):
            epi_seal_record_tool(many)
    finally:
        _current_subject.set(None)


def test_decision_without_a_decision_field_is_flagged(monkeypatch, tmp_path):
    _keys(monkeypatch, tmp_path)
    from epi_mcp.records import seal_record

    r = seal_record([
        {"kind": "user.message", "content": {"text": "q"}, "fidelity": "verbatim"},
        {"kind": "agent.decision", "content": {"text": "chose option A"}},
        {"kind": "agent.decision", "content": {"decision": "approve", "rationale": "ok"}},
    ])
    assert any("1 agent.decision events have no decision field" in w for w in r["fidelity"]["warnings"])


def test_usage_notes_stay_short_and_cover_fidelity_privacy_and_what_to_tell_the_user():
    import epi_mcp.server as srv

    guide = srv.SEAL_GUIDE
    assert len(guide) < 1500
    for needle in ("fidelity", "[REDACTED]", "redaction.omitted", "view link", "SHA-256", "not that it is complete"):
        assert needle in guide, needle


def test_seal_response_never_exceeds_the_mcp_event_limit(monkeypatch, tmp_path):
    """MCP clients cap one event at 1 MiB. The result used to carry the file
    twice (text + structured) so even a minimal seal was over; large files must
    fall back to the download link."""
    import asyncio
    import json

    monkeypatch.setenv("EPI_MCP_KEYS_DIR", str(tmp_path / "keys"))
    from epi_mcp.server import server
    from epi_mcp.tools import _current_subject

    async def call(events):
        _current_subject.set("operator")
        try:
            res = await server.call_tool("epi_seal_record", {"events": events})
        finally:
            _current_subject.set(None)
        text = sum(len(c.text) for c in res.content if hasattr(c, "text"))
        structured = (
            len(json.dumps(res.structured_content))
            if getattr(res, "structured_content", None) is not None
            else 0
        )
        return text + structured, json.loads(res.content[0].text)

    small_total, small = asyncio.run(call([{"kind": "user.message", "content": {"text": "hi"}}]))
    assert small_total < 1_048_576 and "epi_b64" in small      # one copy, delivered inline

    big_total, big = asyncio.run(call([{"kind": "assistant.message", "content": {"text": "x" * 3_000_000}}]))
    assert big_total < 1_048_576
    assert "epi_b64" not in big and "bytes_omitted" in big      # falls back to the link/path
    assert big["filename"] and big["sha256"]


def test_approve_page_requires_passphrase_when_configured(tmp_path, monkeypatch):
    import pytest as _pytest

    starlette_test = _pytest.importorskip("starlette.testclient")
    monkeypatch.setenv("EPI_OAUTH_SECRET", "x" * 32)
    monkeypatch.setenv("EPI_APPROVE_PASSPHRASE", "open-sesame")

    from epi_mcp.http import build_app

    client = starlette_test.TestClient(build_app(), raise_server_exceptions=False)
    reg = client.post("/oauth/register", json={"redirect_uris": ["https://chat.example/cb"]}).json()
    q = "client_id=" + reg["client_id"] + "&redirect_uri=https://chat.example/cb&state=s"
    page = client.get("/oauth/authorize?" + q)
    assert 'type="password"' in page.text

    wrong = client.post("/oauth/approve?" + q, data={"decision": "approve", "passphrase": "nope"},
                        follow_redirects=False)
    assert wrong.status_code == 403 and "code=" not in wrong.headers.get("location", "")
    missing = client.post("/oauth/approve?" + q, data={"decision": "approve"}, follow_redirects=False)
    assert missing.status_code == 403
    ok = client.post("/oauth/approve?" + q, data={"decision": "approve", "passphrase": "open-sesame"},
                     follow_redirects=False)
    assert ok.status_code == 303 and "code=" in ok.headers["location"]
    deny = client.post("/oauth/approve?" + q, data={"decision": "deny"}, follow_redirects=False)
    assert "access_denied" in deny.headers["location"]


def test_no_passphrase_means_no_password_field(monkeypatch):
    import pytest as _pytest

    starlette_test = _pytest.importorskip("starlette.testclient")
    monkeypatch.setenv("EPI_OAUTH_SECRET", "x" * 32)
    monkeypatch.delenv("EPI_APPROVE_PASSPHRASE", raising=False)

    from epi_mcp.http import build_app

    client = starlette_test.TestClient(build_app(), raise_server_exceptions=False)
    reg = client.post("/oauth/register", json={"redirect_uris": ["https://chat.example/cb"]}).json()
    page = client.get("/oauth/authorize", params={
        "client_id": reg["client_id"], "redirect_uri": "https://chat.example/cb", "state": "s"})
    assert 'type="password"' not in page.text


def test_storage_quota_refuses_seal_and_frees_after_purge(tmp_path, monkeypatch):
    from epi_mcp import tools
    from epi_mcp.tools import _current_subject, epi_seal_record_tool

    monkeypatch.setenv("EPI_MCP_KEYS_DIR", str(tmp_path / "keys"))
    monkeypatch.setattr(tools, "MAX_LIVE_ARTIFACTS_PER_CALLER", 1)
    tools._ARTIFACT_OWNER.clear()
    tools._ARTIFACT_EXPIRY.clear()
    tok = _current_subject.set("quota-caller")
    try:
        first = epi_seal_record_tool(_events(), goal="one", include_bytes=False)
        assert first["artifact_id"] in tools._ARTIFACT_OWNER
        import pytest as _pytest

        with _pytest.raises(ValueError, match="quota"):
            epi_seal_record_tool(_events(), goal="two", include_bytes=False)
        # Another caller is unaffected by this caller's quota.
        _current_subject.set("other-caller")
        epi_seal_record_tool(_events(), goal="three", include_bytes=False)
        # Expiry frees the first caller's space.
        _current_subject.set("quota-caller")
        tools.purge_expired_artifacts(now=10**12)
        epi_seal_record_tool(_events(), goal="four", include_bytes=False)
    finally:
        _current_subject.reset(tok)
        tools.purge_expired_artifacts(now=10**12)


def test_tool_is_discoverable_from_natural_requests_and_has_one_click_prompts():
    """Real users say 'seal this chat'. The host must connect that to this tool
    (not write a Markdown file), and the connector menu must offer a no-typing start."""
    import asyncio

    from epi_mcp.server import server

    tools = {t.name: t for t in asyncio.run(server.list_tools())}
    desc = tools["epi_seal_record"].description.lower()
    for phrase in ("seal", "save", "export", "chat", "markdown or text file is not a signed record"):
        assert phrase in desc
    assert "markdown" in (server.instructions or "").lower()

    prompts = {p.name: p for p in asyncio.run(server.list_prompts())}
    assert {"seal_this_conversation", "seal_last_answer"} <= set(prompts)
    for name in prompts:
        text = asyncio.run(server.get_prompt(name))
        body = " ".join(
            getattr(m.content, "text", "") for m in text.messages
        ).lower()
        assert "evidence sealer" in body


def _host_visible_text():
    """Everything the connector puts in front of the model: tool descriptions,
    server instructions and the one-click prompts."""
    import asyncio

    from epi_mcp.server import server

    parts = {"instructions": server.instructions or ""}
    for t in asyncio.run(server.list_tools()):
        parts[f"tool:{t.name}"] = t.description or ""
    for p in asyncio.run(server.list_prompts()):
        m = asyncio.run(server.get_prompt(p.name))
        parts[f"prompt:{p.name}"] = " ".join(getattr(x.content, "text", "") for x in m.messages)
    return parts


# A host's safety filter can read "capture what the model reasoned or was told"
# into wording like this. Compliance users need the product to work every time, so
# the model-facing text avoids the whole family of phrases. Details a host does not
# need before calling belong in the tool result instead.
# Directive wording reads like an attempt to steer the model (injection-style) and gets
# flagged or ignored; the connector states facts and lets the model decide.
_STEERING_TEXT = ("do not", "don't", "must ", "never ", "always ", "ignore", "you should", "important:", "at all costs")

_RISKY_HOST_TEXT = (
    "rationale", "reasoning", "chain of thought", "chain-of-thought", "thinking",
    "system prompt", "system instruction", "hidden", "internal", "supplied by the host",
    "word for word", "every message", "memory context", "scratch",
)


def test_text_shown_to_the_host_model_avoids_phrases_a_safety_filter_can_misread():
    parts = _host_visible_text()
    assert "tool:epi_seal_record" in parts and "prompt:seal_this_conversation" in parts
    for where, text in parts.items():
        low = text.lower()
        for phrase in _RISKY_HOST_TEXT:
            assert phrase not in low, f"{phrase!r} in {where}"


def test_text_shown_to_the_host_model_states_facts_instead_of_giving_orders():
    for where, text in _host_visible_text().items():
        low = text.lower()
        for phrase in _STEERING_TEXT:
            assert phrase not in low, f"{phrase!r} in {where}"


def test_host_visible_text_stays_small_and_still_routes_natural_requests():
    parts = _host_visible_text()
    assert sum(len(v) for v in parts.values()) < 5000
    low = parts["tool:epi_seal_record"].lower()
    for phrase in ("seal", "save", "export", "audit record", "markdown or text file is not a signed record"):
        assert phrase in low, phrase
    assert "markdown" in parts["instructions"].lower()
    for name in ("prompt:seal_this_conversation", "prompt:seal_last_answer"):
        assert "evidence sealer" in parts[name].lower()


def test_over_the_network_tools_accept_only_artifact_ids_never_file_paths(tmp_path, monkeypatch):
    """A public server must not let an approved caller aim verify/read-back/compare at other files."""
    monkeypatch.setenv("EPI_MCP_KEYS_DIR", str(tmp_path / "keys"))
    from epi_mcp import tools
    from epi_mcp.tools import (
        _current_subject,
        compare_runs,
        epi_export_summary_tool,
        epi_seal_record_tool,
        epi_verify_tool,
    )

    secret_file = tmp_path / "other-user.epi"
    secret_file.write_bytes(b"not for you")
    tok = _current_subject.set("remote-caller")
    try:
        sealed = epi_seal_record_tool(_events(), goal="ids only", include_bytes=False)
        aid = sealed["artifact_id"]
        # The id from sealing works for all three tools.
        assert epi_verify_tool(aid)["integrity_ok"] is True
        assert epi_export_summary_tool(aid)["steps_total"] == len(_events())
        assert compare_runs(aid, aid)
        # Paths do not: not a real file, not an existing file, not a relative path.
        for bad in ("/etc/passwd", str(secret_file), "../../etc/hostname", sealed["epi_path"]):
            for call in (epi_verify_tool, epi_export_summary_tool):
                with pytest.raises(ValueError, match="artifact_id"):
                    call(bad)
            with pytest.raises(ValueError, match="artifact_id"):
                compare_runs(aid, bad)
        # An id that has expired gets its own clear message, not a path error.
        tools.purge_expired_artifacts(now=10**12)
        with pytest.raises(ValueError, match="no longer on the server"):
            epi_verify_tool(aid)
    finally:
        _current_subject.reset(tok)
        tools.purge_expired_artifacts(now=10**12)


def test_the_local_operator_can_still_use_file_paths(tmp_path, monkeypatch):
    monkeypatch.setenv("EPI_MCP_KEYS_DIR", str(tmp_path / "keys"))
    from epi_mcp.records import seal_record
    from epi_mcp.tools import _current_subject, epi_verify_tool

    local = seal_record(_events(), goal="local", output_path=tmp_path / "local.epi")["epi_path"]
    assert epi_verify_tool(str(local))["integrity_ok"] is True  # stdio: no subject
    tok = _current_subject.set("operator")  # loopback dev server with no authentication
    try:
        assert epi_verify_tool(str(local))["integrity_ok"] is True
    finally:
        _current_subject.reset(tok)


def test_every_tool_has_a_title_inside_its_annotations_as_the_directory_requires():
    import asyncio

    from epi_mcp.server import server

    tools = asyncio.run(server.list_tools())
    assert len(tools) == 4
    for t in tools:
        assert t.annotations is not None and t.annotations.title, t.name
        assert t.annotations.title == t.title


# ---- a slow public time-stamp service must never hold a seal hostage -------------------------------


@pytest.fixture
def slow_tsa(monkeypatch):
    """A time-stamp service that accepts the request and then takes far too long to answer."""
    import http.server
    import threading
    import time

    class Slow(http.server.BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            time.sleep(30)

        def log_message(self, *a):
            pass

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Slow)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setenv("EPI_TSA_URL", f"http://127.0.0.1:{srv.server_address[1]}/tsr")
    monkeypatch.setenv("EPI_NOTARIZE", "1")
    yield srv
    srv.shutdown()


def test_a_slow_timestamp_service_delays_a_seal_by_seconds_not_half_a_minute(slow_tsa, tmp_path, monkeypatch):
    import time

    monkeypatch.setenv("EPI_MCP_KEYS_DIR", str(tmp_path / "keys"))
    monkeypatch.setenv("EPI_TSA_TIMEOUT", "2")
    from epi_mcp.tools import _current_subject, epi_seal_record_tool

    tok = _current_subject.set("someone")
    try:
        t0 = time.time()
        sealed = epi_seal_record_tool(_events(), goal="slow tsa", include_bytes=False)
        elapsed = time.time() - t0
    finally:
        _current_subject.reset(tok)
    assert elapsed < 8, f"seal took {elapsed:.1f}s"
    assert sealed["seal_check"]["signature_valid"] is True and sealed["seal_check"]["integrity_ok"] is True
    assert any("No trusted timestamp" in w for w in sealed["warnings"])


def test_the_hosted_server_waits_only_a_few_seconds_for_the_timestamp_service_by_default(monkeypatch):
    import subprocess
    import sys

    code = (
        "import os; os.environ.pop('EPI_TSA_TIMEOUT', None); import epi_mcp.tools; "
        "from epi_core.notarize import _tsa_timeout; t = _tsa_timeout(); print(t.read, t.connect)"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True).stdout.split()
    assert float(out[0]) <= 10 and float(out[1]) <= 5
    from epi_core.notarize import _tsa_timeout

    monkeypatch.delenv("EPI_TSA_TIMEOUT", raising=False)
    assert _tsa_timeout().read == 30.0  # the local CLI keeps its patient default
    monkeypatch.setenv("EPI_TSA_TIMEOUT", "not-a-number")
    assert _tsa_timeout().read == 30.0


def test_no_timestamp_warning_is_absent_when_notarization_is_switched_off(tmp_path, monkeypatch):
    monkeypatch.setenv("EPI_MCP_KEYS_DIR", str(tmp_path / "keys"))
    monkeypatch.setenv("EPI_NOTARIZE", "0")
    from epi_mcp.tools import _current_subject, epi_seal_record_tool

    tok = _current_subject.set("someone")
    try:
        sealed = epi_seal_record_tool(_events(), include_bytes=False)
    finally:
        _current_subject.reset(tok)
    assert not any("trusted timestamp" in w for w in sealed["warnings"])


def test_remote_callers_get_links_not_the_whole_file_as_text(tmp_path, monkeypatch):
    """A small chat is over half a megabyte of base64; the chat model needs the links, not the bytes."""
    monkeypatch.setenv("EPI_MCP_KEYS_DIR", str(tmp_path / "keys"))
    monkeypatch.setenv("EPI_NOTARIZE", "0")
    monkeypatch.setenv("EPI_MCP_PUBLIC_URL", "https://epi.example")
    from epi_mcp.tools import _current_subject, epi_seal_record_tool

    tok = _current_subject.set("remote-caller")
    try:
        remote = epi_seal_record_tool(_events(), include_bytes=True)
    finally:
        _current_subject.reset(tok)
    assert "epi_b64" not in remote and remote["view_url"] and remote["download_url"]
    assert len(__import__("json").dumps(remote)) < 20_000
    # Without public links there is no other way to hand over the file, so it still comes inline.
    monkeypatch.delenv("EPI_MCP_PUBLIC_URL")
    tok = _current_subject.set("remote-caller")
    try:
        inline = epi_seal_record_tool(_events(), include_bytes=True)
    finally:
        _current_subject.reset(tok)
    assert inline.get("epi_b64")


def test_near_miss_kind_names_are_read_as_the_canonical_kinds(isolated_keys):
    """A chat model sent user_request / assistant_response; the server must not say there was no user message."""
    import json
    import zipfile

    from epi_mcp.records import seal_record

    r = seal_record([
        {"kind": "user_request", "content": {"text": "hi"}},
        {"kind": "assistant_response", "content": {"text": "yo"}},
        {"kind": "tool_call", "content": {"tool": "search", "input": {}}},
        {"kind": "observation", "content": {"text": "kept as sent"}},
    ])
    steps = [
        json.loads(line)
        for line in zipfile.ZipFile(r["epi_path"]).read("steps.jsonl").decode().splitlines()
    ]
    assert [s["kind"] for s in steps] == ["user.message", "assistant.message", "tool.call", "observation"]
    assert steps[0]["content"]["_epi_provenance"]["caller_kind"] == "user_request"
    assert "caller_kind" not in steps[3]["content"]["_epi_provenance"]
    assert not any("No user message" in w for w in r["fidelity"]["warnings"])


def test_verify_export_and_compare_accept_artifact_id(isolated_keys):
    """The tool descriptions say artifact_id; the parameter must exist under that name."""
    from epi_mcp import server as srv
    from epi_mcp.tools import _current_subject, epi_seal_record_tool

    tok = _current_subject.set("operator")
    try:
        a = epi_seal_record_tool([{"kind": "user.message", "content": {"text": "a"}}], include_bytes=False)
        b = epi_seal_record_tool([{"kind": "user.message", "content": {"text": "b"}}], include_bytes=False)
        assert srv.epi_verify(artifact_id=a["artifact_id"])["integrity_ok"] is True
        assert srv.epi_verify(epi_path=a["artifact_id"])["integrity_ok"] is True
        assert srv.epi_export_summary(artifact_id=a["artifact_id"])
        assert srv.epi_compare_runs(artifact_id_a=a["artifact_id"], artifact_id_b=b["artifact_id"])
        with pytest.raises(ValueError):
            srv.epi_verify()
    finally:
        _current_subject.reset(tok)
