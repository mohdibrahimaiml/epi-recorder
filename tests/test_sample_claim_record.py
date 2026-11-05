"""The worked claim record is a real page on the site, not a bare artifact.

The artifact itself is a standalone document with its own paper styling — that
is deliberate, because a carrier attaches it to a claim file. What failed was
the entry point: the link used to drop a visitor straight into that document
with no site navigation and no explanation. These tests hold the wrapper in
place.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SITE = REPO / "website"
PAGE = SITE / "insurance" / "sample-claim-record" / "index.html"
ARTIFACT = SITE / "assets" / "demo" / "naic-claim-override.html"
EPI = SITE / "assets" / "demo" / "naic-claim-override.epi"


def _page() -> str:
    return PAGE.read_text(encoding="utf-8")


def test_page_and_artifact_exist():
    assert PAGE.is_file()
    assert ARTIFACT.is_file()
    assert EPI.is_file()


def test_it_uses_the_site_chrome():
    text = _page()
    assert 'class="z-header"' in text
    assert "/css/zenjin-epi.css" in text
    assert "z-nav__link" in text
    assert "z-footer" in text


def test_it_shows_a_preview_and_links_to_the_real_artifact():
    text = _page()
    # The site sends X-Frame-Options: DENY, so an iframe would be blocked in
    # production. A real screenshot stands in, and the record opens separately.
    assert "<iframe" not in text
    assert 'src="/assets/demo/naic-claim-override-preview.jpg"' in text
    assert 'href="/assets/demo/naic-claim-override.html"' in text
    assert "Case Overview" not in text
    assert "Decision and Reasons" not in text
    assert (SITE / "assets" / "demo" / "naic-claim-override-preview.jpg").is_file()


def test_it_offers_both_outputs():
    text = _page()
    assert 'href="/assets/demo/naic-claim-override.html"' in text
    assert 'href="/assets/demo/naic-claim-override.epi"' in text


def test_it_says_the_data_is_invented_and_explains_the_paper_style():
    text = _page().lower()
    assert "invented" in text
    assert "not legal advice" in text
    assert "document, not a web page" in text


def test_the_entry_points_land_here_not_on_the_raw_artifact():
    insurance = (
        SITE / "insurance" / "ai-vendor-decision-record" / "index.html"
    ).read_text(encoding="utf-8")
    checklist = (SITE / "checklist" / "index.html").read_text(encoding="utf-8")
    record = (SITE / "decision-record" / "index.html").read_text(encoding="utf-8")

    assert 'href="/insurance/sample-claim-record"' in insurance
    assert 'href="/insurance/sample-claim-record"' in checklist
    assert 'href="/insurance/sample-claim-record"' in record

    # No page should send a visitor straight to the bare document as the
    # primary call to action.
    for name, text in (
        ("insurance", insurance),
        ("checklist", checklist),
        ("decision-record", record),
    ):
        nav_links = re.findall(
            r'href="/assets/demo/naic-claim-override\.html"', text
        )
        assert not nav_links, f"{name} still links straight at the artifact"


def test_sitemap_lists_the_page():
    sitemap = (SITE / "sitemap.xml").read_text(encoding="utf-8")
    assert "https://epilabs.org/insurance/sample-claim-record" in sitemap
