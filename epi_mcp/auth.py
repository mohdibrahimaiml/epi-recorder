"""Caller authentication for the EPI MCP server.

Two modes, in order:

1. OIDC (zero-config for app users): when EPI_OIDC_* is configured, a
   Bearer JWT is verified against the issuer's JWKS and the subject
   becomes the caller identity. The chat host (ChatGPT) authenticates
   the user; the user types nothing.
2. Static token (dev / single-operator): EPI_MCP_TOKEN matches exactly;
   caller identity is the token holder.

Anything else: anonymous (None). Anonymous callers can verify and
export, but sealing requires an authenticated identity so every seal
is bound to someone.
"""

from __future__ import annotations

import hashlib
import os


def subject_key(subject: str) -> str:
    """Stable, opaque key name for a caller subject. Raw ids never stored."""
    return "user-" + hashlib.sha256(subject.encode("utf-8")).hexdigest()[:16]


def auth_configured() -> bool:
    """True when any caller authentication is available."""
    if (os.environ.get("EPI_MCP_TOKEN") or "").strip():
        return True
    return bool((os.environ.get("EPI_OIDC_JWKS_URL") or "").strip())


def verify_bearer_token(token: str | None) -> str | None:
    """Return the caller subject, or None if unauthenticated."""
    presented = (token or "").strip()
    if not presented:
        return None
    static = (os.environ.get("EPI_MCP_TOKEN") or "").strip()
    if static and presented == static:
        return "token-holder"
    oidc_subject = _verify_oidc(presented)
    if oidc_subject:
        return oidc_subject
    return None


def _verify_oidc(token: str) -> str | None:
    jwks_url = (os.environ.get("EPI_OIDC_JWKS_URL") or "").strip()
    issuer = (os.environ.get("EPI_OIDC_ISSUER") or "").strip()
    audience = (os.environ.get("EPI_OIDC_AUDIENCE") or "").strip()
    if not (jwks_url and issuer):
        return None
    try:
        import jwt as _pyjwt
        from jwt import PyJWKClient as _PyJWKClient
    except ImportError:
        return None
    try:
        signing_key = _PyJWKClient(jwks_url).get_signing_key_from_jwt(token)
        payload = _pyjwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=issuer,
            audience=audience or None,
            options={"require": ["exp", "iss", "sub"]},
        )
        sub = str(payload.get("sub") or "").strip()
        return sub or None
    except Exception:
        return None
