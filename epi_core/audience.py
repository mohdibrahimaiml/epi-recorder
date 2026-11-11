"""Seal-chain audiences: who a seal is reported to.

A seal chain is scoped to an *audience*, not to a signing key. One key that
reports to two customers keeps two independent number sequences, so a number
missing from one customer's log is never a hole in the other's.

Audience ids are derived, never guessed:

* ``record(customer="acme-bank")`` -> ``customer:acme-bank`` (explicit; keeps
  one chain continuous when the witness URL changes)
* a Cloud inbox ``https://cloud.epilabs.org/w/<inbox_id>`` -> ``cloud:<id>``
* any other witness URL -> ``url:<sha256(normalised url)[:16]>``
* no witness at all -> ``local:unwitnessed``

The id is stored in the report and (for the audience the file is handed to) in
``artifacts/seal_chain.json``. Other audiences are stored only as salted
commitments in ``artifacts/seal_chains.json`` so one customer's copy reveals
nothing about another customer's chain.
"""

from __future__ import annotations

import hashlib
import json
import re
import secrets
from urllib.parse import urlsplit, urlunsplit

LOCAL_AUDIENCE = "local:unwitnessed"
CLOUD_HOST = "cloud.epilabs.org"
AUDIENCE_COMMITMENT_SCHEME = "epi-audience-commitment/v1"
ENTRY_COMMITMENT_SCHEME = "epi-entry-commitment/v1"


def slug_customer(value: str) -> str:
    """A stable, readable id: lower-case, non-alphanumerics collapsed to '-'."""
    slug = re.sub(r"[^a-z0-9]+", "-", str(value or "").strip().lower()).strip("-")
    return slug[:64]


def normalise_url(url: str) -> str:
    """Lower-case scheme/host, drop a default port, drop a trailing slash."""
    parts = urlsplit(str(url or "").strip())
    scheme = (parts.scheme or "https").lower()
    host = (parts.hostname or "").lower()
    port = parts.port
    if port and not ((scheme == "https" and port == 443) or (scheme == "http" and port == 80)):
        host = f"{host}:{port}"
    path = parts.path or ""
    if path.endswith("/") and len(path) > 1:
        path = path.rstrip("/")
    return urlunsplit((scheme, host, path, parts.query, ""))


def cloud_inbox_id(url: str) -> str | None:
    parts = urlsplit(str(url or "").strip())
    if (parts.hostname or "").lower() != CLOUD_HOST:
        return None
    match = re.match(r"^/w/([A-Za-z0-9_-]{6,})$", parts.path or "")
    return match.group(1) if match else None


def audience_for_url(url: str) -> str:
    inbox = cloud_inbox_id(url)
    if inbox:
        return f"cloud:{inbox}"
    digest = hashlib.sha256(normalise_url(url).encode("utf-8")).hexdigest()[:16]
    return f"url:{digest}"


def derive_audiences(customer: str | None, urls: list[str] | None) -> list[str]:
    """The audiences for one seal, primary first, duplicates removed.

    An explicit customer wins over URL-derived ids: the whole point is that a
    changed witness URL does not break that customer's chain.
    """
    explicit = slug_customer(customer or "")
    if explicit:
        return [f"customer:{explicit}"]
    seen: list[str] = []
    for url in urls or []:
        if not str(url or "").strip():
            continue
        candidate = audience_for_url(str(url))
        if candidate not in seen:
            seen.append(candidate)
    return seen or [LOCAL_AUDIENCE]


def new_nonce() -> str:
    return secrets.token_hex(16)


def _jcs(value: dict) -> bytes:
    import rfc8785

    return rfc8785.dumps(value)


def audience_commitment(audience: str, nonce: str) -> str:
    data = f"{AUDIENCE_COMMITMENT_SCHEME}\n{nonce}\n{audience}".encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def entry_commitment(entry: dict, nonce: str) -> str:
    body = {k: v for k, v in dict(entry or {}).items() if k != "nonce"}
    data = f"{ENTRY_COMMITMENT_SCHEME}\n{nonce}\n".encode("utf-8") + _jcs(body)
    return hashlib.sha256(data).hexdigest()


def commitment_record(entry: dict) -> dict[str, str]:
    nonce = str(entry.get("nonce") or "")
    return {
        "audience_commitment": audience_commitment(str(entry.get("audience") or ""), nonce),
        "entry_commitment": entry_commitment(entry, nonce),
    }


def verify_commitment(entry: dict, commitments: list[dict]) -> bool:
    """True when this report's entry is one committed to by the file."""
    nonce = str(entry.get("nonce") or "")
    if not nonce:
        return False
    want_entry = entry_commitment(entry, nonce)
    want_audience = audience_commitment(str(entry.get("audience") or ""), nonce)
    for item in commitments or []:
        if not isinstance(item, dict):
            continue
        if str(item.get("entry_commitment") or "") != want_entry:
            continue
        if str(item.get("audience_commitment") or "") != want_audience:
            continue
        return True
    return False


def urls_for_audience(audience: str, urls: list[str] | None) -> list[str]:
    """The subset of URLs that report to this audience.

    A heartbeat for audience A must never be posted to audience B's endpoint:
    the receiver would learn A's last number.
    """
    target = str(audience or "")
    return [u for u in (urls or []) if audience_for_url(str(u)) == target]
