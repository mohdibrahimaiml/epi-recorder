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
    import hashlib
    manifest = ManifestModel(spec_version="4.0.1")
    key = _make_deterministic_key()
    signed = sign_manifest(manifest, key, key_name="compat-test")

    assert SIG_REGEX.match(signed.signature), (
        f"Signature format invalid: {signed.signature}"
    )
    expected_key_name = hashlib.sha256(signed.public_key.encode("utf-8")).hexdigest()[:16]
    assert get_signer_name(signed.signature) == expected_key_name


def test_public_key_is_raw_hex_64_chars():
    """Embedded public key must be 64 hex chars (32 raw bytes)."""
    manifest = ManifestModel(spec_version="4.0.1")
    key = _make_deterministic_key()
    signed = sign_manifest(manifest, key, key_name="k")

    assert len(signed.public_key) == 64
    int(signed.public_key, 16)  # valid hex


def test_signature_verifies_with_embedded_key():
    """A signed manifest must verify using only the embedded public key."""
    import hashlib
    manifest = ManifestModel(spec_version="4.0.1")
    key = _make_deterministic_key()
    signed = sign_manifest(manifest, key, key_name="k")

    valid, signer, message = verify_embedded_manifest_signature(signed)
    assert valid is True
    expected_key_name = hashlib.sha256(signed.public_key.encode("utf-8")).hexdigest()[:16]
    assert signer == expected_key_name
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
    import base64, hashlib
    manifest = ManifestModel(spec_version="4.0.1")
    key = _make_deterministic_key()
    signed = sign_manifest(manifest, key, key_name="k")

    # Replace hex with base64 of same bytes
    sig_hex = signed.signature.split(":")[2]
    sig_b64 = base64.b64encode(bytes.fromhex(sig_hex)).decode("ascii")
    derived_key_name = hashlib.sha256(signed.public_key.encode("utf-8")).hexdigest()[:16]
    signed.signature = f"ed25519:{derived_key_name}:{sig_b64}"

    valid, signer, message = verify_embedded_manifest_signature(signed)
    assert valid is True, f"Base64 signature should still verify: {message}"


def test_sign_and_verify_agree_on_every_version_input():
    """Sign and verify must use the same preimage for every spec_version.

    Regression: sign used JCS for 2.x-4.4.0 while verify used legacy JSON,
    and sign used CBOR for missing/malformed versions while verify used
    legacy (chain verify even used JCS) — three answers for one input.
    """
    from epi_core.serialize import canonical_format_for

    for sv in ["1.0", "1.9", "2.0", "3.2", "4.0", "4.4.0", "4.4.1", "4.4.7",
               "", "foo", "0.9", "v4.4.7", "4.4.7-rc1"]:
        manifest = ManifestModel()
        manifest = manifest.model_copy(update={"spec_version": sv})
        key = _make_deterministic_key()
        signed = sign_manifest(manifest, key, key_name="k")
        valid, _signer, message = verify_embedded_manifest_signature(signed)
        assert valid is True, f"spec_version={sv!r}: sign/verify disagree ({message})"

    # Dispatch spot-checks: era rule + sign-compatible fallbacks.
    assert canonical_format_for("1.0") == "cbor"
    assert canonical_format_for("4.4.0") == "legacy"
    assert canonical_format_for("4.4.1") == "jcs"
    assert canonical_format_for("") == "cbor"
    assert canonical_format_for(None) == "cbor"
    assert canonical_format_for("foo") == "cbor"
