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
    1. Compute canonical JSON hash of manifest (excluding signature field)
    2. Sign the hash with Ed25519 private key
    3. Encode signature as hex
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
        
        # Encode as hex with key name prefix
        signature_hex = signature_bytes.hex()
        signature_str = f"ed25519:{key_name}:{signature_hex}"
        
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
        # Parse signature (format: "ed25519:keyname:hexsig")
        parts = manifest.signature.split(":", 2)
        if len(parts) != 3:
            return (False, "Invalid signature format")
        
        algorithm, key_name, signature_hex = parts
        
        if algorithm != "ed25519":
            return (False, f"Unsupported signature algorithm: {algorithm}")

        # Decode signature — hex (current format) or base64 (legacy format)
        try:
            signature_bytes = bytes.fromhex(signature_hex)
        except ValueError:
            try:
                signature_bytes = base64.b64decode(signature_hex)
            except Exception:
                return (False, "Invalid signature encoding (not hex or base64)")
        
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


def decode_embedded_public_key(public_key_value: str) -> bytes:
    """
    Decode an embedded manifest public key.

    Current artifacts store the key as raw hex, but some legacy or externally
    produced artifacts may still carry a base64-encoded raw key string.
    """
    try:
        return bytes.fromhex(public_key_value)
    except ValueError:
        try:
            return base64.b64decode(public_key_value)
        except Exception as e:
            raise VerificationError(f"Invalid embedded public key: {e}") from e


def verify_embedded_manifest_signature(
    manifest: ManifestModel,
) -> tuple[Optional[bool], Optional[str], str]:
    """
    Verify a manifest using the public key embedded inside the manifest itself.

    Returns:
        tuple:
            signature_valid: True, False, or None when no signature exists
            signer_name: extracted signer key name when present
            message: human-readable verification result
    """
    signer_name = get_signer_name(manifest.signature)

    if not manifest.signature:
        return (None, signer_name, "No signature present")

    if not manifest.public_key:
        return (False, signer_name, "No public key embedded in manifest")

    try:
        public_key_bytes = decode_embedded_public_key(manifest.public_key)
    except VerificationError as exc:
        return (False, signer_name, str(exc))

    signature_valid, message = verify_signature(manifest, public_key_bytes)
    return (signature_valid, signer_name, message)


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
        signature: Signature string (format: "ed25519:keyname:hexsig")
        
    Returns:
        str: Key name, or None if signature is invalid/missing
    """
    if not signature:
        return None
    
    parts = signature.split(":", 2)
    if len(parts) != 3:
        return None
    
    return parts[1]


class TrustRegistry:
    """
    Registry of trusted public keys for independent verification.
    
    Now supports:
    1. Local Trusted Keys (~/.epi/trusted_keys/*.pub)
    2. Local Revocation List (~/.epi/trusted_keys/*.revoked)
    3. DID:WEB Resolution (W3C standard, zero-cost hosting)
    4. Remote Anchoring (via registry_url fetching)
    """
    def __init__(
        self, 
        trusted_keys_dir: Optional[Path] = None,
        registry_url: Optional[str] = None
    ):
        import os
        env_dir = os.environ.get("EPI_TRUSTED_KEYS_DIR")
        self.trusted_keys_dir = trusted_keys_dir or (Path(env_dir) if env_dir else (Path.home() / ".epi" / "trusted_keys"))
        self.registry_url = registry_url

    def _verify_did_web(self, did: str, public_key_hex: str) -> tuple[bool, Optional[str], str]:
        """
        Resolve did:web and compare the resolved public key.
        
        Returns:
            (is_trusted, identity_name, status_detail)
        """
        try:
            from epi_core.did_web import resolve_did_web, extract_ed25519_key, DidResolutionError, KeyNotFoundError
            did_document = resolve_did_web(did)
            resolved_key = extract_ed25519_key(did_document)
        except DidResolutionError as exc:
            return False, None, f"DID resolution failed: {exc}"
        except KeyNotFoundError as exc:
            return False, None, f"DID document valid but no Ed25519 key: {exc}"
        except Exception as exc:
            return False, None, f"DID verification error: {exc}"

        if resolved_key.lower() == public_key_hex.lower():
            did_name = did_document.get("id", did)
            return True, did_name, f"Verified via DID:WEB ({did})"

        return False, None, "DID resolved but public key mismatch — possible impersonation"

    def verify_key_trust(
        self,
        public_key_hex: str,
        governance: Optional[dict] = None,
    ) -> tuple[bool, Optional[str], str]:
        """
        Check if a public key is trusted, revoked, or unknown.
        
        Args:
            public_key_hex: Hex-encoded public key from the manifest.
            governance: Optional governance dict (may contain 'did' field).
        
        Returns:
            tuple: (is_trusted: bool, identity_name: str, status_detail: str)
        """
        # 1. Check Revocation First
        if self.trusted_keys_dir.exists():
            for rev_file in self.trusted_keys_dir.glob("*.revoked"):
                try:
                    if public_key_hex in rev_file.read_text().strip():
                        return False, rev_file.stem, "REVOKED: This key has been explicitly compromised or retired."
                except Exception:
                    continue

        # 2. Local trusted keys
        if self.trusted_keys_dir.exists():
            for pub_file in self.trusted_keys_dir.glob("*.pub"):
                try:
                    if public_key_hex in pub_file.read_text().strip():
                        return True, pub_file.stem, "Verified via local trusted registry"
                except Exception:
                    continue
        
        # 3. DID:WEB Resolution (zero-cost, issuer-independent)
        if governance and isinstance(governance, dict):
            did = governance.get("did")
            if did and isinstance(did, str) and did.startswith("did:web:"):
                return self._verify_did_web(did, public_key_hex)
        
        # 4. Remote Registry (Bootstrap / Anchor)
        if self.registry_url:
            try:
                # In a real implementation, this would use a secure fetch + cache
                # For now, we simulate the 'Independent Verifiability' path
                import requests
                resp = requests.get(self.registry_url, timeout=5)
                if resp.status_code == 200:
                    remote_data = resp.json()
                    if public_key_hex in remote_data.get("trusted_keys", {}):
                        return True, remote_data["trusted_keys"][public_key_hex], f"Verified via remote anchor: {self.registry_url}"
                    if public_key_hex in remote_data.get("revoked_keys", []):
                        return False, "Unknown", "REVOKED via remote anchor"
            except Exception as e:
                return False, None, f"Remote registry check failed: {e}"

        # 5. Known Official Keys (EPI Labs)
        EPI_LABS_OFFICIAL_PUB = "5e75e81a25b54859ba05898b7670f152"
        if public_key_hex == EPI_LABS_OFFICIAL_PUB:
            return True, "EPI Labs (Official)", "Verified via built-in trust root"

        return False, None, "UNKNOWN: Identity not found in any trusted registry"


from enum import Enum

class VerificationPolicy(str, Enum):
    """Governance policies for artifact acceptance."""
    PERMISSIVE = "permissive"  # Valid integrity only
    STANDARD = "standard"      # Valid integrity + not revoked
    STRICT = "strict"          # Valid integrity + trusted identity + completeness

def create_verification_report(
    integrity_ok: bool,
    signature_valid: Optional[bool],
    signer_name: Optional[str],
    mismatches: dict[str, str],
    manifest: ManifestModel,
    trusted_registry: Optional[TrustRegistry] = None,
    # New forensic facts
    sequence_ok: bool = True,
    completeness_ok: bool = True,
) -> dict:
    """
    Create a structured verification report separating Facts and Identity.
    Matches the 'Truth Engine' design pattern.
    """
    # 1. Identity Layer
    is_trusted_identity = False
    identity_name = None
    status_detail = "Registry check not performed"
    identity_status = "UNKNOWN"
    
    if manifest.public_key and trusted_registry:
        is_trusted_identity, identity_name, status_detail = trusted_registry.verify_key_trust(
            manifest.public_key,
            governance=manifest.governance,
        )
        if "REVOKED" in status_detail:
            identity_status = "REVOKED"
        elif "mismatch" in status_detail.lower() or "impersonation" in status_detail.lower():
            identity_status = "MISMATCH"
        elif is_trusted_identity:
            identity_status = "KNOWN"

    # 2. Fact Layer (Objective Evidence)
    report = {
        "facts": {
            "integrity_ok": integrity_ok,
            "signature_valid": signature_valid,
            "sequence_ok": sequence_ok,
            "completeness_ok": completeness_ok,
            "has_signature": manifest.signature is not None,
            "mismatches": mismatches,
        },
        "identity": {
            "status": identity_status,
            "name": identity_name or signer_name,
            "detail": status_detail,
            "registry_verified": is_trusted_identity,
            "public_key_id": manifest.public_key[:16] if manifest.public_key else None,
            "did": (manifest.governance or {}).get("did") if manifest.governance else None,
        },
        "metadata": {
            "spec_version": manifest.spec_version,
            "workflow_id": str(manifest.workflow_id),
            "created_at": manifest.created_at.isoformat(),
            "files_checked": len(manifest.file_manifest),
        }
    }

    # 3. Summary Layer (Unified state for quick lookup)
    report["summary"] = {
        "integrity": "VALID" if (integrity_ok and sequence_ok and completeness_ok) else "FAILED",
        "trust": identity_status if signature_valid is True else ("UNTRUSTED" if signature_valid is False else "UNSIGNED"),
    }

    # Legacy field support for backward compatibility with existing tests/UI
    # Note: These are now derived from the structured data above.
    report["integrity_ok"] = integrity_ok
    report["signature_valid"] = signature_valid
    report["identity_trusted"] = is_trusted_identity
    report["has_signature"] = manifest.signature is not None
    # Trust level requires both valid signature AND known trusted identity
    if identity_status == "MISMATCH":
        report["trust_level"] = "FAIL"   # Active impersonation attack detected
    elif identity_status == "REVOKED":
        report["trust_level"] = "INVALID"
    elif integrity_ok and signature_valid is True and identity_status == "KNOWN":
        report["trust_level"] = "HIGH"
    elif integrity_ok and signature_valid is True:
        report["trust_level"] = "LOW"   # Valid signature but unknown identity
    elif integrity_ok and signature_valid is None:
        report["trust_level"] = "MEDIUM"
    else:
        report["trust_level"] = "NONE"
    report["mismatches_count"] = len(mismatches)
    report["signer"] = signer_name
    report["files_checked"] = len(manifest.file_manifest)
    report["workflow_id"] = str(manifest.workflow_id)
    report["created_at"] = manifest.created_at.isoformat()
    report["spec_version"] = manifest.spec_version

    # Human-readable trust message for backward compatibility
    if identity_status == "MISMATCH":
        report["trust_message"] = "Identity mismatch - possible impersonation attack"
    elif identity_status == "REVOKED":
        report["trust_message"] = "Identity revoked - do not trust"
    elif report["trust_level"] == "HIGH":
        report["trust_message"] = "Cryptographically verified and integrity intact"
    elif report["trust_level"] == "MEDIUM":
        report["trust_message"] = "Unsigned but integrity intact"
    elif report["trust_level"] == "LOW":
        report["trust_message"] = "Valid signature from unknown identity - verify signer before trusting"
    elif report["trust_level"] == "INVALID":
        report["trust_message"] = "Invalid signature - do not trust"
    else:
        report["trust_message"] = "Integrity compromised - do not trust"

    return report

def apply_policy(report: dict, policy: VerificationPolicy = VerificationPolicy.STANDARD) -> dict:
    """
    Evaluate a verification report against a specific governance policy.
    Separates the 'Decision' from the 'Proof'.
    """
    facts = report["facts"]
    identity = report["identity"]
    
    decision = {
        "policy": policy.value,
        "status": "FAIL",
        "reason": "Policy requirements not met"
    }

    # Base requirements: Integrity must always be valid
    if not facts["integrity_ok"]:
        decision["reason"] = "Integrity compromised (file tampering detected)"
    elif not facts["sequence_ok"]:
        decision["reason"] = "Audit failure (sequence gap detected)"
    elif facts["signature_valid"] is False:
        decision["reason"] = "Invalid signature"
    
    # Policy-specific logic
    elif policy == VerificationPolicy.PERMISSIVE:
        # Integrity is enough
        decision["status"] = "PASS"
        decision["reason"] = "Integrity verified (Permissive Policy)"

    elif policy == VerificationPolicy.STANDARD:
        # Integrity + not revoked + not mismatched
        if identity["status"] == "REVOKED":
            decision["reason"] = "Identity revoked"
        elif identity["status"] == "MISMATCH":
            decision["status"] = "FAIL"
            decision["reason"] = "Identity mismatch - possible impersonation attack"
        else:
            decision["status"] = "PASS"
            decision["reason"] = "Integrity verified and identity not revoked"

    elif policy == VerificationPolicy.STRICT:
        # Integrity + known identity + completeness
        if identity["status"] != "KNOWN":
            decision["reason"] = "Identity unknown or revoked (Strict Policy requires trusted signer)"
        elif not facts["completeness_ok"]:
             decision["reason"] = "Evidence incomplete (Strict Policy requires full telemetry coverage)"
        else:
            decision["status"] = "PASS"
            decision["reason"] = "All strict criteria met (Integrity, Identity, Completeness)"

    report["decision"] = decision
    return report
