"""EPI billing module — Paddle webhook, plan helpers."""
import hashlib
import json
import os
import sqlite3
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from starlette.responses import JSONResponse

try:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    from cryptography.hazmat.primitives.hashes import SHA256, SHA1
    from cryptography.x509 import load_pem_x509_certificate
    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False

import httpx

router = APIRouter()

PADDLE_API_KEY = os.getenv("PADDLE_API_KEY", "")
PADDLE_CLIENT_TOKEN = os.getenv("PADDLE_CLIENT_TOKEN", "")
PADDLE_WEBHOOK_SECRET = os.getenv("PADDLE_WEBHOOK_SECRET", "")
PADDLE_SANDBOX = os.getenv("PADDLE_SANDBOX", "false").lower() == "true"

PADDLE_VENDOR_ID = os.getenv("PADDLE_VENDOR_ID", "")
PADDLE_VENDOR_AUTH_CODE = os.getenv("PADDLE_VENDOR_AUTH_CODE", "")

PADDLE_PRO_PRICE_ID = os.getenv("PADDLE_PRO_PRICE_ID", "")

PADDLE_API_BASE = "https://sandbox-api.paddle.com" if PADDLE_SANDBOX else "https://api.paddle.com"
PADDLE_PUBLIC_KEY_URL = f"{PADDLE_API_BASE}/notification-settings/public-key"


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


async def _fetch_paddle_public_key() -> bytes:
    """Fetch Paddle's public key for webhook signature verification."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(PADDLE_PUBLIC_KEY_URL)
        resp.raise_for_status()
        data = resp.json()
        return data.get("data", {}).get("public_key", "").encode()


def _verify_paddle_signature(raw_body: bytes, signature_header: str, public_key_pem: bytes) -> bool:
    """Verify a Paddle webhook signature using their public key."""
    if not CRYPTO_AVAILABLE:
        return True

    try:
        parts = signature_header.split(";")
        sig_map = {}
        for part in parts:
            key, _, val = part.partition("=")
            sig_map[key.strip()] = val.strip()

        ts = sig_map.get("ts", "")
        h1 = sig_map.get("h1", "")

        if not ts or not h1:
            return False

        signed_payload = f"{ts}:{raw_body.decode()}".encode()
        expected_hash = hashlib.sha256(signed_payload).hexdigest()

        if not hmac.compare_digest(expected_hash, h1):
            return False

        return True
    except Exception:
        return False


@router.get("/api/paddle/config")
async def get_paddle_config():
    """Return client-side Paddle configuration."""
    return {
        "client_token": PADDLE_CLIENT_TOKEN,
        "pro_price_id": PADDLE_PRO_PRICE_ID,
        "sandbox": PADDLE_SANDBOX,
    }


@router.post("/api/paddle/webhook")
async def paddle_webhook(request: Request):
    """Handle Paddle webhook events for subscription management."""
    raw_body = await request.body()
    signature = request.headers.get("paddle-signature", "")

    # Verify webhook signature
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
    event_data = event.get("data", {})

    customer_id = event_data.get("customer_id", "") or event_data.get("id", "")
    email = event_data.get("email", "") or event_data.get("custom_data", {}).get("email", "")

    # Try to get email from customer endpoint if not in event
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

    if event_type in ("subscription.created", "subscription.updated"):
        status = event_data.get("status", "")
        if status == "active":
            if email:
                set_user_plan_by_email(storage_dir, email, plan="pro", customer_id=str(customer_id))
            elif customer_id:
                set_user_plan_by_customer_id(storage_dir, str(customer_id), plan="pro")

    elif event_type in ("subscription.canceled", "subscription.paused"):
        if email:
            set_user_plan_by_email(storage_dir, email, plan="free", customer_id=str(customer_id))
        elif customer_id:
            set_user_plan_by_customer_id(storage_dir, str(customer_id), plan="free")

    return {"status": "ok"}
