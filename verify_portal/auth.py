"""Authentication helpers for the EPI Verify Portal.

Supports GitHub OAuth for CLI/browser login and issues bearer tokens that the
CLI can use for cloud-only features and linked telemetry.
"""

from __future__ import annotations

import os
import secrets
import sqlite3
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
from fastapi import HTTPException, Request
from fastapi.responses import RedirectResponse


GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_USER_URL = "https://api.github.com/user"
GITHUB_EMAILS_URL = "https://api.github.com/user/emails"

_TOKEN_BYTES = 32
_TOKEN_TTL_DAYS = 90


def _client_id() -> str:
    return os.getenv("GITHUB_CLIENT_ID", "")


def _client_secret() -> str:
    return os.getenv("GITHUB_CLIENT_SECRET", "")


def _base_url() -> str:
    return os.getenv("EPI_VERIFY_BASE_URL", "https://epi-verify-portal.onrender.com").rstrip("/")


def _db_path(storage_dir: Path | str) -> Path:
    return Path(storage_dir) / "users.db"


def init_auth_db(storage_dir: Path | str) -> None:
    """Create users and tokens tables if they do not exist."""
    db = _db_path(storage_dir)
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db))
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            github_id TEXT UNIQUE,
            login TEXT,
            email TEXT,
            org TEXT,
            created_at TEXT,
            updated_at TEXT
        );
        CREATE TABLE IF NOT EXISTS tokens (
            token TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            created_at TEXT,
            expires_at TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        CREATE INDEX IF NOT EXISTS idx_tokens_user ON tokens(user_id);
        """
    )
    conn.commit()
    conn.close()


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _now_iso() -> str:
    return _utc_now().isoformat()


# In-memory state → redirect_uri mapping for the CLI OAuth dance.
# A production service may prefer Redis; this is sufficient for a single-node Render instance.
_oauth_states: dict[str, str] = {}


def start_github_oauth(*, state: str, redirect_uri: str | None = None) -> str:
    """Return the GitHub authorization URL and remember the CLI redirect URI."""
    if not _client_id():
        raise HTTPException(status_code=503, detail="GitHub OAuth is not configured.")
    if redirect_uri:
        _oauth_states[state] = redirect_uri
    params = {
        "client_id": _client_id(),
        "scope": "read:user user:email",
        "state": state,
    }
    query = "&".join(f"{k}={httpx.QueryParams({k: v})}" for k, v in params.items())
    return f"{GITHUB_AUTHORIZE_URL}?{query}"


def _make_github_token_request(code: str) -> dict[str, Any]:
    """Exchange an OAuth code for a GitHub access token."""
    response = httpx.post(
        GITHUB_TOKEN_URL,
        data={
            "client_id": _client_id(),
            "client_secret": _client_secret(),
            "code": code,
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
        return email.split("@", 1)[-1]
    return str(user.get("company") or "")


def _get_or_create_user(storage_dir: Path | str, github_user: dict[str, Any], email: str | None) -> dict[str, Any]:
    db = _db_path(storage_dir)
    github_id = str(github_user.get("id") or "")
    login = str(github_user.get("login") or "")
    org = _derive_org(email, github_user)
    now = _now_iso()

    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM users WHERE github_id = ?", (github_id,)).fetchone()
    if row:
        user_id = row["id"]
        conn.execute(
            "UPDATE users SET login = ?, email = ?, org = ?, updated_at = ? WHERE id = ?",
            (login, email or row["email"], org or row["org"], now, user_id),
        )
    else:
        user_id = f"usr_{uuid.uuid4().hex[:16]}"
        conn.execute(
            "INSERT INTO users (id, github_id, login, email, org, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user_id, github_id, login, email or "", org, now, now),
        )
    conn.commit()
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    return dict(row) if row else {"id": user_id, "github_id": github_id, "login": login, "email": email, "org": org}


def create_token(storage_dir: Path | str, user_id: str) -> str:
    """Create a new bearer token for a user."""
    db = _db_path(storage_dir)
    token = secrets.token_urlsafe(_TOKEN_BYTES)
    now = _utc_now()
    expires = now + timedelta(days=_TOKEN_TTL_DAYS)
    conn = sqlite3.connect(str(db))
    conn.execute(
        "INSERT INTO tokens (token, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
        (token, user_id, now.isoformat(), expires.isoformat()),
    )
    conn.commit()
    conn.close()
    return token


def verify_token(storage_dir: Path | str, token: str | None) -> dict[str, Any] | None:
    """Return the user record for a valid token, or None."""
    if not token:
        return None
    db = _db_path(storage_dir)
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT u.* FROM users u JOIN tokens t ON u.id = t.user_id WHERE t.token = ? AND t.expires_at > ?",
        (token, _now_iso()),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def revoke_token(storage_dir: Path | str, token: str | None) -> None:
    if not token:
        return
    db = _db_path(storage_dir)
    conn = sqlite3.connect(str(db))
    conn.execute("DELETE FROM tokens WHERE token = ?", (token,))
    conn.commit()
    conn.close()


async def handle_github_callback(
    storage_dir: Path | str, *, code: str, state: str
) -> RedirectResponse:
    """Complete GitHub OAuth and redirect back to the CLI with a token."""
    if not _client_id() or not _client_secret():
        raise HTTPException(status_code=503, detail="GitHub OAuth is not configured.")

    token_data = _make_github_token_request(code)
    access_token = token_data.get("access_token")
    if not access_token:
        raise HTTPException(status_code=400, detail="GitHub did not return an access token.")

    github_user = _fetch_github_user(access_token)
    email = _fetch_primary_email(access_token)
    user = _get_or_create_user(storage_dir, github_user, email)
    bearer = create_token(storage_dir, user["id"])

    cli_redirect = _oauth_states.pop(state, None)
    if cli_redirect:
        separator = "&" if "?" in cli_redirect else "?"
        url = f"{cli_redirect}{separator}token={bearer}&user_id={user['id']}&org={httpx.QueryParams({'org': user.get('org') or ''})}"
        return RedirectResponse(url)

    # Browser-only flow: redirect to a simple success page.
    return RedirectResponse(f"/auth/success?token={bearer}")


def init_auth_for_app(storage_dir: Path | str) -> None:
    """Idempotent setup call to run when the verify portal starts."""
    init_auth_db(storage_dir)
