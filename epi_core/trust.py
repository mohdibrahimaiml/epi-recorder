"""
EPI Core Trust - Cryptographic signing and verification using Ed25519.

Implements the trust layer for .epi files, ensuring authenticity and integrity
through digital signatures.
"""

import base64
from pathlib import Path
from typing import Optional

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives import serialization
from cryptography.exceptions import InvalidSignature

from epi_core.schemas import ManifestModel
from epi_core.serialize import get_canonical_hash


class SigningError(Exception):
    """Raised when signing operations fail."""
    pass


class VerificationError(Exception):
    """Raised when signature verification fails."""
    pass


def sign_manifest(
    manifest: ManifestModel,
    private_key: Ed25519PrivateKey,
    key_name: str = "default"
) -> ManifestModel:
    """
    Sign a manifest using Ed25519 private key.
    
    The signing process:
    1. Compute canonical CBOR hash of manifest (excluding signature field)
    2. Sign the hash with Ed25519 private key
    3. Encode signature as base64
    4. Return new manifest with signature field populated
    
    Args:
        manifest: Manifest to sign
        private_key: Ed25519 private key
        key_name: Name of the key used (for verification reference)
        
    Returns:
        ManifestModel: New manifest with signature
        
    Raises:
        SigningError: If signing fails
    """
    try:
        # Derive public key and add to manifest
        public_key_obj = private_key.public_key()
        public_key_hex = public_key_obj.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw
        ).hex()
        
        # We must update the manifest BEFORE hashing so the public key is signed
        manifest.public_key = public_key_hex

        # Compute canonical hash (excluding signature field)
        manifest_hash = get_canonical_hash(manifest, exclude_fields={"signature"})
        hash_bytes = bytes.fromhex(manifest_hash)
        
        # Sign the hash
        signature_bytes = private_key.sign(hash_bytes)
        
        # Encode as base64 with key name prefix
        signature_b64 = base64.b64encode(signature_bytes).decode("utf-8")
        signature_str = f"ed25519:{key_name}:{signature_b64}"
        
        # Create new manifest with signature
        manifest_dict = manifest.model_dump()
        manifest_dict["signature"] = signature_str
        
        return ManifestModel(**manifest_dict)
        
    except Exception as e:
        raise SigningError(f"Failed to sign manifest: {e}") from e


def verify_signature(
    manifest: ManifestModel,
    public_key_bytes: bytes
) -> tuple[bool, str]:
    """
    Verify manifest signature using Ed25519 public key.
    
    Args:
        manifest: Manifest to verify
        public_key_bytes: Raw Ed25519 public key bytes (32 bytes)
        
    Returns:
        tuple: (is_valid: bool, message: str)
    """
    # Check if manifest has signature
    if not manifest.signature:
        return (False, "No signature present")
    
    try:
        # Parse signature (format: "ed25519:keyname:base64sig")
        parts = manifest.signature.split(":", 2)
        if len(parts) != 3:
            return (False, "Invalid signature format")
        
        algorithm, key_name, signature_b64 = parts
        
        if algorithm != "ed25519":
            return (False, f"Unsupported signature algorithm: {algorithm}")
        
        # Decode signature
        signature_bytes = base64.b64decode(signature_b64)
        
        # Compute canonical hash (excluding signature field)
        manifest_hash = get_canonical_hash(manifest, exclude_fields={"signature"})
        hash_bytes = bytes.fromhex(manifest_hash)
        
        # Load public key
        public_key = Ed25519PublicKey.from_public_bytes(public_key_bytes)
        
        # Verify signature
        public_key.verify(signature_bytes, hash_bytes)
        
        return (True, f"Signature valid (key: {key_name})")
        
    except InvalidSignature:
        return (False, "Invalid signature - data may have been tampered")
    except Exception as e:
        return (False, f"Verification error: {str(e)}")


def sign_manifest_inplace(
    manifest_path: Path,
    private_key: Ed25519PrivateKey,
    key_name: str = "default"
) -> None:
    """
    Sign a manifest file in-place.
    
    This reads the manifest JSON, signs it, and writes back the updated version
    with the signature field populated.
    
    Args:
        manifest_path: Path to manifest.json file
        private_key: Ed25519 private key
        key_name: Name of the key used
        
    Raises:
        FileNotFoundError: If manifest doesn't exist
        SigningError: If signing fails
    """
    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifest not found: {manifest_path}")
    
    try:
        # Read manifest
        import json
        manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest = ManifestModel(**manifest_data)
        
        # Sign manifest
        signed_manifest = sign_manifest(manifest, private_key, key_name)
        
        # Write back
        manifest_path.write_text(
            signed_manifest.model_dump_json(indent=2),
            encoding="utf-8"
        )
        
    except Exception as e:
        raise SigningError(f"Failed to sign manifest in-place: {e}") from e


def get_signer_name(signature: Optional[str]) -> Optional[str]:
    """
    Extract signer key name from signature string.
    
    Args:
        signature: Signature string (format: "ed25519:keyname:base64sig")
        
    Returns:
        str: Key name, or None if signature is invalid/missing
    """
    if not signature:
        return None
    
    parts = signature.split(":", 2)
    if len(parts) != 3:
        return None
    
    return parts[1]


def create_verification_report(
    integrity_ok: bool,
    signature_valid: Optional[bool],
    signer_name: Optional[str],
    mismatches: dict[str, str],
    manifest: ManifestModel
) -> dict:
    """
    Create a structured verification report.
    
    Args:
        integrity_ok: Whether file integrity checks passed
        signature_valid: Whether signature is valid (None if no signature)
        signer_name: Name of the signing key
        mismatches: Dict of file mismatches
        manifest: Manifest being verified
        
    Returns:
        dict: Verification report
    """
    report = {
        "integrity_ok": integrity_ok,
        "signature_valid": signature_valid,
        "signer": signer_name,
        "has_signature": manifest.signature is not None,
        "spec_version": manifest.spec_version,
        "workflow_id": str(manifest.workflow_id),
        "created_at": manifest.created_at.isoformat(),
        "files_checked": len(manifest.file_manifest),
        "mismatches_count": len(mismatches),
        "mismatches": mismatches,
    }
    
    # Compute overall trust level
    if signature_valid and integrity_ok:
        report["trust_level"] = "HIGH"
        report["trust_message"] = "Cryptographically verified and integrity intact"
    elif signature_valid is None and integrity_ok:
        report["trust_level"] = "MEDIUM"
        report["trust_message"] = "Unsigned but integrity intact"
    elif signature_valid is False:
        report["trust_level"] = "NONE"
        report["trust_message"] = "Invalid signature - do not trust"
    else:
        report["trust_level"] = "NONE"
        report["trust_message"] = "Integrity compromised - do not trust"
    
    return report


