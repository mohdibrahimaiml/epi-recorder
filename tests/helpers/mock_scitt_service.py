"""
Mock SCITT Transparency Service for unit tests.

Provides an in-memory SCITT service that can:
- Accept Signed Statements (COSE_Sign1)
- Return Receipts (COSE_Sign1 signed by the service)
- Verify its own receipts

No HTTP involved — direct Python method calls for fast, deterministic tests.
"""

from __future__ import annotations

from datetime import UTC

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
)

from epi_core.scitt import (
    SCITTServiceInfo,
    create_scitt_receipt,
    parse_scitt_statement,
    verify_scitt_receipt,
)


class MockSCITTService:
    """
    In-memory SCITT transparency service for testing.

    Usage:
        service = MockSCITTService()
        receipt_bytes, info = service.register(statement_bytes)
        assert verify_scitt_receipt(receipt_bytes, statement_bytes, service.public_key_bytes)
    """

    def __init__(self) -> None:
        self._private_key = Ed25519PrivateKey.generate()
        self._public_key = self._private_key.public_key()
        self._registry: dict[str, bytes] = {}  # statement_hash -> receipt

    @property
    def public_key_bytes(self) -> bytes:
        """Raw Ed25519 public key bytes (32 bytes)."""
        return self._public_key.public_bytes_raw()

    def register(self, statement_bytes: bytes) -> tuple[bytes, SCITTServiceInfo]:
        """
        Register a Signed Statement and return a Receipt.

        Validates the statement structure before issuing a receipt.
        """
        # Validate statement structure
        parse_scitt_statement(statement_bytes)

        # Create receipt
        receipt_bytes = create_scitt_receipt(
            statement_bytes,
            self._private_key,
            kid=b"mock-scitt",
        )

        # Store in registry
        import hashlib
        stmt_hash = hashlib.sha256(statement_bytes).hexdigest()
        self._registry[stmt_hash] = receipt_bytes

        from datetime import datetime
        info = SCITTServiceInfo(
            service_url="https://mock-scitt.example.com",
            entry_id=stmt_hash[:32],
            registered_at=datetime.now(UTC).isoformat(),
        )

        return receipt_bytes, info

    def verify(self, receipt_bytes: bytes, statement_bytes: bytes) -> bool:
        """Verify a receipt against a statement using the service's public key."""
        return verify_scitt_receipt(receipt_bytes, statement_bytes, self.public_key_bytes)

    def get_public_key_hex(self) -> str:
        """Return the service public key as hex."""
        return self.public_key_bytes.hex()
