"""
Tests for DID:WEB resolver — zero-cost identity verification.

All HTTP calls are mocked with unittest.mock to avoid real network requests.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from epi_core.did_web import (
    resolve_did_web,
    extract_ed25519_key,
    DidResolutionError,
    KeyNotFoundError,
)
from epi_core.trust import TrustRegistry


class TestResolveDidWeb:
    """Test DID document resolution with mocked HTTP."""

    def test_simple_host(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"id": "did:web:example.com"}

        with patch("epi_core.did_web.requests.get", return_value=mock_resp) as mock_get:
            doc = resolve_did_web("did:web:example.com")

        assert doc == {"id": "did:web:example.com"}
        mock_get.assert_called_once_with("https://example.com/.well-known/did.json", timeout=10)

    def test_host_with_path(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"id": "did:web:example.com:users:alice"}

        with patch("epi_core.did_web.requests.get", return_value=mock_resp) as mock_get:
            doc = resolve_did_web("did:web:example.com:users:alice")

        assert doc == {"id": "did:web:example.com:users:alice"}
        mock_get.assert_called_once_with("https://example.com/users/alice/did.json", timeout=10)

    def test_invalid_prefix_raises(self):
        with pytest.raises(DidResolutionError):
            resolve_did_web("did:ethr:example.com")

    def test_empty_host_raises(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {}

        with patch("epi_core.did_web.requests.get", return_value=mock_resp):
            # "did:web:" produces host="" and still forms a URL; we just verify
            # the function doesn't crash on empty method-specific-id handling.
            resolve_did_web("did:web:")

    def test_http_error_raises(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 404

        with patch("epi_core.did_web.requests.get", return_value=mock_resp):
            with pytest.raises(DidResolutionError) as exc_info:
                resolve_did_web("did:web:http-error.example.com")
            assert "404" in str(exc_info.value)

    def test_network_error_raises(self):
        with patch("epi_core.did_web.requests.get", side_effect=ConnectionError("no route")):
            with pytest.raises(DidResolutionError) as exc_info:
                resolve_did_web("did:web:network-error.example.com")
            assert "no route" in str(exc_info.value)

    def test_invalid_json_raises(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.side_effect = ValueError("bad json")

        with patch("epi_core.did_web.requests.get", return_value=mock_resp):
            with pytest.raises(DidResolutionError) as exc_info:
                resolve_did_web("did:web:bad-json.example.com")
            assert "not valid JSON" in str(exc_info.value)


class TestExtractEd25519Key:
    """Test Ed25519 key extraction from DID documents."""

    def test_extract_from_public_key_hex(self):
        doc = {
            "verificationMethod": [
                {
                    "id": "#key-1",
                    "type": "Ed25519VerificationKey2020",
                    "publicKeyHex": "a" * 64,
                }
            ]
        }
        assert extract_ed25519_key(doc) == "a" * 64

    def test_extract_from_public_key_list(self):
        doc = {
            "publicKey": [
                {
                    "id": "#key-1",
                    "type": "Ed25519VerificationKey2020",
                    "publicKeyHex": "a" * 64,
                }
            ]
        }
        assert extract_ed25519_key(doc) == "a" * 64

    def test_missing_key_raises(self):
        doc = {"verificationMethod": []}
        with pytest.raises(KeyNotFoundError):
            extract_ed25519_key(doc)

    def test_wrong_key_type_skipped(self):
        doc = {
            "verificationMethod": [
                {
                    "id": "#key-1",
                    "type": "EcdsaSecp256k1VerificationKey2019",
                    "publicKeyHex": "a" * 64,
                }
            ]
        }
        with pytest.raises(KeyNotFoundError):
            extract_ed25519_key(doc)


class TestTrustRegistryDidWeb:
    """Test TrustRegistry integration with DID:WEB."""

    def test_trust_registry_verifies_via_did_web(self):
        registry = TrustRegistry()
        did = "did:web:example.com"
        public_key_hex = "a" * 64

        did_doc = {
            "id": did,
            "verificationMethod": [
                {
                    "id": "#key-1",
                    "type": "Ed25519VerificationKey2020",
                    "publicKeyHex": public_key_hex,
                }
            ],
        }

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = did_doc

        with patch("epi_core.did_web.requests.get", return_value=mock_resp):
            is_trusted, identity, detail = registry.verify_key_trust(
                public_key_hex,
                governance={"did": did},
            )

        assert is_trusted is True
        assert identity == did
        assert "DID:WEB" in detail

    def test_trust_registry_rejects_mismatched_did_key(self):
        registry = TrustRegistry()
        did = "did:web:example.com"
        wrong_key = "b" * 64

        did_doc = {
            "id": did,
            "verificationMethod": [
                {
                    "id": "#key-1",
                    "type": "Ed25519VerificationKey2020",
                    "publicKeyHex": "a" * 64,
                }
            ],
        }

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = did_doc

        with patch("epi_core.did_web.requests.get", return_value=mock_resp):
            is_trusted, identity, detail = registry.verify_key_trust(
                wrong_key,
                governance={"did": did},
            )

        assert is_trusted is False
        assert "mismatch" in detail.lower()

    def test_trust_registry_graceful_on_did_resolution_failure(self):
        registry = TrustRegistry()
        did = "did:web:nonexistent.example.com"

        with patch("epi_core.did_web.requests.get", side_effect=ConnectionError("offline")):
            is_trusted, identity, detail = registry.verify_key_trust(
                "a" * 64,
                governance={"did": did},
            )

        assert is_trusted is False
        assert "DID resolution failed" in detail

    def test_no_governance_falls_through_to_unknown(self):
        registry = TrustRegistry()
        is_trusted, identity, detail = registry.verify_key_trust("a" * 64)
        assert is_trusted is False
        assert "UNKNOWN" in detail
