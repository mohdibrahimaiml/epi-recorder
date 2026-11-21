"""Legacy portal plan helpers. Billing itself has moved to EPI Cloud.

Paddle checkout, the customer portal and the Paddle webhook all run on EPI
Cloud (cloud.epilabs.org / api.epilabs.org). This legacy portal no longer
accepts Paddle events or hands out checkout configuration: both routes answer
410 Gone and change nothing, so a stale Paddle notification destination that
still points here can never change a plan behind the real billing system's back.

The helpers below remain because the legacy portal still reads the plan column
on its own users (see verify_portal.auth). Sunset: 2027-02-01.
"""
from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from verify_portal.auth import (
    get_user_plan as auth_get_user_plan,
    init_auth_db,
    set_user_plan,
)

router = APIRouter()

BILLING_MOVED = {
    "error": "gone",
    "detail": (
        "Billing moved to EPI Cloud. Plans are bought and managed at "
        "https://cloud.epilabs.org; Paddle events go to "
        "https://api.epilabs.org/billing/paddle/webhook. This endpoint changes nothing."
    ),
}


def init_billing_columns(storage_dir):
    """Ensure auth.db exists with plan columns (delegates to auth)."""
    init_auth_db(storage_dir)


def get_user_plan(storage_dir, user_id):
    return auth_get_user_plan(storage_dir, user_id)


def set_user_plan_by_email(storage_dir, email, *, plan, customer_id=None):
    return set_user_plan(storage_dir, plan=plan, email=email, customer_id=customer_id)


def set_user_plan_by_customer_id(storage_dir, cid, *, plan):
    return set_user_plan(storage_dir, plan=plan, customer_id=cid)


@router.get("/api/paddle/config")
async def get_paddle_config():
    """Retired: checkout runs on EPI Cloud."""
    return JSONResponse(status_code=410, content=BILLING_MOVED)


@router.post("/api/paddle/webhook")
async def paddle_webhook():
    """Retired: Paddle events go to EPI Cloud. Never changes a plan here."""
    return JSONResponse(status_code=410, content=BILLING_MOVED)
