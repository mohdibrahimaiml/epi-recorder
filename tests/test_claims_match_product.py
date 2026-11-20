"""Guards for the v4.11.0 claims pass.

These are static checks on the public copy and docs. They fail if a claim that
was corrected drifts back to something the product does not do.
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SITE = REPO / "website"
DOCS = REPO / "docs"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def test_plans_page_claims_match_the_code() -> None:
    text = _read(SITE / "plans.html")
    assert "Kept while subscribed" in text
    assert "7 years while subscribed" not in text
    # Growth includes the licensed package, not Enterprise only.
    assert "Growth includes the licensed" in text
    assert "epi-enterprise" in text
    assert "within 2 working days of payment" in text
    # The DPA is not claimed as signed; the policy says what is true today.
    assert "data processing agreement (we sign ours or review yours)" in text
    assert "signed DPA" not in text
    # Moving between paid plans is by email, same day.
    assert "Moving between Startup and Growth after that" in text
    # Upgrades extend existing files.
    assert "Upgrading extends the files you already have" in text


def test_refund_page_describes_the_real_plan_change_path() -> None:
    text = _read(SITE / "refund.html")
    assert "Upgrading from Free takes effect as soon as payment clears." in text
    assert "To move between Startup and Growth, write to us" in text
    assert "An upgrade takes effect straight away" not in text


def test_contact_form_posts_before_it_falls_back_to_email() -> None:
    js = _read(SITE / "js" / "contact.js")
    assert 'window.EPI_CONTACT_ENDPOINT = "https://cloud.epilabs.org/contact"' in js
    assert "work_email" in js
    assert "website" in js  # honeypot field
    assert "mailtoFallback(d)" in js
    plans = _read(SITE / "plans.html")
    assert 'name="website"' in plans
    assert "Send message" in plans
    privacy = _read(SITE / "privacy.html")
    assert "12 months" in privacy
    assert "on Render" not in privacy


def test_retention_doc_names_only_current_plans() -> None:
    text = _read(DOCS / "DATA-RETENTION.md")
    assert "| Startup |" in text
    assert "| Growth |" in text
    assert "| Business |" not in text
    assert "| Team |" not in text
    assert "kept while subscribed" in text
    assert "90-day export window" in text
    assert "Upgrading extends existing files" in text


def test_cloud_doc_does_not_invent_add_on_prices() -> None:
    text = _read(DOCS / "CLOUD.md")
    assert "more by agreement" in text
    assert "+$100/month each" not in text
    assert "+$150/month each" not in text
    assert "7 years while subscribed" not in text
