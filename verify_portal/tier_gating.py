"""Tier-gating for paid plan features.

Honesty contract (must match website/pricing.html + auth.normalize_plan):

- Free forever offline: CLI, local SCITT, Annex multi-sign, CLI PDF, public GitHub Action.
- Paid self-serve plan is **hosted** (aliases: pro, starter → hosted via normalize_plan).
- Paid plans gate hosted verification volume, API key limits, and remote SCITT only.
- Hosted PDF API is not implemented — `pdf` is always False (use CLI).
- Seats / SSO / regulatory adapters are not gated here because they are not shipped.

Keys in PLAN_FEATURES must match VALID_PLANS after normalize_plan (free, hosted,
team, enterprise). Looking up raw aliases like "pro" without normalize falls back
incorrectly — always call normalize_plan first (features_for_plan does).
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import HTTPException, Request

from verify_portal.auth import extract_token, normalize_plan, verify_token
from verify_portal.billing import get_user_plan, init_billing_columns

PLAN_RANK = {"free": 0, "hosted": 1, "team": 2, "enterprise": 3}

# Canonical plan keys only (post-normalize). Do not list free CLI features as paid flags.
PLAN_FEATURES = {
    "free": {
        "verifications": 100,
        "scitt": False,
        "pdf": False,
        "api_keys": True,
        "api_key_limit": 1,
        "support": "Community",
        "label": "Free / Open Source",
    },
    "hosted": {
        # Self-serve paid tier on /plans ($199/mo). Aliases: pro, starter.
        "verifications": 10_000,
        "scitt": True,
        "pdf": False,
        "api_keys": True,
        "api_key_limit": 10,
        "support": "Email",
        "label": "Hosted",
    },
    "team": {
        # Higher volume tier on /plans ($799/mo).
        "verifications": 50_000,
        "scitt": True,
        "pdf": False,
        "api_keys": True,
        "api_key_limit": 50,
        "support": "Email 48h target",
        "label": "Team",
    },
    "enterprise": {
        "verifications": None,  # custom / negotiated
        "scitt": True,
        "pdf": False,
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
