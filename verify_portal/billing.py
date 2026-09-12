"""EPI billing module — Paddle webhook, plan helpers.

Plans live in the same auth.db as users (see verify_portal.auth) so Starter / Pro
/ Advanced / Enterprise upgrades apply to the logged-in GitHub identity.
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

PADDLE_ENV = os.getenv("PADDLE_ENV", "sandbox").lower()
if PADDLE_ENV not in ("sandbox", "live", "production"):
    raise RuntimeError(f"PADDLE_ENV must be sandbox or live, got: {PADDLE_ENV}")

PADDLE_HOSTED_PRICE_ID_MONTHLY = os.getenv("PADDLE_HOSTED_PRICE_ID_MONTHLY", "pri_01m0y54ba4vpjaczkkn56hpc9m")
PADDLE_HOSTED_PRICE_ID_YEARLY = os.getenv("PADDLE_HOSTED_PRICE_ID_YEARLY", "pri_01m0y54bn0pqwrvvyqhf1qq1ge")
PADDLE_STARTER_PRICE_ID_MONTHLY = os.getenv("PADDLE_STARTER_PRICE_ID_MONTHLY", "pri_01m0y54ba4vpjaczkkn56hpc9m")
PADDLE_STARTER_PRICE_ID_YEARLY = os.getenv("PADDLE_STARTER_PRICE_ID_YEARLY", "pri_01m0y54bn0pqwrvvyqhf1qq1ge")
PADDLE_PRO_PRICE_ID = os.getenv("PADDLE_PRO_PRICE_ID", "pri_01m0y54canxd7z63ykf928qs04")
PADDLE_PRO_PRICE_ID_YEARLY = os.getenv("PADDLE_PRO_PRICE_ID_YEARLY", "pri_01m0y54ckbm8vj32dsms9xfeev")
PADDLE_ADVANCED_PRICE_ID = os.getenv("PADDLE_ADVANCED_PRICE_ID", "pri_01m0y54d6t0q3ehgqmmepg45vj")
PADDLE_ADVANCED_PRICE_ID_YEARLY = os.getenv("PADDLE_ADVANCED_PRICE_ID_YEARLY", "pri_01m0y54df4smpc7qq4p21j4v9s")
PADDLE_TEAM_PRICE_ID = os.getenv("PADDLE_TEAM_PRICE_ID", "") or PADDLE_ADVANCED_PRICE_ID
PADDLE_ENTERPRISE_PRICE_ID = os.getenv("PADDLE_ENTERPRISE_PRICE_ID", "")
PADDLE_SPRINT_PRICE_ID = os.getenv("PADDLE_SPRINT_PRICE_ID", "pri_01m0y5tp4geerk93exrs4fkpgp")

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
    """Map a Paddle price ID to an internal plan name.

    Internal plan hierarchy (see auth.PLAN_ALIASES + auth.VALID_PLANS):
        free < hosted (= starter, pro) < team (= advanced) < enterprise

    Checked in order from most-specific to least-specific so that every
    price ID served by the live /plans page maps to the right tier.

    Empty or unknown price IDs raise ValueError (never a default plan):
    the webhook route turns that into a non-2xx response, which Paddle
    retries and which can be replayed from the dashboard.
    """
    if not price_id:
        raise ValueError("Empty Paddle price_id: refusing to map to a plan — check PADDLE_*_PRICE_ID env")

    # ── Enterprise ───────────────────────────────────────────────────────────
    if PADDLE_ENTERPRISE_PRICE_ID and price_id == PADDLE_ENTERPRISE_PRICE_ID:
        return "enterprise"

    # ── Advanced / Team (monthly + yearly) ───────────────────────────────────
    _advanced_ids = {
        id_ for id_ in (
            PADDLE_ADVANCED_PRICE_ID,
            PADDLE_ADVANCED_PRICE_ID_YEARLY,
            PADDLE_TEAM_PRICE_ID,
        ) if id_
    }
    if _advanced_ids and price_id in _advanced_ids:
        return "team"

    # ── Pro (monthly + yearly) → hosted ──────────────────────────────────────
    _pro_ids = {id_ for id_ in (PADDLE_PRO_PRICE_ID, PADDLE_PRO_PRICE_ID_YEARLY) if id_}
    if _pro_ids and price_id in _pro_ids:
        return "hosted"  # normalize_plan maps pro → hosted

    # ── Starter (monthly + yearly) → hosted ──────────────────────────────────
    _starter_ids = {
        id_ for id_ in (
            PADDLE_STARTER_PRICE_ID_MONTHLY,
            PADDLE_STARTER_PRICE_ID_YEARLY,
            PADDLE_HOSTED_PRICE_ID_MONTHLY,
            PADDLE_HOSTED_PRICE_ID_YEARLY,
        ) if id_
    }
    if _starter_ids and price_id in _starter_ids:
        return "hosted"

    # ── Sprint is a one-time charge — subscription webhooks won't fire for it,
    #    but guard it just in case. ────────────────────────────────────────────
    if PADDLE_SPRINT_PRICE_ID and price_id == PADDLE_SPRINT_PRICE_ID:
        return "hosted"

    # ── Fallback: unknown price must fail loudly, not silently map to hosted.
    # Raising yields a non-2xx response, which Paddle retries (60 attempts over
    # ~3 days on live accounts) and which can be replayed from the dashboard;
    # nothing real is ever silently dropped. Callers must let this propagate
    # instead of catching it into a default plan.
    raise ValueError(f"Unknown Paddle price_id: {price_id} — add to PADDLE_*_PRICE_ID env")


def _extract_price_id(event_data: dict) -> str:
    items = event_data.get("items") or []
    if items and isinstance(items[0], dict):
        price = items[0].get("price") or {}
        if isinstance(price, dict):
            return str(price.get("id") or "")
        return str(items[0].get("price_id") or "")
    return str(event_data.get("price_id") or "")


def verify_paddle_signature(raw_body: bytes, signature_header: str, secret: str) -> bool:
    """Paddle Billing: HMAC-SHA256 of ``ts:rawBody`` compared to ``h1``."""
    if not secret or not signature_header:
        return False
    sig_map: dict[str, str] = {}
    for part in signature_header.split(";"):
        key, _, val = part.partition("=")
        if key.strip():
            sig_map[key.strip()] = val.strip()
    ts = sig_map.get("ts", "")
    h1 = sig_map.get("h1", "")
    if not ts or not h1:
        return False
    try:
        body_text = raw_body.decode("utf-8")
    except UnicodeDecodeError:
        body_text = raw_body.decode("utf-8", errors="replace")
    signed_payload = f"{ts}:{body_text}".encode("utf-8")
    computed = hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(computed, h1)


def _apply_plan_from_webhook(
    storage_dir,
    *,
    plan: str,
    custom: dict,
    email: str,
    customer_id: str,
) -> bool:
    """Prefer GitHub user_id from checkout custom_data, then email, then customer_id."""
    plan = normalize_plan(plan)
    cid = str(customer_id) if customer_id else None
    user_id = str(custom.get("user_id") or custom.get("epi_user_id") or "").strip() or None
    if user_id:
        if set_user_plan(storage_dir, plan=plan, user_id=user_id, customer_id=cid):
            return True
    if email:
        if set_user_plan_by_email(storage_dir, email, plan=plan, customer_id=cid):
            return True
    if cid:
        if set_user_plan_by_customer_id(storage_dir, cid, plan=plan):
            return True
    return False


@router.get("/api/paddle/config")
async def get_paddle_config(request: Request):
    """Return client-side Paddle configuration."""
    country = request.headers.get("cf-ipcountry") or request.headers.get("x-vercel-ip-country")
    return {
        "client_token": PADDLE_CLIENT_TOKEN,
        "environment": "sandbox" if PADDLE_SANDBOX else "production",
        "country": country,
        "tiers": {
            "starter": {
                "month": PADDLE_STARTER_PRICE_ID_MONTHLY,
                "year": PADDLE_STARTER_PRICE_ID_YEARLY,
            },
            "hosted": {
                "month": PADDLE_HOSTED_PRICE_ID_MONTHLY,
                "year": PADDLE_HOSTED_PRICE_ID_YEARLY,
            },
            "pro": {
                "month": PADDLE_PRO_PRICE_ID,
                "year": PADDLE_PRO_PRICE_ID_YEARLY,
            },
            "advanced": {
                "month": PADDLE_ADVANCED_PRICE_ID,
                "year": PADDLE_ADVANCED_PRICE_ID_YEARLY,
            },
            "team": {
                "month": PADDLE_TEAM_PRICE_ID,
                "year": PADDLE_ADVANCED_PRICE_ID_YEARLY,
            },
        },
        "sprint_price_id": PADDLE_SPRINT_PRICE_ID,
        "enterprise_price_id": PADDLE_ENTERPRISE_PRICE_ID,
        "require_sign_in": True,
    }


@router.post("/api/paddle/webhook")
async def paddle_webhook(request: Request):
    """Handle Paddle webhook events for subscription management."""
    raw_body = await request.body()
    signature = request.headers.get("paddle-signature", "")

    if not PADDLE_WEBHOOK_SECRET:
        import logging as _logging

        _logging.getLogger("uvicorn.error").error(
            "PADDLE_WEBHOOK_SECRET is not configured — rejecting webhook. "
            "Set PADDLE_WEBHOOK_SECRET and PADDLE_ENV correctly; no unverified webhook will be processed."
        )
        raise HTTPException(status_code=500, detail="Webhook secret not configured")

    if not signature or not verify_paddle_signature(raw_body, signature, PADDLE_WEBHOOK_SECRET):
        raise HTTPException(status_code=401, detail="Invalid Paddle webhook signature")

    event = json.loads(raw_body)
    event_type = event.get("event_type", "")
    event_data = event.get("data", {}) or {}

    customer_id = str(event_data.get("customer_id", "") or "")
    custom = event_data.get("custom_data") or {}
    if not isinstance(custom, dict):
        custom = {}
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

    applied = False
    if event_type in ("subscription.created", "subscription.updated", "subscription.activated"):
        status = (event_data.get("status") or "").lower()
        if status in ("active", "trialing"):
            plan = normalize_plan(_plan_from_price_id(_extract_price_id(event_data)))
            applied = _apply_plan_from_webhook(
                storage_dir,
                plan=plan,
                custom=custom,
                email=str(email or ""),
                customer_id=customer_id,
            )

    elif event_type in ("subscription.canceled", "subscription.paused", "subscription.past_due"):
        applied = _apply_plan_from_webhook(
            storage_dir,
            plan="free",
            custom=custom,
            email=str(email or ""),
            customer_id=customer_id,
        )

    return {
        "status": "ok",
        "applied": applied,
        "event_type": event_type,
        "db": str(auth_db_path(storage_dir)),
    }
