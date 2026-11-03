"""The insurance page must stay accurate about an unadopted NAIC draft.

These tests are the guard rails for the July-November 2026 publication window: the
supplement is a draft, the item number moved between versions, and the page must
never claim the NAIC requires a decision record.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SITE = REPO / "website"
PAGE = SITE / "insurance" / "ai-vendor-decision-record" / "index.html"
CHECKLIST_TXT = SITE / "assets" / "checklist.txt"
CHECKLIST_PDF = SITE / "assets" / "checklist.pdf"
SAMPLE = SITE / "assets" / "demo" / "naic-claim-override.html"
SAMPLE_EPI = SITE / "assets" / "demo" / "naic-claim-override.epi"
CANONICAL_CHECKLIST = SITE / "assets" / "decision-record-checklist.txt"

QUESTIONS = [
    "For one specific decision, can you show what data the AI saw?",
    "Can you show what it recommended or decided, and why?",
    "Which policy provisions or rules did it rely on, and which version was in force that day?",
    "Which model and version answered, and would the record show if it changed later?",
    "Who reviewed it, and did they agree, change or override the AI?",
    "When did each step happen?",
    "Was the record made at the time of the decision, not assembled later for an exam?",
    "Can the carrier open it without logging into the vendor's system?",
    "Would the carrier notice if the record were changed after it was handed over?",
    "Can you list decisions that should have a record but don't?",
]


def _page() -> str:
    return PAGE.read_text(encoding="utf-8")


def test_page_and_assets_exist():
    assert PAGE.is_file()
    assert CHECKLIST_TXT.is_file()
    assert CHECKLIST_PDF.is_file()
    assert SAMPLE.is_file()
    assert SAMPLE_EPI.is_file()


def test_pdf_is_a_pdf_and_small_enough_to_email():
    head = CHECKLIST_PDF.read_bytes()[:5]
    assert head == b"%PDF-", head
    assert CHECKLIST_PDF.stat().st_size < 400_000


def test_never_says_the_naic_requires_a_record():
    text = _page()
    forbidden = [
        "naic requires",
        "naic now requires",
        "the naic mandates",
        "required by the naic",
    ]
    lowered = text.lower()
    for phrase in forbidden:
        assert phrase not in lowered, phrase


def test_says_it_is_not_adopted_and_adds_the_legal_disclaimer():
    text = _page()
    assert "draft" in text.lower()
    assert "16 November 2026" in text
    assert "Not legal advice" in text


def test_cites_the_version_6_item_number_and_names_the_v5_one():
    text = _page()
    # 3n is the vendor item in v6.0; 3p was v5.0 and means something else now.
    assert "3n" in text
    assert "3p in version 5.0" in text
    assert "Governs, monitors, tests and ensures transparency" in text


def test_quotes_the_two_regulatory_anchors_verbatim():
    text = _page()
    assert "permit reconstruction of the insurer's activities relative to each claim" in text
    assert "noted as to date received, date processed or date mailed" in text
    # Model 902 is P&C only; the page must say so.
    assert "property and casualty" in text.lower()


def test_attributes_the_trade_group_comments():
    text = _page()
    assert "minimum information insurers are expected to obtain from third-party vendors" in text
    assert "source code, training data, model weights" in text


def test_states_what_the_record_leaves_out():
    text = _page()
    lowered = text.lower()
    assert "no source code" in lowered
    assert "no training data" in lowered
    assert "no model weights" in lowered


def test_page_points_at_the_one_checklist():
    text = _page()
    assert 'href="/checklist"' in text
    assert 'href="/assets/checklist.pdf"' in text
    # The four insurance additions are summarised in prose, not re-listed.
    assert "Did the reviewer agree with the AI" not in text


def test_checklist_text_carries_all_fourteen_questions():
    text = CHECKLIST_TXT.read_text(encoding="utf-8")
    assert len(re.findall(r"^\d+\.\s", text, re.M)) == 14
    assert "Every no is a gap" in text


def test_checklist_avoids_cryptography_vocabulary():
    text = (CHECKLIST_TXT.read_text(encoding="utf-8") + _page()).lower()
    for term in ("cryptograph", "hash", "sha-256", "ed25519", "seal", "signature"):
        assert term not in text, term


def test_links_to_the_sample_the_checklist_and_the_record_page():
    text = _page()
    assert 'href="/assets/demo/naic-claim-override.html"' in text
    assert 'href="/assets/demo/naic-claim-override.epi"' in text
    assert 'href="/checklist"' in text
    assert 'href="/decision-record"' in text


def test_quotes_the_nyfs_audit_right_clause_verbatim():
    """CL7 paragraph 37, quoted exactly: "qualified auditing entities", not auditors."""
    text = _page()
    assert "provide audit rights or entitle the insurer to receive audit reports by qualified auditing entities" in text
    assert "require the third-party vendor to cooperate with the insurer regarding regulatory inquiries and investigations" in text
    assert "https://www.dfs.ny.gov/industry-guidance/circular-letters/cl2024-07" in text
    # The scope caveat must survive: it is underwriting and pricing, in New York.
    assert "underwriting and pricing" in text


def test_sample_artifact_is_committable():
    """*.epi is gitignored; the sample must be allow-listed or the link 404s."""
    ignore = (REPO / ".gitignore").read_text(encoding="utf-8")
    assert "!website/assets/demo/naic-claim-override.epi" in ignore
    assert "!site/assets/demo/*.epi" in ignore


def test_sample_is_labelled_invented():
    html = SAMPLE.read_text(encoding="utf-8", errors="replace")
    lowered = html.lower()
    assert "invented" in lowered or "simulated" in lowered
    assert "CLM-2026-04417" in html


def test_the_checklist_two_paths_reach_the_insurance_page():
    # The one checklist page links to the insurance argument; the legacy text
    # file is generated from the same source and must not drift.
    checklist_page = (SITE / "checklist" / "index.html").read_text(encoding="utf-8")
    assert 'href="/insurance/ai-vendor-decision-record"' in checklist_page
    canonical = CANONICAL_CHECKLIST.read_text(encoding="utf-8")
    assert canonical == (SITE / "assets" / "checklist.txt").read_text(encoding="utf-8")
    record_page = (SITE / "decision-record" / "index.html").read_text(encoding="utf-8")
    assert 'href="/checklist"' in record_page


def test_sitemap_lists_the_page():
    sitemap = (SITE / "sitemap.xml").read_text(encoding="utf-8")
    assert "https://epilabs.org/insurance/ai-vendor-decision-record" in sitemap
