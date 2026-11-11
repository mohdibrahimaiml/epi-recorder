"""The tamper lab must re-render every detail line, in both directions.

A flipped byte used to leave ``02 Integrity PASS`` / ``03 Signature VALID``
under a red "file changed" headline, because the viewer-fail branch returned
before updating the six check rows. A verifier that says VALID on a tampered
file cannot ship.
"""

from __future__ import annotations

import http.server
import threading
from pathlib import Path

import pytest

pytestmark = pytest.mark.browser


def _with_page(config):  # type: ignore[no-untyped-def]
    playwright = pytest.importorskip("playwright.sync_api")
    headless = bool(config.getoption("--headless", default=True))
    manager = playwright.sync_playwright()
    started = manager.__enter__()
    try:
        try:
            browser = started.chromium.launch(headless=headless)
        except Exception as exc:  # pragma: no cover - local browser install
            pytest.skip(f"Playwright Chromium is not installed or cannot launch: {exc}")
        return manager, browser, browser.new_page()
    except Exception:
        manager.__exit__(None, None, None)
        raise


def _serve(directory: Path):  # type: ignore[no-untyped-def]
    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):  # noqa: ANN002, ANN003
            super().__init__(*args, directory=str(directory), **kwargs)

        def log_message(self, *args):  # noqa: ANN002
            return

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_port}"


def _checks(page) -> dict[str, str]:
    return {
        key: page.locator(f"#{key}").inner_text()
        for key in ("chk1", "chk2", "chk3", "chk4", "chk5", "chk6")
    }


def test_flip_and_restore_re_render_every_line(request) -> None:
    website = Path(__file__).resolve().parents[2] / "website"
    server, base = _serve(website)
    manager, browser, page = _with_page(request.config)
    page.route(
        "https://cloud.epilabs.org/**",
        lambda route: route.fulfill(status=200, content_type="application/json", body="{}"),
    )
    try:
        page.goto(base + "/verify/", wait_until="networkidle")
        page.click("#loadSampleValidBtn")
        page.wait_for_function(
            "() => { const e = document.querySelector('#chk2'); return e && /PASS/.test(e.innerText); }",
            timeout=20000,
        )
        before = _checks(page)
        assert "PASS" in before["chk2"]
        assert "VALID" in before["chk3"]

        page.click("#tamperLoadedFileBtn")
        page.wait_for_function(
            "() => { const e = document.querySelector('#chk2'); return e && /FAIL/.test(e.innerText); }",
            timeout=20000,
        )
        after = _checks(page)
        assert "PASS" not in after["chk2"], after
        assert "FAIL" in after["chk2"], after
        assert "INVALID" in after["chk3"], after

        page.click("#restoreLoadedFileBtn")
        page.wait_for_function(
            "() => { const e = document.querySelector('#chk2'); return e && /PASS/.test(e.innerText); }",
            timeout=20000,
        )
        restored = _checks(page)
        assert "PASS" in restored["chk2"], restored
        assert "VALID" in restored["chk3"], restored
        assert "FAIL" not in restored["chk2"], restored
    finally:
        browser.close()
        manager.__exit__(None, None, None)
        server.shutdown()
