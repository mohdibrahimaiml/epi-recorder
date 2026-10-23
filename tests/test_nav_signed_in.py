"""epilabs.org nav: Dashboard when signed in at cloud.epilabs.org, else Sign In.

Serves website/ statically and stubs ONLY the cross-origin session probe
(Playwright route interception) — the page, its JS and the nav logic are real.
Browser-marked like the other site tests.
"""

from __future__ import annotations

import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

pytestmark = pytest.mark.browser

REPO = Path(__file__).resolve().parents[1]
PROBE = "https://cloud.epilabs.org/auth/session"


@pytest.fixture()
def site():
    handler = partial(SimpleHTTPRequestHandler, directory=str(REPO / "website"))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()


@pytest.fixture()
def browser():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        try:
            b = p.chromium.launch(args=["--no-sandbox"])
        except Exception:
            pytest.skip("no chromium available")
        yield b
        b.close()


def _stub_probe(pg, origin: str, body: str):
    def fulfill(route):
        route.fulfill(
            status=200,
            headers={
                "Access-Control-Allow-Origin": origin,
                "Access-Control-Allow-Credentials": "true",
                "Content-Type": "application/json",
            },
            body=body,
        )

    pg.route(PROBE, fulfill)


def test_nav_says_dashboard_when_signed_in(site, browser) -> None:
    ctx = browser.new_context()
    pg = ctx.new_page()
    try:
        _stub_probe(pg, site, '{"signed_in":true}')
        pg.goto(site + "/")
        pg.wait_for_selector("#nav-auth >> text=Dashboard", timeout=15000)
        assert pg.locator("#nav-auth").first.inner_text() == "Dashboard"
        assert pg.locator("#mob-nav-auth").inner_text() == "Dashboard"
    finally:
        ctx.close()


def test_nav_keeps_sign_in_when_probe_unreachable(site, browser) -> None:
    ctx = browser.new_context()
    pg = ctx.new_page()
    try:
        pg.route(PROBE, lambda route: route.abort())
        pg.goto(site + "/")
        pg.wait_for_selector("#nav-auth", timeout=15000)
        # The aborted probe resolves via the safety net; the label stays.
        pg.wait_for_timeout(3200)
        assert pg.locator("#nav-auth").first.inner_text() == "Sign In"
    finally:
        ctx.close()
