"""WP-PRICING-0: the public site sells one offer, not a hosted $199/$799 plan.

Originally this test pinned the Design Partner Program. That programme is gone:
the site now sells one witnessed pilot at a fixed price, and the assertions moved
with it, so the guard against hosted-verification checkout survives.
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
WEBSITE = REPO / "website"

PRICE = "\u20ac4,500"


def test_plans_does_not_sell_hosted_199_799():
    text = (WEBSITE / "plans.html").read_text(encoding="utf-8")
    assert "$199" not in text
    assert "$799" not in text
    assert "Hosted Plan" not in text
    assert "Team Plan" not in text
    assert "Witnessed pilot" in text
    assert PRICE in text
    assert "one of your AI workflows" in text
    assert "private beta" in text.lower()
    assert "EPI Cloud" in text
    assert "id=\"tiersGrid\"" not in text
    assert "epi verify FILE --policy strict --witness-log received.jsonl --offline" in text
    # one offer, no discount ladder and no "custom pilot" bucket
    assert "Design Partner" not in text
    assert "Custom pilot" not in text
    assert "Founding price" not in text


def test_home_teaser_is_not_hosted_team_checkout():
    text = (WEBSITE / "index.html").read_text(encoding="utf-8")
    assert "Hosted \u00b7 Team" not in text
    assert "$199" not in text
    assert "$799" not in text
    assert "Witnessed pilot" in text
    assert PRICE in text
    assert "private beta" in text.lower()
