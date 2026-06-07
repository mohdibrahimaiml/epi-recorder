"""
SCITT Transparency Service routes for the EPI Verify Portal.

Mounted at /scitt/* on the existing FastAPI app. Provides:
    POST /register        — Submit a COSE_Sign1 Signed Statement, get a Receipt
    GET  /keys            — Fetch the service's Ed25519 public key
    GET  /entries/{id}    — Lookup a registered statement by entry ID
    GET  /tree-head       — Get the current signed tree head (Merkle root)
    GET  /proof/{id}      — Get inclusion proof for a registered entry

The service now maintains a proper Merkle tree and produces inclusion proofs
in receipts. This implements the SCITT transparency log pattern where each
receipt cryptographically proves inclusion at a specific position.

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

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from fastapi import APIRouter, HTTPException, Request, Response

from epi_core.scitt import (
    SCITTRegistrationError,
    SCITTVerificationError,
    create_scitt_receipt_with_proof,
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
# Merkle tree
# ─────────────────────────────────────────────────────────────


def _merkle_root(hashes: list[bytes]) -> bytes:
    """Compute a Merkle tree root from leaf hashes (SHA-256)."""
    if not hashes:
        return hashlib.sha256(b"").digest()
    level = list(hashes)
    while len(level) > 1:
        next_level = []
        for i in range(0, len(level), 2):
            left = level[i]
            right = level[i + 1] if i + 1 < len(level) else left
            node = hashlib.sha256(b"\x01" + left + right).digest()
            next_level.append(node)
        level = next_level
    return level[0]


def _compute_leaf_hash(tree_index: int, entry_hash: bytes) -> bytes:
    """Compute the leaf hash for a given entry at its tree position."""
    idx_bytes = tree_index.to_bytes(8, "big")
    return hashlib.sha256(b"\x00" + idx_bytes + entry_hash).digest()


def _audit_path(leaf_hashes: list[bytes], index: int) -> list[tuple[bytes, bool]]:
    """Compute the audit path for a leaf at the given index.

    Returns list of (sibling_hash, is_right) tuples.
    """
    path: list[tuple[bytes, bool]] = []
    level = list(leaf_hashes)
    idx = index
    while len(level) > 1:
        if idx % 2 == 0:
            sibling = level[idx + 1] if idx + 1 < len(level) else level[idx]
            path.append((sibling, False))  # sibling is to the right
        else:
            sibling = level[idx - 1]
            path.append((sibling, True))  # sibling is to the left
        next_level = []
        for i in range(0, len(level), 2):
            left = level[i]
            right = level[i + 1] if i + 1 < len(level) else left
            node = hashlib.sha256(b"\x01" + left + right).digest()
            next_level.append(node)
        level = next_level
        idx = idx // 2
    return path


def _verify_audit_path(
    leaf_hash: bytes, leaf_index: int, audit_path: list[tuple[bytes, bool]], root: bytes
) -> bool:
    """Verify an audit path by recomputing the root."""
    h = leaf_hash
    idx = leaf_index
    for sibling, is_left_sibling in audit_path:
        if is_left_sibling:
            h = hashlib.sha256(b"\x01" + sibling + h).digest()
        else:
            h = hashlib.sha256(b"\x01" + h + sibling).digest()
        idx //= 2
    return h == root


# ─────────────────────────────────────────────────────────────
# Signed Tree Head
# ─────────────────────────────────────────────────────────────


def _sign_tree_head(
    root_hash: bytes,
    tree_size: int,
    timestamp: str,
    private_key: ServiceKey,
) -> dict:
    """Produce a signed tree head."""
    payload = hashlib.sha256(
        root_hash + tree_size.to_bytes(8, "big") + timestamp.encode()
    ).digest()
    import cbor2
    from cryptography.exceptions import InvalidSignature

    sig = private_key.private_key.sign(payload)
    return {
        "root_hash": root_hash.hex(),
        "tree_size": tree_size,
        "timestamp": timestamp,
        "signature": sig.hex(),
    }


def _verify_tree_head(sth: dict, public_key_hex: str) -> bool:
    """Verify a signed tree head."""
    try:
        root_hash = bytes.fromhex(sth["root_hash"])
        tree_size = sth["tree_size"]
        timestamp = sth["timestamp"]
        signature = bytes.fromhex(sth["signature"])
        payload = hashlib.sha256(
            root_hash + tree_size.to_bytes(8, "big") + timestamp.encode()
        ).digest()
        pk = Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key_hex))
        pk.verify(signature, payload)
        return True
    except Exception:
        return False


# ─────────────────────────────────────────────────────────────
# In-memory registry
# ─────────────────────────────────────────────────────────────


@dataclass
class RegistryEntry:
    statement_bytes: bytes
    entry_hash: bytes  # SHA-256 of statement bytes
    receipt_bytes: bytes
    registered_at: str
    entry_id: str
    tree_index: int


_registry: list[RegistryEntry] = []
_registry_index: int = 0


def _current_tree_state() -> tuple[bytes, list[bytes]]:
    """Return (root_hash, leaf_hashes) for the current registry."""
    if not _registry:
        return hashlib.sha256(b"").digest(), []
    leaf_hashes = [
        _compute_leaf_hash(entry.tree_index, entry.entry_hash)
        for entry in _registry
    ]
    root = _merkle_root(leaf_hashes)
    return root, leaf_hashes


# ─────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────


@router.post("/register")
async def scitt_register(request: Request) -> Response:
    """
    Register a SCITT Signed Statement and return a Merkle-tree-backed Receipt.

    Accepts: application/cose
    Returns: application/cose (COSE_Sign1 receipt with inclusion proof)
    Header:  X-Scitt-Entry-Id
    """
    body = await request.body()
    if not body:
        raise HTTPException(status_code=400, detail="Empty request body")

    svc = _get_service_key()
    global _registry_index

    # Validate statement structure before issuing receipt
    try:
        stmt = parse_scitt_statement(body)
    except SCITTVerificationError as exc:
        raise HTTPException(
            status_code=400, detail=f"Invalid SCITT statement: {exc}"
        ) from exc

    # Derive entry ID and compute hashes
    entry_hash = hashlib.sha256(body).digest()
    entry_id = entry_hash.hex()[:32]
    tree_index = _registry_index
    _registry_index += 1

    # Compute leaf hash and build Merkle tree
    leaf_hash = _compute_leaf_hash(tree_index, entry_hash)

    # Get current tree state (before adding)
    _, prev_leaf_hashes = _current_tree_state()
    prev_leaf_hashes.append(leaf_hash)
    root = _merkle_root(prev_leaf_hashes)
    tree_size = len(prev_leaf_hashes)
    now_ts = datetime.now(UTC).isoformat()

    # Compute audit path for this leaf
    path = _audit_path(prev_leaf_hashes, tree_index)

    # Build signed tree head
    sth = _sign_tree_head(root, tree_size, now_ts, svc)

    # Build inclusion proof as CBOR
    import cbor2

    proof_data = cbor2.dumps({
        2: tree_index,
        3: [[sibling.hex(), is_left] for sibling, is_left in path],
        4: sth,
        5: tree_size,
    })

    # Sign receipt with service key — proof embedded in unprotected headers
    import json

    receipt_bytes = create_scitt_receipt_with_proof(
        body,
        svc.private_key,
        proof_data=proof_data,
        kid=b"epilabs-scitt",
    )

    # Store in registry
    _registry.append(RegistryEntry(
        statement_bytes=body,
        entry_hash=entry_hash,
        receipt_bytes=receipt_bytes,
        registered_at=now_ts,
        entry_id=entry_id,
        tree_index=tree_index,
    ))

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
    for entry in _registry:
        if entry.entry_id == entry_id:
            return {
                "entry_id": entry.entry_id,
                "registered_at": entry.registered_at,
                "statement_hash": entry.entry_hash.hex(),
                "tree_index": entry.tree_index,
            }
    raise HTTPException(status_code=404, detail="Entry not found")


@router.get("/tree-head")
async def scitt_tree_head() -> dict:
    """Get the current signed tree head."""
    svc = _get_service_key()
    root, leaf_hashes = _current_tree_state()
    tree_size = len(_registry)
    now_ts = datetime.now(UTC).isoformat()
    return _sign_tree_head(root, tree_size, now_ts, svc)


@router.get("/proof/{entry_id}")
async def scitt_proof(entry_id: str) -> dict:
    """Get the inclusion proof for a registered entry."""
    for entry in _registry:
        if entry.entry_id == entry_id:
            leaf_hashes = [
                _compute_leaf_hash(e.tree_index, e.entry_hash)
                for e in _registry
            ]
            path = _audit_path(leaf_hashes, entry.tree_index)
            return {
                "entry_id": entry.entry_id,
                "tree_index": entry.tree_index,
                "audit_path": [[s.hex(), is_left] for s, is_left in path],
                "root_hash": _merkle_root(leaf_hashes).hex(),
            }
    raise HTTPException(status_code=404, detail="Entry not found")
