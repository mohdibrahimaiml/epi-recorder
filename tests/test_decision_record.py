"""The Decision Record page is the category page; it must ship with the demo."""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SITE = REPO / "website"
PAGE = SITE / "decision-record" / "index.html"
CHECKLIST = SITE / "assets" / "decision-record-checklist.md"
DEMO = SITE / "assets" / "demo" / "decision-record-example.html"


def test_the_page_exists_and_names_the_category():
    text = PAGE.read_text(encoding="utf-8")
    assert "Every AI decision needs a Decision Record." in text
    assert "Not a log. Not a trace. Not a dashboard." in text
    assert "ten-question completeness checklist" in text.lower()
    assert "Decision Record" in text


def test_checklist_has_ten_questions_and_a_download_link():
    text = CHECKLIST.read_text(encoding="utf-8")
    questions = re.findall(r"^\d+\.\s", text, re.M)
    assert len(questions) == 10, questions
    page = PAGE.read_text(encoding="utf-8")
    assert "/assets/decision-record-checklist.md" in page
    assert "download" in page


def test_the_demo_is_real_output_from_the_cli():
    assert DEMO.is_file()
    text = DEMO.read_text(encoding="utf-8")
    assert "<title>EPI Decision Record" in text
    assert "EPI Decision Record" in text
    assert "/assets/demo/decision-record-example.html" in PAGE.read_text(encoding="utf-8")


def test_homepage_leads_with_decision_record_not_cryptography():
    home = (SITE / "index.html").read_text(encoding="utf-8")
    assert "Every AI decision needs a" in home
    assert "Decision Record." in home
    assert 'href="/decision-record"' in home
    # The old front-door promise and its signer caveat moved to /trust and /verify.
    assert "hand them a file they can check" not in home
    assert "signer unknown" not in home


def test_the_nav_links_to_the_category_page():
    for name in ("index.html", "plans.html", "how-it-works.html", "trust.html"):
        text = (SITE / name).read_text(encoding="utf-8")
        assert 'href="/decision-record"' in text, name


def test_sitemap_includes_the_page():
    sitemap = (SITE / "sitemap.xml").read_text(encoding="utf-8")
    assert "https://epilabs.org/decision-record" in sitemap


def test_docs_page_and_index_point_to_the_category():
    assert (REPO / "docs" / "DECISION-RECORD.md").is_file()
    index = (REPO / "docs" / "README.md").read_text(encoding="utf-8")
    assert "DECISION-RECORD.md" in index
