"""The offer states its terms, and the sales script is not in the public repo.

Both of these have regressed before: the offer was published without payment and
access terms, and an internal sales script sat in a world-readable folder.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PLANS = REPO / "website" / "plans.html"
OFFER = REPO / "docs" / "PILOT-OFFER.md"
PRIVATE_SALES = REPO / "PRIVATE-EPI" / "SALES-QUESTIONS.md"

TERMS = [
    "Invoiced in full at the start",
    "Access within 5 working days",
    "30 days of email support",
]


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8").replace("&mdash;", "-")


def test_the_plans_page_states_the_terms():
    text = _text(PLANS)
    for term in TERMS:
        assert term in text, term


def test_the_offer_states_the_terms():
    text = _text(OFFER)
    for term in TERMS:
        assert term in text, term


def test_support_is_email_support_not_generic_support():
    for path in (PLANS, OFFER):
        text = _text(path)
        assert "30 days of support" not in text, path
        assert "30 days of email support" in text, path


def test_the_sales_script_is_not_tracked():
    tracked = subprocess.run(
        ["git", "ls-files", "internal", "PRIVATE-EPI"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert "SALES-QUESTIONS.md" not in tracked
    assert not (REPO / "internal" / "SALES-QUESTIONS.md").exists()


def test_private_epi_is_ignored():
    if not PRIVATE_SALES.exists():
        return  # local-only folder; on a clean clone there is nothing to ignore
    result = subprocess.run(
        ["git", "check-ignore", str(PRIVATE_SALES)],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, "PRIVATE-EPI/ must stay out of the public repo"
