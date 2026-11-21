"""The legacy Render portal must never change a plan from a Paddle event.

Billing runs on EPI Cloud. If a Paddle notification destination still points at
the old portal, the event must be refused (410) and change nothing.
"""

from __future__ import annotations

import json

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from verify_portal import billing  # noqa: E402


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(billing.router)
    return TestClient(app)


def test_legacy_paddle_webhook_is_gone_and_changes_nothing(tmp_path, monkeypatch):
    monkeypatch.setenv("EPI_STORAGE_DIR", str(tmp_path))
    called = []
    monkeypatch.setattr(billing, "set_user_plan", lambda *a, **k: called.append((a, k)))
    event = {
        "event_type": "subscription.created",
        "data": {"status": "active", "customer_id": "ctm_1", "custom_data": {"email": "a@example.com"}},
    }
    res = _client().post("/api/paddle/webhook", content=json.dumps(event), headers={"Paddle-Signature": "ts=1;h1=x"})
    assert res.status_code == 410
    assert res.json() == billing.BILLING_MOVED
    assert called == []


def test_legacy_checkout_config_is_gone():
    res = _client().get("/api/paddle/config")
    assert res.status_code == 410
    assert res.json() == billing.BILLING_MOVED


def test_the_message_names_where_billing_went():
    assert billing.BILLING_MOVED["detail"].endswith("This endpoint changes nothing.")


def test_module_holds_no_paddle_secrets_or_prices():
    source = open(billing.__file__, encoding="utf-8").read()
    for marker in ("PADDLE_API_KEY", "PADDLE_WEBHOOK_SECRET", "pri_0"):
        assert marker not in source
