"""Regression: plan aliases must resolve to canonical PLAN_FEATURES keys."""

import pytest
from verify_portal.auth import normalize_plan
from verify_portal.tier_gating import PLAN_FEATURES, PLAN_RANK, features_for_plan, get_rate_limit

pytestmark = pytest.mark.experimental

def test_canonical_plans_have_features():
    for key in ("free", "hosted", "team", "enterprise"):
        assert key in PLAN_FEATURES
        assert key in PLAN_RANK
        feats = features_for_plan(key)
        assert feats["label"]
        assert feats["pdf"] is False  # hosted PDF not shipped


def test_pro_and_starter_alias_to_hosted():
    assert normalize_plan("pro") == "hosted"
    assert normalize_plan("starter") == "hosted"
    assert features_for_plan("pro")["verifications"] == 10_000
    assert features_for_plan("starter")["verifications"] == 10_000
    assert features_for_plan("hosted")["scitt"] is True
    assert features_for_plan("pro")["api_key_limit"] == 10


def test_free_is_not_accidentally_paid():
    free = features_for_plan("free")
    assert free["verifications"] == 100
    assert free["scitt"] is False
    assert free["api_key_limit"] == 1


def test_rate_limit_matches_features():
    assert get_rate_limit("hosted") == 10_000
    assert get_rate_limit("pro") == 10_000
    assert get_rate_limit("free") == 100
    assert get_rate_limit("enterprise") is None
