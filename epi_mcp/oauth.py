"""Minimal OAuth authorization server for the EPI MCP endpoint.

Purpose: let a chat host (ChatGPT) complete an OAuth code flow without
the user typing URLs or tokens. The approver gets a stable pseudonymous
subject (per approval, stored server-side); seals bind to that subject
via the normal per-caller key path.

Honest limits (documented, not hidden):
- Pseudonymous, not human-verified: approval proves control of the
  chat session that approved, nothing more.
- In-memory stores: approvals, codes, and clients vanish on restart.
  Fine for testing and single-operator use; production needs durable
  storage before this carries real trust.
- No user accounts, no passwords. Do not layer real identity claims
  on top of these subjects.
"""

from __future__ import annotations

import base64
import hashlib
import os
import secrets
import time
from typing import Any

_OAUTH_SECRET_ENV = "EPI_OAUTH_SECRET"


def oauth_secret() -> str | None:
    """Server secret for minting tokens. Falls back to the MCP token."""
    return (os.environ.get(_OAUTH_SECRET_ENV) or "").strip() or (
        (os.environ.get("EPI_MCP_TOKEN") or "").strip() or None
    )


def oauth_enabled() -> bool:
    return oauth_secret() is not None


def public_base() -> str:
    return (os.environ.get("EPI_MCP_PUBLIC_URL") or "").strip().rstrip("/")


# In-memory stores (see module docstring for limits).
CLIENTS: dict[str, dict[str, Any]] = {}
CODES: dict[str, dict[str, Any]] = {}
SUBJECTS: dict[str, dict[str, Any]] = {}
REFRESH: dict[str, str] = {}


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _pkce_ok(verifier: str, challenge: str, method: str | None) -> bool:
    if not challenge:
        return True
    if (method or "plain") == "S256":
        digest = hashlib.sha256(verifier.encode("ascii")).digest()
        import hmac as _hmac

        return _hmac.compare_digest(_b64url(digest), challenge)
    return verifier == challenge


def register_client(info: dict[str, Any]) -> dict[str, Any]:
    """Dynamic client registration: accept and record, return credentials."""
    client_id = "epi-client-" + secrets.token_hex(8)
    client_secret = secrets.token_hex(32)
    CLIENTS[client_id] = {
        "secret": client_secret,
        "redirect_uris": info.get("redirect_uris", []),
        "created_at": int(time.time()),
    }
    return {"client_id": client_id, "client_secret": client_secret}


def create_approval() -> str:
    """Mint a fresh pseudonymous subject for one approval."""
    subject = "chatgpt-" + secrets.token_hex(8)
    SUBJECTS[subject] = {"created_at": int(time.time())}
    return subject


def issue_code(subject: str, client_id: str, redirect_uri: str, challenge: str, method: str | None) -> str:
    code = "epi-code-" + secrets.token_hex(16)
    CODES[code] = {
        "subject": subject,
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "challenge": challenge,
        "method": method,
        "expires_at": int(time.time()) + 600,
    }
    return code


def mint_token(subject: str, audience: str | None = None) -> tuple[str, str]:
    """Return (access_jwt, refresh_token) for a subject."""
    import jwt as _pyjwt

    secret = oauth_secret()
    assert secret, "OAuth not configured"
    now = int(time.time())
    access = _pyjwt.encode(
        {"sub": subject, "aud": audience or public_base(), "iat": now, "exp": now + 3600 * 24 * 30,
         "scope": "seal verify export"},
        secret,
        algorithm="HS256",
    )
    refresh = "epi-refresh-" + secrets.token_hex(24)
    REFRESH[refresh] = subject
    return access, refresh


def verify_own_token(token: str) -> str | None:
    """Verify a token minted here. Returns the subject or None."""
    secret = oauth_secret()
    if not secret:
        return None
    try:
        import jwt as _pyjwt
    except ImportError:
        return None
    try:
        payload = _pyjwt.decode(
            token, secret, algorithms=["HS256"],
            audience=public_base() or None,
            options={"require": ["exp", "sub"]},
        )
        sub = str(payload.get("sub") or "")
        return sub or None
    except Exception:
        return None


def redeem_code(code: str, client_id: str, redirect_uri: str, verifier: str) -> dict[str, Any] | None:
    """Exchange an authorization code for tokens. Single-use."""
    rec = CODES.pop(code, None)
    if not rec or rec["expires_at"] < int(time.time()):
        return None
    if rec["client_id"] != client_id or rec["redirect_uri"] != redirect_uri:
        return None
    if not _pkce_ok(verifier or "", rec["challenge"], rec["method"]):
        return None
    access, refresh = mint_token(rec["subject"])
    return {"access_token": access, "refresh_token": refresh,
            "token_type": "Bearer", "expires_in": 3600 * 24 * 30}


def redeem_refresh(refresh: str) -> dict[str, Any] | None:
    subject = REFRESH.get(refresh)
    if not subject:
        return None
    access, new_refresh = mint_token(subject)
    del REFRESH[refresh]
    return {"access_token": access, "refresh_token": new_refresh,
            "token_type": "Bearer", "expires_in": 3600 * 24 * 30}
