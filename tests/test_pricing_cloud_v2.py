"""WP-PRICING-0: stop selling $199/$799 hosted verification on the public site."""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
WEBSITE = REPO / "website"


def test_plans_does_not_sell_hosted_199_799():
    text = (WEBSITE / "plans.html").read_text(encoding="utf-8")
    assert "$199" not in text
    assert "$799" not in text
    assert "Hosted Plan" not in text
    assert "Team Plan" not in text
    assert "Design Partner Program" in text
    assert "5 places" in text
    assert "private beta" in text.lower()
    assert "Founding price" in text
    assert "EPI Cloud" in text
    assert "id=\"tiersGrid\"" not in text
    assert "epi verify FILE --policy strict --witness-log received.jsonl --offline" in text


def test_home_teaser_is_not_hosted_team_checkout():
    text = (WEBSITE / "index.html").read_text(encoding="utf-8")
    assert "Hosted · Team" not in text
    assert "$199" not in text
    assert "$799" not in text
    assert "Design partner" in text or "Design Partner" in text
    assert "private beta" in text.lower()
