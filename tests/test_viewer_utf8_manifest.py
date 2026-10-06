"""The embedded viewer must verify manifests whose text is not plain ASCII.

Bug: the viewer decoded manifest.json with a bare atob() (Latin-1), so any
non-ASCII character in signed metadata (an em dash in the goal) changed the
bytes it hashed and a valid signature was shown as INVALID.
"""

from __future__ import annotations

import glob
import os
import re
import zipfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


def test_viewer_does_not_latin1_decode_the_manifest():
    src = (REPO / "web_viewer" / "app.js").read_text(encoding="utf-8")
    assert "atob(caseData.files['manifest.json'])" not in src
    assert "new TextDecoder('utf-8').decode(base64ToUint8Array(caseData.files['manifest.json']))" in src


def test_viewer_mirrors_match_canonical():
    canonical = (REPO / "web_viewer" / "app.js").read_bytes()
    for rel in ("site/viewer/app.js", "website/viewer/app.js",
                "epi-official/viewer/app.js", "verify_portal/static/viewer/app.js"):
        p = REPO / rel
        if p.exists():
            assert p.read_bytes() == canonical, rel


def _chromium():
    hits = glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome")
    return os.environ.get("EPI_TEST_CHROMIUM") or (hits[0] if hits else None)


@pytest.mark.parametrize("goal", ["plain ascii goal", "goal with an em dash — here", "Café ✓ 日本語"])
def test_browser_viewer_shows_valid_signature_for_non_ascii_goal(goal, monkeypatch, tmp_path):
    sync_api = pytest.importorskip("playwright.sync_api")
    exe = _chromium()
    if not exe:
        pytest.skip("no chromium available")
    monkeypatch.setenv("EPI_MCP_KEYS_DIR", str(tmp_path / "keys"))
    from epi_mcp.records import seal_record

    r = seal_record(
        [{"kind": "user.message", "content": {"text": "héllo — ✓"}, "timestamp": "2026-10-05T10:00:00Z"}],
        goal=goal,
    )
    html = tmp_path / "viewer.html"
    html.write_bytes(zipfile.ZipFile(r["epi_path"]).read("viewer.html"))
    with sync_api.sync_playwright() as p:
        browser = p.chromium.launch(executable_path=exe, args=["--no-sandbox"])
        page = browser.new_page()
        page.goto(html.as_uri())
        page.wait_for_timeout(3500)
        text = page.inner_text("body")
        browser.close()
    assert re.search(r"SIGNATURE VALID", text), text[:400]
    assert "SIGNATURE INVALID" not in text
