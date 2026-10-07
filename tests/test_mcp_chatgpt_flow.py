"""What ChatGPT does when it connects a custom MCP connector, step by step, against a real server.

ChatGPT cannot be driven from a test, so this replays its documented sequence: probe
the MCP URL, follow the 401's resource metadata, discover the authorization server,
register dynamically with its own redirect URI, authorize with PKCE and an RFC 8707
`resource`, redeem the code, call tools with the Bearer token, and later refresh.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import socket
import threading
import time
from urllib.parse import parse_qs, urlparse

import pytest

uvicorn = pytest.importorskip("uvicorn")
httpx = pytest.importorskip("httpx")

CHATGPT_REDIRECT = "https://chatgpt.com/connector_platform_oauth_redirect"
VERIFIER = "chatgpt-verifier-0123456789-abcdefghijklmnopqrstuvwxyz"
CHALLENGE = base64.urlsafe_b64encode(hashlib.sha256(VERIFIER.encode()).digest()).rstrip(b"=").decode()
EVENTS = [
    {"kind": "user.message", "content": {"text": "Approve invoice 8812 for payment"}, "fidelity": "verbatim"},
    {"kind": "assistant.message", "content": {"text": "Approved, within the 5,000 limit."}, "fidelity": "verbatim"},
]


@pytest.fixture
def live(monkeypatch, tmp_path):
    from epi_mcp import tools
    from epi_mcp.http import build_app

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    base = f"http://127.0.0.1:{port}"
    monkeypatch.setenv("EPI_OAUTH_SECRET", "c" * 40)
    monkeypatch.setenv("EPI_MCP_KEYS_DIR", str(tmp_path / "keys"))
    monkeypatch.setenv("EPI_MCP_PUBLIC_URL", base)
    monkeypatch.delenv("EPI_IDP_ISSUER", raising=False)
    server = uvicorn.Server(uvicorn.Config(build_app(), host="127.0.0.1", port=port, log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.1)
    assert server.started
    yield base
    server.should_exit = True
    thread.join(timeout=10)
    tools.purge_expired_artifacts(now=10**12)


def _connect_like_chatgpt(base):
    c = httpx.Client(timeout=10, follow_redirects=False)

    # 1. ChatGPT probes the MCP URL with no credentials and expects an OAuth challenge.
    probe = c.post(f"{base}/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
                   headers={"Accept": "application/json, text/event-stream"})
    assert probe.status_code == 401
    meta_url = probe.headers["www-authenticate"].split('resource_metadata="')[1].split('"')[0]

    # 2. It reads the protected-resource metadata, then the authorization server's.
    resource = c.get(meta_url).json()
    assert resource["resource"] == f"{base}/mcp"
    as_url = resource["authorization_servers"][0]
    as_meta = c.get(f"{as_url}/.well-known/oauth-authorization-server").json()
    assert "S256" in as_meta["code_challenge_methods_supported"]
    assert "none" in as_meta["token_endpoint_auth_methods_supported"]
    # Some clients ask for the path-suffixed well-known forms too.
    assert c.get(f"{base}/.well-known/oauth-authorization-server/mcp").status_code == 200
    assert c.get(f"{base}/.well-known/oauth-protected-resource/mcp").status_code == 200

    # 3. Dynamic client registration with ChatGPT's redirect URI.
    reg = c.post(as_meta["registration_endpoint"], json={
        "client_name": "ChatGPT", "redirect_uris": [CHATGPT_REDIRECT],
        "grant_types": ["authorization_code", "refresh_token"], "response_types": ["code"],
        "token_endpoint_auth_method": "none", "scope": "seal verify export",
    }).json()
    client_id = reg["client_id"]

    # 4. Authorization request (PKCE S256 + RFC 8707 resource), then the person approves.
    params = {"response_type": "code", "client_id": client_id, "redirect_uri": CHATGPT_REDIRECT,
              "state": "xyz", "scope": "seal verify export", "code_challenge": CHALLENGE,
              "code_challenge_method": "S256", "resource": f"{base}/mcp"}
    page = c.get(as_meta["authorization_endpoint"], params=params)
    assert page.status_code == 200 and "Approve" in page.text
    from urllib.parse import urlencode

    approve = c.post(f"{base}/oauth/approve?{urlencode(params)}", data={"decision": "approve"})
    assert approve.status_code == 303
    loc = urlparse(approve.headers["location"])
    assert f"{loc.scheme}://{loc.netloc}{loc.path}" == CHATGPT_REDIRECT
    q = parse_qs(loc.query)
    assert q["state"] == ["xyz"]

    # 5. Token exchange (form-encoded, public client, resource repeated).
    tok = c.post(as_meta["token_endpoint"], data={
        "grant_type": "authorization_code", "code": q["code"][0], "redirect_uri": CHATGPT_REDIRECT,
        "client_id": client_id, "code_verifier": VERIFIER, "resource": f"{base}/mcp"}).json()
    assert tok["token_type"].lower() == "bearer" and tok["access_token"] and tok["refresh_token"]
    return c, as_meta, client_id, tok


def test_chatgpt_connects_lists_and_seals_over_oauth(live):
    base = live
    c, as_meta, client_id, tok = _connect_like_chatgpt(base)
    from mcp.client.session import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    async def _use(access):
        async with httpx.AsyncClient(headers={"Authorization": f"Bearer {access}"}, timeout=30) as http:
            async with streamable_http_client(f"{base}/mcp", http_client=http) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    tools = {t.name: t for t in (await session.list_tools()).tools}
                    out = await session.call_tool(
                        "epi_seal_record", {"events": EVENTS, "goal": "ChatGPT flow", "include_bytes": False})
                    return tools, json.loads(out.content[0].text)

    tools, sealed = asyncio.run(_use(tok["access_token"]))

    # ChatGPT uses annotations to decide what needs a confirmation prompt.
    assert tools["epi_seal_record"].annotations.read_only_hint is False
    assert tools["epi_seal_record"].annotations.destructive_hint is False
    for name in ("epi_verify", "epi_export_summary", "epi_compare_runs"):
        assert tools[name].annotations.read_only_hint is True, name
    assert all(t.title for t in tools.values())

    # The seal works and hands back links a person can open from the chat.
    assert sealed["seal_check"]["signature_valid"] is True
    assert sealed["view_url"].startswith(f"{base}/view/") and sealed["download_url"].startswith(f"{base}/artifacts/")
    page = httpx.get(sealed["view_url"], timeout=10)
    assert page.status_code == 200 and page.headers["content-type"].startswith("text/html")

    # Later, ChatGPT refreshes the token and keeps working.
    fresh = c.post(as_meta["token_endpoint"], data={
        "grant_type": "refresh_token", "refresh_token": tok["refresh_token"], "client_id": client_id}).json()
    assert fresh["access_token"]
    again = asyncio.run(_use(fresh["access_token"]))[1]
    assert again["seal_check"]["signature_valid"] is True


def test_a_redirect_uri_the_client_did_not_register_is_refused(live):
    base = live
    c = httpx.Client(timeout=10, follow_redirects=False)
    reg = c.post(f"{base}/oauth/register", json={"redirect_uris": [CHATGPT_REDIRECT]}).json()
    bad = c.get(f"{base}/oauth/authorize", params={
        "response_type": "code", "client_id": reg["client_id"], "redirect_uri": "https://evil.example/cb",
        "state": "s", "code_challenge": CHALLENGE, "code_challenge_method": "S256"})
    assert bad.status_code == 400


def test_each_approved_caller_gets_their_own_signer_over_http(live):
    """Two people approve separately; their seals must not share a signing key or a quota bucket."""
    import zipfile

    base = live
    from mcp.client.session import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    async def _seal(access):
        async with httpx.AsyncClient(headers={"Authorization": f"Bearer {access}"}, timeout=30) as http:
            async with streamable_http_client(f"{base}/mcp", http_client=http) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    out = await session.call_tool(
                        "epi_seal_record", {"events": EVENTS, "goal": "who signed", "include_bytes": False})
                    return json.loads(out.content[0].text)

    def _public_key(sealed):
        with zipfile.ZipFile(sealed["epi_path"]) as zf:
            return json.loads(zf.read("manifest.json"))["public_key"]

    first = asyncio.run(_seal(_connect_like_chatgpt(base)[3]["access_token"]))
    second = asyncio.run(_seal(_connect_like_chatgpt(base)[3]["access_token"]))
    third = asyncio.run(_seal(_connect_like_chatgpt(base)[3]["access_token"]))
    assert len({first["sealed_for_subject"], second["sealed_for_subject"], third["sealed_for_subject"]}) == 3
    assert len({_public_key(first), _public_key(second), _public_key(third)}) == 3


def test_a_remote_caller_cannot_choose_where_the_server_writes(live, tmp_path):
    """output_path is for the local operator; over the network it must not write anywhere."""
    base = live
    from mcp.client.session import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    target = tmp_path / "planted.epi"
    access = _connect_like_chatgpt(base)[3]["access_token"]

    async def _try():
        async with httpx.AsyncClient(headers={"Authorization": f"Bearer {access}"}, timeout=30) as http:
            async with streamable_http_client(f"{base}/mcp", http_client=http) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    out = await session.call_tool("epi_seal_record", {
                        "events": EVENTS, "goal": "path", "output_path": str(target), "include_bytes": False})
                    return out

    asyncio.run(_try())
    assert not target.exists()


def test_a_messy_real_chat_seals_views_downloads_and_verifies_end_to_end(live, tmp_path):
    """A chat host's own style of record, through the real server: odd kind names, unicode, big tool
    output. The seal must succeed, say nothing false, open in a browser, download, and verify by id
    and from the downloaded bytes with the CLI."""
    import subprocess
    import sys

    base = live
    from mcp.client.session import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    big = "Result row — résumé 日本語 \"quoted\" \\ end\n" * 4000
    events = [
        {"kind": "user_request", "content": {"text": "find free tools like https://example.com \U0001F600"}},
        {"kind": "tool_call", "content": {"tool": "web_search", "input": {"q": "free alternatives 2026"}}},
        {"kind": "tool_result", "content": {"result": big}, "fidelity": "summary"},
        {"kind": "assistant_response", "content": {"text": "Straight answer: no free clone.\n\n| a | b |\n|--|--|\n| 1 | 2 |"},
         "fidelity": "verbatim"},
        {"kind": "observation", "content": {"text": "kept under the name it was sent with"}},
    ]
    access = _connect_like_chatgpt(base)[3]["access_token"]

    async def _run():
        async with httpx.AsyncClient(headers={"Authorization": f"Bearer {access}"}, timeout=60) as http:
            async with streamable_http_client(f"{base}/mcp", http_client=http) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()

                    async def call(name, args):
                        out = await session.call_tool(name, args)
                        assert not out.is_error, out.content
                        return json.loads(out.content[0].text)

                    sealed = await call("epi_seal_record", {"events": events, "goal": "Chat session"})
                    by_id = await call("epi_verify", {"artifact_id": sealed["artifact_id"]})
                    timeline = await call("epi_export_summary", {"artifact_id": sealed["artifact_id"]})
                    other = await call("epi_seal_record", {"events": events[:2], "goal": "second"})
                    diff = await call("epi_compare_runs", {
                        "artifact_id_a": sealed["artifact_id"], "artifact_id_b": other["artifact_id"]})
                    return sealed, by_id, timeline, diff

    sealed, by_id, timeline, diff = asyncio.run(_run())

    assert "epi_b64" not in sealed and len(json.dumps(sealed)) < 20_000      # a link, not the file as text
    assert sealed["seal_check"]["signature_valid"] and sealed["seal_check"]["integrity_ok"]
    assert not any("No user message" in w for w in sealed["warnings"])
    assert by_id["integrity_ok"] and by_id["signature_valid"]
    assert timeline and diff

    page = httpx.get(sealed["view_url"], timeout=20)
    assert page.status_code == 200 and "text/html" in page.headers["content-type"]
    got = httpx.get(sealed["download_url"], timeout=20)
    assert got.status_code == 200
    assert hashlib.sha256(got.content).hexdigest() == sealed["sha256"]
    saved = tmp_path / "record.epi"
    saved.write_bytes(got.content)
    cli = subprocess.run([sys.executable, "-m", "epi_cli.main", "verify", str(saved)],
                         capture_output=True, text=True, timeout=120)
    assert cli.returncode == 0, cli.stdout + cli.stderr
