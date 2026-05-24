"""
SCITT Transparency Service routes for the EPI Verify Portal.

Mounted at /scitt/* on the existing FastAPI app. Provides:
    POST /register      — Submit a COSE_Sign1 Signed Statement, get a Receipt
    GET  /keys          — Fetch the service's Ed25519 public key
    GET  /entries/{id}  — Lookup a registered statement by entry ID

Environment:
    EPI_SCITT_SERVICE_PRIVATE_KEY — Base64-encoded raw 32-byte Ed25519 private key

Note: The in-memory registry is cleared on app restart (acceptable for the
free-tier demo; receipts verify cryptographically offline once embedded).
"""

from __future__ import annotations

import base64
import hashlib
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import APIRouter, HTTPException, Request, Response

from epi_core.scitt import (
    SCITTRegistrationError,
    SCITTVerificationError,
    create_scitt_receipt,
    parse_scitt_statement,
)

router = APIRouter()

# ─────────────────────────────────────────────────────────────
# Key loading
# ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ServiceKey:
    private_key: Ed25519PrivateKey
    public_key_hex: str


def _load_service_key() -> ServiceKey | None:
    """Load the SCITT service Ed25519 private key from env var."""
    raw_b64 = os.environ.get("EPI_SCITT_SERVICE_PRIVATE_KEY")
    if not raw_b64:
        return None
    try:
        key_bytes = base64.b64decode(raw_b64)
        if len(key_bytes) != 32:
            return None
        pk = Ed25519PrivateKey.from_private_bytes(key_bytes)
        pub_hex = pk.public_key().public_bytes_raw().hex()
        return ServiceKey(private_key=pk, public_key_hex=pub_hex)
    except Exception:
        return None


# Lazy-loaded singleton
_service_key: ServiceKey | None = None


def _get_service_key() -> ServiceKey:
    global _service_key
    if _service_key is None:
        _service_key = _load_service_key()
    if _service_key is None:
        raise HTTPException(
            status_code=503,
            detail="SCITT service not configured. EPI_SCITT_SERVICE_PRIVATE_KEY is missing.",
        )
    return _service_key


# ─────────────────────────────────────────────────────────────
# In-memory registry
# ─────────────────────────────────────────────────────────────


@dataclass
class RegistryEntry:
    statement_bytes: bytes
    receipt_bytes: bytes
    registered_at: str
    entry_id: str


_registry: dict[str, RegistryEntry] = {}


# ─────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────


@router.post("/register")
async def scitt_register(request: Request) -> Response:
    """
    Register a SCITT Signed Statement and return a Receipt.

    Accepts: application/cose
    Returns: application/cose (COSE_Sign1 receipt)
    Header:  X-Scitt-Entry-Id
    """
    body = await request.body()
    if not body:
        raise HTTPException(status_code=400, detail="Empty request body")

    svc = _get_service_key()

    # Validate statement structure before issuing receipt
    try:
        stmt = parse_scitt_statement(body)
    except SCITTVerificationError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid SCITT statement: {exc}") from exc

    # Create receipt
    try:
        receipt_bytes = create_scitt_receipt(
            body, svc.private_key, kid=b"epilabs-scitt"
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"Failed to create receipt: {exc}"
        ) from exc

    # Derive entry ID from statement hash
    entry_id = hashlib.sha256(body).hexdigest()[:32]

    # Store in registry
    _registry[entry_id] = RegistryEntry(
        statement_bytes=body,
        receipt_bytes=receipt_bytes,
        registered_at=datetime.now(UTC).isoformat(),
        entry_id=entry_id,
    )

    return Response(
        content=receipt_bytes,
        media_type="application/cose",
        headers={"X-Scitt-Entry-Id": entry_id},
    )


@router.get("/keys")
async def scitt_keys() -> dict:
    """Return the SCITT service's Ed25519 public key."""
    svc = _get_service_key()
    return {"public_key": svc.public_key_hex}


@router.get("/entries/{entry_id}")
async def scitt_entry(entry_id: str) -> dict:
    """Lookup a registered statement by entry ID."""
    entry = _registry.get(entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    return {
        "entry_id": entry.entry_id,
        "registered_at": entry.registered_at,
        "statement_hash": hashlib.sha256(entry.statement_bytes).hexdigest(),
    }
