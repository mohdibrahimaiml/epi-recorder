"""
DID:WEB resolution for EPI trust verification.

Implements W3C DID:WEB resolution (https://w3c-ccg.github.io/did-method-web/)
for zero-cost, issuer-independent identity binding.

Uses only stdlib urllib — no external HTTP dependencies required.
"""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import quote
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError


class DidResolutionError(Exception):
    """Raised when a DID:WEB document cannot be fetched (network, HTTP error, etc.)."""


class KeyNotFoundError(Exception):
    """Raised when a DID document is valid but contains no Ed25519 key."""


def _did_to_url(did: str) -> str:
    """
    Convert a did:web DID to its DID document HTTPS URL.

    Conversion rules (W3C DID:WEB spec):
    - did:web:example.com            → https://example.com/.well-known/did.json
    - did:web:example.com:path:sub   → https://example.com/path/sub/did.json
    - Percent-encoded colons in the host are decoded.
    """
    if not did.startswith("did:web:"):
        raise DidResolutionError(f"Not a did:web DID: {did}")

    method_specific_id = did[len("did:web:"):]
    parts = method_specific_id.split(":")
    host = parts[0].replace("%3A", ":").replace("%3a", ":")

    if len(parts) == 1:
        return f"https://{host}/.well-known/did.json"
    else:
        path = "/".join(quote(p, safe="") for p in parts[1:])
        return f"https://{host}/{path}/did.json"


def resolve_did_web(did: str, timeout: int = 10) -> dict[str, Any]:
    """
    Resolve a did:web DID to its DID document.

    Args:
        did: A DID string starting with "did:web:".
        timeout: HTTP request timeout in seconds (default 10).

    Returns:
        The parsed DID document dict.

    Raises:
        DidResolutionError: On any network, HTTP, or parse failure.
    """
    url = _did_to_url(did)
    req = Request(url, headers={"Accept": "application/json"})

    try:
        with urlopen(req, timeout=timeout) as resp:  # noqa: S310
            if resp.status != 200:
                raise DidResolutionError(
                    f"DID document fetch returned HTTP {resp.status} for {url}"
                )
            body = resp.read().decode("utf-8")
    except HTTPError as exc:
        raise DidResolutionError(
            f"DID document fetch returned HTTP {exc.code} for {url}"
        ) from exc
    except URLError as exc:
        raise DidResolutionError(str(exc.reason)) from exc
    except Exception as exc:
        raise DidResolutionError(str(exc)) from exc

    try:
        return json.loads(body)
    except Exception as exc:
        raise DidResolutionError(f"DID document is not valid JSON: {exc}") from exc


def extract_ed25519_key(did_doc: dict[str, Any]) -> str:
    """
    Extract the first Ed25519 public key (hex) from a DID document.

    Supports the following key formats in verificationMethod / publicKey entries:
    - publicKeyHex  (Ed25519VerificationKey2018 / 2020)
    - publicKeyMultibase  (z-prefixed base58btc, 2020 suite)
    - publicKeyJwk  (JWK with crv=Ed25519 and x field)

    Args:
        did_doc: A parsed DID document dict.

    Returns:
        The Ed25519 public key as a lowercase hex string (64 chars).

    Raises:
        KeyNotFoundError: If no Ed25519 public key is found.
    """
    vm_list = did_doc.get("verificationMethod") or did_doc.get("publicKey") or []

    ed25519_types = {
        "Ed25519VerificationKey2018",
        "Ed25519VerificationKey2020",
        "JsonWebKey2020",
    }

    for vm in vm_list:
        if not isinstance(vm, dict):
            continue

        vm_type = vm.get("type", "")
        if vm_type not in ed25519_types and "Ed25519" not in vm_type:
            continue

        # Format 1: publicKeyHex (most common in 2018/2020 suites)
        key_hex = vm.get("publicKeyHex")
        if key_hex:
            return key_hex.lower()

        # Format 2: publicKeyMultibase (z-prefixed base58btc, 2020 suite)
        multibase = vm.get("publicKeyMultibase")
        if multibase and multibase.startswith("z"):
            try:
                key_hex = _base58_to_hex(multibase[1:])
                if len(key_hex) == 64:  # 32-byte Ed25519 key
                    return key_hex
            except Exception:
                pass

        # Format 3: publicKeyJwk with crv=Ed25519
        jwk = vm.get("publicKeyJwk")
        if jwk and jwk.get("crv") == "Ed25519" and jwk.get("x"):
            try:
                import base64
                x_bytes = base64.urlsafe_b64decode(jwk["x"] + "==")
                if len(x_bytes) == 32:
                    return x_bytes.hex()
            except Exception:
                pass

    raise KeyNotFoundError(
        "DID document contains no Ed25519 public key "
        "(checked publicKeyHex, publicKeyMultibase, publicKeyJwk)"
    )


_BASE58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def _base58_to_hex(s: str) -> str:
    """Decode a base58-encoded string to a lowercase hex string."""
    n = 0
    for char in s:
        n = n * 58 + _BASE58_ALPHABET.index(char)
    hex_str = f"{n:x}"
    # Preserve leading zeros from base58 '1' characters
    leading = len(s) - len(s.lstrip("1"))
    return "00" * leading + hex_str.zfill(len(hex_str) + len(hex_str) % 2)


def generate_did_document(did: str, public_key_hex: str) -> dict[str, Any]:
    """
    Generate a minimal DID document for a given did:web DID and Ed25519 public key.

    This is a helper for local testing and self-hosting. Publish the result as
    JSON at the URL returned by _did_to_url(did) to enable DID:WEB verification.

    Example:
        doc = generate_did_document("did:web:example.com", my_public_key_hex)
        # Publish at https://example.com/.well-known/did.json

    Args:
        did: The did:web DID string.
        public_key_hex: The Ed25519 public key as a 64-character hex string.

    Returns:
        A minimal DID document dict ready for JSON serialisation.
    """
    return {
        "@context": [
            "https://www.w3.org/ns/did/v1",
            "https://w3id.org/security/suites/ed25519-2020/v1",
        ],
        "id": did,
        "verificationMethod": [
            {
                "id": f"{did}#key-1",
                "type": "Ed25519VerificationKey2020",
                "controller": did,
                "publicKeyHex": public_key_hex,
            }
        ],
        "authentication": [f"{did}#key-1"],
        "assertionMethod": [f"{did}#key-1"],
    }
