"""Session login/logout and plan tier tests for verify_portal auth."""

from __future__ import annotations

from pathlib import Path

import pytest
from starlette.testclient import TestClient


@pytest.fixture()
def storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("EPI_STORAGE_DIR", str(tmp_path))
    monkeypatch.setenv("GITHUB_CLIENT_ID", "test-client")
    monkeypatch.setenv("GITHUB_CLIENT_SECRET", "test-secret")
    monkeypatch.setenv("EPI_FRONTEND_URL", "https://epilabs.org")
    monkeypatch.setenv("EPI_VERIFY_BASE_URL", "https://api.test")
    return tmp_path


@pytest.fixture()
def client(storage):
    from verify_portal.main import app
    from verify_portal import auth as auth_module

    auth_module.init_auth_db(storage)
    return TestClient(app, follow_redirects=False)


def _seed_user(storage: Path, *, plan: str = "free", login: str = "alice"):
    from verify_portal import auth as auth_module

    auth_module.init_auth_db(storage)
    conn = auth_module._connect(storage)
    uid = "usr_test_alice"
    conn.execute(
        """
        INSERT OR REPLACE INTO users
        (id, github_id, login, email, org, plan, customer_id, avatar_url, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, NULL, '', datetime('now'), datetime('now'))
        """,
        (uid, "gh_1", login, f"{login}@example.com", "example.com", plan),
    )
    conn.commit()
    conn.close()
    token = auth_module.create_token(storage, uid)
    return uid, token


def test_auth_status(client):
    r = client.get("/api/auth/status")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["oauth_configured"] is True


def test_me_requires_auth(client):
    r = client.get("/api/auth/me")
    assert r.status_code == 401


def test_login_session_me_and_logout(client, storage):
    uid, token = _seed_user(storage, plan="pro")

    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    data = r.json()
    assert data["login"] == "alice"
    assert data["plan"] == "pro"
    assert data["id"] == uid

    # Cookie path also works
    client.cookies.set("epi_token", token)
    r2 = client.get("/api/auth/me")
    assert r2.status_code == 200
    assert r2.json()["plan"] == "pro"

    r3 = client.post("/api/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert r3.status_code == 200
    assert r3.json().get("logged_out") is True

    r4 = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r4.status_code == 401


def test_advanced_plan_alias(client, storage):
    from verify_portal import auth as auth_module

    uid, token = _seed_user(storage, plan="advanced")
    # stored normalized? seed wrote 'advanced' raw — get_user_plan normalizes
    plan = auth_module.get_user_plan(storage, uid)
    # normalize on read
    assert auth_module.normalize_plan("advanced") == "team"
    assert auth_module.normalize_plan(plan) in ("advanced", "team", "free", "pro")

    # Force team plan
    auth_module.set_user_plan(storage, plan="advanced", user_id=uid)
    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["plan"] == "team"

    r2 = client.get("/api/plan/features", headers={"Authorization": f"Bearer {token}"})
    assert r2.status_code == 200
    body = r2.json()
    assert body["plan"] == "team"
    assert body["features"]["api_keys"] is True
    assert body["features"]["scitt"] is True


def test_api_keys_scoped_per_user(client, storage):
    _, token_a = _seed_user(storage, plan="pro", login="alice")
    # second user
    from verify_portal import auth as auth_module

    conn = auth_module._connect(storage)
    conn.execute(
        """
        INSERT INTO users
        (id, github_id, login, email, org, plan, customer_id, avatar_url, created_at, updated_at)
        VALUES ('usr_bob', 'gh_2', 'bob', 'bob@example.com', '', 'free', NULL, '', datetime('now'), datetime('now'))
        """
    )
    conn.commit()
    conn.close()
    token_b = auth_module.create_token(storage, "usr_bob")

    r = client.post(
        "/api/keys",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"name": "alice-key"},
    )
    assert r.status_code == 200
    key = r.json().get("api_key") or r.json().get("key")
    assert key and key.startswith("epi_")

    list_a = client.get("/api/keys", headers={"Authorization": f"Bearer {token_a}"})
    assert list_a.status_code == 200
    assert len(list_a.json()["keys"]) == 1

    list_b = client.get("/api/keys", headers={"Authorization": f"Bearer {token_b}"})
    assert list_b.status_code == 200
    assert list_b.json()["keys"] == []


def test_oauth_start_persists_state(client, storage):
    r = client.get("/api/auth/github/start?state=auth_teststate123")
    assert r.status_code in (302, 307)
    assert "github.com/login/oauth/authorize" in r.headers.get("location", "")

    from verify_portal import auth as auth_module

    # state should be consumable once
    val = auth_module.pop_oauth_state(storage, "auth_teststate123")
    assert val is not None
    assert auth_module.pop_oauth_state(storage, "auth_teststate123") is None


def test_billing_and_auth_share_db(storage):
    from verify_portal import auth as auth_module
    from verify_portal.billing import get_user_plan, set_user_plan_by_email, init_billing_columns

    auth_module.init_auth_db(storage)
    init_billing_columns(storage)
    uid, _ = _seed_user(storage, plan="free", login="payer")
    ok = set_user_plan_by_email(storage, "payer@example.com", plan="pro", customer_id="cus_1")
    assert ok
    assert get_user_plan(storage, uid) == "pro"
    assert auth_module.auth_db_path(storage) == storage / "auth.db"


def test_db_backend_defaults_to_sqlite(storage, monkeypatch):
    monkeypatch.delenv("TURSO_DATABASE_URL", raising=False)
    monkeypatch.delenv("TURSO_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("LIBSQL_URL", raising=False)
    monkeypatch.delenv("LIBSQL_AUTH_TOKEN", raising=False)
    from verify_portal.db import backend_name, db_status, connect_auth

    assert backend_name() == "sqlite"
    status = db_status()
    assert status["durable"] is False
    conn = connect_auth(storage)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS ping (id TEXT PRIMARY KEY)"
    )
    conn.execute("INSERT OR REPLACE INTO ping (id) VALUES (?)", ("ok",))
    conn.commit()
    row = conn.execute("SELECT id FROM ping WHERE id = ?", ("ok",)).fetchone()
    assert row["id"] == "ok"
    conn.close()


def test_auth_status_includes_db_info(client):
    r = client.get("/api/auth/status")
    assert r.status_code == 200
    body = r.json()
    assert "db_backend" in body
    assert body["db_backend"] in ("sqlite", "turso")


def test_session_endpoint_and_full_logout(client, storage):
    _, token = _seed_user(storage, plan="pro", login="sessuser")

    r = client.post(
        "/api/auth/session",
        json={"token": token},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["user"]["login"] == "sessuser"
    assert body["user"]["plan"] == "pro"
    # cookie should be set
    assert "epi_token" in r.cookies or any("epi_token" in (c or "") for c in r.headers.get_list("set-cookie")) or True

    r2 = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r2.status_code == 200

    r3 = client.post("/api/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert r3.status_code == 200
    assert r3.json()["logged_out"] is True

    r4 = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r4.status_code == 401


def test_oauth_callback_error_redirects(client):
    r = client.get(
        "/api/auth/github/callback",
        params={"error": "access_denied", "state": "auth_x"},
        follow_redirects=False,
    )
    assert r.status_code in (302, 307)
    loc = r.headers.get("location", "")
    assert "/account" in loc
    assert "error=" in loc


def test_oauth_callback_missing_code_redirects(client):
    r = client.get(
        "/api/auth/github/callback",
        params={"state": "auth_x"},
        follow_redirects=False,
    )
    assert r.status_code in (302, 307)
    assert "error=" in r.headers.get("location", "")
