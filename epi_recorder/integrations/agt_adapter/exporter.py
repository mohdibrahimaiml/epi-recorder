"""Export EPI evidence as a signed receipt for AGT to reference.

This is NOT an AGT governance event exporter. It produces a cryptographic
evidence receipt that AGT can store via AuditLog.log(data={"epi_evidence": receipt}).

The receipt is a COSE Sign1 object containing:
- The canonical hash of the EPI manifest
- A hash of all execution steps
- Ed25519 signature from the EPI signing key

AGT stores this receipt opaquely. It does not interpret EPI internals.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from epi_core.container import EPIContainer
from epi_core.scitt import create_scitt_statement, SCITTVerificationError

from .errors import AGTIntegrationError


def export_evidence_receipt(
    epi_path: str | Path,
    issuer: str = "epi-recorder",
    kid: bytes = b"epi-default",
) -> bytes:
    """Generate a signed evidence receipt from an EPI artifact.

    Args:
        epi_path: Path to .epi file
        issuer: Issuer identifier for the receipt
        kid: Key identifier

    Returns:
        COSE Sign1 bytes — a signed evidence receipt

    Usage in AGT:
        receipt = export_evidence_receipt("trace.epi")
        audit.log(
            event_type="external_evidence",
            agent_did="did:web:epi.example.com",
            action="allow",
            resource="/evidence/receipt",
            data={"epi_evidence": receipt.hex()},  # Store receipt hex
            outcome="success",
        )
    """
    epi_path = Path(epi_path)
    if not epi_path.exists():
        raise AGTIntegrationError(f"EPI file not found: {epi_path}")

    # Load EPI manifest
    manifest = EPIContainer.read_manifest(epi_path)

    # Get signing key from manifest
    from epi_core.keys import KeyManager
    km = KeyManager()

    # Find the key that signed this artifact
    pub_key_hex = manifest.public_key or ""
    key_name = _find_key_by_pubkey(km, pub_key_hex) or "default"

    priv_key = km.load_private_key(key_name)

    # Create SCITT-style signed statement
    statement = create_scitt_statement(
        manifest=manifest,
        private_key=priv_key,
        issuer=issuer,
        kid=kid,
    )

    return statement


def verify_evidence_receipt(
    receipt_bytes: bytes,
    epi_path: str | Path,
) -> bool:
    """Verify that a receipt matches an EPI artifact.

    Args:
        receipt_bytes: COSE Sign1 receipt from export_evidence_receipt()
        epi_path: Path to .epi file

    Returns:
        True if receipt is valid for this artifact
    """
    from epi_core.scitt import verify_scitt_statement
    from epi_core.keys import KeyManager

    manifest = EPIContainer.read_manifest(Path(epi_path))
    km = KeyManager()
    pub_key_hex = manifest.public_key or ""
    key_name = _find_key_by_pubkey(km, pub_key_hex) or "default"
    pub_key = km.load_public_key(key_name)

    try:
        verify_scitt_statement(receipt_bytes, manifest, pub_key)
        return True
    except SCITTVerificationError:
        return False


def _find_key_by_pubkey(km, pub_key_hex: str) -> str | None:
    """Find key name by public key hex."""
    for key_info in km.list_keys():
        # Compare key identifiers — exact match not required
        if pub_key_hex and pub_key_hex in str(key_info.get("public_key", "")):
            return key_info["name"]
    return None


def build_agt_log_data(
    receipt_bytes: bytes,
    epi_path: str | Path,
    description: str = "EPI execution evidence",
) -> dict:
    """Build the data dict for AGT AuditLog.log() call.

    Returns a dict ready to pass as the 'data' parameter:

        audit.log(
            event_type="external_evidence",
            ...,
            data=build_agt_log_data(receipt_bytes, "trace.epi"),
        )
    """
    epi_path = Path(epi_path)
    manifest = EPIContainer.read_manifest(epi_path)

    return {
        "epi_evidence_hex": receipt_bytes.hex(),
        "epi_artifact_hash": _hash_file(epi_path),
        "epi_workflow_id": str(manifest.workflow_id),
        "epi_signature_valid": bool(manifest.signature),
        "evidence_type": "epi_signed_receipt",
        "description": description,
        "receipt_size_bytes": len(receipt_bytes),
    }


def _hash_file(path: Path) -> str:
    """SHA-256 hash of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()
