"""Minimal OAuth authorization server for the EPI MCP endpoint.

Purpose: let a chat host (ChatGPT) complete an OAuth code flow without
the user typing URLs or tokens. The approver gets a stable pseudonymous
subject (per approval, stored server-side); seals bind to that subject
via the normal per-caller key path.

Honest limits (documented, not hidden):
- Pseudonymous, not human-verified: approval proves control of the
  chat session that approved, nothing more.
- Clients and refresh tokens are self-contained signed tokens, so they
  survive restarts and sleeping hosts with no database. Authorization
  codes (10 minutes) and refresh-rotation bookkeeping stay in memory: a
  restart inside that window forces one re-approval, and a refresh token
  replayed after a restart is not detected. Nothing here is revocable
  before expiry except by rotating the server secret.
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
REFRESH_TTL_SECONDS = 90 * 24 * 3600


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


def _sig(kind: str, value: str) -> str:
    import hmac as _hmac

    secret = (oauth_secret() or "").encode("utf-8")
    return _hmac.new(secret, f"{kind}:{value}".encode("utf-8"), hashlib.sha256).hexdigest()


def _client_secret_for(client_id: str) -> str:
    return _sig("client-secret", client_id)


def _decode_client(client_id: str) -> dict[str, Any] | None:
    """Return the registration encoded in a stateless client_id, or None."""
    import hmac as _hmac
    import json

    prefix = "epi-client-"
    if not client_id.startswith(prefix) or "." not in client_id:
        return None
    body, _, mac = client_id[len(prefix):].rpartition(".")
    if not oauth_enabled() or not _hmac.compare_digest(_sig("client", body)[:32], mac):
        return None
    try:
        padded = body + "=" * (-len(body) % 4)
        data = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def register_client(info: dict[str, Any]) -> dict[str, Any]:
    """Dynamic client registration.

    With a server secret configured the client_id itself carries the
    registered redirect URIs and a MAC, so registrations survive restarts.
    Without one (loopback dev) they live in memory.
    """
    import json

    uris = [u for u in (info.get("redirect_uris") or []) if isinstance(u, str)][:5]
    now = int(time.time())
    if oauth_enabled():
        body = _b64url(json.dumps({"r": uris, "t": now}, separators=(",", ":")).encode("utf-8"))
        client_id = f"epi-client-{body}.{_sig('client', body)[:32]}"
        client_secret = _client_secret_for(client_id)
    else:
        client_id = "epi-client-" + secrets.token_hex(8)
        client_secret = secrets.token_hex(32)
        CLIENTS[client_id] = {"secret": client_secret, "redirect_uris": uris, "created_at": now}
    return {
        "client_id": client_id,
        "client_secret": client_secret,
        "client_id_issued_at": now,
        "client_secret_expires_at": 0,
        "redirect_uris": uris,
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": info.get("token_endpoint_auth_method", "client_secret_post"),
    }


def redirect_allowed(client_id: str, redirect_uri: str) -> bool:
    """Registered clients may only use their registered redirect URIs."""
    rec = _decode_client(client_id)
    registered = (
        rec.get("r") if rec is not None else (CLIENTS.get(client_id) or {}).get("redirect_uris")
    )
    if rec is None and client_id not in CLIENTS:
        return False
    registered = registered or []
    return redirect_uri in registered if registered else bool(redirect_uri)


def create_approval(subject: str | None = None) -> str:
    """Mint a pseudonymous subject for one approval, or reuse a signed-in person's."""
    subject = subject or "chatgpt-" + secrets.token_hex(8)
    SUBJECTS[subject] = {"created_at": int(time.time())}
    return subject


def issue_code(
    subject: str,
    client_id: str,
    redirect_uri: str,
    challenge: str,
    method: str | None,
    identity: dict[str, Any] | None = None,
) -> str:
    code = "epi-code-" + secrets.token_hex(16)
    CODES[code] = {
        "subject": subject,
        "identity": identity,
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "challenge": challenge,
        "method": method,
        "expires_at": int(time.time()) + 600,
    }
    return code


def mint_token(
    subject: str, audience: str | None = None, identity: dict[str, Any] | None = None
) -> tuple[str, str]:
    """Return (access_jwt, refresh_token) for a subject."""
    import jwt as _pyjwt

    secret = oauth_secret()
    assert secret, "OAuth not configured"
    now = int(time.time())
    extra = {"idn": identity} if identity else {}
    access = _pyjwt.encode(
        {"sub": subject, "aud": audience or public_base(), "iat": now, "exp": now + 3600 * 24 * 30,
         "scope": "seal verify export", **extra},
        secret,
        algorithm="HS256",
    )
    refresh = _pyjwt.encode(
        {"sub": subject, "typ": "refresh", "aud": "epi-refresh", "jti": secrets.token_hex(8),
         "iat": now, "exp": now + REFRESH_TTL_SECONDS, **extra},
        secret,
        algorithm="HS256",
    )
    return access, refresh


def verify_own_claims(token: str) -> tuple[str, dict[str, Any] | None] | None:
    """Verify a token minted here. Returns (subject, identity-or-None) or None."""
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
        if not sub:
            return None
        idn = payload.get("idn")
        return sub, (idn if isinstance(idn, dict) else None)
    except Exception:
        return None


def verify_own_token(token: str) -> str | None:
    """Verify a token minted here. Returns the subject or None."""
    claims = verify_own_claims(token)
    return claims[0] if claims else None


def redeem_code(code: str, client_id: str, redirect_uri: str, verifier: str) -> dict[str, Any] | None:
    """Exchange an authorization code for tokens. Single-use."""
    rec = CODES.pop(code, None)
    if not rec or rec["expires_at"] < int(time.time()):
        return None
    if rec["client_id"] != client_id or rec["redirect_uri"] != redirect_uri:
        return None
    if not _pkce_ok(verifier or "", rec["challenge"], rec["method"]):
        return None
    access, refresh = mint_token(rec["subject"], identity=rec.get("identity"))
    return {"access_token": access, "refresh_token": refresh,
            "token_type": "Bearer", "expires_in": 3600 * 24 * 30}


def redeem_refresh(refresh: str) -> dict[str, Any] | None:
    """Rotate a refresh token. Stateless: the token is a signed JWT."""
    secret = oauth_secret()
    if not secret:
        return None
    try:
        import jwt as _pyjwt

        payload = _pyjwt.decode(
            refresh, secret, algorithms=["HS256"], audience="epi-refresh",
            options={"require": ["exp", "sub", "jti"]},
        )
    except Exception:
        return None
    if payload.get("typ") != "refresh" or payload["jti"] in REFRESH:
        return None  # not a refresh token, or already rotated this process
    REFRESH[payload["jti"]] = str(payload["sub"])
    idn = payload.get("idn")
    access, new_refresh = mint_token(str(payload["sub"]), identity=idn if isinstance(idn, dict) else None)
    return {"access_token": access, "refresh_token": new_refresh,
            "token_type": "Bearer", "expires_in": 3600 * 24 * 30}
