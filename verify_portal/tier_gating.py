"""Tier-gating for paid plan features."""

from fastapi import HTTPException, Request


def get_plan(request: Request) -> str:
    token = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    if not token:
        token = request.cookies.get("epi_token", "")
    if not token:
        return "free"
    import os
    from pathlib import Path
    from verify_portal import auth as auth_module
    from verify_portal.billing import init_billing_columns, get_user_plan

    storage_dir = Path(os.environ.get("EPI_STORAGE_DIR", "./data"))
    user = auth_module.verify_token(storage_dir, token)
    if not user:
        return "free"
    init_billing_columns(storage_dir)
    return get_user_plan(storage_dir, user["id"])


def require_plan(min_plan: str):
    """Dependency: raises 402 if user plan is below min_plan.
    min_plan: 'free', 'pro', 'team', 'enterprise'
    Plan hierarchy: free < pro < team < enterprise
    """
    plan_rank = {"free": 0, "pro": 1, "team": 2, "enterprise": 3}

    async def check(request: Request):
        plan = get_plan(request)
        if plan_rank.get(plan, 0) < plan_rank.get(min_plan, 0):
            raise HTTPException(
                status_code=402,
                detail=f"This feature requires a {min_plan.capitalize()} plan or higher. "
                       f"Your current plan is {plan.capitalize()}. Upgrade at /pricing.",
            )
        return plan

    return check


def get_rate_limit(plan: str) -> int:
    """Return monthly API call limit based on plan."""
    limits = {
        "free": 100,
        "pro": 10000,
        "team": 50000,
        "enterprise": None,  # unlimited
    }
    return limits.get(plan, 0)
