"""WP-DEMO-TRUST: static demo trust page at /t/acme-demo (DEMO-labelled, real .epi files)."""
from __future__ import annotations

import hashlib
import json
import pathlib
import re

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
