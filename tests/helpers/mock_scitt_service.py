"""
Mock SCITT Transparency Service for unit tests.

Provides an in-memory SCITT service with Merkle tree support that can:
- Accept Signed Statements (COSE_Sign1)
- Return Merkle-backed Receipts with inclusion proofs
- Verify its own receipts
- Serve signed tree heads

No HTTP involved — direct Python method calls for fast, deterministic tests.
"""

from __future__ import annotations

from datetime import UTC, datetime

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from epi_core.scitt import (
    SCITTServiceInfo,
    create_scitt_receipt_with_proof,
    parse_scitt_statement,
    verify_scitt_receipt,
)

# ── Merkle tree utilities ──────────────────────────────────────────────────


def _merkle_root(hashes: list[bytes]) -> bytes:
    import hashlib
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
    import hashlib
    idx_bytes = tree_index.to_bytes(8, "big")
    return hashlib.sha256(b"\x00" + idx_bytes + entry_hash).digest()


def _audit_path(leaf_hashes: list[bytes], index: int) -> list[tuple[bytes, bool]]:
    path: list[tuple[bytes, bool]] = []
    level = list(leaf_hashes)
    idx = index
    while len(level) > 1:
        if idx % 2 == 0:
            sibling = level[idx + 1] if idx + 1 < len(level) else level[idx]
            path.append((sibling, False))
        else:
            sibling = level[idx - 1]
            path.append((sibling, True))
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
    import hashlib
    h = leaf_hash
    for sibling, is_left_sibling in audit_path:
        if is_left_sibling:
            h = hashlib.sha256(b"\x01" + sibling + h).digest()
        else:
            h = hashlib.sha256(b"\x01" + h + sibling).digest()
    return h == root


# ── Signed Tree Head ───────────────────────────────────────────────────────


class MockSCITTService:
    """
    In-memory SCITT transparency service for testing with Merkle tree support.

    Usage:
        service = MockSCITTService()
        receipt_bytes, info = service.register(statement_bytes)
        proof = service.get_proof(info.entry_id)
        assert service.verify_with_proof(receipt_bytes, statement_bytes, proof)
    """

    def __init__(self) -> None:
        self._private_key = Ed25519PrivateKey.generate()
        self._public_key = self._private_key.public_key()
        self._registry: list[dict] = []
        self._index: int = 0

    @property
    def public_key_bytes(self) -> bytes:
        """Raw Ed25519 public key bytes (32 bytes)."""
        return self._public_key.public_bytes_raw()

    def register(self, statement_bytes: bytes) -> tuple[bytes, SCITTServiceInfo]:
        """Register a Signed Statement and return a Merkle-backed Receipt."""
        import hashlib
        import cbor2

        # Validate statement structure
        parse_scitt_statement(statement_bytes)

        entry_hash = hashlib.sha256(statement_bytes).digest()
        entry_id = entry_hash.hex()[:32]
        tree_index = self._index
        self._index += 1

        # Compute leaf hash
        leaf_hash = _compute_leaf_hash(tree_index, entry_hash)

        # Compute current tree with new leaf
        existing_hashes = [e["leaf_hash"] for e in self._registry]
        existing_hashes.append(leaf_hash)
        root = _merkle_root(existing_hashes)
        tree_size = len(existing_hashes)
        now_ts = datetime.now(UTC).isoformat()

        # Audit path
        path = _audit_path(existing_hashes, tree_index)

        # Signed tree head
        import hashlib as hl
        payload = hl.sha256(root + tree_size.to_bytes(8, "big") + now_ts.encode()).digest()
        sth_sig = self._private_key.sign(payload)
        sth = {
            "root_hash": root.hex(),
            "tree_size": tree_size,
            "timestamp": now_ts,
            "signature": sth_sig.hex(),
        }

        # Build receipt — the payload is the statement hash
        # (compatible with verify_scitt_receipt), and the inclusion proof
        # is embedded in unprotected headers as extra CBOR data.
        import struct
        proof_data = cbor2.dumps({
            2: tree_index,
            3: [[s.hex(), is_left] for s, is_left in path],
            4: sth,
            5: tree_size,
        })
        receipt_bytes = create_scitt_receipt_with_proof(
            statement_bytes,
            self._private_key,
            proof_data=proof_data,
            kid=b"mock-scitt",
        )

        self._registry.append({
            "entry_hash": entry_hash,
            "leaf_hash": leaf_hash,
            "entry_id": entry_id,
            "tree_index": tree_index,
            "receipt_bytes": receipt_bytes,
            "registered_at": now_ts,
        })

        info = SCITTServiceInfo(
            service_url="https://mock-scitt.example.com",
            entry_id=entry_id,
            registered_at=now_ts,
        )

        return receipt_bytes, info

    def verify(self, receipt_bytes: bytes, statement_bytes: bytes) -> bool:
        """Verify a receipt against a statement using the service's public key."""
        return verify_scitt_receipt(receipt_bytes, statement_bytes, self.public_key_bytes)

    def get_proof(self, entry_id: str) -> dict | None:
        """Get the inclusion proof for a registered entry."""
        for entry in self._registry:
            if entry["entry_id"] == entry_id:
                hashes = [e["leaf_hash"] for e in self._registry]
                path = _audit_path(hashes, entry["tree_index"])
                return {
                    "tree_index": entry["tree_index"],
                    "audit_path": path,
                    "entry_id": entry_id,
                }
        return None

    def verify_with_proof(
        self, receipt_bytes: bytes, statement_bytes: bytes, proof: dict
    ) -> bool:
        """Verify a receipt with inclusion proof."""
        import hashlib

        if not verify_scitt_receipt(receipt_bytes, statement_bytes, self.public_key_bytes):
            return False

        entry_hash = hashlib.sha256(statement_bytes).digest()
        leaf_hash = _compute_leaf_hash(proof["tree_index"], entry_hash)

        hashes = [e["leaf_hash"] for e in self._registry]
        root = _merkle_root(hashes)

        return _verify_audit_path(leaf_hash, proof["tree_index"], proof["audit_path"], root)

    def get_public_key_hex(self) -> str:
        """Return the service public key as hex."""
        return self.public_key_bytes.hex()
