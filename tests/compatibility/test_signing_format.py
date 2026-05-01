"""
Lock the Ed25519 signing format contract.
"""

import re

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from epi_core.schemas import ManifestModel
from epi_core.trust import sign_manifest, verify_embedded_manifest_signature, get_signer_name
from epi_core.serialize import get_canonical_hash

# Deterministic key for reproducible tests
DETERMINISTIC_SEED = b"\x42" * 32
SIG_REGEX = re.compile(r"^ed25519:[^:]+:[a-f0-9]{128}$")


def _make_deterministic_key():
    return Ed25519PrivateKey.from_private_bytes(DETERMINISTIC_SEED)


def test_signature_string_format():
    """Signature must match ed25519:<key_name>:<128_hex_chars>."""
    manifest = ManifestModel(spec_version="4.0.1")
    key = _make_deterministic_key()
    signed = sign_manifest(manifest, key, key_name="compat-test")

    assert SIG_REGEX.match(signed.signature), (
        f"Signature format invalid: {signed.signature}"
    )
    assert get_signer_name(signed.signature) == "compat-test"


def test_public_key_is_raw_hex_64_chars():
    """Embedded public key must be 64 hex chars (32 raw bytes)."""
    manifest = ManifestModel(spec_version="4.0.1")
    key = _make_deterministic_key()
    signed = sign_manifest(manifest, key, key_name="k")

    assert len(signed.public_key) == 64
    int(signed.public_key, 16)  # valid hex


def test_signature_verifies_with_embedded_key():
    """A signed manifest must verify using only the embedded public key."""
    manifest = ManifestModel(spec_version="4.0.1")
    key = _make_deterministic_key()
    signed = sign_manifest(manifest, key, key_name="k")

    valid, signer, message = verify_embedded_manifest_signature(signed)
    assert valid is True
    assert signer == "k"
    assert "valid" in message.lower()


def test_tampered_manifest_fails_verification():
    """Any modification to the manifest after signing must fail verification."""
    manifest = ManifestModel(spec_version="4.0.1")
    key = _make_deterministic_key()
    signed = sign_manifest(manifest, key, key_name="k")

    # Tamper
    signed.goal = "tampered"
    valid, signer, message = verify_embedded_manifest_signature(signed)
    assert valid is False


def test_signed_payload_excludes_signature_field():
    """The hash being signed must not include the signature field itself."""
    from epi_core.trust import verify_signature
    manifest = ManifestModel(spec_version="4.0.1")
    key = _make_deterministic_key()

    signed = sign_manifest(manifest, key, key_name="k")

    # Extract the signature bytes
    sig_hex = signed.signature.split(":")[2]
    sig_bytes = bytes.fromhex(sig_hex)

    # Compute the hash that was actually signed (excluding signature field)
    signed_hash = get_canonical_hash(signed, exclude_fields={"signature"})
    hash_bytes = bytes.fromhex(signed_hash)

    # Verify the signature directly against this hash
    public_key = key.public_key()
    public_key.verify(sig_bytes, hash_bytes)  # raises InvalidSignature if wrong

    # Also confirm that including the signature field changes the hash
    hash_with_sig = get_canonical_hash(signed)
    assert hash_with_sig != signed_hash, "Signature field must not be in signed payload"


def test_unsupported_algorithm_rejected():
    """Only 'ed25519' algorithm prefix is accepted."""
    manifest = ManifestModel(spec_version="4.0.1")
    manifest.public_key = "a" * 64
    manifest.signature = "rsa2048:somekey:" + "b" * 128

    valid, signer, message = verify_embedded_manifest_signature(manifest)
    assert valid is False
    assert "Unsupported" in message


def test_invalid_signature_format_rejected():
    """Signatures without exactly 3 colon-separated parts are rejected."""
    manifest = ManifestModel(spec_version="4.0.1")
    manifest.public_key = "a" * 64
    manifest.signature = "ed25519:only-two-parts"

    valid, signer, message = verify_embedded_manifest_signature(manifest)
    assert valid is False
    assert "Invalid signature format" in message


def test_legacy_base64_signature_still_accepted():
    """Base64-encoded signatures (legacy) must still verify if valid."""
    import base64
    manifest = ManifestModel(spec_version="4.0.1")
    key = _make_deterministic_key()
    signed = sign_manifest(manifest, key, key_name="k")

    # Replace hex with base64 of same bytes
    sig_hex = signed.signature.split(":")[2]
    sig_b64 = base64.b64encode(bytes.fromhex(sig_hex)).decode("ascii")
    signed.signature = f"ed25519:k:{sig_b64}"

    valid, signer, message = verify_embedded_manifest_signature(signed)
    assert valid is True, f"Base64 signature should still verify: {message}"
