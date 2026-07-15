"""EPI billing module — Paddle webhook handler, plan helpers."""
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

router = APIRouter()

PADDLE_API_KEY = os.getenv("PADDLE_API_KEY", "")
PADDLE_WEBHOOK_SECRET = os.getenv("PADDLE_WEBHOOK_SECRET", "")

# ── Database ────────────────────────────────────────────────────────

def _billing_db_path(storage_dir) -> Path:
    db_dir = Path(storage_dir) / "data"
    db_dir.mkdir(parents=True, exist_ok=True)
    return db_dir / "auth.db"


def init_billing_columns(storage_dir: str) -> None:
    db = _billing_db_path(storage_dir)
    conn = sqlite3.connect(str(db))
    try:
        conn.execute("ALTER TABLE users ADD COLUMN plan TEXT DEFAULT 'free'")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE users ADD COLUMN customer_id TEXT")
    except sqlite3.OperationalError:
        pass
    conn.commit()
    conn.close()


# ── Plan helpers ─────────────────────────────────────────────────────

def get_user_plan(storage_dir: str, user_id: str) -> str:
    db = _billing_db_path(storage_dir)
    conn = sqlite3.connect(str(db))
    row = conn.execute("SELECT plan FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    return row[0] if row else "free"


def set_user_plan_by_customer_id(storage_dir: str, customer_id: str, plan: str) -> None:
    db = _billing_db_path(storage_dir)
    conn = sqlite3.connect(str(db))
    conn.execute(
        "UPDATE users SET plan = ? WHERE customer_id = ?",
        (plan, customer_id),
    )
    conn.commit()
    conn.close()


def set_user_plan_by_email(storage_dir: str, email: str, plan: str) -> None:
    db = _billing_db_path(storage_dir)
    conn = sqlite3.connect(str(db))
    conn.execute(
        "UPDATE users SET plan = ? WHERE email = ?",
        (plan, email),
    )
    conn.commit()
    conn.close()


# ── API key plan helpers ─────────────────────────────────────────────

_PRO_MONTHLY_LIMIT = 10_000
_ENTERPRISE_MONTHLY_LIMIT = 100_000


def get_plan_rate_limit(plan: str) -> int | None:
    if plan == "pro" or plan == "starter":
        return _PRO_MONTHLY_LIMIT
    if plan == "advanced":
        return _ENTERPRISE_MONTHLY_LIMIT
    return None


# ── Paddle Webhook ───────────────────────────────────────────────────

def _verify_paddle_signature(request: Request, body: bytes) -> bool:
    if not PADDLE_WEBHOOK_SECRET:
        return True
    received = request.headers.get("paddle-signature", "")
    expected = hmac.new(
        PADDLE_WEBHOOK_SECRET.encode(),
        body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(received, expected)


@router.post("/api/paddle/webhook")
async def paddle_webhook(request: Request) -> dict:
    body = await request.body()

    if not _verify_paddle_signature(request, body):
        raise HTTPException(status_code=401, detail="Invalid signature")

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    event_type = payload.get("event_type", "")
    data = payload.get("data", {})

    storage_dir = os.getenv("STORAGE_DIR", "./evidence_vault")
    init_billing_columns(storage_dir)

    if event_type == "subscription.activated":
        customer_id = data.get("customer_id", "")
        items = data.get("items", [])
        plan = "starter"
        for item in items:
            price = item.get("price", {})
            pid = price.get("id", "")
            if "pro" in pid:
                plan = "pro"
            elif "advanced" in pid or "enterprise" in pid:
                plan = "advanced"
        if customer_id:
            set_user_plan_by_customer_id(storage_dir, customer_id, plan)

    elif event_type == "subscription.updated":
        customer_id = data.get("customer_id", "")
        status = data.get("status", "")
        if status == "canceled":
            set_user_plan_by_customer_id(storage_dir, customer_id, "free")

    elif event_type == "subscription.canceled":
        customer_id = data.get("customer_id", "")
        if customer_id:
            set_user_plan_by_customer_id(storage_dir, customer_id, "free")

    return {"status": "ok"}


# ── Price lookup endpoint (server-side, no API key exposure) ─────────

@router.get("/api/paddle/prices")
async def paddle_prices(request: Request) -> dict:
    env = os.getenv("PADDLE_ENV", "live")
    if not env:
        raise HTTPException(status_code=500, detail="PADDLE_ENV not configured")

    price_ids = {
        "starter": {
            "month": os.getenv("PADDLE_PRICE_STARTER_MONTH", ""),
            "year": os.getenv("PADDLE_PRICE_STARTER_YEAR", ""),
        },
        "pro": {
            "month": os.getenv("PADDLE_PRICE_PRO_MONTH", ""),
            "year": os.getenv("PADDLE_PRICE_PRO_YEAR", ""),
        },
        "advanced": {
            "month": os.getenv("PADDLE_PRICE_ADVANCED_MONTH", ""),
            "year": os.getenv("PADDLE_PRICE_ADVANCED_YEAR", ""),
        },
    }

    return {
        "price_ids": price_ids,
        "client_token": os.getenv("PADDLE_CLIENT_TOKEN", ""),
        "env": env,
    }


@router.get("/api/paddle/config")
async def paddle_config() -> dict:
    return {
        "client_token": os.getenv("PADDLE_CLIENT_TOKEN", ""),
        "env": os.getenv("PADDLE_ENV", "live"),
    }
