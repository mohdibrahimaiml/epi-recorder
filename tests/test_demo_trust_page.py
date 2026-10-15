"""WP-DEMO-TRUST: static /t/acme-demo is labelled DEMO and lives in website/."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
WEBSITE = REPO / "website"
DEMO_DIR = WEBSITE / "t" / "acme-demo"
DEMO_HTML = DEMO_DIR / "index.html"
DEMO_JS = DEMO_DIR / "demo.js"
DEMO_JSON = DEMO_DIR / "demo-data.json"


def test_demo_page_is_in_website_source():
    assert DEMO_HTML.is_file(), "demo must live in website/ (source of truth), not only a mirror"
    assert DEMO_JS.is_file()
    assert DEMO_JSON.is_file()


def test_demo_is_labelled_and_gated():
    html = DEMO_HTML.read_text(encoding="utf-8")
    js = DEMO_JS.read_text(encoding="utf-8")
    data = json.loads(DEMO_JSON.read_text(encoding="utf-8"))
    assert "DEMO" in html
    assert 'name="robots" content="noindex' in html
    assert 'name="referrer" content="no-referrer"' in html
    assert 'id="gateBtn"' in html
    assert "Open evidence" in html
    assert "epi verify FILE --policy strict --witness-log received.jsonl --offline" in html
    assert "/t/{slug}#k=" in html or "#k=" in html
    assert "display:none" in html  # evidence hidden until click
    assert "No tracking" in js or "No events are sent" in js
    assert data.get("demo") is True
    assert "DEMO" in data.get("demo_notice", "")
    assert "DEMO" in data.get("vendor", "")


def test_demo_uses_three_real_epi_files_with_matching_hashes():
    data = json.loads(DEMO_JSON.read_text(encoding="utf-8"))
    files = data.get("files") or []
    assert len(files) == 3
    for item in files:
        rel = item["path"].lstrip("/")
        path = WEBSITE / rel
        assert path.is_file(), f"missing shipped sample {rel}"
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        assert item["claimed_sha256"] == digest, f"stale claimed_sha256 for {rel}"
        assert "DEMO" in item.get("demo_note", "")
        assert "DEMO" in item.get("label", "")


def test_demo_counts_are_labelled_illustrations():
    data = json.loads(DEMO_JSON.read_text(encoding="utf-8"))
    cp = data.get("checkpoint_DEMO") or {}
    assert "DEMO" in str(cp.get("head_hash", ""))
    assert "DEMO" in str(cp.get("note", ""))
    agent = (data.get("agents") or [{}])[0]
    assert "runs_witnessed_30d_DEMO" in agent


def test_demo_not_in_sitemap():
    sitemap = (WEBSITE / "sitemap.xml").read_text(encoding="utf-8")
    assert "acme-demo" not in sitemap


def test_redirects_carve_out_demo_from_trust_shell():
    text = (WEBSITE / "_redirects").read_text(encoding="utf-8")
    assert "/t/acme-demo /t/acme-demo/ 301" in text
    assert "/t/acme-demo/demo.js /t/acme-demo/demo.js 200" in text
    assert "/t/acme-demo/demo-data.json /t/acme-demo/demo-data.json 200" in text
    assert "/t/acme-demo/* /t/acme-demo/:splat 200" in text
