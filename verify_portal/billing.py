"""EPI billing module — Paddle webhook, plan helpers.

Plans live in the same auth.db as users (see verify_portal.auth) so Pro / Team
(Advanced) / Enterprise upgrades apply to the logged-in GitHub identity.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

try:
    from cryptography.hazmat.primitives import serialization  # noqa: F401
    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False

import httpx

from verify_portal.auth import (
    auth_db_path,
    get_user_plan as auth_get_user_plan,
    init_auth_db,
    normalize_plan,
    set_user_plan,
)

router = APIRouter()

PADDLE_API_KEY = os.getenv("PADDLE_API_KEY", "")
PADDLE_CLIENT_TOKEN = os.getenv("PADDLE_CLIENT_TOKEN", "")
PADDLE_WEBHOOK_SECRET = os.getenv("PADDLE_WEBHOOK_SECRET", "")
PADDLE_SANDBOX = os.getenv("PADDLE_SANDBOX", "false").lower() == "true"

PADDLE_VENDOR_ID = os.getenv("PADDLE_VENDOR_ID", "")
PADDLE_VENDOR_AUTH_CODE = os.getenv("PADDLE_VENDOR_AUTH_CODE", "")

PADDLE_PRO_PRICE_ID = os.getenv("PADDLE_PRO_PRICE_ID", "")
PADDLE_TEAM_PRICE_ID = os.getenv("PADDLE_TEAM_PRICE_ID", "") or os.getenv("PADDLE_ADVANCED_PRICE_ID", "")
PADDLE_ENTERPRISE_PRICE_ID = os.getenv("PADDLE_ENTERPRISE_PRICE_ID", "")

PADDLE_API_BASE = "https://sandbox-api.paddle.com" if PADDLE_SANDBOX else "https://api.paddle.com"


def init_billing_columns(storage_dir):
    """Ensure auth.db exists with plan columns (delegates to auth)."""
    init_auth_db(storage_dir)


def get_user_plan(storage_dir, user_id):
    return auth_get_user_plan(storage_dir, user_id)


def set_user_plan_by_email(storage_dir, email, *, plan, customer_id=None):
    return set_user_plan(storage_dir, plan=plan, email=email, customer_id=customer_id)


def set_user_plan_by_customer_id(storage_dir, cid, *, plan):
    return set_user_plan(storage_dir, plan=plan, customer_id=cid)


def _plan_from_price_id(price_id: str) -> str:
    if not price_id:
        return "pro"
    if PADDLE_ENTERPRISE_PRICE_ID and price_id == PADDLE_ENTERPRISE_PRICE_ID:
        return "enterprise"
    if PADDLE_TEAM_PRICE_ID and price_id == PADDLE_TEAM_PRICE_ID:
        return "team"
    if PADDLE_PRO_PRICE_ID and price_id == PADDLE_PRO_PRICE_ID:
        return "pro"
    # Fallback: name heuristics
    low = price_id.lower()
    if "enterprise" in low:
        return "enterprise"
    if "team" in low or "advanced" in low:
        return "team"
    return "pro"


def _extract_price_id(event_data: dict) -> str:
    items = event_data.get("items") or []
    if items and isinstance(items[0], dict):
        price = items[0].get("price") or {}
        if isinstance(price, dict):
            return str(price.get("id") or "")
        return str(items[0].get("price_id") or "")
    return str(event_data.get("price_id") or "")


@router.get("/api/paddle/config")
async def get_paddle_config():
    """Return client-side Paddle configuration."""
    return {
        "client_token": PADDLE_CLIENT_TOKEN,
        "pro_price_id": PADDLE_PRO_PRICE_ID,
        "team_price_id": PADDLE_TEAM_PRICE_ID,
        "advanced_price_id": PADDLE_TEAM_PRICE_ID,
        "enterprise_price_id": PADDLE_ENTERPRISE_PRICE_ID,
        "sandbox": PADDLE_SANDBOX,
    }


@router.post("/api/paddle/webhook")
async def paddle_webhook(request: Request):
    """Handle Paddle webhook events for subscription management."""
    raw_body = await request.body()
    signature = request.headers.get("paddle-signature", "")

    if PADDLE_WEBHOOK_SECRET and signature:
        try:
            parts = signature.split(";")
            sig_map = {}
            for part in parts:
                key, _, val = part.partition("=")
                sig_map[key.strip()] = val.strip()

            ts = sig_map.get("ts", "")
            h1 = sig_map.get("h1", "")
            signed_payload = f"{ts}:{raw_body.decode()}".encode()
            computed = hashlib.sha256(signed_payload).hexdigest()
            if not hmac.compare_digest(computed, h1):
                raise HTTPException(status_code=401, detail="Invalid signature")
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(status_code=401, detail="Invalid signature")

    event = json.loads(raw_body)
    event_type = event.get("event_type", "")
    event_data = event.get("data", {}) or {}

    customer_id = event_data.get("customer_id", "") or event_data.get("id", "")
    custom = event_data.get("custom_data") or {}
    email = (
        event_data.get("email", "")
        or custom.get("email", "")
        or (event_data.get("customer") or {}).get("email", "")
    )

    if not email and customer_id and PADDLE_API_KEY:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{PADDLE_API_BASE}/customers/{customer_id}",
                    headers={"Authorization": f"Bearer {PADDLE_API_KEY}"},
                )
                if resp.status_code == 200:
                    cust_data = resp.json().get("data", {})
                    email = cust_data.get("email", "")
        except Exception:
            pass

    storage_dir = os.getenv("EPI_STORAGE_DIR", "./data")
    init_billing_columns(storage_dir)

    if event_type in ("subscription.created", "subscription.updated", "subscription.activated"):
        status = (event_data.get("status") or "").lower()
        if status in ("active", "trialing"):
            plan = normalize_plan(_plan_from_price_id(_extract_price_id(event_data)))
            if email:
                set_user_plan_by_email(storage_dir, email, plan=plan, customer_id=str(customer_id) if customer_id else None)
            elif customer_id:
                set_user_plan_by_customer_id(storage_dir, str(customer_id), plan=plan)

    elif event_type in ("subscription.canceled", "subscription.paused", "subscription.past_due"):
        if email:
            set_user_plan_by_email(storage_dir, email, plan="free", customer_id=str(customer_id) if customer_id else None)
        elif customer_id:
            set_user_plan_by_customer_id(storage_dir, str(customer_id), plan="free")

    return {"status": "ok", "db": str(auth_db_path(storage_dir))}
