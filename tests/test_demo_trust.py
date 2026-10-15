"""WP-DEMO-TRUST: static demo trust page at /t/acme-demo (DEMO-labelled, real .epi files)."""
from __future__ import annotations

import glob
import hashlib
import json
import os
import pathlib
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
PAGE = REPO / "website" / "t" / "acme-demo" / "index.html"
DATA = REPO / "website" / "t" / "acme-demo" / "demo-data.json"
JS = REPO / "website" / "t" / "acme-demo" / "demo.js"

FILES = [
    "website/assets/sample.epi",
    "website/assets/demo/demo-lending-affordability.epi",
    "website/assets/demo/demo-finance-loan-underwriter.epi",
]

BANNED = ["compliant", "certified", "guaranteed", "court-admissible", "immutable", "tamper-proof"]


def _read(p):
    return p.read_text(encoding="utf-8", errors="ignore")


def test_demo_page_and_assets_exist():
    assert PAGE.is_file(), "demo trust page missing: website/t/acme-demo/index.html"
    assert DATA.is_file(), "demo-data.json missing"
    assert JS.is_file(), "demo.js missing"
    for rel in FILES:
        assert (REPO / rel).is_file(), f"real .epi missing: {rel}"


def test_demo_labelled_everywhere():
    html = _read(PAGE)
    assert "DEMO" in html, "page must label DEMO data"
    assert html.count("DEMO") >= 5, "DEMO label must appear on every screen/section"
    data = json.loads(_read(DATA))
    assert data.get("demo") is True
    for f in data["files"]:
        assert "DEMO" in f.get("demo_note", ""), "each file needs DEMO note"


def test_claimed_hashes_match_real_files():
    data = json.loads(_read(DATA))
    by_path = {f["path"]: f for f in data["files"]}
    for rel in FILES:
        pub = "/" + rel.replace("website/", "")
        assert pub in by_path, f"{pub} not listed in demo-data.json"
        real = hashlib.sha256((REPO / rel).read_bytes()).hexdigest()
        assert by_path[pub]["claimed_sha256"] == real, f"claimed hash wrong for {pub}"


def test_gate_button_and_no_prefetch():
    html = _read(PAGE)
    assert "Open evidence" in html, "gate button missing"
    assert "demo-data.json" not in html, "data must load only after click (no fetch on load)"
    js = _read(JS)
    assert "demo-data.json" in js, "demo.js must fetch data on click"
    assert "click" in js.lower(), "gate click handler missing"


def test_witness_key_checkpoint_verify_blocks():
    html = _read(PAGE)
    lowered = html.lower()
    for token in ["witness", "key history", "checkpoint", "verify in my browser", "verify yourself"]:
        assert token in lowered, f"section missing: {token}"
    assert "epi verify" in lowered
    assert "--policy strict" in html
    assert "--witness-log received.jsonl" in html
    # Real key material from the sealed samples (not invented).
    assert "92dc7b40403f6383527773b35eb9305ddf01306889ad4e9987a098e6304bead0" in html or \
        "92dc7b40403f6383527773b35eb9305ddf01306889ad4e9987a098e6304bead0" in _read(DATA)
    assert "7004" in html or "7004" in _read(DATA)


def test_no_query_token_and_noindex():
    html = _read(PAGE)
    for m in re.finditer(r'''(?:href|src)\s*=\s*"([^"]+)"|(?:href|src)\s*=\s*'([^']+)' ''', html):
        url = m.group(1) if m.group(1) is not None else m.group(2)
        assert "?k=" not in url and "&k=" not in url and "?token=" not in url, \
            f"share token in URL query: {url} (use #k= fragment)"
    assert "noindex" in html.lower(), "demo page must be noindex"
    assert "no-referrer" in html, "demo page must set Referrer-Policy: no-referrer"


def test_no_banned_claims():
    for path in (PAGE, DATA):
        lowered = _read(path).lower()
        for word in BANNED:
            assert word not in lowered, f"banned word {word!r} in {path.name}"


# --- Browser: every "Verify in my browser" must show the VALID/amber line ---
# Regression test for the flat-shape bug (demo.js read report.facts.* while
# window.verifyEPI returns flat integrity/signature, so every genuine file
# showed FAIL). Asserts the displayed verdict, not just the hashes.

@pytest.fixture(scope="session")
def _browser():
    from playwright.sync_api import sync_playwright

    hits = glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome")
    exe = os.environ.get("EPI_TEST_CHROMIUM") or (hits[0] if hits else None)
    with sync_playwright() as p:
        tried = [{"args": ["--no-sandbox"]}]
        if exe:
            tried.append({"executable_path": exe, "args": ["--no-sandbox"]})
        for kwargs in tried:
            try:
                b = p.chromium.launch(**kwargs)
                break
            except Exception:
                continue
        else:
            pytest.skip("no chromium available")
        yield b
        b.close()


@pytest.fixture()
def _page(_browser):
    ctx = _browser.new_context()
    pg = ctx.new_page()
    yield pg
    ctx.close()


@pytest.fixture()
def _static():
    root = str(REPO / "website")

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            path = urlparse(self.path).path
            target = (pathlib.Path(root) / path.lstrip("/")).resolve()
            base = pathlib.Path(root).resolve()
            if base not in target.parents and target != base:
                self.send_error(403)
                return
            if target.is_dir():
                target = target / "index.html"
            if not target.is_file():
                self.send_error(404)
                return
            data = target.read_bytes()
            ctype = {".js": "text/javascript", ".css": "text/css",
                     ".json": "application/json", ".epi": "application/octet-stream"}.get(
                target.suffix, "text/html")
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


@pytest.mark.browser
def test_every_demo_verify_button_shows_valid_amber(_static, _page) -> None:
    _page.goto(f"{_static}/t/acme-demo/")
    _page.click("#gateBtn")
    _page.wait_for_selector("[data-verify]", timeout=10000)
    buttons = _page.query_selector_all("[data-verify]")
    assert len(buttons) == 3, f"want 3 demo files, found {len(buttons)}"
    for i, btn in enumerate(buttons):
        btn.click()
    _page.wait_for_function(
        "() => [...document.querySelectorAll('.vresult')].length === 3 && "
        "[...document.querySelectorAll('.vresult')].every("
        "el => el.textContent.includes('Hash matches') || el.textContent.includes('FAIL'))",
        timeout=60000,
    )
    results = _page.query_selector_all(".vresult")
    assert len(results) == 3
    for r in results:
        text = r.inner_text()
        assert "Hash matches" in text, f"demo file hash mismatch: {text[:200]}"
        assert "SEAL VALID" in text and "NOT PINNED" in text, f"no amber verdict: {text[:300]}"
        assert "FAIL" not in text, f"genuine demo file shows FAIL: {text[:300]}"
