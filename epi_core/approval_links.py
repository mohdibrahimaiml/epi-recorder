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

#: Event-content label for a decision recorded by clicking a gateway link.
APPROVAL_LINK_SOURCE = "gateway_link_unsigned"

#: Recorded when no authenticated principal was presented with the request.
UNVERIFIED_REVIEWER = "approval-link (identity not verified)"


def build_approval_link_token() -> str:
    """256 bits of URL-safe randomness (well over the 128-bit minimum)."""
    return secrets.token_urlsafe(32)


def hash_approval_link_token(token: str) -> str:
    """The only form in which a link token is stored."""
    return hashlib.sha256(str(token or "").encode("utf-8")).hexdigest()
