"""WP-PRICING-0: $199/$799 hosted-verification plans removed; Design Partner + EPI Cloud beta present.

Fail-first test for the v2 build plan §8 package WP-PRICING-0 (gated).
"""
from __future__ import annotations

import pathlib
import re

REPO = pathlib.Path(__file__).resolve().parents[1]
PLANS = REPO / "website" / "plans.html"
PADDLE_CFG = REPO / "website" / "js" / "paddle-config.js"
INDEX = REPO / "website" / "index.html"

BANNED = ["compliant", "certified", "guaranteed", "court-admissible", "immutable", "tamper-proof"]


def _read(p):
    return p.read_text(encoding="utf-8", errors="ignore")


def test_hosted_team_checkout_removed_from_plans():
    text = _read(PLANS)
    assert "Hosted Plan ($199/mo)" not in text, "old Hosted contact option still present"
    assert "Team Plan ($799/mo)" not in text, "old Team contact option still present"
    # Dynamic tier buttons for the old self-serve tiers must be gone.
    assert 'data-buy="Hosted"' not in text and "data-buy='Hosted'" not in text
    assert 'data-buy="Team"' not in text and "data-buy='Team'" not in text
    # Old hosted-verification volume language must be gone from the plans page.
    assert "10,000 hosted verifications" not in text
    assert "50,000 hosted verifications" not in text


def test_paddle_config_no_hosted_team_tiers():
    text = _read(PADDLE_CFG)
    # Archived price IDs must not be offered as active tiers.
    assert '"Hosted"' not in text and "name: \"Hosted\"" not in text, "Hosted tier still in paddle-config.js"
    assert '"Team"' not in text and "name: \"Team\"" not in text, "Team tier still in paddle-config.js"
    # Sprint checkout (founder-led $1,500) stays intact.
    assert "sprintPriceId" in text


def test_design_partner_and_cloud_beta_present():
    text = _read(PLANS)
    assert "Design Partner" in text, "Design Partner program missing from /plans"
    assert "5 places" in text, "Design Partner scarcity (5 places) missing"
    assert "EPI Cloud" in text, "EPI Cloud missing from /plans"
    assert "private beta" in text.lower(), "private-beta label missing from /plans"
    # Witness-first positioning: hashes only, customer bucket, no customer data held.
    lowered = text.lower()
    assert "witness" in lowered, "witness-first positioning missing"
    assert "bucket" in lowered or "your bucket" in lowered or "customer" in lowered


def test_homepage_teaser_no_longer_sells_hosted_team_checkout():
    text = _read(INDEX)
    assert "Hosted · Team" not in text, "homepage still advertises Hosted/Team self-serve"
    lowered = text.lower()
    assert "epi cloud" in lowered or "design partner" in lowered or "private beta" in lowered


def test_new_copy_has_no_banned_claims():
    for path in (PLANS, INDEX):
        lowered = _read(path).lower()
        for word in BANNED:
            assert word not in lowered, f"banned word {word!r} in {path.name}"
