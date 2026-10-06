"""view_url: a person with nothing installed can open a sealed file in the browser."""

from __future__ import annotations

import glob
import os
import socket
import threading
import time

import pytest

pytest.importorskip("starlette.testclient")
from starlette.testclient import TestClient  # noqa: E402

EVENTS = [
    {"kind": "user.message", "content": {"text": "Approve the refund for order 4411"}, "fidelity": "verbatim"},
    {"kind": "assistant.message", "content": {"text": "Approved. Refund issued."}, "fidelity": "verbatim"},
]


@pytest.fixture
def sealed(monkeypatch, tmp_path):
    from epi_mcp import tools
    from epi_mcp.tools import _current_subject, epi_seal_record_tool

    monkeypatch.setenv("EPI_OAUTH_SECRET", "s" * 40)
    monkeypatch.setenv("EPI_MCP_KEYS_DIR", str(tmp_path / "keys"))
    monkeypatch.setenv("EPI_MCP_PUBLIC_URL", "http://127.0.0.1:8765")
    tok = _current_subject.set("view-caller")
    try:
        result = epi_seal_record_tool(EVENTS, goal="View test", include_bytes=False)
    finally:
        _current_subject.reset(tok)
    yield result
    tools.purge_expired_artifacts(now=10**12)


def _token(url):
    return url.split("?t=")[1]


def test_seal_result_gives_a_view_link_and_plain_instructions(sealed):
    assert sealed["view_url"].startswith("http://127.0.0.1:8765/view/" + sealed["artifact_id"] + "?t=")
    assert sealed["download_url"].startswith("http://127.0.0.1:8765/artifacts/")
    text = sealed["how_to_view"]
    assert "nothing" in text and "epilabs.org/verify" in text and "optional" in text


def test_view_serves_the_file_as_a_sandboxed_web_page_without_credentials(sealed):
    from epi_mcp.http import build_app

    client = TestClient(build_app(), raise_server_exceptions=False)
    r = client.get(f"/view/{sealed['artifact_id']}", params={"t": _token(sealed["view_url"])})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    csp = r.headers["content-security-policy"]
    assert "sandbox" in csp and "allow-same-origin" not in csp
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["cache-control"] == "no-store"
    assert "content-disposition" not in r.headers  # shown, not downloaded
    on_disk = open(sealed["epi_path"], "rb").read()
    assert r.content == on_disk  # the exact sealed bytes


def test_view_rejects_missing_wrong_and_other_files_tokens(sealed):
    from epi_mcp.http import build_app

    client = TestClient(build_app(), raise_server_exceptions=False)
    aid = sealed["artifact_id"]
    for params in ({}, {"t": "wrong"}, {"t": _token(sealed["view_url"]) + "x"}):
        r = client.get(f"/view/{aid}", params=params)
        assert r.status_code == 404 and "expired" in r.text and "epilabs.org/verify" in r.text
    # A link for one file does not open another.
    other = client.get("/view/0000000000000000", params={"t": _token(sealed["view_url"])})
    assert other.status_code == 404


def test_view_after_retention_purge_is_a_friendly_404(sealed):
    from epi_mcp import tools
    from epi_mcp.http import build_app

    client = TestClient(build_app(), raise_server_exceptions=False)
    token = _token(sealed["view_url"])
    tools.purge_expired_artifacts(now=10**12)
    r = client.get(f"/view/{sealed['artifact_id']}", params={"t": token})
    assert r.status_code == 404 and "<h1>" in r.text


def _chromium():
    hits = glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome")
    return os.environ.get("EPI_TEST_CHROMIUM") or (hits[0] if hits else None)


def test_view_link_renders_the_verified_record_in_a_real_browser_with_nothing_installed(monkeypatch, tmp_path):
    """Real server, real browser, no credentials: the person only has the link."""
    sync_api = pytest.importorskip("playwright.sync_api")
    uvicorn = pytest.importorskip("uvicorn")
    exe = _chromium()
    if not exe:
        pytest.skip("no chromium available")

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    base = f"http://127.0.0.1:{port}"
    monkeypatch.setenv("EPI_OAUTH_SECRET", "s" * 40)
    monkeypatch.setenv("EPI_MCP_KEYS_DIR", str(tmp_path / "keys"))
    monkeypatch.setenv("EPI_MCP_PUBLIC_URL", base)

    from epi_mcp import tools
    from epi_mcp.http import build_app
    from epi_mcp.tools import _current_subject, epi_seal_record_tool

    t = _current_subject.set("browser-caller")
    try:
        sealed = epi_seal_record_tool(EVENTS, goal="Browser view test", include_bytes=False)
    finally:
        _current_subject.reset(t)

    server = uvicorn.Server(uvicorn.Config(build_app(), host="127.0.0.1", port=port, log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.1)
    assert server.started
    try:
        with sync_api.sync_playwright() as p:
            browser = p.chromium.launch(executable_path=exe, args=["--no-sandbox"])
            page = browser.new_page()
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(sealed["view_url"])  # no Authorization header: only the link's token
            page.wait_for_timeout(4000)
            body = page.inner_text("body")
            browser.close()
        assert "INTEGRITY VERIFIED" in body and "SIGNATURE VALID" in body
        assert "Approve the refund for order 4411" in body
        assert not [e for e in errors if "SecurityError" in e or "Blocked" in e], errors
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        tools.purge_expired_artifacts(now=10**12)
