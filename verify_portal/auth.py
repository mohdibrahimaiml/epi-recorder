"""Authentication for the EPI Verify Portal.

GitHub OAuth for browser + CLI. Issues bearer tokens stored in a durable SQLite
DB (same DB as billing plans) so Free / Pro / Team (Advanced) / Enterprise users
share one identity source of truth.
"""

from __future__ import annotations

import base64
import json
import os
import secrets
import sqlite3
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import httpx
from fastapi import HTTPException, Request
from fastapi.responses import RedirectResponse, JSONResponse, Response

from verify_portal.db import auth_db_path as _auth_db_path
from verify_portal.db import backend_name, connect_auth, db_status, turso_configured


GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_USER_URL = "https://api.github.com/user"
GITHUB_EMAILS_URL = "https://api.github.com/user/emails"

COOKIE_NAME = "epi_token"
_TOKEN_BYTES = 32
_TOKEN_TTL_DAYS = 90
_OAUTH_STATE_TTL_MINUTES = 15

# Plan hierarchy used across auth, billing, and tier gating.
PLAN_ALIASES = {
    "advanced": "team",
    "advance": "team",
    "business": "team",
}
VALID_PLANS = frozenset({"free", "pro", "team", "enterprise"})


def _client_id() -> str:
    return os.getenv("GITHUB_CLIENT_ID", "").strip()


def _client_secret() -> str:
    return os.getenv("GITHUB_CLIENT_SECRET", "").strip()


def _base_url() -> str:
    return os.getenv("EPI_VERIFY_BASE_URL", "https://epi-verify-portal.onrender.com").rstrip("/")


def _frontend_url() -> str:
    return os.getenv("EPI_FRONTEND_URL", "https://epilabs.org").rstrip("/")


def auth_db_path(storage_dir: Path | str) -> Path:
    """Local path for auth.db (used when Turso is not configured)."""
    return _auth_db_path(storage_dir)


def normalize_plan(plan: str | None) -> str:
    raw = (plan or "free").strip().lower()
    raw = PLAN_ALIASES.get(raw, raw)
    return raw if raw in VALID_PLANS else "free"


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _now_iso() -> str:
    return _utc_now().isoformat()


def _connect(storage_dir: Path | str):
    """Open auth DB: Turso free remote if configured, else local SQLite."""
    return connect_auth(storage_dir)


def _rowcount(cur) -> int:
    return int(getattr(cur, "rowcount", 0) or 0)


def init_auth_db(storage_dir: Path | str) -> None:
    """Create/migrate auth tables. Safe to call on every startup."""
    conn = _connect(storage_dir)
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            github_id TEXT UNIQUE,
            login TEXT,
            email TEXT,
            org TEXT,
            plan TEXT DEFAULT 'free',
            customer_id TEXT,
            avatar_url TEXT,
            created_at TEXT,
            updated_at TEXT
        );
        CREATE TABLE IF NOT EXISTS tokens (
            token TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            created_at TEXT,
            expires_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_tokens_user ON tokens(user_id);
        CREATE TABLE IF NOT EXISTS oauth_states (
            state TEXT PRIMARY KEY,
            redirect_uri TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    # Migrations for older schemas
    for ddl in (
        "ALTER TABLE users ADD COLUMN plan TEXT DEFAULT 'free'",
        "ALTER TABLE users ADD COLUMN customer_id TEXT",
        "ALTER TABLE users ADD COLUMN avatar_url TEXT",
    ):
        try:
            conn.execute(ddl)
            conn.commit()
        except Exception:
            pass

    # One-time import from legacy users.db if present and auth.db has no users
    # (local SQLite only — skip when Turso is the backend)
    if not turso_configured():
        legacy = Path(storage_dir) / "users.db"
        if legacy.exists():
            try:
                count_row = conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()
                count = int(count_row["c"]) if count_row else 0
                if count == 0:
                    legacy_conn = sqlite3.connect(str(legacy))
                    legacy_conn.row_factory = sqlite3.Row
                    for row in legacy_conn.execute("SELECT * FROM users"):
                        cols = row.keys()
                        conn.execute(
                            """
                            INSERT OR IGNORE INTO users
                            (id, github_id, login, email, org, plan, customer_id, avatar_url, created_at, updated_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                row["id"],
                                row["github_id"] if "github_id" in cols else "",
                                row["login"] if "login" in cols else "",
                                row["email"] if "email" in cols else "",
                                row["org"] if "org" in cols else "",
                                normalize_plan(row["plan"]) if "plan" in cols else "free",
                                row["customer_id"] if "customer_id" in cols else None,
                                row["avatar_url"] if "avatar_url" in cols else "",
                                row["created_at"] if "created_at" in cols else _now_iso(),
                                row["updated_at"] if "updated_at" in cols else _now_iso(),
                            ),
                        )
                    for row in legacy_conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' AND name='tokens'"
                    ):
                        for t in legacy_conn.execute("SELECT * FROM tokens"):
                            conn.execute(
                                "INSERT OR IGNORE INTO tokens (token, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
                                (t["token"], t["user_id"], t["created_at"], t["expires_at"]),
                            )
                    legacy_conn.close()
            except Exception:
                pass

        legacy_billing = Path(storage_dir) / "data" / "auth.db"
        if legacy_billing.exists():
            try:
                bconn = sqlite3.connect(str(legacy_billing))
                bconn.row_factory = sqlite3.Row
                for row in bconn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='users'"
                ):
                    for u in bconn.execute("SELECT id, email, plan, customer_id FROM users"):
                        plan = normalize_plan(u["plan"] if "plan" in u.keys() else "free")
                        if plan != "free" or u["customer_id"]:
                            conn.execute(
                                """
                                UPDATE users SET plan = ?, customer_id = COALESCE(?, customer_id), updated_at = ?
                                WHERE id = ? OR lower(email) = lower(?)
                                """,
                                (plan, u["customer_id"], _now_iso(), u["id"], u["email"] or ""),
                            )
                bconn.close()
            except Exception:
                pass

    conn.commit()
    conn.close()


def save_oauth_state(storage_dir: Path | str, state: str, redirect_uri: str | None = None) -> None:
    conn = _connect(storage_dir)
    conn.execute(
        "INSERT OR REPLACE INTO oauth_states (state, redirect_uri, created_at) VALUES (?, ?, ?)",
        (state, redirect_uri or "", _now_iso()),
    )
    # prune expired
    cutoff = (_utc_now() - timedelta(minutes=_OAUTH_STATE_TTL_MINUTES)).isoformat()
    conn.execute("DELETE FROM oauth_states WHERE created_at < ?", (cutoff,))
    conn.commit()
    conn.close()


def pop_oauth_state(storage_dir: Path | str, state: str) -> str | None:
    """Validate and consume OAuth state. Returns redirect_uri or '' if browser flow."""
    conn = _connect(storage_dir)
    cutoff = (_utc_now() - timedelta(minutes=_OAUTH_STATE_TTL_MINUTES)).isoformat()
    row = conn.execute(
        "SELECT redirect_uri, created_at FROM oauth_states WHERE state = ?",
        (state,),
    ).fetchone()
    if row:
        conn.execute("DELETE FROM oauth_states WHERE state = ?", (state,))
        conn.commit()
        conn.close()
        if row["created_at"] < cutoff:
            return None  # expired
        return row["redirect_uri"] or ""
    conn.close()
    return None


def start_github_oauth(
    storage_dir: Path | str,
    *,
    state: str,
    redirect_uri: str | None = None,
) -> str:
    """Return the GitHub authorization URL and persist state for the callback."""
    if not _client_id():
        raise HTTPException(status_code=503, detail="GitHub OAuth is not configured.")
    save_oauth_state(storage_dir, state, redirect_uri)
    params = {
        "client_id": _client_id(),
        "scope": "read:user user:email",
        "state": state,
        "redirect_uri": f"{_base_url()}/api/auth/github/callback",
    }
    return f"{GITHUB_AUTHORIZE_URL}?{urlencode(params)}"


def _make_github_token_request(code: str) -> dict[str, Any]:
    response = httpx.post(
        GITHUB_TOKEN_URL,
        data={
            "client_id": _client_id(),
            "client_secret": _client_secret(),
            "code": code,
            "redirect_uri": f"{_base_url()}/api/auth/github/callback",
        },
        headers={"Accept": "application/json"},
        timeout=30.0,
    )
    response.raise_for_status()
    data = response.json()
    if "error" in data:
        raise HTTPException(status_code=400, detail=f"GitHub OAuth error: {data['error']}")
    return data


def _fetch_github_user(access_token: str) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {access_token}", "Accept": "application/vnd.github+json"}
    user_resp = httpx.get(GITHUB_USER_URL, headers=headers, timeout=30.0)
    user_resp.raise_for_status()
    return user_resp.json()


def _fetch_primary_email(access_token: str) -> str | None:
    headers = {"Authorization": f"Bearer {access_token}", "Accept": "application/vnd.github+json"}
    emails_resp = httpx.get(GITHUB_EMAILS_URL, headers=headers, timeout=30.0)
    if emails_resp.status_code != 200:
        return None
    emails = emails_resp.json()
    for entry in emails:
        if isinstance(entry, dict) and entry.get("primary") and entry.get("verified"):
            return entry.get("email")
    for entry in emails:
        if isinstance(entry, dict) and entry.get("verified"):
            return entry.get("email")
    return None


def _derive_org(email: str | None, user: dict[str, Any]) -> str:
    if email and "@" in email:
        domain = email.split("@", 1)[-1].lower()
        if domain not in ("gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "icloud.com", "me.com"):
            return domain
    company = str(user.get("company") or "").strip().lstrip("@")
    return company


def _get_or_create_user(
    storage_dir: Path | str,
    github_user: dict[str, Any],
    email: str | None,
) -> dict[str, Any]:
    github_id = str(github_user.get("id") or "")
    login = str(github_user.get("login") or "")
    org = _derive_org(email, github_user)
    avatar = str(github_user.get("avatar_url") or "")
    now = _now_iso()

    conn = _connect(storage_dir)
    row = conn.execute("SELECT * FROM users WHERE github_id = ?", (github_id,)).fetchone()
    if row:
        user_id = row["id"]
        conn.execute(
            """
            UPDATE users SET login = ?, email = ?, org = ?, avatar_url = ?, updated_at = ?
            WHERE id = ?
            """,
            (login, email or row["email"], org or row["org"], avatar or row["avatar_url"], now, user_id),
        )
    else:
        user_id = f"usr_{uuid.uuid4().hex[:16]}"
        conn.execute(
            """
            INSERT INTO users
            (id, github_id, login, email, org, plan, customer_id, avatar_url, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, 'free', NULL, ?, ?, ?)
            """,
            (user_id, github_id, login, email or "", org, avatar, now, now),
        )
    conn.commit()
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    return dict(row) if row else {
        "id": user_id,
        "github_id": github_id,
        "login": login,
        "email": email,
        "org": org,
        "plan": "free",
        "avatar_url": avatar,
    }


def create_token(storage_dir: Path | str, user_id: str) -> str:
    conn = _connect(storage_dir)
    token = secrets.token_urlsafe(_TOKEN_BYTES)
    now = _utc_now()
    expires = now + timedelta(days=_TOKEN_TTL_DAYS)
    conn.execute(
        "INSERT INTO tokens (token, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
        (token, user_id, now.isoformat(), expires.isoformat()),
    )
    conn.commit()
    conn.close()
    return token


def verify_token(storage_dir: Path | str, token: str | None) -> dict[str, Any] | None:
    if not token:
        return None
    conn = _connect(storage_dir)
    row = conn.execute(
        """
        SELECT u.* FROM users u
        JOIN tokens t ON u.id = t.user_id
        WHERE t.token = ? AND t.expires_at > ?
        """,
        (token, _now_iso()),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def revoke_token(storage_dir: Path | str, token: str | None) -> None:
    if not token:
        return
    conn = _connect(storage_dir)
    conn.execute("DELETE FROM tokens WHERE token = ?", (token,))
    conn.commit()
    conn.close()


def revoke_all_user_tokens(storage_dir: Path | str, user_id: str) -> None:
    conn = _connect(storage_dir)
    conn.execute("DELETE FROM tokens WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()


def extract_token(request: Request) -> str:
    """Bearer header first, then session cookie."""
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        tok = auth[7:].strip()
        if tok:
            return tok
    return (request.cookies.get(COOKIE_NAME) or "").strip()


def set_session_cookie(response: Response, token: str) -> None:
    """HttpOnly cookie on the API host (works with credentials:include + CORS)."""
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=_TOKEN_TTL_DAYS * 24 * 3600,
        httponly=True,
        secure=True,
        samesite="none",
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        key=COOKIE_NAME,
        path="/",
        secure=True,
        samesite="none",
    )


def get_user_plan(storage_dir: Path | str, user_id: str) -> str:
    conn = _connect(storage_dir)
    row = conn.execute("SELECT plan FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    return normalize_plan(row["plan"] if row else "free")


def set_user_plan(
    storage_dir: Path | str,
    *,
    plan: str,
    user_id: str | None = None,
    email: str | None = None,
    customer_id: str | None = None,
) -> bool:
    plan = normalize_plan(plan)
    conn = _connect(storage_dir)
    ok = False
    if user_id:
        cur = conn.execute(
            "UPDATE users SET plan = ?, customer_id = COALESCE(?, customer_id), updated_at = ? WHERE id = ?",
            (plan, customer_id, _now_iso(), user_id),
        )
        ok = _rowcount(cur) > 0
    if not ok and email:
        cur = conn.execute(
            "UPDATE users SET plan = ?, customer_id = COALESCE(?, customer_id), updated_at = ? WHERE lower(email) = lower(?)",
            (plan, customer_id, _now_iso(), email),
        )
        ok = _rowcount(cur) > 0
    if not ok and customer_id:
        cur = conn.execute(
            "UPDATE users SET plan = ?, updated_at = ? WHERE customer_id = ?",
            (plan, _now_iso(), customer_id),
        )
        ok = _rowcount(cur) > 0
    conn.commit()
    conn.close()
    return ok


def user_public_dict(user: dict[str, Any], plan: str | None = None) -> dict[str, Any]:
    p = normalize_plan(plan if plan is not None else user.get("plan"))
    return {
        "id": user.get("id"),
        "login": user.get("login") or "",
        "email": user.get("email") or "",
        "org": user.get("org") or "",
        "plan": p,
        "avatar_url": user.get("avatar_url") or "",
        "created_at": user.get("created_at") or "",
    }


async def handle_github_callback(
    storage_dir: Path | str, *, code: str, state: str
) -> RedirectResponse:
    """Complete GitHub OAuth; set API-domain cookie and redirect to frontend."""
    if not _client_id() or not _client_secret():
        raise HTTPException(status_code=503, detail="GitHub OAuth is not configured.")

    # Validate CSRF state (must have been created by /start)
    redirect_uri = pop_oauth_state(storage_dir, state)
    if redirect_uri is None:
        # Unknown/expired state — still allow browser completion if GitHub returned a code
        # only when state looks like our browser format (auth_*) to avoid open abuse.
        if not (state or "").startswith("auth_"):
            raise HTTPException(status_code=400, detail="Invalid or expired OAuth state. Please try signing in again.")
        redirect_uri = ""

    try:
        token_data = _make_github_token_request(code)
        access_token = token_data.get("access_token")
        if not access_token:
            raise HTTPException(status_code=400, detail="GitHub did not return an access token.")

        github_user = _fetch_github_user(access_token)
        email = _fetch_primary_email(access_token)
        user = _get_or_create_user(storage_dir, github_user, email)
        bearer = create_token(storage_dir, user["id"])
        plan = normalize_plan(user.get("plan") or get_user_plan(storage_dir, user["id"]))
    except HTTPException:
        err = RedirectResponse(f"{_frontend_url()}/account?error=oauth_failed", status_code=302)
        return err
    except Exception:
        err = RedirectResponse(f"{_frontend_url()}/account?error=oauth_failed", status_code=302)
        return err

    # CLI / custom redirect (token in query — local loopback only expected)
    if redirect_uri and redirect_uri.startswith(("http://127.0.0.1", "http://localhost", "epi://")):
        separator = "&" if "?" in redirect_uri else "?"
        org_q = urlencode({"org": user.get("org") or ""})
        url = f"{redirect_uri}{separator}token={bearer}&user_id={user['id']}&{org_q}&plan={plan}"
        response = RedirectResponse(url, status_code=302)
        set_session_cookie(response, bearer)
        return response

    # Browser flow: hash token so static frontend can store it (cross-domain safe).
    # Also set HttpOnly cookie on API host for credentials:include fetches.
    user_payload = user_public_dict(user, plan)
    user_b64 = base64.urlsafe_b64encode(json.dumps(user_payload).encode()).decode()
    dest = f"{_frontend_url()}/account#token={bearer}&user={user_b64}"
    response = RedirectResponse(dest, status_code=302)
    set_session_cookie(response, bearer)
    return response


def init_auth_for_app(storage_dir: Path | str) -> None:
    init_auth_db(storage_dir)


def logout_response(storage_dir: Path | str, token: str | None) -> JSONResponse:
    revoke_token(storage_dir, token)
    response = JSONResponse({"ok": True, "logged_out": True})
    clear_session_cookie(response)
    return response
