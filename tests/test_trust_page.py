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

    def pack_doc(self) -> dict:
        """Whole-link pack slug: every artifact matches, keys carry history."""
        from epi_core.container import EPIContainer
        from epi_core.keys import key_fingerprint

        manifest = EPIContainer.read_manifest(SAMPLE)
        digest = hashlib.sha256(SAMPLE.read_bytes()).hexdigest()
        current_fp = key_fingerprint(str(manifest.public_key), grouped=False)
        return {
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
            "artifacts": [
                {
                    "goal": "Website sample run",
                    "workflow_id": str(manifest.workflow_id),
                    "claimed_sha256": digest,
                    "content_url": "/assets/sample.epi",
                    "download_url": "/assets/sample.epi",
                    "sealed_at": "2026-10-15T12:00:00Z",
                    "key_fingerprint": current_fp,
                    "signature_check": "valid",
                    "witness_status": "witnessed",
                },
            ],
            "keys": [
                {
                    "fingerprint": "9aa7c001f00d0001",
                    "label": "2024 sealer",
                    "valid_from": "2024-01-10",
                    "revoked_at": "2026-03-01",
                    "revoke_reason": "scheduled rotation — superseded by the 2026 sealer",
                },
                {
                    "fingerprint": current_fp,
                    "label": "2026 sealer",
                    "valid_from": "2026-03-01",
                    "revoked_at": None,
                    "revoke_reason": None,
                },
            ],
            "note": "stub",
        }

    def witness_lines(self) -> dict:
        """Signed-stub witness-lines doc (spec shape, real test signature).

        A fresh test Ed25519 key signs the receipt canonical bytes exactly as
        the server does; witness_pubkey rides in the doc so the pack test can
        run the README flow for real: signed witness.json + --witness-pubkey.
        """
        from epi_core.container import EPIContainer
        from epi_core.keys import key_fingerprint
        from epi_core.serialize import get_canonical_hash
        from epi_core.webhook import build_witness_payload, witness_content_digest

        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from cryptography.hazmat.primitives import serialization

        priv = Ed25519PrivateKey.generate()
        pub_hex = priv.public_key().public_bytes(
            encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw
        ).hex()
        raw = SAMPLE.read_bytes()
        manifest = EPIContainer.read_manifest(SAMPLE)
        manifest_hash = get_canonical_hash(manifest, exclude_fields=["signature"])
        file_sha256 = hashlib.sha256(raw).hexdigest()
        payload = build_witness_payload(
            workflow_id=str(manifest.workflow_id),
            manifest_hash=manifest_hash,
            file_sha256=file_sha256,
            public_key=getattr(manifest, "public_key", None),
            content_digest=witness_content_digest(manifest),
            key_fingerprint=key_fingerprint(str(manifest.public_key), grouped=False),
            steps=1,
            sealed_at="2026-10-15T12:00:00+00:00",
            seal_timestamp={"status": "none", "gen_time": None},
            goal=getattr(manifest, "goal", None),
        )
        payload["received_at"] = "2026-10-15T12:00:01+00:00"
        payload_raw = json.dumps(payload, sort_keys=True)
        line_sha256 = hashlib.sha256(payload_raw.encode("utf-8")).hexdigest()
        canonical = json.dumps(
            {
                "artifact_sha256": file_sha256,
                "inbox_id": "inb_1",
                "line_sha256": line_sha256,
                "received_at": payload["received_at"],
                "seq": 1,
            },
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        return {
            "link": "sh_pack",
            "witness_pubkey": pub_hex,
            "note": "stub (signed): receipt verifiable with witness_pubkey",
            "lines": [
                {
                    "inbox": "inb_1",
                    "seq": 1,
                    "received_at": payload["received_at"],
                    "payload_raw": payload_raw,
                    "receipt": {
                        "inbox_id": "inb_1",
                        "seq": 1,
                        "line_sha256": line_sha256,
                        "artifact_sha256": file_sha256,
                        "received_at": payload["received_at"],
                        "signature": priv.sign(canonical).hex(),
                    },
                }
            ],
        }


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


def _viewer_tampered(data: bytes) -> bytes:
    """Flip one byte in the outer polyglot viewer HTML (display layer).

    The ZIP payload is untouched, so only the envelope header's viewer hash
    (reserved_tail[0:32]) catches it — exactly what the CLI and /verify/
    reject and what the trust page drop zone once let through as SEAL VALID.
    """
    marker = b"\n<!-- EPI_ZIP_PAYLOAD_START -->\n"
    assert data[:4] == b"<!--" and marker in data, "sample must be an envelope-v2 polyglot"
    assert any(data[72:104]), "sample must carry a viewer hash"
    out = bytearray(data)
    at = out.index(b"<html", 128)
    assert at < data.index(marker)
    out[at + 1] ^= 0x20  # <html -> <Html
    return bytes(out)


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
            elif self.path == "/v1/trust/sh_pack":
                if self.headers.get("X-EPI-Share-Token") != TOKEN:
                    self._send(404, b'{"error":{}}')
                else:
                    self._send(200, json.dumps(state.pack_doc()).encode())
            elif self.path == "/v1/trust/sh_pack/witness-lines":
                if self.headers.get("X-EPI-Share-Token") != TOKEN:
                    self._send(404, b'{"error":{}}')
                else:
                    self._send(200, json.dumps(state.witness_lines()).encode())
            elif self.path == "/v1/trust/sh_test/witness-lines":
                if self.headers.get("X-EPI-Share-Token") != TOKEN:
                    self._send(404, b'{"error":{}}')
                else:
                    self._send(
                        200,
                        json.dumps(
                            {
                                "link": "sh_test",
                                "witness_pubkey": None,
                                "note": "stub",
                                "lines": [],
                            }
                        ).encode(),
                    )
            else:
                self._send(404, b'{"error":{"code":"not_found"}}')

        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", 0) or 0)
            body = self.rfile.read(length) if length else b""
            state.requests.append(
                {"method": "POST", "path": self.path, "headers": dict(self.headers), "body": body}
            )
            if self.path in ("/v1/trust/sh_test/events", "/v1/trust/sh_pack/events"):
                if self.headers.get("X-EPI-Share-Token") != TOKEN:
                    self._send(404, b"{}")
                else:
                    try:
                        kind = json.loads(body.decode())["kind"]
                    except Exception:
                        kind = None
                    if kind not in ("opened", "verified_file", "downloaded_pack", "downloaded_witness"):
                        self._send(400, b"{}")
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


def _pack_url(static: str, api: str) -> str:
    return f"{static}/t/sh_pack?api={api}#k={TOKEN}"


def _tamper_manifest_goal(data: bytes) -> bytes:
    """Rewrite one manifest field (goal) and re-zip, keeping the old signature.

    The file still parses, but manifest_hash/content_digest no longer match
    the witnessed version and the signature is invalid: `epi verify
    --witness-log` must report witness MISMATCH (a different version).
    """
    import io
    import zipfile

    src = zipfile.ZipFile(io.BytesIO(data))
    manifest = json.loads(src.read("manifest.json"))
    manifest["goal"] = (manifest.get("goal") or "run") + " (altered)"
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as dest:
        for name in src.namelist():
            info = src.getinfo(name)
            dest.writestr(
                name,
                json.dumps(manifest).encode("utf-8") if name == "manifest.json" else src.read(name),
                compress_type=info.compress_type,
            )
    return out.getvalue()


def _event_kinds(state: StubState) -> list[str]:
    return [json.loads(r["body"])["kind"] for r in state.requests if r["path"].endswith("/events")]


def _verify_cli(epi_file, witness_log, tmp_path, name: str, pubkey: str | None = None) -> dict:
    """Run the README offline flow and return the parsed JSON report."""
    import subprocess
    import sys

    args = [
        sys.executable, "-m", "epi_cli", "verify", str(epi_file),
        "--policy", "strict", "--witness-log", str(witness_log),
        "--offline", "--json",
    ]
    if pubkey:
        args += ["--witness-pubkey", pubkey]
    proc = subprocess.run(args, capture_output=True, text=True, timeout=180, cwd=str(REPO))
    (tmp_path / f"{name}.stdout").write_text(proc.stdout)
    (tmp_path / f"{name}.stderr").write_text(proc.stderr[-4000:])
    return json.loads(proc.stdout)


def test_pack_gate_fires_no_pack_signal(servers, browser) -> None:
    """Page load and the gate click never fetch witness-lines or fire pack events."""
    state, static, api = servers
    ctx = browser.new_context()
    pg = ctx.new_page()
    try:
        pg.goto(_pack_url(static, api))
        pg.wait_for_timeout(1200)
        assert state.requests == [], f"page load must not touch the API: {state.requests}"
        pg.click("#gateBtn")
        pg.wait_for_selector("#trustContent:not([style*='display: none'])", timeout=10000)
        assert pg.locator("#packBtn").is_visible()
        assert _event_kinds(state) == ["opened"]
        assert not any(r["path"].endswith("/witness-lines") for r in state.requests)
    finally:
        ctx.close()


def test_pack_downloads_verified_zip(servers, browser, tmp_path) -> None:
    """Full M6 flow: click pack -> verified zip -> offline `epi verify` says WITNESSED."""
    import zipfile

    state, static, api = servers
    ctx = browser.new_context(accept_downloads=True)
    pg = ctx.new_page()
    try:
        pg.goto(_pack_url(static, api))
        pg.click("#gateBtn")
        pg.wait_for_selector("#trustContent:not([style*='display: none'])", timeout=10000)
        with pg.expect_download(timeout=30000) as dl_info:
            pg.click("#packBtn")
        download = dl_info.value
        pack_zip = tmp_path / "evidence-pack.zip"
        download.save_as(str(pack_zip))
        pg.wait_for_function(
            "() => document.querySelector('#packStatus').textContent.includes('downloaded')",
            timeout=15000,
        )
    finally:
        ctx.close()

    with zipfile.ZipFile(pack_zip) as zf:
        names = set(zf.namelist())
        assert "acme-corp/sample.epi" in names, names
        for required in ("trust.json", "witness.json", "README.txt", "MANIFEST.json"):
            assert required in names, names

        manifest = json.loads(zf.read("MANIFEST.json"))
        assert manifest == [
            {"name": "acme-corp/sample.epi", "sha256": hashlib.sha256(zf.read("acme-corp/sample.epi")).hexdigest()}
        ]
        for entry in manifest:
            assert hashlib.sha256(zf.read(entry["name"])).hexdigest() == entry["sha256"]

        readme = zf.read("README.txt").decode("utf-8")
        assert "epi verify FILE --policy strict --witness-log witness.json --witness-pubkey <PASTE-KEY> --offline" in readme
        assert (
            "checkable offline ONLY against a witness public key you pinned yourself"
            in readme
        )
        assert "NEVER trust the witness_pubkey printed inside witness.json" in readme
        assert 'If the result does not say "verified witness receipt"' in readme
        assert "cloud.epilabs.org/.well-known/epi-witness-key.json" in readme
        assert "epi-witness-checkpoints" in readme
        assert "per-line Merkle inclusion proofs are planned, not present" in readme
        assert manifest[0]["sha256"] in readme
        # Step 1: confirm + pin the vendor key (strict needs it), per-file expectation.
        assert "STEP 1" in readme and "confirm" in readme.lower()
        assert 'epi keys trust acme-corp/sample.epi --name acme-corp --fingerprint "' in readme
        assert "expect: PASS" in readme
        assert "received.jsonl" not in readme

        trust = json.loads(zf.read("trust.json"))
        assert trust["vendor"] == "Acme Corp"
        assert any("fingerprint" in k and k["fingerprint"] for k in trust["keys"])
        revoked = [k for k in trust["keys"] if k.get("revoked_at")]
        assert revoked and revoked[0].get("revoke_reason"), "revocation reasons must ride in trust.json"

        witness = json.loads(zf.read("witness.json"))
        assert witness["witness_pubkey"], "pack must carry the witness key for offline checks"
        assert len(witness["lines"]) == 1
        line = witness["lines"][0]
        assert set(line["receipt"]) >= {
            "inbox_id", "seq", "line_sha256", "artifact_sha256", "received_at", "signature",
        }
        assert line["receipt"]["signature"], "stub signs the receipt for real"
        payload = json.loads(line["payload_raw"])
        assert payload["workflow_id"] and payload["manifest_hash"] and payload["file_sha256"]

        epi_bytes = zf.read("acme-corp/sample.epi")
        witness_raw = zf.read("witness.json")
    assert hashlib.sha256(epi_bytes).hexdigest() == manifest[0]["sha256"]
    assert hashlib.sha256(epi_bytes).hexdigest() == hashlib.sha256(SAMPLE.read_bytes()).hexdigest()

    # The README flow for real: signed witness.json + the packed witness key.
    # Tampered payload or forged receipt must never read WITNESSED.
    witness_file = tmp_path / "witness.json"
    witness_file.write_text(witness_raw.decode("utf-8"))
    epi_file = tmp_path / "downloaded.epi"
    epi_file.write_bytes(epi_bytes)
    report = _verify_cli(epi_file, witness_file, tmp_path, "pack-genuine", pubkey=witness["witness_pubkey"])
    assert report["witness"]["status"] == "WITNESSED", report["witness"]
    assert report["witness"].get("receipt_verified", 0) >= 1, report["witness"]

    # Same log, altered copy: the witnessed version differs -> MISMATCH.
    tampered = tmp_path / "tampered.epi"
    tampered.write_bytes(_tamper_manifest_goal(epi_bytes))
    bad_report = _verify_cli(tampered, witness_file, tmp_path, "pack-tampered", pubkey=witness["witness_pubkey"])
    assert bad_report["witness"]["status"] == "MISMATCH", bad_report["witness"]
    assert bad_report["decision"]["status"] == "FAIL"

    # The #121 blocker repro through the real pack: same signed pack, but NO
    # pinned key (the README command without --witness-pubkey). The stamps
    # are UNCHECKED — must read NOT CONFIRMED, never WITNESSED.
    nokey_report = _verify_cli(epi_file, witness_file, tmp_path, "pack-nokey")
    assert nokey_report["witness"]["status"] == "NOT CONFIRMED", nokey_report["witness"]
    assert "NOT CONFIRMED" in nokey_report["witness"]["detail"]
    assert nokey_report["decision"]["status"] == "FAIL", nokey_report["decision"]

    # The full README flow an auditor follows: pin the confirmed vendor key
    # (step 1), then the exact step-3 command. Must reach a clear PASS.
    import os
    import subprocess
    import sys

    from epi_core.container import EPIContainer
    from epi_core.keys import key_fingerprint

    vendor_fp = key_fingerprint(str(EPIContainer.read_manifest(epi_file).public_key))
    env = dict(os.environ, EPI_TRUSTED_KEYS_DIR=str(tmp_path / "auditor-trusted"), NO_COLOR="1")
    env.pop("EPI_WITNESS_PUBKEY", None)
    pin = subprocess.run(
        [sys.executable, "-m", "epi_cli.main", "keys", "trust", str(epi_file),
         "--name", "acme-corp", "--fingerprint", vendor_fp],
        capture_output=True, text=True, timeout=120, cwd=str(REPO), env=env,
    )
    assert pin.returncode == 0, pin.stdout + pin.stderr
    proc = subprocess.run(
        [sys.executable, "-m", "epi_cli.main", "verify", str(epi_file), "--policy", "strict",
         "--witness-log", str(witness_file), "--witness-pubkey", witness["witness_pubkey"],
         "--offline", "--json"],
        capture_output=True, text=True, timeout=180, cwd=str(REPO), env=env,
    )
    pinned = json.loads(proc.stdout)
    assert pinned["decision"]["status"] == "PASS", pinned["decision"]
    assert pinned["witness"]["status"] == "WITNESSED", pinned["witness"]

    kinds = _event_kinds(state)
    assert kinds.count("downloaded_pack") == 1, kinds
    assert kinds.count("downloaded_witness") == 1, kinds


def test_pack_aborts_on_mismatched_bytes(servers, page) -> None:
    """One bad artifact aborts the whole pack: red message, no download, no events."""
    state, static, api = servers
    page.goto(_page_url(static, api))
    page.click("#gateBtn")
    page.wait_for_selector("[data-artifact='1']", timeout=10000)
    seen: list = []
    page.on("download", lambda dl: seen.append(dl))
    page.click("#packBtn")
    page.wait_for_function(
        "() => document.querySelector('#packStatus').textContent.toLowerCase().includes('abort')",
        timeout=30000,
    )
    assert "does not match" in page.inner_text("#packStatus")
    style = page.get_attribute("#packStatus", "style") or ""
    assert "var(--bad)" in style, f"abort message must be red: {style}"
    page.wait_for_timeout(2000)
    assert seen == [], "aborted pack must not trigger any download"
    kinds = _event_kinds(state)
    assert "downloaded_pack" not in kinds, kinds
    assert "downloaded_witness" not in kinds, kinds


def test_pack_per_file_download_link(servers, browser, tmp_path) -> None:
    """The subtle per-file 'Download file' link saves the artifact bytes."""
    import hashlib as _hashlib

    _, static, api = servers
    ctx = browser.new_context(accept_downloads=True)
    pg = ctx.new_page()
    try:
        pg.goto(_page_url(static, api))
        pg.click("#gateBtn")
        pg.wait_for_selector("[data-dlartifact='0']", timeout=10000)
        with pg.expect_download(timeout=30000) as dl_info:
            pg.click("[data-dlartifact='0']")
        download = dl_info.value
        target = tmp_path / "single.epi"
        download.save_as(str(target))
    finally:
        ctx.close()
    assert _hashlib.sha256(target.read_bytes()).hexdigest() == _hashlib.sha256(SAMPLE.read_bytes()).hexdigest()


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


def test_viewer_tampered_file_verifies_red(servers, page, tmp_path) -> None:
    """A flipped byte in the embedded viewer must FAIL here, as on /verify/ and the CLI."""
    _, static, api = servers
    bad = tmp_path / "viewer-tampered.epi"
    bad.write_bytes(_viewer_tampered(SAMPLE.read_bytes()))
    page.goto(_page_url(static, api))
    page.click("#gateBtn")
    page.wait_for_selector("#trustContent:not([style*='display: none'])", timeout=10000)
    page.set_input_files("#fileInput", str(bad))
    page.wait_for_function(
        "() => /FAIL|VALID/.test(document.querySelector('#dropResult').textContent)",
        timeout=30000,
    )
    text = page.inner_text("#dropResult")
    assert "FAIL" in text and "changed after it was sealed" in text, text
    assert "SEAL VALID" not in text, text
    assert "not one of the files shared" in text, text


def test_dropped_shared_file_is_identified(servers, page) -> None:
    """Dropping a shared file names it; the hash line is green only when checks pass."""
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
    assert "This is the shared file" in text and "Website sample run" in text, text
    assert "witnessed" in text, text


def test_summary_and_cards_speak_plainly(servers, page) -> None:
    _, static, api = servers
    page.goto(_page_url(static, api))
    gate = page.inner_text("#gate")
    assert "An AI vendor shared sealed evidence" in gate
    page.click("#gateBtn")
    page.wait_for_selector("#trustContent:not([style*='display: none'])", timeout=10000)
    summary = page.inner_text("#trustSummary")
    assert "All 2 shared files were registered with EPI" in summary, summary
    assert "not registered a signing key" in summary, summary
    assert "What these terms mean" in summary
    assert page.title() == "Acme Corp \u2014 evidence"
    assert "2 of 2" in page.inner_text("#trustStats")
    assert "received.jsonl" not in page.inner_text("#trustContent")


def test_refresh_keeps_token_and_strips_url(servers, page) -> None:
    _, static, api = servers
    page.goto(_page_url(static, api))
    page.wait_for_timeout(300)
    assert "#k=" not in page.url
    page.reload()
    page.wait_for_timeout(300)
    assert page.locator("#gateBtn").is_enabled()
    page.click("#gateBtn")
    page.wait_for_selector("#trustContent:not([style*='display: none'])", timeout=10000)


def test_missing_token_explains_and_disables(servers, page) -> None:
    _, static, api = servers
    page.goto(f"{static}/t/sh_test?api={api}")
    page.wait_for_timeout(300)
    assert "copied without its key" in page.inner_text("#gateStatus")
    assert not page.locator("#gateBtn").is_enabled()


def test_dead_link_disables_open_button(servers, page) -> None:
    _, static, api = servers
    page.goto(f"{static}/t/sh_old?api={api}#k={TOKEN}")
    page.click("#gateBtn")
    page.wait_for_function(
        "() => document.querySelector('#gateStatus').textContent.includes('invalid')", timeout=10000
    )
    assert not page.locator("#gateBtn").is_enabled()


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
