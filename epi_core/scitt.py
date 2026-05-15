"""
SCITT (Supply Chain Integrity, Transparency and Trust) integration for EPI.

Implements Mode B: SCITT Producer — EPI artifacts can be registered with a
SCITT transparency service, producing an embedded COSE_Sign1 receipt that is
verified during ``epi verify``.

COSE_Sign1 is implemented manually using ``cbor2`` + ``cryptography`` (both
already EPI dependencies) to avoid an extra dependency on ``pycose``.

Architecture:
- Ed25519 remains the primary signature. SCITT is additive.
- The SCITT statement payload is the canonical SHA-256 hex of the manifest.
- Receipts are COSE_Sign1 signed by the transparency service.
- Everything verifies offline once the receipt is embedded.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC
from pathlib import Path
from urllib.parse import urljoin

import cbor2
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from epi_core.schemas import ManifestModel
from epi_core.serialize import get_canonical_hash

# ─────────────────────────────────────────────────────────────
# COSE header parameter labels
# ─────────────────────────────────────────────────────────────

COSE_HDR_ALG = 1
COSE_HDR_KID = 4
COSE_HDR_CONTENT_TYPE = 3

# CWT_Claims in protected header — using private-use label -260
# (consistent with emerging SCITT implementations; will migrate to
# the IANA-registered label once standardized).
COSE_HDR_CWT_CLAIMS = -260

# CWT claim keys
CWT_ISS = 1
CWT_SUB = 2

# COSE algorithm value for EdDSA
COSE_ALG_EDDSA = -8

# COSE tag for Sign1
COSE_TAG_SIGN1 = 18


# ─────────────────────────────────────────────────────────────
# Exceptions
# ─────────────────────────────────────────────────────────────

class SCITTError(Exception):
    """Base exception for SCITT operations."""
    pass


class SCITTRegistrationError(SCITTError):
    """Raised when registration with a transparency service fails."""
    pass


class SCITTVerificationError(SCITTError):
    """Raised when SCITT statement or receipt verification fails."""
    pass


# ─────────────────────────────────────────────────────────────
# Low-level COSE_Sign1 (manual cbor2 implementation)
# ─────────────────────────────────────────────────────────────

def _cose_sign1_encode(
    protected: dict,
    unprotected: dict,
    payload: bytes | None,
    signature: bytes,
) -> bytes:
    """Encode a COSE_Sign1 message with CBOR tag 18."""
    protected_bstr = cbor2.dumps(protected)
    arr = [protected_bstr, unprotected, payload, signature]
    return cbor2.dumps(cbor2.CBORTag(COSE_TAG_SIGN1, arr))


def _cose_sign1_decode(cose_bytes: bytes) -> tuple[dict, dict, bytes | None, bytes]:
    """Decode a COSE_Sign1 message. Returns (protected, unprotected, payload, signature)."""
    try:
        obj = cbor2.loads(cose_bytes)
    except Exception as exc:
        raise SCITTVerificationError(f"Invalid CBOR: {exc}") from exc

    if not isinstance(obj, cbor2.CBORTag) or obj.tag != COSE_TAG_SIGN1:
        raise SCITTVerificationError("Expected CBORTag(18) for COSE_Sign1")

    value = obj.value
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        raise SCITTVerificationError("COSE_Sign1 must be a 4-element array")

    protected_bstr, unprotected, payload, signature = value

    try:
        protected = cbor2.loads(protected_bstr)
    except Exception as exc:
        raise SCITTVerificationError(f"Invalid protected headers: {exc}") from exc

    # cbor2 may return frozendict instead of dict
    if not isinstance(protected, (dict, cbor2.frozendict)):
        raise SCITTVerificationError("Protected headers must be a CBOR map")
    if not isinstance(unprotected, (dict, cbor2.frozendict)):
        raise SCITTVerificationError("Unprotected headers must be a CBOR map")
    if payload is not None and not isinstance(payload, bytes):
        raise SCITTVerificationError("Payload must be bstr or nil")
    if not isinstance(signature, bytes):
        raise SCITTVerificationError("Signature must be bstr")

    return protected, unprotected, payload, signature


def _build_sig_structure(protected_bstr: bytes, payload: bytes | None) -> bytes:
    """Build the Sig_structure for COSE_Sign1."""
    # Sig_structure = ["Signature1", protected, external_aad, payload]
    return cbor2.dumps(["Signature1", protected_bstr, b"", payload])


def _ed25519_sign(
    private_key: Ed25519PrivateKey,
    protected: dict,
    payload: bytes | None,
) -> bytes:
    """Sign a COSE_Sign1 structure with Ed25519."""
    protected_bstr = cbor2.dumps(protected)
    to_sign = _build_sig_structure(protected_bstr, payload)
    return private_key.sign(to_sign)


def _ed25519_verify(
    public_key: Ed25519PublicKey,
    protected: dict,
    payload: bytes | None,
    signature: bytes,
) -> bool:
    """Verify a COSE_Sign1 Ed25519 signature."""
    protected_bstr = cbor2.dumps(protected)
    to_verify = _build_sig_structure(protected_bstr, payload)
    try:
        public_key.verify(signature, to_verify)
        return True
    except InvalidSignature:
        return False


# ─────────────────────────────────────────────────────────────
# SCITT Statement
# ─────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class SCITTStatement:
    """Parsed SCITT Signed Statement."""
    issuer: str
    subject: str
    payload: bytes | None
    protected: dict
    unprotected: dict
    signature: bytes
    raw_bytes: bytes


def create_scitt_statement(
    manifest: ManifestModel | dict,
    private_key: Ed25519PrivateKey,
    issuer: str,
    kid: bytes = b"default",
) -> bytes:
    """
    Create a SCITT Signed Statement (COSE_Sign1) for an EPI manifest.

    The statement's payload is the canonical SHA-256 hex of the manifest
    (excluding the signature field).  This is the same hash that Ed25519
    signing already computes, ensuring the two signatures attest to the
    identical content.

    Args:
        manifest: The EPI manifest to attest (ManifestModel or dict).
        private_key: Ed25519 private key of the issuer.
        issuer: Issuer identifier (DID, URI, or key name).
        kid: Key identifier byte string.

    Returns:
        COSE_Sign1 bytes.
    """
    if isinstance(manifest, dict):
        manifest = ManifestModel(**manifest)
    manifest_hash = get_canonical_hash(manifest, exclude_fields={"signature"})
    payload = manifest_hash.encode("utf-8")

    protected = {
        COSE_HDR_ALG: COSE_ALG_EDDSA,
        COSE_HDR_CONTENT_TYPE: "application/vnd.epi.manifest+hash",
        COSE_HDR_CWT_CLAIMS: {
            CWT_ISS: issuer,
            CWT_SUB: manifest_hash,
        },
    }
    unprotected = {
        COSE_HDR_KID: kid,
    }

    signature = _ed25519_sign(private_key, protected, payload)
    return _cose_sign1_encode(protected, unprotected, payload, signature)


def parse_scitt_statement(cose_bytes: bytes) -> SCITTStatement:
    """Parse and validate the structure of a SCITT Signed Statement."""
    protected, unprotected, payload, signature = _cose_sign1_decode(cose_bytes)

    alg = protected.get(COSE_HDR_ALG)
    if alg != COSE_ALG_EDDSA:
        raise SCITTVerificationError(f"Unsupported COSE algorithm: {alg}")

    cwt = protected.get(COSE_HDR_CWT_CLAIMS, {})
    issuer = cwt.get(CWT_ISS)
    subject = cwt.get(CWT_SUB)
    if not issuer or not subject:
        raise SCITTVerificationError("SCITT statement missing iss or sub CWT claims")

    return SCITTStatement(
        issuer=issuer,
        subject=subject,
        payload=payload,
        protected=protected,
        unprotected=unprotected,
        signature=signature,
        raw_bytes=cose_bytes,
    )


def verify_scitt_statement(
    cose_bytes: bytes,
    manifest: ManifestModel,
    public_key_bytes: bytes | None = None,
) -> bool:
    """
    Verify a SCITT Signed Statement against a manifest.

    Checks:
    1. COSE structure is valid.
    2. Algorithm is EdDSA.
    3. CWT claims (iss, sub) are present.
    4. Payload matches the manifest's canonical hash.
    5. Signature is valid (if public_key_bytes provided).

    Args:
        cose_bytes: The COSE_Sign1 statement bytes.
        manifest: The manifest to verify against.
        public_key_bytes: Optional Ed25519 public key bytes (32 bytes) to verify signature.

    Returns:
        True if the statement is valid for this manifest.
    """
    if isinstance(manifest, dict):
        manifest = ManifestModel(**manifest)

    statement = parse_scitt_statement(cose_bytes)

    # Verify payload matches manifest hash
    expected_hash = get_canonical_hash(manifest, exclude_fields={"signature"})
    if statement.payload is None:
        raise SCITTVerificationError("SCITT statement has detached payload")
    actual_hash = statement.payload.decode("utf-8")
    if actual_hash != expected_hash:
        raise SCITTVerificationError(
            f"SCITT payload hash mismatch: expected {expected_hash}, got {actual_hash}"
        )

    # Verify signature if key provided
    if public_key_bytes is not None:
        public_key = Ed25519PublicKey.from_public_bytes(public_key_bytes)
        if not _ed25519_verify(
            public_key,
            statement.protected,
            statement.payload,
            statement.signature,
        ):
            raise SCITTVerificationError("SCITT statement signature invalid")

    return True


# ─────────────────────────────────────────────────────────────
# SCITT Receipt
# ─────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class SCITTReceipt:
    """Parsed SCITT Receipt (COSE_Sign1 signed by transparency service)."""
    protected: dict
    unprotected: dict
    payload: bytes | None
    signature: bytes
    raw_bytes: bytes


def create_scitt_receipt(
    statement_bytes: bytes,
    service_private_key: Ed25519PrivateKey,
    kid: bytes = b"scitt-service",
) -> bytes:
    """
    Create a SCITT receipt for a given statement.

    The receipt is a COSE_Sign1 message signed by the transparency service
    whose payload is the SHA-256 of the original statement bytes.  This
    binds the receipt to the statement cryptographically.
    """
    statement_hash = hashlib.sha256(statement_bytes).digest()

    protected = {
        COSE_HDR_ALG: COSE_ALG_EDDSA,
        COSE_HDR_CONTENT_TYPE: "application/vnd.scitt.receipt",
    }
    unprotected = {
        COSE_HDR_KID: kid,
    }

    signature = _ed25519_sign(service_private_key, protected, statement_hash)
    return _cose_sign1_encode(protected, unprotected, statement_hash, signature)


def parse_scitt_receipt(cose_bytes: bytes) -> SCITTReceipt:
    """Parse a SCITT Receipt."""
    protected, unprotected, payload, signature = _cose_sign1_decode(cose_bytes)

    alg = protected.get(COSE_HDR_ALG)
    if alg != COSE_ALG_EDDSA:
        raise SCITTVerificationError(f"Receipt unsupported algorithm: {alg}")

    return SCITTReceipt(
        protected=protected,
        unprotected=unprotected,
        payload=payload,
        signature=signature,
        raw_bytes=cose_bytes,
    )


def verify_scitt_receipt(
    receipt_bytes: bytes,
    statement_bytes: bytes,
    service_public_key_bytes: bytes,
) -> bool:
    """
    Verify a SCITT receipt against a statement.

    Checks:
    1. Receipt COSE structure is valid.
    2. Algorithm is EdDSA.
    3. Receipt payload matches SHA-256 of the statement bytes.
    4. Receipt signature is valid from the transparency service.
    """
    receipt = parse_scitt_receipt(receipt_bytes)

    if receipt.payload is None:
        raise SCITTVerificationError("SCITT receipt has detached payload")

    expected_hash = hashlib.sha256(statement_bytes).digest()
    if receipt.payload != expected_hash:
        raise SCITTVerificationError(
            "SCITT receipt payload does not match statement hash"
        )

    public_key = Ed25519PublicKey.from_public_bytes(service_public_key_bytes)
    if not _ed25519_verify(
        public_key,
        receipt.protected,
        receipt.payload,
        receipt.signature,
    ):
        raise SCITTVerificationError("SCITT receipt signature invalid")

    return True


# ─────────────────────────────────────────────────────────────
# Transparency Service Client
# ─────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class SCITTServiceInfo:
    """Metadata about a SCITT registration."""
    service_url: str
    entry_id: str
    registered_at: str


class SCITTServiceClient:
    """
    HTTP client for a SCITT transparency service.

    This is a minimal client sufficient for EPI's use case:
    - POST /register  → submit a Signed Statement, get a Receipt
    - GET  /keys      → fetch the service's public key for receipt verification
    """

    def __init__(self, base_url: str, timeout: int = 30):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def register(self, statement_bytes: bytes) -> tuple[bytes, SCITTServiceInfo]:
        """
        Register a Signed Statement with the transparency service.

        Returns:
            (receipt_bytes, service_info)

        Raises:
            SCITTRegistrationError: on HTTP or validation failure.
        """
        import urllib.error
        import urllib.request
        from datetime import datetime

        url = urljoin(self.base_url + "/", "register")
        req = urllib.request.Request(
            url,
            data=statement_bytes,
            headers={
                "Content-Type": "application/cose",
                "Accept": "application/cose",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                receipt_bytes = resp.read()
                entry_id = resp.headers.get("X-Scitt-Entry-Id", "")
                if not entry_id:
                    # Fallback: derive entry_id from statement hash
                    entry_id = hashlib.sha256(statement_bytes).hexdigest()[:32]
                info = SCITTServiceInfo(
                    service_url=self.base_url,
                    entry_id=entry_id,
                    registered_at=datetime.now(UTC).isoformat(),
                )
                return receipt_bytes, info
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")[:500]
            raise SCITTRegistrationError(
                f"SCITT service returned {exc.code}: {body}"
            ) from exc
        except Exception as exc:
            raise SCITTRegistrationError(f"SCITT registration failed: {exc}") from exc

    def get_public_key(self) -> bytes:
        """
        Fetch the transparency service's Ed25519 public key raw bytes.

        Returns:
            32-byte raw Ed25519 public key.
        """
        import urllib.error
        import urllib.request

        url = urljoin(self.base_url + "/", "keys")
        try:
            with urllib.request.urlopen(url, timeout=self.timeout) as resp:
                data = json.loads(resp.read())
                key_hex = data.get("public_key", "")
                if not key_hex:
                    raise SCITTRegistrationError("Service did not return public_key")
                return bytes.fromhex(key_hex)
        except Exception as exc:
            raise SCITTRegistrationError(f"Failed to fetch service public key: {exc}") from exc


# ─────────────────────────────────────────────────────────────
# High-level helpers for EPI integration
# ─────────────────────────────────────────────────────────────

def scitt_governance_from_info(
    info: SCITTServiceInfo,
    issuer: str,
    algorithm: str = "EdDSA",
) -> dict:
    """Build the manifest.governance['scitt'] dict from service info."""
    return {
        "service_url": info.service_url,
        "entry_id": info.entry_id,
        "registered_at": info.registered_at,
        "statement_path": "artifacts/scitt/statement.cbor",
        "receipt_path": "artifacts/scitt/receipt.cbor",
        "issuer": issuer,
        "algorithm": algorithm,
    }


def extract_scitt_artifacts(
    epi_path: Path,
) -> tuple[bytes | None, bytes | None, dict | None]:
    """
    Extract SCITT statement and receipt bytes from an .epi file.

    Returns:
        (statement_bytes, receipt_bytes, scitt_governance_dict)
        Any of these may be None if SCITT artifacts are not present.
    """
    import zipfile

    statement_bytes: bytes | None = None
    receipt_bytes: bytes | None = None
    scitt_gov: dict | None = None

    try:
        with zipfile.ZipFile(epi_path, "r") as zf:
            # Read manifest to find SCITT governance
            try:
                manifest_data = json.loads(zf.read("manifest.json"))
                scitt_gov = (manifest_data.get("governance") or {}).get("scitt")
            except Exception:
                return None, None, None

            if not scitt_gov:
                return None, None, None

            stmt_path = scitt_gov.get("statement_path", "artifacts/scitt/statement.cbor")
            rcpt_path = scitt_gov.get("receipt_path", "artifacts/scitt/receipt.cbor")

            try:
                statement_bytes = zf.read(stmt_path)
            except KeyError:
                pass
            try:
                receipt_bytes = zf.read(rcpt_path)
            except KeyError:
                pass
    except Exception:
        return None, None, None

    return statement_bytes, receipt_bytes, scitt_gov
