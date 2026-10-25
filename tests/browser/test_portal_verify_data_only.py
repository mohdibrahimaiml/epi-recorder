"""Portal verify page accepts a data-only .epi (no embedded viewer) without blanking.

The free `/verify/` page renders the *verdict* (structure/integrity/signature),
not an embedded viewer, so a data-only seal must verify exactly like a polyglot.
This drops a data-only artifact into the real page and asserts the verdict renders.
"""

from __future__ import annotations

import functools
import http.server
import threading
from pathlib import Path

import pytest

from epi_core.container import (
    EPIContainer,
    EPI_CONTAINER_FORMAT_LEGACY,
)
from epi_core.schemas import ManifestModel

pytestmark = pytest.mark.browser

ROOT = Path(__file__).resolve().parents[2]
STATIC = ROOT / "verify_portal" / "static"


def _with_page(config):  # type: ignore[no-untyped-def]
    playwright = pytest.importorskip("playwright.sync_api")
    headless = bool(config.getoption("--headless", default=True))
    manager = playwright.sync_playwright()
    started = manager.__enter__()
    try:
        try:
            browser = started.chromium.launch(headless=headless)
        except Exception as exc:  # pragma: no cover - depends on local browser install
            pytest.skip(f"Playwright Chromium is not installed or cannot launch: {exc}")
        return manager, browser, browser.new_page()
    except Exception:
        manager.__exit__(None, None, None)
        raise


def _write_data_only_epi(tmp_path: Path) -> Path:
    src = tmp_path / "src"
    src.mkdir()
    (src / "steps.jsonl").write_text(
        '{"index": 0, "kind": "session.start", "content": {}}\n', encoding="utf-8"
    )
    (src / "environment.json").write_text('{"runtime": "python"}', encoding="utf-8")
    out = tmp_path / "data-only.epi"
    EPIContainer.pack(
        src,
        ManifestModel(cli_command="portal-test"),
        out,
        container_format=EPI_CONTAINER_FORMAT_LEGACY,
        embed_viewer=False,
        generate_analysis=False,
    )
    # Guard the premise: this artifact has no embedded viewer.html.
    with EPIContainer._payload_zip_path(out) as payload:
        import zipfile

        with zipfile.ZipFile(payload) as zf:
            assert "viewer.html" not in zf.namelist()
    return out


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):  # noqa: D102 - silence test server
        pass


def test_portal_verifies_data_only_file(tmp_path: Path, request):
    if not STATIC.exists():
        pytest.skip("verify_portal static assets are not present")

    epi = _write_data_only_epi(tmp_path)

    handler = functools.partial(_QuietHandler, directory=str(STATIC))
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()

    try:
        manager, browser, page = _with_page(request.config)
        try:
            page.goto(f"http://127.0.0.1:{port}/verify/", wait_until="load")
            # The page's drop zone is wired to this hidden file input.
            page.set_input_files("#fileInput", str(epi))
            # Wait for the verdict to populate (the panel first shows "Reading …").
            page.wait_for_function(
                "() => { const el = document.querySelector('#chk2');"
                " return el && el.innerText.includes('PASS'); }",
                timeout=20000,
            )
            verdict = page.locator("#dropResult").inner_text(timeout=5000)
            integrity_check = page.locator("#chk2").inner_text(timeout=5000)
        finally:
            browser.close()
            manager.__exit__(None, None, None)
    finally:
        httpd.shutdown()

    # Not blank, not an error: the seal verdict rendered for a data-only file.
    # (The verdict prose lives in a collapsed <details>, so assert on the panel
    # being populated plus the integrity check row.)
    assert verdict.strip(), "result panel was blank"
    assert "no signature" in verdict.lower(), verdict  # unsigned test artifact
    assert "Integrity" in integrity_check and "PASS" in integrity_check, integrity_check
