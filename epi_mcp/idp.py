"""Optional "Sign in" for the approve page (OpenID Connect, authorization-code flow).

Off unless the operator configures an identity provider:

    EPI_IDP_ISSUER         e.g. https://accounts.google.com (any OIDC issuer: Google,
                           Microsoft Entra, Okta, Auth0, Keycloak)
    EPI_IDP_CLIENT_ID      OAuth client id registered with that provider
    EPI_IDP_CLIENT_SECRET  its secret
    EPI_IDP_NAME           optional button label, default "your account"

Anonymous approval stays the default and is never removed. When a person signs in,
the server learns who the provider says they are and writes that into the sealed
file's signed environment.json. The claim is "the sealing server saw this person
sign in with <issuer>"; it does not say who typed the chat, and it is not made by
Claude or ChatGPT, which never tell this server who the user is.

State is stateless (signed), so a sleeping free-tier host does not break a login.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import time
import urllib.parse
import urllib.request
from typing import Any

STATE_AUD = "epi-idp-state"
STATE_TTL_SECONDS = 600
_DISCOVERY_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}


class IdpError(Exception):
    """Sign-in failed. The message is safe to show to the person."""


def idp_config() -> dict[str, str] | None:
    issuer = (os.environ.get("EPI_IDP_ISSUER") or "").strip().rstrip("/")
    client_id = (os.environ.get("EPI_IDP_CLIENT_ID") or "").strip()
    client_secret = (os.environ.get("EPI_IDP_CLIENT_SECRET") or "").strip()
    if not (issuer and client_id and client_secret):
        return None
    return {
        "issuer": issuer,
        "client_id": client_id,
        "client_secret": client_secret,
        "name": (os.environ.get("EPI_IDP_NAME") or "your account").strip(),
    }


def idp_enabled() -> bool:
    from epi_mcp import oauth

    return idp_config() is not None and oauth.oauth_secret() is not None


# Network seams: tests replace these; production uses the stdlib only.
def _http_get_json(url: str) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=10) as resp:  # noqa: S310 (https issuer)
        return json.loads(resp.read().decode("utf-8"))


def _http_post_form(url: str, data: dict[str, str]) -> dict[str, Any]:
    body = urllib.parse.urlencode(data).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310
        return json.loads(resp.read().decode("utf-8"))


def _decode_id_token(id_token: str, jwks_uri: str, issuer: str, audience: str, nonce: str) -> dict[str, Any]:
    import jwt as _pyjwt
    from jwt import PyJWKClient

    key = PyJWKClient(jwks_uri).get_signing_key_from_jwt(id_token)
    claims = _pyjwt.decode(
        id_token,
        key.key,
        algorithms=["RS256", "ES256"],
        audience=audience,
        issuer=issuer,
        options={"require": ["exp", "iss", "sub", "aud"]},
    )
    if claims.get("nonce") != nonce:
        raise IdpError("Sign-in could not be confirmed (nonce mismatch). Please start again.")
    return claims


def _discovery(issuer: str) -> dict[str, Any]:
    now = time.time()
    cached = _DISCOVERY_CACHE.get(issuer)
    if cached and now - cached[0] < 3600:
        return cached[1]
    doc = _http_get_json(f"{issuer}/.well-known/openid-configuration")
    for field in ("authorization_endpoint", "token_endpoint", "jwks_uri"):
        if not doc.get(field):
            raise IdpError("The sign-in provider is misconfigured.")
    _DISCOVERY_CACHE[issuer] = (now, doc)
    return doc


def _callback_url() -> str:
    from epi_mcp import oauth

    return f"{oauth.public_base()}/oauth/idp/callback"


def _sign_state(payload: dict[str, Any]) -> str:
    import jwt as _pyjwt

    from epi_mcp import oauth

    now = int(time.time())
    return _pyjwt.encode(
        {**payload, "aud": STATE_AUD, "iat": now, "exp": now + STATE_TTL_SECONDS},
        oauth.oauth_secret(),
        algorithm="HS256",
    )


def _read_state(state: str) -> dict[str, Any]:
    import jwt as _pyjwt

    from epi_mcp import oauth

    try:
        return _pyjwt.decode(state, oauth.oauth_secret(), algorithms=["HS256"], audience=STATE_AUD)
    except Exception as exc:
        raise IdpError("This sign-in link expired or is invalid. Please start again.") from exc


def begin_login(params: dict[str, str], include_email: bool) -> str:
    """Return the identity provider URL to send the person to."""
    cfg = idp_config()
    if cfg is None:
        raise IdpError("Sign-in is not enabled on this server.")
    doc = _discovery(cfg["issuer"])
    nonce = secrets.token_urlsafe(16)
    state = _sign_state({"p": params, "nonce": nonce, "inc": bool(include_email)})
    query = urllib.parse.urlencode({
        "response_type": "code",
        "client_id": cfg["client_id"],
        "redirect_uri": _callback_url(),
        "scope": "openid email",
        "state": state,
        "nonce": nonce,
    })
    sep = "&" if "?" in doc["authorization_endpoint"] else "?"
    return f"{doc['authorization_endpoint']}{sep}{query}"


def finish_login(code: str, state: str) -> tuple[dict[str, str], str, dict[str, Any]]:
    """Complete sign-in. Returns (original authorize params, subject, identity claim)."""
    cfg = idp_config()
    if cfg is None:
        raise IdpError("Sign-in is not enabled on this server.")
    st = _read_state(state)
    doc = _discovery(cfg["issuer"])
    try:
        tokens = _http_post_form(doc["token_endpoint"], {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": _callback_url(),
            "client_id": cfg["client_id"],
            "client_secret": cfg["client_secret"],
        })
        claims = _decode_id_token(
            str(tokens.get("id_token", "")), doc["jwks_uri"], doc.get("issuer", cfg["issuer"]),
            cfg["client_id"], st["nonce"],
        )
    except IdpError:
        raise
    except Exception as exc:
        raise IdpError("The sign-in provider did not confirm your login. Nothing was approved.") from exc

    issuer = str(claims["iss"])
    digest = hashlib.sha256(f"{issuer}|{claims['sub']}".encode("utf-8")).hexdigest()
    subject = "oidc-" + digest[:20]
    email_ok = bool(claims.get("email")) and claims.get("email_verified") in (True, "true")
    identity: dict[str, Any] = {
        "method": "oidc",
        "verified_by": issuer,
        "account_id": digest[:16],
        "email_verified": email_ok,
    }
    if st.get("inc") and email_ok:
        identity["email"] = str(claims["email"])
    return st["p"], subject, identity


def describe_identity(identity: dict[str, Any] | None) -> dict[str, Any]:
    """The block written into the sealed file. Always says what it does not prove."""
    if not identity or identity.get("method") != "oidc":
        return {
            "method": "pseudonymous",
            "verified": False,
            "statement": "Approved without sign-in. The signer is a pseudonym, not a verified person.",
        }
    out = dict(identity)
    out["verified"] = True
    out["statement"] = (
        f"The sealing server saw this person sign in with {identity['verified_by']}. "
        "This is asserted by the sealing server. It does not prove who typed the "
        "conversation, and Claude or ChatGPT did not supply it."
    )
    return out
