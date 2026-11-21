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


def test_offer_answers_the_review_it_does_not_promise_a_pass() -> None:
    """We answer the AI-evidence part of a customer's review; we never promise a pass."""
    plans = _read(SITE / "plans.html")
    assert "Answer the AI questions in your customer’s review." in plans
    assert "Pass the review" not in plans
    assert "Pass a review" not in plans
    assert "An answer sheet: each AI question in your customer’s review" in plans
    assert "We answer the AI-evidence part of the review, not all of it." in plans
    offer = _read(DOCS / "PILOT-OFFER.md")
    assert offer.startswith("# Answer the AI questions in your customer's review")
    assert "| Answer sheet |" in offer
    assert "Pass your customer" not in offer
    # The engagement includes 3 months of Cloud; the exclusions must agree.
    assert "Hosting beyond the 3 months of EPI Cloud Startup" in offer


def test_witnessing_is_unlimited_and_startup_keeps_files_while_subscribed() -> None:
    plans = _read(SITE / "plans.html")
    assert "Every decision witnessed, unlimited. File limits count only records stored and shared in EPI Cloud." in plans
    assert "Recording, witnessing and verifying are unlimited and never counted." in plans
    # Startup and Growth both keep files while subscribed; no plan row says "1 year".
    assert plans.count("Kept while subscribed") >= 2
    assert '<td style="padding:0.7rem 0.6rem">1 year</td>' not in plans
    retention = _read(DOCS / "DATA-RETENTION.md")
    assert "| Startup | 3 | 1,000 a year | kept while subscribed | unlimited |" in retention
    cloud = _read(DOCS / "CLOUD.md")
    assert "| 1,000 / year | kept while subscribed |" in cloud


def test_readme_describes_the_real_checkout() -> None:
    readme = _read(REPO / "README.md")
    assert "there is no public checkout" not in readme
    assert "Startup and Growth are self-serve by card in the dashboard" in readme
