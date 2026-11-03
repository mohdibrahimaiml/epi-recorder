"""One checklist: ten general questions, then four for insurance.

The point of this file is that there is exactly one place to read them and one
PDF to send. If a second list of questions appears on another page, the outreach
link stops meaning what it says.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SITE = REPO / "website"
PAGE = SITE / "checklist" / "index.html"
PDF = SITE / "assets" / "checklist.pdf"
TXT = SITE / "assets" / "checklist.txt"
LEGACY_TXT = SITE / "assets" / "decision-record-checklist.txt"

GENERAL = [
    "What was decided, in plain language?",
    "What outcome was recorded, and when?",
    "What inputs and data did the model rely on?",
    "Which model and version answered?",
    "What rules, policy or limit applied?",
    "What reasons were recorded for the decision?",
    "Who or what approved it, and when?",
    "If a human approval was required, is it attached to this record?",
    "What happened next",
    "Can the reviewer read this without the vendor's system?",
]

INSURANCE = [
    "Did the reviewer agree with the AI, change it, or override it?",
    "Which version of the policy or rule was in force on the day of the decision?",
    "Was the record made at the time of the decision, not assembled later for an exam?",
    "Would the carrier notice if the record were changed after it was handed over?",
]


def test_page_and_assets_exist():
    assert PAGE.is_file()
    assert PDF.is_file()
    assert TXT.is_file()
    assert LEGACY_TXT.is_file()


def test_pdf_is_one_page():
    # No optional PDF library: the release gate does not install one, and a test
    # that needs pypdf fails the build instead of checking the page count.
    data = PDF.read_bytes()
    assert data[:5] == b"%PDF-"
    counts = [int(n) for n in re.findall(rb"/Count\s+(\d+)", data)]
    assert counts, "the page tree should declare a page count"
    assert counts[0] == 1, counts
    assert len(re.findall(rb"/Type\s*/Page[^s]", data)) == 1


def test_page_lists_the_ten_then_the_four():
    text = PAGE.read_text(encoding="utf-8")
    for question in GENERAL:
        assert question in text, question
    for question in INSURANCE:
        assert question in text, question
    assert "For insurance" in text
    assert "four more" in text.lower()


def test_the_text_files_carry_all_fourteen_and_agree():
    canonical = TXT.read_text(encoding="utf-8")
    legacy = LEGACY_TXT.read_text(encoding="utf-8")
    assert canonical == legacy, "the legacy path must not drift from the real one"
    assert len(re.findall(r"^\d+\.\s", canonical, re.M)) == 14
    for question in GENERAL + INSURANCE:
        assert question in canonical, question


def test_page_offers_one_pdf_and_one_link_target():
    text = PAGE.read_text(encoding="utf-8")
    assert 'href="/assets/checklist.pdf"' in text
    assert 'href="/assets/checklist.txt"' in text
    assert "Every no is a gap" in text


def test_no_second_question_list_on_the_other_pages():
    """The category page and the insurance page point here instead of repeating."""
    record_page = (SITE / "decision-record" / "index.html").read_text(encoding="utf-8")
    insurance_page = (
        SITE / "insurance" / "ai-vendor-decision-record" / "index.html"
    ).read_text(encoding="utf-8")
    for page in (record_page, insurance_page):
        assert 'href="/checklist"' in page
        assert 'href="/assets/checklist.pdf"' in page
    # The insurance page keeps its own argument, but not a second numbered list.
    assert insurance_page.count("<ol") == 0


def test_sitemap_lists_the_checklist():
    sitemap = (SITE / "sitemap.xml").read_text(encoding="utf-8")
    assert "https://epilabs.org/checklist" in sitemap
