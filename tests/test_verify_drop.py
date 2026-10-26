"""The public /verify/ drop zone works with a real drop, like a customer does.

Opens the real website/verify/ page in Chromium and dispatches a genuine
`drop` event carrying a real file (via DataTransfer) onto the drop zone —
the same handler a customer's drag-and-drop hits. The existing
set_input_files tests only drive the click-to-choose path; nothing until now
executed the drop path, so a broken drop handler would pass every test.
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
SAMPLE_URL = "/assets/sample.epi"

DROP_JS = """(async (url, mutate) => {
  const buf = await (await fetch(url)).arrayBuffer();
  let blob;
  let name = 'case.epi';
  if (mutate === 'text') {
    blob = new Blob(['hello, not an epi file'], { type: 'text/plain' });
    name = 'notes.txt';
  } else {
    const bytes = new Uint8Array(buf);
    if (mutate === 'viewer') {
      const text = new TextDecoder().decode(bytes.slice(0, 4096));
      const i = text.indexOf('<html');
      if (i < 0) return 'no-viewer-marker';
      bytes[i + 1] ^= 0x20;
    }
    blob = new Blob([bytes], { type: 'application/octet-stream' });
  }
  const dt = new DataTransfer();
  dt.items.add(new File([blob], name));
  const dz = document.getElementById('dropZoneEl');
  dz.dispatchEvent(new DragEvent('drop', { bubbles: true, cancelable: true, dataTransfer: dt }));
  return 'dropped';
})"""


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


def _drop(pg, mutate=None) -> str:
    return pg.evaluate(DROP_JS + (f'("{SAMPLE_URL}", "{mutate}")' if mutate else f'("{SAMPLE_URL}")'))


def test_genuine_file_dropped_on_verify_page(site, browser) -> None:
    ctx = browser.new_context()
    pg = ctx.new_page()
    try:
        pg.goto(site + "/verify/")
        pg.wait_for_selector("#dropZoneEl", timeout=15000)
        assert _drop(pg) == "dropped"
        pg.wait_for_function(
            "() => document.querySelector('#dropResult').textContent.length > 20",
            timeout=30000,
        )
        text = pg.locator("#dropResult").inner_text()
        assert "hasn't been changed since it was sealed" in text, text[:500]
        # What the AI did is shown up front, read from the sealed steps.
        assert "WHAT THE AI DID" in text, text[:500]
        pg.locator("#dropResult summary", has_text="Details").click()
        pg.wait_for_selector("#dropResult >> text=Signature:", timeout=10000)
        full = pg.locator("#dropResult").inner_text()
        assert "Signature: VALID" in full, full[:800]
        assert "was changed after it was sealed" not in text, text[:500]
        assert "INVALID" not in full, full[:800]
    finally:
        ctx.close()


def test_tampered_file_dropped_on_verify_page(site, browser) -> None:
    ctx = browser.new_context()
    pg = ctx.new_page()
    try:
        pg.goto(site + "/verify/")
        pg.wait_for_selector("#dropZoneEl", timeout=15000)
        assert _drop(pg, "viewer") == "dropped"
        pg.wait_for_function(
            "() => document.querySelector('#dropResult').textContent.length > 20",
            timeout=30000,
        )
        text = pg.locator("#dropResult").inner_text()
        assert "was changed after it was sealed" in text, text[:500]
        assert "hasn't been changed since it was sealed" not in text, text[:500]
    finally:
        ctx.close()


def test_non_epi_file_dropped_on_verify_page(site, browser) -> None:
    ctx = browser.new_context()
    pg = ctx.new_page()
    try:
        pg.goto(site + "/verify/")
        pg.wait_for_selector("#dropZoneEl", timeout=15000)
        assert _drop(pg, "text") == "dropped"
        pg.wait_for_function(
            "() => document.querySelector('#dropResult').textContent.length > 20",
            timeout=30000,
        )
        text = pg.locator("#dropResult").inner_text()
        assert "isn't an EPI evidence file" in text, text[:500]
    finally:
        ctx.close()
