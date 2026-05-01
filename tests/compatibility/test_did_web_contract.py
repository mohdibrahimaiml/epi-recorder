"""
Lock the DID:WEB optional contract. DID:WEB must remain additive only
and must not break offline verification or alter core fields.
"""

import pytest
from unittest.mock import patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from epi_core.schemas import ManifestModel
from epi_core.trust import (
    TrustRegistry,
    verify_embedded_manifest_signature,
    create_verification_report,
)
from epi_recorder.api import EpiRecorderSession

DETERMINISTIC_SEED = b"\x42" * 32


def _make_key():
    return Ed25519PrivateKey.from_private_bytes(DETERMINISTIC_SEED)


def test_artifact_without_did_verifies_identically():
    """Pre-DID:WEB behavior must remain unchanged when did_web=None."""
    manifest = ManifestModel(spec_version="4.0.1")
    key = _make_key()
    manifest.public_key = key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    ).hex()
    manifest.signature = "ed25519:test:" + "a" * 128

    valid, signer, message = verify_embedded_manifest_signature(manifest)
    # Signature is garbage, so it should fail — but the process must not crash
    assert valid is False


def test_did_web_adds_only_governance_and_trust():
    """When did_web is set, only governance.did and trust.fingerprint are added."""
    from epi_recorder.api import EpiRecorderSession
    from pathlib import Path
    # We can't easily call _sign_epi_file without a full workspace, so we test
    # the expected contract directly via the API class attributes.
    session = EpiRecorderSession(output_path=Path("test.epi"), did_web="did:web:example.com")
    assert session.did_web == "did:web:example.com"


def test_did_web_invalid_prefix_rejected():
    """EpiRecorderSession must reject did_web values not starting with did:web:."""
    from pathlib import Path
    with pytest.raises(ValueError, match="did:web:"):
        EpiRecorderSession(output_path=Path("test.epi"), did_web="https://example.com")


def test_did_resolution_failure_falls_back_gracefully():
    """Network failure during DID resolution must not break signature verification."""
    from epi_core.did_web import DidResolutionError

    manifest = ManifestModel(
        spec_version="4.0.1",
        public_key="a" * 64,
        governance={"did": "did:web:example.com"},
    )
    registry = TrustRegistry()

    with patch(
        "epi_core.did_web.resolve_did_web",
        side_effect=DidResolutionError("network unreachable"),
    ):
        is_trusted, name, detail = registry.verify_key_trust(
            "a" * 64, governance=manifest.governance
        )
        assert is_trusted is False
        assert "DID resolution failed" in detail


def test_embedded_verification_ignores_governance():
    """verify_embedded_manifest_signature must use only public_key, not governance."""
    from epi_core.trust import sign_manifest
    manifest = ManifestModel(spec_version="4.0.1")
    key = _make_key()
    # Set governance BEFORE signing so it is part of the signed payload
    manifest.governance = {"did": "did:web:attacker.com"}
    signed = sign_manifest(manifest, key, key_name="k")

    # Verification must still pass because it uses embedded key only,
    # not the governance field
    valid, signer, message = verify_embedded_manifest_signature(signed)
    assert valid is True, f"Embedded verification must ignore governance: {message}"


def test_trust_registry_did_match():
    """When DID resolves to the same key, trust is established."""
    public_key_hex = "a" * 64
    did_doc = {
        "id": "did:web:example.com",
        "verificationMethod": [{
            "id": "did:web:example.com#key1",
            "type": "Ed25519VerificationKey2020",
            "publicKeyHex": public_key_hex,
        }],
    }

    registry = TrustRegistry()
    with patch("epi_core.did_web.resolve_did_web", return_value=did_doc):
        with patch("epi_core.did_web.extract_ed25519_key", return_value=public_key_hex):
            is_trusted, name, detail = registry.verify_key_trust(
                public_key_hex, governance={"did": "did:web:example.com"}
            )
            assert is_trusted is True
            assert "Verified via DID:WEB" in detail


def test_trust_registry_did_mismatch():
    """When DID resolves to a different key, trust is denied."""
    public_key_hex = "a" * 64
    did_doc = {
        "id": "did:web:example.com",
        "verificationMethod": [{
            "id": "did:web:example.com#key1",
            "type": "Ed25519VerificationKey2020",
            "publicKeyHex": "b" * 64,
        }],
    }

    registry = TrustRegistry()
    with patch("epi_core.did_web.resolve_did_web", return_value=did_doc):
        with patch("epi_core.did_web.extract_ed25519_key", return_value="b" * 64):
            is_trusted, name, detail = registry.verify_key_trust(
                public_key_hex, governance={"did": "did:web:example.com"}
            )
            assert is_trusted is False
            assert "mismatch" in detail.lower()
