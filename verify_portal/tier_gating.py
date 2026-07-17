"""Tier-gating for paid plan features."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import HTTPException, Request

from verify_portal.auth import extract_token, normalize_plan, verify_token
from verify_portal.billing import get_user_plan, init_billing_columns

PLAN_RANK = {"free": 0, "pro": 1, "team": 2, "enterprise": 3}

PLAN_FEATURES = {
    "free": {
        "verifications": 100,
        "scitt": False,
        "pdf": False,
        "api_keys": True,  # 1 free key for onboarding
        "api_key_limit": 1,
        "support": "Community",
        "label": "Free",
    },
    "pro": {
        "verifications": 10_000,
        "scitt": True,
        "pdf": True,
        "api_keys": True,
        "api_key_limit": 10,
        "support": "Email 48h",
        "label": "Pro",
    },
    "team": {
        "verifications": 50_000,
        "scitt": True,
        "pdf": True,
        "api_keys": True,
        "api_key_limit": 50,
        "support": "Email 48h + Slack",
        "label": "Team / Advanced",
    },
    "enterprise": {
        "verifications": None,
        "scitt": True,
        "pdf": True,
        "api_keys": True,
        "api_key_limit": None,
        "support": "Dedicated",
        "label": "Enterprise",
    },
}


def get_plan(request: Request) -> str:
    token = extract_token(request)
    if not token:
        return "free"
    storage_dir = Path(os.environ.get("EPI_STORAGE_DIR", "./data"))
    user = verify_token(storage_dir, token)
    if not user:
        return "free"
    init_billing_columns(storage_dir)
    return normalize_plan(get_user_plan(storage_dir, user["id"]))


def require_plan(min_plan: str):
    """Dependency: raises 402 if user plan is below min_plan."""
    min_plan = normalize_plan(min_plan)

    async def check(request: Request):
        plan = get_plan(request)
        if PLAN_RANK.get(plan, 0) < PLAN_RANK.get(min_plan, 0):
            raise HTTPException(
                status_code=402,
                detail=(
                    f"This feature requires a {PLAN_FEATURES.get(min_plan, {}).get('label', min_plan)} plan or higher. "
                    f"Your current plan is {PLAN_FEATURES.get(plan, {}).get('label', plan)}. Upgrade at /pricing."
                ),
            )
        return plan

    return check


def get_rate_limit(plan: str) -> int | None:
    plan = normalize_plan(plan)
    return PLAN_FEATURES.get(plan, PLAN_FEATURES["free"])["verifications"]


def features_for_plan(plan: str) -> dict:
    plan = normalize_plan(plan)
    return dict(PLAN_FEATURES.get(plan, PLAN_FEATURES["free"]))
