"""M2 trust page: gate discipline, human-only events, browser verify states."""

from __future__ import annotations

import base64
import hashlib
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
TOKEN = "f" * 64
SAMPLE = REPO / "website" / "assets" / "sample.epi"

pytestmark = pytest.mark.browser


class StubState:
    def __init__(self) -> None:
        self.requests: list[dict] = []
        self.doc = {
            "vendor": "Acme Corp",
            "link_label": "Acme Bank Q3",
            "agents": [{"id": "g1", "name": "loans", "status": "active"}],
            "inboxes": [
                {
                    "id": "inb_1",
                    "label": "Acme Bank",
                    "total_witnessed": 40,
                    "d30": 40,
                    "d90": 40,
                    "last_day": "2026-10-15",
                    "anchored": True,
                }
            ],
            "artifacts": [],
            "keys": [],
            "note": "stub",
        }

    def genuine_doc(self) -> dict:
        doc = json.loads(json.dumps(self.doc))
        digest = hashlib.sha256(SAMPLE.read_bytes()).hexdigest()
        doc["artifacts"] = [
            {
                "goal": "Website sample run",
                "claimed_sha256": digest,
                "download_url": "/assets/sample.epi",
                "signature_check": "valid",
                "witness_status": "witnessed",
            },
            {
                "goal": "Mismatched bytes",
                "claimed_sha256": digest,
                "download_url": "data:application/octet-stream;base64,"
                + base64.b64encode(_tampered(SAMPLE.read_bytes())).decode(),
                "signature_check": "valid",
                "witness_status": "witnessed",
            },
        ]
        return doc


def _tampered(data: bytes) -> bytes:
    """Flip a byte inside the hashed ZIP payload (not presentation bytes).

    Rebuilds the container with one steps.jsonl byte changed so the manifest
    hashes no longer match: a real tamper, caught as red.
    """
    import io
    import zipfile

    src = zipfile.ZipFile(io.BytesIO(data))
    names = src.namelist()
    target = "steps.jsonl" if "steps.jsonl" in names else names[-1]
    raw = bytearray(src.read(target))
    raw[len(raw) // 2] ^= 0x01
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as dest:
        for name in names:
            dest.writestr(name, bytes(raw) if name == target else src.read(name))
    return out.getvalue()


def _make_stub(state: StubState) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def _send(self, code: int, payload: bytes, ctype: str = "application/json") -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_OPTIONS(self) -> None:
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Headers", "content-type, x-epi-share-token")
            self.send_header("Access-Control-Allow-Methods", "GET, POST")
            self.end_headers()

        def do_GET(self) -> None:
            length = int(self.headers.get("Content-Length", 0) or 0)
            body = self.rfile.read(length) if length else b""
            state.requests.append(
                {"method": "GET", "path": self.path, "headers": dict(self.headers), "body": body}
            )
            if self.path == "/v1/trust/sh_test":
                if self.headers.get("X-EPI-Share-Token") != TOKEN:
                    self._send(404, b'{"error":{}}')
                else:
                    self._send(200, json.dumps(state.genuine_doc()).encode())
            else:
                self._send(404, b'{"error":{"code":"not_found"}}')

        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", 0) or 0)
            body = self.rfile.read(length) if length else b""
            state.requests.append(
                {"method": "POST", "path": self.path, "headers": dict(self.headers), "body": body}
            )
            if self.path == "/v1/trust/sh_test/events":
                if self.headers.get("X-EPI-Share-Token") != TOKEN:
                    self._send(404, b"{}")
                else:
                    self._send(200, b'{"ok":true}')
            else:
                self._send(404, b"{}")

        def log_message(self, *args) -> None:
            pass

    return Handler


@pytest.fixture(scope="session")
def browser():
    import glob
    import os

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
def page(browser):
    ctx = browser.new_context()
    pg = ctx.new_page()
    yield pg
    ctx.close()


@pytest.fixture()
def servers():
    state = StubState()
    api = ThreadingHTTPServer(("127.0.0.1", 0), _make_stub(state))
    threading.Thread(target=api.serve_forever, daemon=True).start()
    from functools import partial

    static = ThreadingHTTPServer(
        ("127.0.0.1", 0), partial(_StaticHandler, directory=str(REPO / "website"))
    )
    threading.Thread(target=static.serve_forever, daemon=True).start()
    yield state, f"http://127.0.0.1:{static.server_port}", f"http://127.0.0.1:{api.server_port}"
    api.shutdown()
    static.shutdown()


class _StaticHandler(BaseHTTPRequestHandler):
    def __init__(self, *args, directory: str = ".", **kwargs) -> None:
        self._directory = directory
        super().__init__(*args, **kwargs)

    def do_GET(self) -> None:
        from urllib.parse import urlparse

        path = urlparse(self.path).path
        target = (Path(self._directory) / path.lstrip("/")).resolve()
        base = Path(self._directory).resolve()
        if base not in target.parents and target != base:
            self.send_error(403)
            return
        if target.is_dir():
            target = target / "index.html"
        if not target.is_file():
            # Mirror the production rewrite (/t/* -> shell): pretty trust
            # links resolve to the app shell, which reads the slug itself.
            if path.startswith("/t/"):
                shell = base / "t" / "app" / "index.html"
                if shell.is_file():
                    data = shell.read_bytes()
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html")
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                    return
            self.send_error(404)
            return
        data = target.read_bytes()
        ctype = "text/html"
        if target.suffix == ".js":
            ctype = "text/javascript"
        elif target.suffix == ".css":
            ctype = "text/css"
        elif target.suffix == ".json":
            ctype = "application/json"
        elif target.suffix == ".epi":
            ctype = "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args) -> None:
        pass


def _page_url(static: str, api: str, slug: str = "sh_test") -> str:
    return f"{static}/t/{slug}?api={api}#k={TOKEN}"


def test_gate_load_creates_no_signal(servers, page) -> None:
    state, static, api = servers
    page.goto(_page_url(static, api))
    page.wait_for_timeout(1500)
    assert state.requests == [], f"page load must not touch the API: {state.requests}"


def test_open_renders_and_records_opened(servers, page) -> None:
    state, static, api = servers
    page.goto(_page_url(static, api))
    page.click("#gateBtn")
    page.wait_for_selector("#trustContent:not([style*='display: none'])", timeout=10000)
    assert "Acme Corp" in page.inner_text("#vendorTitle")
    assert "40" in page.inner_text("#trustStats")
    kinds = [json.loads(r["body"])["kind"] for r in state.requests if r["path"].endswith("/events")]
    assert kinds == ["opened"]


def test_genuine_file_verifies_amber(servers, page) -> None:
    _, static, api = servers
    page.goto(_page_url(static, api))
    page.click("#gateBtn")
    page.wait_for_selector("#trustContent:not([style*='display: none'])", timeout=10000)
    page.set_input_files("#fileInput", str(SAMPLE))
    page.wait_for_function(
        "() => document.querySelector('#dropResult').textContent.includes('NOT PINNED')",
        timeout=30000,
    )
    text = page.inner_text("#dropResult")
    assert "VALID" in text


def test_tampered_file_verifies_red(servers, page, tmp_path) -> None:
    _, static, api = servers
    bad = tmp_path / "tampered.epi"
    bad.write_bytes(_tampered(SAMPLE.read_bytes()))
    page.goto(_page_url(static, api))
    page.click("#gateBtn")
    page.wait_for_selector("#trustContent:not([style*='display: none'])", timeout=10000)
    page.set_input_files("#fileInput", str(bad))
    page.wait_for_function(
        "() => document.querySelector('#dropResult').textContent.includes('FAIL')",
        timeout=30000,
    )


def test_claimed_mismatch_is_red(servers, page) -> None:
    _, static, api = servers
    page.goto(_page_url(static, api))
    page.click("#gateBtn")
    page.wait_for_selector("[data-artifact='1']", timeout=10000)
    page.click("[data-artifact='1']")
    page.wait_for_function(
        "() => document.body.textContent.includes('do not match')",
        timeout=30000,
    )


def test_genuine_artifact_hash_matches(servers, page) -> None:
    _, static, api = servers
    page.goto(_page_url(static, api))
    page.click("#gateBtn")
    page.wait_for_selector("[data-artifact='0']", timeout=10000)
    page.click("[data-artifact='0']")
    page.wait_for_function(
        "() => document.body.textContent.includes('Hash matches')",
        timeout=30000,
    )


def test_expired_link_shows_clear_error(servers, page) -> None:
    _, static, api = servers
    page.goto(f"{static}/t/sh_old?api={api}#k={TOKEN}")
    page.click("#gateBtn")
    status_text = "#gateStatus"
    page.wait_for_function(
        "() => document.querySelector('" + status_text + "').textContent.includes('invalid')",
        timeout=10000,
    )
    assert "expired, or revoked" in page.inner_text(status_text)


def test_token_never_reaches_server_logs(servers, page) -> None:
    state, static, api = servers
    page.goto(_page_url(static, api))
    page.click("#gateBtn")
    page.wait_for_selector("#trustContent:not([style*='display: none'])", timeout=10000)
    page.set_input_files("#fileInput", str(SAMPLE))
    page.wait_for_function(
        "() => document.querySelector('#dropResult').textContent.length > 20",
        timeout=30000,
    )
    for r in state.requests:
        # The token travels ONLY as the X-EPI-Share-Token header (auth).
        # It must never appear in paths, queries, bodies, or log lines —
        # and the #k= fragment must never leave the browser at all.
        assert TOKEN not in r["path"], f"token leaked into path: {r['path']}"
        assert TOKEN not in r["body"].decode("utf-8", "ignore"), "token leaked into body"
        assert "#" not in r["path"], "fragment must never be sent"
        assert r["headers"].get("X-EPI-Share-Token") in (TOKEN, None)


def test_demo_gate_hides_evidence_until_click(page) -> None:
    """Scanners that load /t/acme-demo without a click see no evidence."""
    from functools import partial
    from http.server import SimpleHTTPRequestHandler

    handler = partial(SimpleHTTPRequestHandler, directory=str(REPO / "website"))
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_port}"
    fetched: list[str] = []
    page.on("request", lambda req: fetched.append(req.url))
    try:
        page.goto(f"{base}/t/acme-demo/", wait_until="domcontentloaded")
        page.wait_for_timeout(800)
        assert page.is_visible("#gateBtn")
        assert page.locator("#demoContent").is_hidden()
        assert not any("demo-data.json" in u for u in fetched)
        page.click("#gateBtn")
        page.wait_for_selector("#demoContent", state="visible", timeout=10000)
        assert "DEMO" in page.inner_text("#demoContent")
        assert any("demo-data.json" in u for u in fetched)
        assert not any("/v1/trust" in u for u in fetched)
    finally:
        httpd.shutdown()
