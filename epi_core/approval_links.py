"""Single-use, expiring tokens for gateway approval links (step 3b).

A gateway approval link proves nothing about a person: clicking it records a
*link click*, never a signed human approval. The token exists only so that an
old link cannot be **replayed**, **guessed**, or **forwarded to a different
approval**. It is never called an approval, and verification never treats it as
one — see ``epi_core.review.verify_human_approvals``.

Storage policy: the raw token is returned once (to the notifier) and never
written down; the store keeps ``sha256(token)`` only. Mirrors
:mod:`epi_core.auth_local` (``build_session_token`` / ``hash_session_token``).
"""

from __future__ import annotations

import hashlib
import secrets

#: Event-content label for a decision recorded by clicking a gateway link
#: without an authenticated principal.
APPROVAL_LINK_SOURCE = "gateway_link_unsigned"

#: Event-content label for a link click made by an authenticated gateway user.
#: It is gateway-attested (analysis counts it), but it is still not a signed
#: approval: it does not satisfy ``--require-human-approval``.
APPROVAL_LINK_AUTHENTICATED_SOURCE = "gateway_link_authenticated"

#: Legacy label written by gateways before 3b. Kept so old artifacts analyze the
#: same, and so the ingest boundary knows it is a gateway-only label.
APPROVAL_LINK_LEGACY_SOURCE = "gateway_human"

#: Approval-source labels only the gateway itself may write. A capture client
#: claiming one is demoted to ``raw_api_unverified`` at the HTTP boundary.
GATEWAY_ONLY_APPROVAL_SOURCES = frozenset(
    {APPROVAL_LINK_LEGACY_SOURCE, APPROVAL_LINK_AUTHENTICATED_SOURCE, APPROVAL_LINK_SOURCE}
)

#: The label a capture client's steps always end up with.
CLIENT_APPROVAL_SOURCE = "raw_api_unverified"

#: Recorded when no authenticated principal was presented with the request.
UNVERIFIED_REVIEWER = "approval-link (identity not verified)"


def build_approval_link_token() -> str:
    """256 bits of URL-safe randomness (well over the 128-bit minimum)."""
    return secrets.token_urlsafe(32)


def hash_approval_link_token(token: str) -> str:
    """The only form in which a link token is stored."""
    return hashlib.sha256(str(token or "").encode("utf-8")).hexdigest()
