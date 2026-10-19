"""End-to-end customer walkthrough against real workerd + real browser.

Vendor -> reviewer -> auditor, on the same build the dashboard serves:

1. Vendor: create customer (API), record with `epi record` CLI while
   EPI_WITNESS_URL/SECRET point at the inbox, push tagged with --agent.
2. Reviewer: open the dashboard-made trust link served from the real
   website/ directory through a same-origin /v1/trust/* proxy (the exact
   contract functions/v1/[[path]].js implements) in real Chromium at
   390px, gate-click, verify bytes in-page, download the evidence pack.
3. Auditor: offline `epi verify --witness-log witness.json --witness-pubkey`
   on a downloaded file must say WITNESSED (pack carries >= 1 receipt).

Also asserts Bank A isolation over the wire: a second customer's run never
appears in Bank A's trust doc, exports, or chain.

Browser-marked: runs in dashboard-browser.yml, not the release gate.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from typer.testing import CliRunner

pytestmark = pytest.mark.browser

REPO = Path(__file__).resolve().parents[1]
WEBSITE = REPO / "website"
CLOUD = REPO / "cloud"

SESSION_RAW = "walk-e2e-session-0123456789abcdef0123456789abcdef"
INBOX_KEY = "ef" * 32
SIGNING_KEY = secrets.token_hex(32)

runner = CliRunner()


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _npx() -> str:
    resolved = shutil.which("npx")
    assert resolved, "npx not found on PATH (need Node.js + cloud/node_modules)"
    return resolved


def _wrangler(*args: str, persist: Path) -> None:
    cmd = [_npx(), "wrangler", *args, "--persist-to", str(persist), "--config", "wrangler.toml"]
    proc = subprocess.run(
        cmd,
        cwd=str(CLOUD),
        capture_output=True,
        text=True,
        timeout=300,
        encoding="utf-8",
        errors="replace",
    )
    assert proc.returncode == 0, f"wrangler {' '.join(args)} failed:\n{proc.stdout}\n{proc.stderr}"


def _api(
    base: str, method: str, path: str, cookie: str, body: dict | None = None
) -> tuple[int, dict]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        base + path,
        data=data,
        method=method,
        headers={"Cookie": cookie, "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            return res.status, json.loads(res.read().decode() or "{}")
    except urllib.error.HTTPError as exc:
        try:
            payload = json.loads(exc.read().decode() or "{}")
        except Exception:
            payload = {}
        return exc.code, payload


def _pub_of_secret(secret_hex: str) -> str:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    priv = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(secret_hex))
    return (
        priv.public_key()
        .public_bytes(encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw)
        .hex()
    )


@pytest.fixture(scope="module")
def cloud():
    persist = Path.cwd() / f".tmp-walk-e2e-{secrets.token_hex(4)}"
    persist.mkdir(parents=True, exist_ok=True)
    _wrangler("d1", "migrations", "apply", "epi-cloud", "--local", persist=persist)
    session_hash = hashlib.sha256(SESSION_RAW.encode()).hexdigest()
    _wrangler(
        "d1",
        "execute",
        "epi-cloud",
        "--local",
        "--command",
        "INSERT INTO users (id, email, display_name, email_verified, created_at)"
        " VALUES ('usr_e2e','e2e@example.com','E2E',1,'2026-10-17T00:00:00.000Z');"
        f" INSERT INTO sessions (id_hash, user_id, expires_at) VALUES"
        f" ('{session_hash}','usr_e2e','2999-01-01T00:00:00.000Z');",
        persist=persist,
    )
    port = _free_port()
    local_origin = f"http://127.0.0.1:{port}"
    proc = subprocess.Popen(
        [
            _npx(),
            "wrangler",
            "dev",
            "--local",
            "--persist-to",
            str(persist),
            "--port",
            str(port),
            "--config",
            "wrangler.toml",
            "--var",
            f"INBOX_SECRET_KEY:{INBOX_KEY}",
            "--var",
            f"APP_ORIGIN:{local_origin}",
            "--var",
            f"PUBLIC_WITNESS_URL:{local_origin}",
            "--var",
            f"WITNESS_SIGNING_KEY:{SIGNING_KEY}",
        ],
        cwd=str(CLOUD),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    base = local_origin
    try:
        for _ in range(60):
            try:
                with urllib.request.urlopen(base + "/health", timeout=3) as res:
                    if res.status == 200:
                        break
            except Exception:
                time.sleep(2)
        else:
            raise RuntimeError("workerd did not boot")
        yield base, f"epi_session={SESSION_RAW}", persist
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=20)
        except Exception:
            proc.kill()
        shutil.rmtree(persist, ignore_errors=True)


class _SiteWithTrustProxy(BaseHTTPRequestHandler):
    """Serve website/ statically; forward ONLY /v1/trust/* to workerd.

    Mirrors the contract of functions/v1/[[path]].js: allow-listed paths,
    share-token header only, no cookies forwarded.
    """

    base: str = ""
    directory: str = "."

    def _send(self, status: int, body: bytes, ctype: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_file(self, path: str) -> None:
        from urllib.parse import urlparse

        rel = urlparse(path).path.lstrip("/")
        target = (Path(self.directory) / rel).resolve()
        base = Path(self.directory).resolve()
        if base not in target.parents and target != base:
            self.send_error(403)
            return
        if target.is_dir():
            target = target / "index.html"
        if not target.is_file():
            if urlparse(path).path.startswith("/t/"):
                shell = base / "t" / "app" / "index.html"
                if shell.is_file():
                    data = shell.read_bytes()
                    self._send(200, data, "text/html")
                    return
            self.send_error(404)
            return
        suffix = target.suffix
        ctype = (
            "text/html"
            if suffix == ".html"
            else "text/javascript"
            if suffix == ".js"
            else "text/css"
            if suffix == ".css"
            else "application/octet-stream"
        )
        self._send(200, target.read_bytes(), ctype)

    def _proxy_trust(self) -> None:
        import re
        from urllib.parse import urlparse

        path = urlparse(self.path).path
        allowed = (
            (re.fullmatch(r"/v1/trust/[A-Za-z0-9_-]{1,128}", path) and self.command == "GET")
            or (
                re.fullmatch(r"/v1/trust/[A-Za-z0-9_-]{1,128}/witness-lines", path)
                and self.command == "GET"
            )
            or (
                re.fullmatch(r"/v1/trust/[A-Za-z0-9_-]{1,128}/events", path)
                and self.command == "POST"
            )
            or (
                re.fullmatch(
                    r"/v1/orgs/[A-Za-z0-9_-]{1,64}/artifacts/[A-Za-z0-9_-]{1,64}/content", path
                )
                and self.command == "GET"
            )
        )
        if not allowed:
            self._send(404, b'{"error":"not found"}', "application/json")
            return
        length = int(self.headers.get("Content-Length", "0") or 0)
        raw = self.rfile.read(length) if length else None
        headers = {}
        token = self.headers.get("X-EPI-Share-Token")
        if token:
            headers["X-EPI-Share-Token"] = token
        if self.command == "POST" and self.headers.get("Content-Type"):
            headers["Content-Type"] = self.headers["Content-Type"]
        req = urllib.request.Request(
            self.base + path, data=raw, method=self.command, headers=headers
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as res:
                body = res.read()
                self._send(res.status, body, res.headers.get("Content-Type", "application/json"))
        except urllib.error.HTTPError as exc:
            self._send(exc.code, exc.read(), "application/json")
        except Exception as exc:
            self._send(502, json.dumps({"error": str(exc)[:120]}).encode(), "application/json")

    def do_GET(self) -> None:
        from urllib.parse import urlparse

        if urlparse(self.path).path.startswith("/v1/"):
            self._proxy_trust()
        else:
            self._serve_file(self.path)

    def do_POST(self) -> None:
        from urllib.parse import urlparse

        if urlparse(self.path).path.startswith("/v1/"):
            self._proxy_trust()
        else:
            self.send_error(404)

    def log_message(self, *args) -> None:
        pass


@pytest.fixture()
def site(cloud):
    base, _, _ = cloud
    handler = _SiteWithTrustProxy
    handler.base = base
    handler.directory = str(WEBSITE)
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


def _hermetic_cli(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("EPI_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("EPI_KEYS_DIR", str(tmp_path / "home" / "keys"))
    monkeypatch.setenv("EPI_NOTARIZE", "0")
    monkeypatch.setenv("EPI_CHECKPOINTS_ENABLED", "0")
    for key in ("EPI_WITNESS_URL", "EPI_WITNESS_SECRET"):
        monkeypatch.delenv(key, raising=False)


def test_vendor_records_pushes_and_reviewer_verifies_offline(
    cloud, site, browser, tmp_path, monkeypatch
) -> None:
    from epi_cli.main import app as cli_app

    base, cookie, persist = cloud
    _hermetic_cli(monkeypatch, tmp_path)

    # Vendor: workspace, recorder name, customer inbox.
    st, org = _api(
        base,
        "POST",
        "/v1/orgs",
        cookie,
        {"name": "Acme AI", "slug": f"acme-{secrets.token_hex(3)}"},
    )
    assert st == 201, (st, org)
    org_id = org["id"]
    # Room for two customers: lift the free plan's 1-inbox cap for this org.
    _wrangler(
        "d1",
        "execute",
        "epi-cloud",
        "--local",
        "--command",
        f"UPDATE orgs SET plan='growth' WHERE id='{org_id}'",
        persist=persist,
    )
    st, _ = _api(base, "POST", f"/v1/orgs/{org_id}/agents", cookie, {"name": "Acme Bank"})
    assert st in (200, 201), st
    st, inbox = _api(
        base, "POST", f"/v1/orgs/{org_id}/inboxes", cookie, {"customer_label": "Acme Bank"}
    )
    assert st == 201, (st, inbox)
    st, agents = _api(base, "GET", f"/v1/orgs/{org_id}/agents", cookie)
    agent_id = [a for a in agents["agents"] if a["name"] == "Acme Bank"][0]["id"]

    # Vendor: seal with `epi record` while the witness env points at the inbox.
    witness_url = inbox["url"]
    assert witness_url.startswith(base + "/w/"), witness_url
    monkeypatch.setenv("EPI_WITNESS_URL", witness_url)
    monkeypatch.setenv("EPI_WITNESS_SECRET", inbox["secret"])
    epi = tmp_path / "run.epi"
    result = runner.invoke(
        cli_app, ["record", "--out", str(epi), "--", sys.executable, "-c", "pass"]
    )
    assert result.exit_code == 0, result.output
    assert "Witness: delivered to" in result.output

    # Vendor: log in the CLI and push tagged to the customer.
    st, key = _api(
        base, "POST", f"/v1/orgs/{org_id}/api-keys", cookie, {"scopes": ["push", "read"]}
    )
    assert st == 201, (st, key)
    result = runner.invoke(
        cli_app, ["cloud", "login", "--url", base, "--org", org_id, "--api-key", key["key"]]
    )
    assert result.exit_code == 0, result.output
    result = runner.invoke(
        cli_app, ["cloud", "push", str(epi), "--reason", "sample", "--agent", "Acme Bank"]
    )
    assert result.exit_code == 0, result.output
    assert "witnessed" in result.output.lower()

    # Reviewer: a second customer whose runs must never leak into Bank A's link.
    has_b = False
    inbox_b = None
    st, inbox_b = _api(
        base, "POST", f"/v1/orgs/{org_id}/inboxes", cookie, {"customer_label": "Other Bank"}
    )
    assert st == 201, (st, inbox_b)
    st, _ = _api(base, "POST", f"/v1/orgs/{org_id}/agents", cookie, {"name": "Other Bank"})
    assert st in (200, 201), st
    epi_b = tmp_path / "run-b.epi"
    result = runner.invoke(
        cli_app, ["record", "--out", str(epi_b), "--", sys.executable, "-c", "pass"]
    )
    assert result.exit_code == 0, result.output
    result = runner.invoke(
        cli_app, ["cloud", "push", str(epi_b), "--reason", "sample", "--agent", "Other Bank"]
    )
    assert result.exit_code == 0, result.output
    has_b = True

    # Reviewer link scoped to Bank A only.
    st, link = _api(
        base,
        "POST",
        f"/v1/orgs/{org_id}/share-links",
        cookie,
        {"label": "Acme review", "scope": {"agents": [agent_id], "inboxes": [inbox["id"]]}},
    )
    assert st == 201, (st, link)
    token = link["token"]

    # Bank A isolation over the wire: no Bank B bytes anywhere.
    tok = {"X-EPI-Share-Token": token}
    req = urllib.request.Request(base + f"/v1/trust/{link['id']}", headers=tok)
    with urllib.request.urlopen(req, timeout=30) as res:
        doc = json.loads(res.read().decode())
    got = json.dumps(doc)
    assert "Other Bank" not in got, got[:500]
    assert all(a.get("agent_id") == agent_id for a in doc.get("artifacts", []))
    if has_b:
        assert inbox_b is not None
        req = urllib.request.Request(base + f"/w/{inbox_b['id']}/export.jsonl", headers=tok)
        try:
            with urllib.request.urlopen(req, timeout=30):
                raise AssertionError("Bank B export must 403 on Bank A's link")
        except urllib.error.HTTPError as exc:
            assert exc.code == 403, exc.code

    # Vendor: an untagged run, assigned to the customer from the Runs tab.
    # The dashboard is live now (link exists), so the Runs tab renders.
    epi_c = tmp_path / "run-c.epi"
    result = runner.invoke(
        cli_app, ["record", "--out", str(epi_c), "--", sys.executable, "-c", "pass"]
    )
    assert result.exit_code == 0, result.output
    result = runner.invoke(cli_app, ["cloud", "push", str(epi_c), "--reason", "sample"])
    assert result.exit_code == 0, result.output
    st, owned = _api(base, "GET", f"/v1/orgs/{org_id}/artifacts", cookie)
    assert st == 200, (st, owned)
    assert any(a.get("agent_id") is None for a in owned["artifacts"])
    dctx = browser.new_context()
    dpg = dctx.new_page()
    try:
        dctx.add_cookies(
            [{"name": "epi_session", "value": SESSION_RAW, "domain": "127.0.0.1", "path": "/"}]
        )
        dpg.goto(base + "/")
        dpg.wait_for_selector("text=Your evidence", timeout=20000)
        dpg.wait_for_selector("#tab-runs td >> text=Unassigned", timeout=20000)
        dpg.locator("#tab-runs select[data-assign]").first.select_option(label="Acme Bank")
        dpg.locator("#tab-runs button[data-assignbtn]").first.click()
        # Assign reloads the runs; the cell detaching means it landed.
        dpg.wait_for_selector("#tab-runs td >> text=Unassigned", state="detached", timeout=20000)
        dpg.click("button.tab:text-is('Customers')")
        dpg.wait_for_selector("#tab-customers >> text=Acme Bank", timeout=20000)
    finally:
        dctx.close()
    st, owned = _api(base, "GET", f"/v1/orgs/{org_id}/artifacts", cookie)
    assert st == 200, (st, owned)
    assert all(a.get("agent_id") is not None for a in owned["artifacts"]), owned

    # Reviewer in a real browser at 390px through the same-origin proxy.
    ctx = browser.new_context(viewport={"width": 390, "height": 844})
    pg = ctx.new_page()
    try:
        pg.goto(f"{site}/t/{link['id']}#k={token}")
        pg.click("#gateBtn")
        pg.wait_for_selector("#trustFiles >> text=Sealed run", timeout=20000)
        assert pg.locator("#trustFiles >> text=Other Bank").count() == 0
        # FIX 5: every shared file says why it is (not) witnessed, in one line.
        assert pg.locator("#trustFiles >> text=Witnessed").count() >= 1
        # Awaiting-checkpoint counts say when they appear; one Key history heading.
        assert pg.locator("#trustStats >> text=Counts by date appear after tonight").count() >= 1
        assert pg.locator("#trustContent >> text=Key history").count() == 1
        pg.locator("text=Verify these bytes").first.click()
        pg.wait_for_selector(
            "#trustFiles .vresult >> text=/Hash matches|FAIL|Could not/", timeout=30000
        )
        vresult = pg.locator("#trustFiles .vresult").first.inner_text()
        assert "Hash matches" in vresult, f"in-browser verify said: {vresult!r}"
        with pg.expect_download() as dl:
            pg.click("#packBtn")
        download = dl.value
        pack_path = tmp_path / "pack.zip"
        download.save_as(str(pack_path))
        import zipfile

        with zipfile.ZipFile(pack_path) as z:
            names = z.namelist()
            assert "witness.json" in names
            witness = json.loads(z.read("witness.json"))
            assert len(witness.get("lines", [])) >= 1, "pack must carry >= 1 witnessed line"
            epifiles = [n for n in names if n.endswith(".epi")]
            assert epifiles, names
            z.extractall(tmp_path / "pack")
    finally:
        ctx.close()

    # Auditor offline: the exact README flow with a pinned key.
    pub = _pub_of_secret(SIGNING_KEY)
    assert witness.get("witness_pubkey") == pub
    epi_file = next((tmp_path / "pack").rglob("*.epi"))
    wit_path = tmp_path / "wit.json"
    wit_path.write_text(json.dumps(witness), encoding="utf-8")
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "epi_cli",
            "verify",
            str(epi_file),
            "--policy",
            "strict",
            "--witness-log",
            str(wit_path),
            "--witness-pubkey",
            pub,
            "--offline",
            "--json",
        ],
        capture_output=True,
        text=True,
        timeout=180,
        cwd=str(REPO),
    )
    report = json.loads(proc.stdout)
    # The seal itself is self-signed (fresh local key), so strict mode may
    # FAIL overall on identity — but the witness verdict must be WITNESSED.
    assert report["witness"]["status"] == "WITNESSED", report["witness"]
