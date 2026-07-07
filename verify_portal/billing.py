"""EPI billing module — Stripe webhook, plan helpers."""
import os
import sqlite3
from pathlib import Path

import stripe
from fastapi import APIRouter, HTTPException, Request

router = APIRouter()

stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")


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
        c.execute("ALTER TABLE users ADD COLUMN stripe_customer_id TEXT")
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


def set_user_plan_by_email(storage_dir, email, *, plan, cid=None):
    if not email:
        return False
    db = _billing_db_path(storage_dir)
    c = sqlite3.connect(str(db))
    c.execute(
        "UPDATE users SET plan = ?, stripe_customer_id = COALESCE(?, stripe_customer_id) WHERE email = ?",
        (plan, cid, email),
    )
    ok = c.total_changes > 0
    c.commit()
    c.close()
    return ok


def set_user_plan_by_stripe_customer(storage_dir, cid, *, plan):
    db = _billing_db_path(storage_dir)
    c = sqlite3.connect(str(db))
    c.execute(
        "UPDATE users SET plan = ? WHERE stripe_customer_id = ?",
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


@router.post("/api/stripe/webhook")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")
    try:
        event = stripe.Webhook.construct_event(payload, sig, STRIPE_WEBHOOK_SECRET)
    except (ValueError, stripe.error.SignatureVerificationError):
        raise HTTPException(status_code=400, detail="Invalid signature")

    storage_dir = os.getenv("EPI_STORAGE_DIR", "./data")
    init_billing_columns(storage_dir)

    event_type = event["type"]
    data = event["data"]["object"]

    if event_type == "checkout.session.completed":
        email = (data.get("customer_details") or {}).get("email")
        customer_id = data.get("customer")
        if email:
            set_user_plan_by_email(storage_dir, email, plan="pro", cid=customer_id)

    elif event_type == "customer.subscription.deleted":
        customer_id = data.get("customer")
        if customer_id:
            set_user_plan_by_stripe_customer(storage_dir, customer_id, plan="free")

    return {"status": "ok"}
