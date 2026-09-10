"""
EPI Core Trust - Cryptographic signing and verification using Ed25519.

Implements the trust layer for .epi files, ensuring authenticity and integrity
through digital signatures.
"""

import base64
import hashlib
from enum import StrEnum
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from epi_core.schemas import ManifestModel
from epi_core.serialize import get_canonical_hash


def _get_verifier_version() -> str:
    """Return the installed epi-recorder package version, or 'unknown'."""
    try:
        from importlib.metadata import version
        return version("epi-recorder")
    except Exception:
        return "unknown"


class SigningError(Exception):
    """Raised when signing operations fail."""

    pass


class VerificationError(Exception):
    """Raised when signature verification fails."""

    pass


def sign_manifest(
    manifest: ManifestModel, private_key: Ed25519PrivateKey, key_name: str = "default"
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
            encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw
        ).hex()

        # We must update the manifest BEFORE hashing so the public key is signed
        manifest_copy = manifest.model_copy(deep=True)
        manifest_copy.public_key = public_key_hex

        # Compute canonical hash (excluding signature field)
        manifest_hash = get_canonical_hash(manifest_copy, exclude_fields={"signature"})
        hash_bytes = bytes.fromhex(manifest_hash)

        # Sign the hash
        signature_bytes = private_key.sign(hash_bytes)

        # Encode as hex with derived key name prefix (cryptographically bound to public key)
        signature_hex = signature_bytes.hex()
        derived_key_name = hashlib.sha256(public_key_hex.encode("utf-8")).hexdigest()[:16]
        signature_str = f"ed25519:{derived_key_name}:{signature_hex}"

        # Create new manifest with signature
        manifest_dict = manifest_copy.model_dump()
        manifest_dict["signature"] = signature_str

        return ManifestModel(**manifest_dict)

    except Exception as e:
        raise SigningError(f"Failed to sign manifest: {e}") from e


def verify_signature(manifest: ManifestModel, public_key_bytes: bytes) -> tuple[bool, str]:
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

        # Cryptographically bind key_name to public key
        expected_key_name = hashlib.sha256(public_key_bytes.hex().encode("utf-8")).hexdigest()[:16]
        if key_name != expected_key_name:
            return (False, "Key name does not match public key")

        # Decode signature — hex (current format) or base64 (legacy format)
        try:
            signature_bytes = bytes.fromhex(signature_hex)
        except ValueError:
            try:
                signature_bytes = base64.b64decode(signature_hex, validate=True)
            except Exception:
                return (False, "Invalid signature encoding (not hex or base64)")
        if len(signature_bytes) != 64:
            return (False, f"Invalid signature length: expected 64 bytes, got {len(signature_bytes)}")
        if len(public_key_bytes) != 32:
            return (False, f"Invalid public key length: expected 32 bytes, got {len(public_key_bytes)}")

        # Dispatch by spec_version: CBOR (1.x) vs legacy json vs JCS (no trial)
        from epi_core._version import JCS_INTRODUCED_TUPLE, JCS_INTRODUCED_VERSION

        def _is_cbor():
            sv = getattr(manifest, "spec_version", "") or ""
            try:
                major = int(str(sv).lstrip("v").split(".")[0])
                return major == 1
            except Exception:
                return False

        def _is_legacy():
            if _is_cbor():
                return False
            sv = getattr(manifest, "spec_version", "") or ""
            try:
                parts = str(sv).lstrip("v").split(".")
                major = int(parts[0]) if parts[0] else 0
                minor = int(parts[1]) if len(parts) > 1 and parts[1] else 0
                patch = int(parts[2]) if len(parts) > 2 and parts[2].split("-")[0].isdigit() else 0
                # Legacy if < cutoff and not CBOR
                cutoff_major, cutoff_minor, cutoff_patch = JCS_INTRODUCED_TUPLE
                if major < cutoff_major:
                    return True
                if major == cutoff_major and minor < cutoff_minor:
                    return True
                if major == cutoff_major and minor == cutoff_minor and patch < cutoff_patch:
                    return True
                return False
            except Exception:
                return True  # unknown version → assume legacy for safety

        is_cbor = _is_cbor()
        is_legacy = _is_legacy()
        if is_cbor:
            # CBOR path — 1.x artifacts (guardrails)
            try:
                cbor_hash = get_canonical_hash(manifest, exclude_fields={"signature"}, format="cbor")
                public_key = Ed25519PublicKey.from_public_bytes(public_key_bytes)
                public_key.verify(signature_bytes, bytes.fromhex(cbor_hash))
                return (True, f"Signature valid (CBOR legacy, key: {key_name})")
            except InvalidSignature:
                return (False, "Invalid signature - data may have been tampered (CBOR)")
            except Exception as exc:
                return (False, f"Verification error (CBOR): {exc}")
        elif is_legacy:
            # Legacy path only — old json sort_keys
            try:
                from epi_core.serialize import _get_legacy_json_hash, omit_absent_optional_hash_fields
                from datetime import datetime, timezone
                from uuid import UUID

                def _norm(v):
                    if isinstance(v, datetime):
                        if v.tzinfo is None:
                            v = v.replace(microsecond=0, tzinfo=timezone.utc)
                        else:
                            v = v.astimezone(timezone.utc).replace(microsecond=0)
                        return v.strftime("%Y-%m-%dT%H:%M:%SZ")
                    if isinstance(v, UUID):
                        return str(v)
                    if isinstance(v, dict):
                        return {k: _norm(x) for k, x in v.items()}
                    if isinstance(v, list):
                        return [_norm(x) for x in v]
                    return v

                d = _norm(manifest.model_dump())
                omit_absent_optional_hash_fields(d, "ManifestModel")
                d.pop("signature", None)
                legacy_hash = _get_legacy_json_hash(d)
                public_key = Ed25519PublicKey.from_public_bytes(public_key_bytes)
                public_key.verify(signature_bytes, bytes.fromhex(legacy_hash))
                # Visible legacy warning — reviewer can see which path ran
                import warnings

                warnings.warn(
                    f"Verified via legacy canonicalization (spec_version={getattr(manifest,'spec_version','unknown')} <{JCS_INTRODUCED_VERSION})",
                    UserWarning,
                )
                return (True, f"Signature valid (legacy pre-{JCS_INTRODUCED_VERSION}, key: {key_name})")
            except InvalidSignature:
                return (False, "Invalid signature - data may have been tampered (legacy)")
            except Exception as exc:
                return (False, f"Verification error (legacy): {exc}")
        else:
            # JCS path only — current
            manifest_hash = get_canonical_hash(manifest, exclude_fields={"signature"})
            hash_bytes = bytes.fromhex(manifest_hash)
            public_key = Ed25519PublicKey.from_public_bytes(public_key_bytes)
            try:
                public_key.verify(signature_bytes, hash_bytes)
                return (True, f"Signature valid (key: {key_name})")
            except InvalidSignature:
                return (False, "Invalid signature - data may have been tampered")
    except InvalidSignature:
        return (False, "Invalid signature - data may have been tampered")
    except Exception as exc:
        return (False, f"Verification error: {exc}")


def decode_embedded_public_key(public_key_value: str) -> bytes:
    """
    Decode an embedded manifest public key.

    Public keys must be hex-encoded raw Ed25519 key bytes (64 hex chars = 32 bytes).
    """
    try:
        raw = bytes.fromhex(public_key_value.strip())
    except ValueError as e:
        raise VerificationError(f"Invalid embedded public key: {e}") from e
    if len(raw) != 32:
        raise VerificationError(f"Invalid embedded public key length: expected 32 bytes, got {len(raw)}")
    return raw


def verify_embedded_manifest_signature(
    manifest: ManifestModel,
) -> tuple[bool | None, str | None, str]:
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
    manifest_path: Path, private_key: Ed25519PrivateKey, key_name: str = "default"
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
        manifest_path.write_text(signed_manifest.model_dump_json(indent=2), encoding="utf-8")

    except Exception as e:
        raise SigningError(f"Failed to sign manifest in-place: {e}") from e


def get_signer_name(signature: str | None) -> str | None:
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

    def __init__(self, trusted_keys_dir: Path | None = None, registry_url: str | None = None):
        import os
        import warnings

        env_dir = os.environ.get("EPI_TRUSTED_KEYS_DIR")
        self.trusted_keys_dir = trusted_keys_dir or (
            Path(env_dir) if env_dir else (Path.home() / ".epi" / "trusted_keys")
        )
        # Default to EPI Labs public trust registry if no URL provided
        self.registry_url = registry_url or os.environ.get(
            "EPI_TRUSTED_REGISTRY_URL",
            "https://epilabs.org/.well-known/epi-trust-registry.json",
        )

        # AUD-IA-04: Warn when the trust registry is stored in the same directory as the signing key
        try:
            from epi_core.keys import _resolve_default_keys_dir
            keys_dir = _resolve_default_keys_dir()
            if keys_dir and self.trusted_keys_dir:
                if keys_dir.resolve() == self.trusted_keys_dir.resolve():
                    warnings.warn(
                        f"Trust registry directory '{self.trusted_keys_dir}' matches "
                        f"signing keys directory '{keys_dir}'. This violates AUD-IA-04 trust registry independence.",
                        UserWarning,
                    )
        except Exception:
            pass

    def _verify_did_web(self, did: str, public_key_hex: str) -> tuple[bool, str | None, str]:
        """
        Resolve did:web and compare the resolved public key.

        Returns:
            (is_trusted, identity_name, status_detail)
        """
        try:
            from epi_core.did_web import (
                DidResolutionError,
                KeyNotFoundError,
                extract_ed25519_key,
                resolve_did_web,
            )

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
        governance: dict | None = None,
    ) -> tuple[bool, str | None, str]:
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
                        return (
                            False,
                            rev_file.stem,
                            "REVOKED: This key has been explicitly compromised or retired.",
                        )
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
                        return (
                            True,
                            remote_data["trusted_keys"][public_key_hex],
                            f"Verified via remote anchor: {self.registry_url}",
                        )
                    if public_key_hex in remote_data.get("revoked_keys", []):
                        return False, "Unknown", "REVOKED via remote anchor"
            except Exception:
                # Network or parsing failure — don't block verification.
                # Fall through to built-in roots and UNKNOWN so offline
                # verification remains possible.
                pass

        return False, None, "UNKNOWN: Identity not found in any trusted registry"


class VerificationPolicy(StrEnum):
    """Governance policies for artifact acceptance."""

    PERMISSIVE = "permissive"  # Valid integrity only
    STANDARD = "standard"  # Valid integrity + not revoked
    STRICT = "strict"  # Valid integrity + trusted identity + completeness


def _match_local_signing_key_name(public_key_hex: str) -> str | None:
    """Return local key name if *public_key_hex* matches a key under KeyManager.keys_dir."""
    if not public_key_hex or len(public_key_hex) < 64:
        return None
    want = public_key_hex.strip().lower()
    try:
        from epi_core.keys import KeyManager

        km = KeyManager()
        for info in km.list_keys():
            name = info.get("name") or ""
            try:
                raw = km.load_public_key(name)
                if raw.hex().lower() == want:
                    return name
            except Exception:
                continue
    except Exception:
        return None
    return None


def sealed_payload_gate(manifest: ManifestModel, integrity_ok: bool) -> bool:
    """Fail integrity when the sealer admits it truncated step content."""
    if manifest.content_truncated is True:
        return False
    return integrity_ok


def create_verification_report(
    integrity_ok: bool,
    signature_valid: bool | None,
    signer_name: str | None,
    mismatches: dict[str, str],
    manifest: ManifestModel,
    trusted_registry: TrustRegistry | None = None,
    # New forensic facts
    sequence_ok: bool = True,
    completeness_ok: bool = True,
    chain_ok: bool = True,
    transparency_ok: bool | None = None,
    completeness_gaps: list[str] | None = None,
    forensic_reason: str | None = None,
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
    local_key_name: str | None = None

    if manifest.public_key and not trusted_registry:
        # Artifact is signed but caller supplied no registry to check against.
        # Make this explicit so operators know they should configure one.
        status_detail = (
            "No trusted keys registry configured — cannot verify signer identity. "
            "Populate ~/.epi/trusted_keys/ with the signer's .pub file or pass a "
            "TrustRegistry instance to enable identity verification."
        )

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

    # Local self-recognition: sealer key present on this machine (not org-pinned)
    if (
        identity_status == "UNKNOWN"
        and manifest.public_key
        and signature_valid is not False
    ):
        local_key_name = _match_local_signing_key_name(manifest.public_key)
        if local_key_name:
            identity_status = "LOCAL"
            identity_name = identity_name or local_key_name
            status_detail = (
                f"Matches local signing key '{local_key_name}' on this computer "
                "(not an org trust-list pin). Optional: epi keys trust <file.epi> "
                f"--name {local_key_name}"
            )

    # 2. Fact Layer (Objective Evidence)
    scitt_gov = (manifest.governance or {}).get("scitt") if manifest.governance else None
    pk = (manifest.public_key or "").strip().lower()
    gaps = list(completeness_gaps or [])
    if not forensic_reason and gaps:
        forensic_reason = gaps[0]
    report = {
        "facts": {
            "integrity_ok": integrity_ok,
            "signature_valid": signature_valid,
            "sequence_ok": sequence_ok,
            "completeness_ok": completeness_ok,
            "chain_ok": chain_ok,
            "transparency_ok": transparency_ok,
            "has_signature": manifest.signature is not None,
            "mismatches": mismatches,
            "completeness_gaps": gaps,
            "forensic_reason": forensic_reason,
            "content_truncated": manifest.content_truncated,
            "content_complete_asserted": manifest.content_truncated is False,
        },
        "identity": {
            "status": identity_status,
            "name": identity_name or signer_name,
            "detail": status_detail,
            "registry_verified": is_trusted_identity,
            "public_key_id": pk[:16] if pk else None,
            "public_key_fingerprint": pk[:32] if pk else None,
            "local_key_name": local_key_name,
            "did": (manifest.governance or {}).get("did") if manifest.governance else None,
            "scitt": {
                "service_url": scitt_gov.get("service_url") if scitt_gov else None,
                "entry_id": scitt_gov.get("entry_id") if scitt_gov else None,
                "registered_at": scitt_gov.get("registered_at") if scitt_gov else None,
            }
            if scitt_gov
            else None,
        },
        "metadata": {
            "spec_version": manifest.spec_version,
            "workflow_id": str(manifest.workflow_id),
            "created_at": manifest.created_at.isoformat(),
            "files_checked": len(manifest.file_manifest),
                    "steps_count": manifest.total_steps or 0,
            "verifier_version": _get_verifier_version(),
        },
    }

    # 3. Summary Layer (Unified state for quick lookup)
    report["summary"] = {
        "integrity": (
            "VALID" if (integrity_ok and sequence_ok and completeness_ok and chain_ok) else "FAILED"
        ),
        "trust": (
            identity_status
            if signature_valid is True
            else ("UNTRUSTED" if signature_valid is False else "UNSIGNED")
        ),
        "transparency": (
            "VERIFIED"
            if transparency_ok is True
            else ("FAILED" if transparency_ok is False else "MISSING")
        ),
    }

    # Legacy field support for backward compatibility with existing tests/UI
    # Note: These are now derived from the structured data above.
    report["integrity_ok"] = integrity_ok
    report["signature_valid"] = signature_valid
    report["identity_trusted"] = is_trusted_identity
    report["has_signature"] = manifest.signature is not None
    # Trust level requires both valid signature AND known trusted identity
    if identity_status == "MISMATCH":
        report["trust_level"] = "FAIL"  # Active impersonation attack detected
    elif identity_status == "REVOKED":
        report["trust_level"] = "INVALID"
    elif integrity_ok and signature_valid is True and identity_status == "KNOWN":
        report["trust_level"] = "HIGH"
    elif integrity_ok and signature_valid is True and identity_status == "LOCAL":
        # Sealer key is on this machine; not an org registry pin
        report["trust_level"] = "MEDIUM"
    elif integrity_ok and signature_valid is True and transparency_ok is True:
        # Valid sig + unknown identity + SCITT valid = upgraded from LOW
        report["trust_level"] = "MEDIUM"
    elif integrity_ok and signature_valid is True:
        report["trust_level"] = "LOW"  # Valid signature but unknown identity
    elif integrity_ok and signature_valid is None:
        report["trust_level"] = "LOW"  # Unsigned ranks LOW, not above valid-unknown
    else:
        report["trust_level"] = "NONE"
    report["mismatches_count"] = len(mismatches)
    report["signer"] = signer_name
    report["files_checked"] = len(manifest.file_manifest)
    report["steps_count"] = manifest.total_steps or 0
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
    elif identity_status == "LOCAL" and signature_valid is True and integrity_ok:
        report["trust_message"] = (
            "Seal OK; sealer matches a key on this computer (not org-pinned)"
        )
    elif report["trust_level"] == "MEDIUM":
        report["trust_message"] = "Seal OK with transparency anchor (SCITT) — identity not pinned"
    elif report["trust_level"] == "LOW" and signature_valid is None:
        report["trust_message"] = "Unsigned but integrity intact (no signature) — lower trust than signed-unknown"
    elif report["trust_level"] == "LOW":
        report["trust_message"] = (
            "Seal OK (valid signature); signer not pinned in trust list yet — "
            "normal until you run epi keys trust"
        )
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

    decision = {"policy": policy.value, "status": "FAIL", "reason": "Policy requirements not met"}

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
        # Integrity + not revoked + not mismatched.
        # A valid self-signature proves internal consistency only — not who
        # signed. Unpinned (UNKNOWN) and machine-local (LOCAL) sealers are both
        # WARN so a forger cannot skim "PASS" / "SEAL OK" without an org pin.
        # Claim / insurer acceptance must use STRICT (KNOWN identity required).
        if identity["status"] == "REVOKED":
            decision["reason"] = "Identity revoked"
        elif identity["status"] == "MISMATCH":
            decision["status"] = "FAIL"
            decision["reason"] = "Identity mismatch - possible impersonation attack"
        elif facts["signature_valid"] is True and identity["status"] == "UNKNOWN":
            decision["status"] = "WARN"
            decision["reason"] = (
                "Unverified identity — signature valid but signer not pinned in any "
                "trusted registry. Anyone can generate a key and re-sign a rebuilt "
                "chain. Optional: epi keys trust <file.epi> --name sealer. "
                "For claims / audit: epi verify --policy strict (FAIL until org pin)."
            )
        elif facts["signature_valid"] is True and identity["status"] == "LOCAL":
            decision["status"] = "WARN"
            decision["reason"] = (
                "Local sealer only — signature valid and matches a key on this computer "
                f"({identity.get('name') or 'local'}), but this is not an org trust-list "
                "pin. Optional: epi keys trust <file.epi> --name sealer. "
                "For claims / audit: epi verify --policy strict."
            )
        else:
            decision["status"] = "PASS"
            decision["reason"] = "Integrity verified and identity not revoked"

    elif policy == VerificationPolicy.STRICT:
        # Integrity + known identity + completeness
        if identity["status"] not in ("KNOWN",):
            decision["reason"] = (
                "Identity unknown or revoked (Strict Policy requires trusted signer; "
                "LOCAL self-match is not enough — pin with epi keys trust)"
            )
        elif not facts["completeness_ok"]:
            decision["reason"] = (
                "Evidence incomplete (Strict Policy requires full telemetry coverage)"
            )
        else:
            decision["status"] = "PASS"
            decision["reason"] = "All strict criteria met (Integrity, Identity, Completeness)"

    report["decision"] = decision
    return report
