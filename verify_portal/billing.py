"""EPI billing module — Lemon Squeezy webhook, plan helpers."""
import hashlib
import hmac
import json
import os
import sqlite3
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from starlette.responses import JSONResponse

router = APIRouter()

LEMONSQUEEZY_WEBHOOK_SECRET = os.getenv("LEMONSQUEEZY_WEBHOOK_SECRET", "")


def _billing_db_path(storage_dir):
    db_dir = Path(storage_dir) / "data"
    db_dir.mkdir(parents=True, exist_ok=True)
    return db_dir / "auth.db"


def init_billing_columns(storage_dir):
    db = _billing_db_path(storage_dir)
    c = sqlite3.connect(str(db))
    try:
        c.execute("ALTER TABLE users ADD COLUMN plan TEXT DEFAULT 'free'")
    except sqlite3.OperationalError:
        pass
    try:
        c.execute("ALTER TABLE users ADD COLUMN customer_id TEXT")
    except sqlite3.OperationalError:
        pass
    c.commit()
    c.close()


def get_user_plan(storage_dir, user_id):
    db = _billing_db_path(storage_dir)
    c = sqlite3.connect(str(db))
    c.row_factory = sqlite3.Row
    r = c.execute("SELECT plan FROM users WHERE id = ?", (user_id,)).fetchone()
    c.close()
    return r["plan"] if r else "free"


def set_user_plan_by_email(storage_dir, email, *, plan, customer_id=None):
    if not email:
        return False
    db = _billing_db_path(storage_dir)
    c = sqlite3.connect(str(db))
    c.execute(
        "UPDATE users SET plan = ?, customer_id = COALESCE(?, customer_id) WHERE email = ?",
        (plan, customer_id, email),
    )
    ok = c.total_changes > 0
    c.commit()
    c.close()
    return ok


def set_user_plan_by_customer_id(storage_dir, cid, *, plan):
    db = _billing_db_path(storage_dir)
    c = sqlite3.connect(str(db))
    c.execute(
        "UPDATE users SET plan = ? WHERE customer_id = ?",
        (plan, cid),
    )
    ok = c.total_changes > 0
    c.commit()
    c.close()
    return ok


@router.get("/api/stripe/payment-link")
async def get_payment_link():
    url = os.getenv("STRIPE_PAYMENT_LINK", "")
    return {"url": url}


@router.post("/api/lemonsqueezy/webhook")
async def lemonsqueezy_webhook(request: Request):
    raw_body = await request.body()
    signature = request.headers.get("x-signature", "")
    digest = hmac.new(
        LEMONSQUEEZY_WEBHOOK_SECRET.encode(), raw_body, hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(digest, signature):
        raise HTTPException(status_code=401, detail="Invalid signature")

    event = json.loads(raw_body)
    event_name = request.headers.get("x-event-name", "")
    attrs = event.get("data", {}).get("attributes", {})
    email = attrs.get("user_email")
    customer_id = str(attrs.get("customer_id", ""))

    storage_dir = os.getenv("EPI_STORAGE_DIR", "./data")
    init_billing_columns(storage_dir)

    if event_name in ("subscription_created", "subscription_updated") and attrs.get(
        "status"
    ) == "active":
        if email:
            set_user_plan_by_email(
                storage_dir, email, plan="pro", customer_id=customer_id
            )

    elif event_name in ("subscription_cancelled", "subscription_expired"):
        if customer_id:
            set_user_plan_by_customer_id(storage_dir, customer_id, plan="free")

    return {"status": "ok"}
