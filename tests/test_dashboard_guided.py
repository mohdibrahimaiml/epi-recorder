"""Dashboard 3-step guided flow on a 390px phone: real workerd + real browser.

Boots `wrangler dev --local` against an isolated persist dir, seeds one
owner session straight into local D1, then walks the guided start the way
a new customer would: company -> connect + pick customer (device code) ->
first run + share link -> dashboard tabs. Screenshots land in
docs/dashboard-v2/ and are committed for the PR.

Browser-marked: the release gate deselects it; .github/workflows/
dashboard-browser.yml runs it with Playwright chromium on every PR.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import shutil
import socket
import subprocess
import time
import urllib.request
from pathlib import Path

import pytest

pytestmark = pytest.mark.browser

REPO = Path(__file__).resolve().parents[1]
CLOUD = REPO / "cloud"
SHOTS = REPO / "docs" / "dashboard-v2"

SESSION_RAW = "dash-e2e-session-0123456789abcdef0123456789abcdef"
INBOX_KEY = "cd" * 32


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
    import urllib.error

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


@pytest.fixture(scope="module")
def cloud():
    persist = Path.cwd() / f".tmp-dash-e2e-{secrets.token_hex(4)}"
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
        yield base, f"epi_session={SESSION_RAW}"
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=20)
        except Exception:
            proc.kill()
        shutil.rmtree(persist, ignore_errors=True)


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


def _no_overflow(pg) -> None:
    width = pg.evaluate("() => document.documentElement.scrollWidth")
    assert width <= 391, f"page overflows 390px viewport: scrollWidth={width}"


def test_guided_flow_on_phone(cloud, browser, tmp_path) -> None:
    base, cookie = cloud
    SHOTS.mkdir(parents=True, exist_ok=True)
    ctx = browser.new_context(viewport={"width": 390, "height": 844})
    ctx.add_cookies(
        [
            {
                "name": "epi_session",
                "value": SESSION_RAW,
                "domain": "127.0.0.1",
                "path": "/",
            }
        ]
    )
    pg = ctx.new_page()
    try:
        # Step 1: name the company.
        pg.goto(base + "/")
        pg.wait_for_selector("#org-go", timeout=15000)
        assert pg.locator("text=Name your company").is_visible()
        pg.screenshot(path=str(SHOTS / "01-guided.png"))
        _no_overflow(pg)
        pg.fill("#org-name", "Acme AI")
        assert pg.input_value("#org-slug") == "acme-ai"
        pg.click("#org-go")
        pg.wait_for_selector("text=Connect your computer", timeout=15000)
        orgs = _api(base, "GET", "/v1/orgs", cookie)[1]["orgs"]
        org_id = [o for o in orgs if o["name"] == "Acme AI"][0]["id"]

        # Step 2: connect via device code (what `epi cloud login` does),
        # picking the customer in the browser. No secrets to copy.
        pg.screenshot(path=str(SHOTS / "02-connect.png"))
        _no_overflow(pg)
        _, started = _api(base, "POST", "/auth/device/start", cookie, {"device_name": "e2e-laptop"})
        st, _ = _api(
            base,
            "POST",
            "/auth/device/authorize",
            cookie,
            {"user_code": started["user_code"], "org_id": org_id, "customer_label": "Acme Bank"},
        )
        assert st == 200, st
        pg.reload()
        pg.wait_for_selector("text=Record your first run and share it", timeout=15000)
        # Guided step 2 is gone as a separate customer form: no secrets pasted.
        assert pg.locator("#cust-go").count() == 0
        assert pg.locator("text=EPI_WITNESS_SECRET=").count() == 0

        # Step 3: push one real run through the API the CLI uses.
        manifest = json.dumps(
            {
                "spec_version": "2",
                "workflow_id": "w1",
                "goal": "g",
                "total_steps": 1,
                "created_at": "2026-10-17T00:00:00.000Z",
            }
        )
        file_bytes = b"e2e-run-bytes"
        import hashlib as _hashlib

        digest = _hashlib.sha256(file_bytes).hexdigest()
        st, init = _api(
            base,
            "POST",
            f"/v1/orgs/{org_id}/artifacts/init",
            cookie,
            {
                "manifest_json": manifest,
                "claimed_sha256": digest,
                "claimed_crc32": 1,
                "size_bytes": len(file_bytes),
                "reason": "sample",
            },
        )
        assert st in (200, 201), (st, init)
        if not init.get("deduped"):
            put = urllib.request.Request(
                base + init["put_url"],
                data=file_bytes,
                method="PUT",
                headers={"Cookie": cookie, "Content-Length": str(len(file_bytes))},
            )
            with urllib.request.urlopen(put, timeout=30):
                pass
        pg.reload()
        # Step 3: run arrived, now share it. The link form lives in step 3;
        # there is no separate customer step and no secrets pasted.
        pg.wait_for_selector("#link-go", timeout=15000)
        assert pg.locator("#cust-go").count() == 0
        assert pg.locator("text=EPI_WITNESS_SECRET=").count() == 0
        assert pg.locator("#link-all").count() == 0
        # The step-3 status reflects the data: runs exist, so it must say
        # received (with the latest run name), never "Waiting for the first run".
        s3msg = pg.locator("#s3-msg").text_content() or ""
        assert "received" in s3msg, s3msg
        assert "Waiting for the first run" not in s3msg, s3msg
        pg.screenshot(path=str(SHOTS / "03-customer.png"))
        _no_overflow(pg)

        # Share link scoped to that customer only. The result appears inline,
        # right under the button (in view), with a ready-to-send message; it
        # stays for 12 s across re-renders and the dashboard must not appear.
        pg.select_option("#link-cust", label="Acme Bank")
        pg.fill("#link-label", "Acme review")
        pg.click("#link-go")
        rev = '[data-rev="guide-link"]'
        link_sel = f"{rev} >> text=Open it as your customer will see it"
        pg.wait_for_selector(link_sel, timeout=15000)
        href = pg.locator(link_sel).get_attribute("href")
        assert href and href.startswith("https://epilabs.org/t/"), href
        rev_text = pg.locator(rev).text_content() or ""
        assert "nothing to install" in rev_text, rev_text
        assert "shown once" in rev_text, rev_text
        # Visible without scrolling: the result is in the viewport.
        assert pg.locator(f"{rev} .reveal").evaluate(
            "e => { const r = e.getBoundingClientRect(); return r.top < innerHeight && r.bottom > 0; }"
        )
        # No second "Create" button next to the result (no accidental 2nd link).
        assert pg.locator("#link-go").count() == 0
        for _ in range(12):
            assert pg.locator(link_sel).is_visible(), "link token vanished before Done"
            assert not pg.locator("#dash").is_visible(), "dashboard appeared past unacked link"
            pg.wait_for_timeout(1000)
        pg.screenshot(path=str(SHOTS / "04-link.png"))
        _no_overflow(pg)
        pg.click(f'[data-done="guide-link"]')
        pg.wait_for_selector("#dash", state="visible", timeout=15000)
        # Setup-complete banner appears once, right after the guide.
        assert pg.locator("#setup-done").is_visible()
        assert pg.locator("text=https://epilabs.org/t/").count() == 0, "token shown again after Done"

        # Dashboard tabs after setup (tab content loads async — wait for it).
        pg.wait_for_selector("button.tab:text-is('Computers & keys')", timeout=15000)
        pg.click("button.tab:text-is('Computers & keys')")
        pg.wait_for_selector("text=e2e-laptop", timeout=15000)
        for tab in ("Customers", "Share links", "Team"):
            pg.click(f"button.tab:text-is('{tab}')")
            pg.wait_for_timeout(800)
            _no_overflow(pg)
        pg.click("button.tab:text-is('Customers')")
        assert pg.locator("#tab-customers >> text=Acme Bank").is_visible()
        pg.click("button.tab:text-is('Share links')")
        assert pg.locator("#tab-links >> text=Acme review").is_visible()
        # A plan-limit error survives the re-render that follows the action.
        pg.click("#tab-link-go")
        pg.wait_for_selector('[data-msg="tab-link"] >> text=epilabs.org/plans', timeout=15000)
        pg.wait_for_timeout(2500)
        assert pg.locator('[data-msg="tab-link"] >> text=epilabs.org/plans').is_visible()

        # Rotate: the result appears inline under that customer. The main
        # instruction is `epi cloud login`; env vars stay collapsed under
        # Advanced (CI only). It stays across re-renders until Done.
        pg.click("button.tab:text-is('Customers')")
        pg.wait_for_selector("button[data-rotate]", timeout=15000)
        dialogs: list[str] = []
        pg.on("dialog", lambda d: (dialogs.append(d.message), d.accept()))
        pg.click("button[data-rotate]")
        rot = "#tab-customers [data-rev] .reveal"
        pg.wait_for_selector(f"{rot} >> text=On each computer for Acme Bank", timeout=15000)
        assert dialogs and "epi cloud login" in dialogs[-1] and "EPI_WITNESS" not in dialogs[-1], dialogs
        secret_sel = f"{rot} >> text=EPI_WITNESS_SECRET="
        assert not pg.locator(secret_sel).is_visible(), "secret must be collapsed under Advanced"
        for _ in range(12):
            assert pg.locator(f"{rot} >> text=On each computer for Acme Bank").is_visible(), "rotate result vanished"
            pg.wait_for_timeout(1000)
        pg.locator(f"{rot} summary").click()
        assert pg.locator(secret_sel).is_visible()
        pg.screenshot(path=str(SHOTS / "06-rotate.png"))
        _no_overflow(pg)
        pg.locator("#tab-customers [data-done]").click()
        assert pg.locator(secret_sel).count() == 0

        pg.click("button.tab:text-is('Runs')")
        pg.screenshot(path=str(SHOTS / "05-dashboard.png"))
        _no_overflow(pg)
        # FIX 2/3/5: the run shows its short id under the goal, and the
        # not-witnessed badge explains itself with a next step.
        runs_text = pg.locator("#tab-runs").text_content() or ""
        assert "No witness stamp arrived for this file yet" in runs_text, runs_text
        assert "epi witness flush" in runs_text, runs_text
        assert "then push the file again" in runs_text, runs_text
    finally:
        ctx.close()


def test_sign_out_returns_to_landing(cloud, browser) -> None:
    base, cookie = cloud
    ctx = browser.new_context(viewport={"width": 1280, "height": 800})
    ctx.add_cookies(
        [
            {
                "name": "epi_session",
                "value": SESSION_RAW,
                "domain": "127.0.0.1",
                "path": "/",
            }
        ]
    )
    pg = ctx.new_page()
    try:
        pg.goto(base + "/")
        pg.wait_for_selector("#signout", timeout=15000)
        assert "Signed in as" in (pg.content() or "")
        pg.click("#signout")
        pg.wait_for_selector("text=Sign in with GitHub", timeout=15000)
        assert "Signed in as" not in (pg.content() or "")
        pg.reload()
        pg.wait_for_selector("text=Sign in with GitHub", timeout=15000)
        assert "Signed in as" not in (pg.content() or "")
    finally:
        ctx.close()
