"""Paddle Billing webhook HMAC + plan mapping."""

from __future__ import annotations

import hashlib
import hmac
import json

from verify_portal.billing import (
    _plan_from_price_id,
    verify_paddle_signature,
)


def _sign(ts: str, body: bytes, secret: str) -> str:
    payload = f"{ts}:{body.decode('utf-8')}".encode("utf-8")
    h1 = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    return f"ts={ts};h1={h1}"


def test_verify_paddle_signature_accepts_valid_hmac():
    body = json.dumps({"event_type": "subscription.activated"}).encode()
    secret = "test_webhook_secret"
    header = _sign("1710000000", body, secret)
    assert verify_paddle_signature(body, header, secret) is True


def test_verify_paddle_signature_rejects_wrong_secret():
    body = b'{"event_type":"x"}'
    header = _sign("1710000000", body, "good")
    assert verify_paddle_signature(body, header, "bad") is False


def test_verify_paddle_signature_rejects_plain_sha256_mistake():
    """Regression: old code used sha256(ts:body) without HMAC key."""
    body = b'{"event_type":"x"}'
    ts = "1710000000"
    plain = hashlib.sha256(f"{ts}:{body.decode()}".encode()).hexdigest()
    header = f"ts={ts};h1={plain}"
    assert verify_paddle_signature(body, header, "secret") is False


def test_plan_from_price_id_defaults_hosted():
    import pytest as _pytest
    # Empty env-not-configured keeps hosted for backward compat; unknown non-empty must fail loudly (P2 fix)
    assert _plan_from_price_id("") == "hosted"
    with _pytest.raises(ValueError):
        _plan_from_price_id("pri_something_pro_month")
