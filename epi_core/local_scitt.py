"""
Local SCITT transparency service for offline/CI compliance.

This module provides a lightweight, file-based SCITT transparency service that
works after a plain ``pip install epi-recorder`` without extra dependencies.
It maintains:

  * A separate Ed25519 service keypair in ``~/.epi/local-scitt/service.{key,pub}``
  * An append-only JSONL ledger in ``~/.epi/local-scitt/log.jsonl``
  * A Merkle tree over the ledger, with inclusion proofs embedded in receipts

Because the service key is independent from the artifact-signing key, receipts
produced here satisfy the SCITT separation-of-duties model locally.  For a
production AIUC-1 audit you should still point ``epi scitt register`` at a
public or organizational SCITT service, but this local service is sufficient
for development, CI, and air-gapped environments.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

import cbor2
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from epi_core.keys import KeyManager
from epi_core.scitt import (
    SCITTServiceInfo,
    _compute_leaf_hash,
    _merkle_root,
    create_scitt_receipt_with_proof,
)
from epi_core.time_utils import utc_now_iso

LOCAL_SCITT_SERVICE_URL = "local"


def _state_dir() -> Path:
    override = os.getenv("EPI_HOME")
    base = Path(override).expanduser() if override else Path.home() / ".epi"
    return base / "local-scitt"


def _service_private_key_path() -> Path:
    return _state_dir() / "service.key"


def _service_public_key_path() -> Path:
    return _state_dir() / "service.pub"


def _log_path() -> Path:
    return _state_dir() / "log.jsonl"


def _ensure_state_dir() -> Path:
    path = _state_dir()
    path.mkdir(parents=True, exist_ok=True)
    return path


def _generate_service_keypair() -> tuple[Ed25519PrivateKey, bytes]:
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    public_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )

    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    _ensure_state_dir()
    _service_private_key_path().write_bytes(private_pem)
    _service_public_key_path().write_bytes(public_pem)
    return private_key, public_bytes


def _load_service_private_key() -> Ed25519PrivateKey:
    path = _service_private_key_path()
    if not path.exists():
        return _generate_service_keypair()[0]
    return serialization.load_pem_private_key(path.read_bytes(), password=None)


def service_public_key() -> bytes:
    """Return the raw 32-byte Ed25519 public key of the local SCITT service."""
    path = _service_public_key_path()
    if not path.exists():
        return _generate_service_keypair()[1]
    public_key = serialization.load_pem_public_key(path.read_bytes())
    return public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )


def ensure_service_keypair() -> tuple[Ed25519PrivateKey, bytes]:
    """Load or create the local SCITT service keypair."""
    private_key = _load_service_private_key()
    return private_key, service_public_key()


def read_ledger() -> list[dict[str, Any]]:
    """Read the append-only local SCITT ledger."""
    path = _log_path()
    if not path.exists():
        return []
    entries: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return entries


def _leaf_hashes(entries: list[dict[str, Any]]) -> list[bytes]:
    return [
        _compute_leaf_hash(i, bytes.fromhex(e["statement_hash"]))
        for i, e in enumerate(entries)
    ]


def _compute_audit_path(
    leaf_hashes: list[bytes], leaf_index: int
) -> list[tuple[bytes, bool]]:
    """Build a Merkle audit path for ``leaf_index``."""
    path: list[tuple[bytes, bool]] = []
    level = list(leaf_hashes)
    index = leaf_index

    while len(level) > 1:
        if index % 2 == 0:
            sibling_index = index + 1 if index + 1 < len(level) else index
            is_left = False
        else:
            sibling_index = index - 1
            is_left = True
        path.append((level[sibling_index], is_left))

        next_level: list[bytes] = []
        for i in range(0, len(level), 2):
            left = level[i]
            right = level[i + 1] if i + 1 < len(level) else left
            next_level.append(hashlib.sha256(b"\x01" + left + right).digest())
        level = next_level
        index //= 2

    return path


def register_statement(statement_bytes: bytes) -> tuple[bytes, SCITTServiceInfo]:
    """
    Register a SCITT statement with the local transparency service.

    Returns the receipt bytes and service info.  The receipt contains a Merkle
    inclusion proof signed by the independent local SCITT service key.
    """
    private_key, _ = ensure_service_keypair()

    statement_hash = hashlib.sha256(statement_bytes).hexdigest()
    entry_id = statement_hash[:32]
    registered_at = utc_now_iso()

    entry = {
        "entry_id": entry_id,
        "statement_hash": statement_hash,
        "registered_at": registered_at,
    }

    _ensure_state_dir()
    with _log_path().open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, separators=(",", ":")) + "\n")

    entries = read_ledger()
    leaf_hashes = _leaf_hashes(entries)
    tree_index = len(entries) - 1
    tree_size = len(entries)
    root_hash = _merkle_root(leaf_hashes)
    audit_path = _compute_audit_path(leaf_hashes, tree_index)

    proof = {
        2: tree_index,
        3: [[h.hex(), is_left] for h, is_left in audit_path],
        4: {"tree_size": tree_size, "root_hash": root_hash.hex()},
    }
    proof_bytes = cbor2.dumps(proof)

    receipt_bytes = create_scitt_receipt_with_proof(
        statement_bytes, private_key, proof_bytes, kid=b"local-scitt"
    )

    info = SCITTServiceInfo(
        service_url=LOCAL_SCITT_SERVICE_URL,
        entry_id=entry_id,
        registered_at=registered_at,
    )
    return receipt_bytes, info
