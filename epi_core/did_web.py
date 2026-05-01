"""
DID:WEB resolution for EPI trust verification.

Implements W3C DID:WEB resolution (https://w3c-ccg.github.io/did-method-web/)
for zero-cost, issuer-independent identity binding.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

import requests


class DidResolutionError(Exception):
    """Raised when a DID:WEB document cannot be fetched (network, HTTP error, etc.)."""


class KeyNotFoundError(Exception):
    """Raised when a DID document is valid but contains no Ed25519 key."""


def resolve_did_web(did: str) -> dict[str, Any]:
    """
    Resolve a did:web DID to its DID document.

    Conversion rules (W3C DID:WEB spec):
    - did:web:example.com            → https://example.com/.well-known/did.json
    - did:web:example.com:path:sub   → https://example.com/path/sub/did.json
    - Percent-encoded characters in the method-specific-id are decoded for the host.

    Args:
        did: A DID string starting with "did:web:".

    Returns:
        The parsed DID document dict.

    Raises:
        DidResolutionError: On any network or HTTP failure.
    """
    if not did.startswith("did:web:"):
        raise DidResolutionError(f"Not a did:web DID: {did}")

    method_specific_id = did[len("did:web:"):]

    # Split on ":" — first segment is the host (possibly percent-encoded)
    parts = method_specific_id.split(":")
    host = parts[0].replace("%3A", ":").replace("%3a", ":")

    if len(parts) == 1:
        url = f"https://{host}/.well-known/did.json"
    else:
        path = "/".join(quote(p, safe="") for p in parts[1:])
        url = f"https://{host}/{path}/did.json"

    try:
        resp = requests.get(url, timeout=10)  # noqa: S113  # patchable at module level
    except Exception as exc:
        raise DidResolutionError(str(exc)) from exc

    if resp.status_code != 200:
        raise DidResolutionError(
            f"DID document fetch returned HTTP {resp.status_code} for {url}"
        )

    try:
        return resp.json()
    except Exception as exc:
        raise DidResolutionError(f"DID document is not valid JSON: {exc}") from exc


def extract_ed25519_key(did_doc: dict[str, Any]) -> str:
    """
    Extract the first Ed25519 public key (hex) from a DID document.

    Looks through verificationMethod entries for Ed25519VerificationKey2018/2020
    with a publicKeyHex field.

    Args:
        did_doc: A parsed DID document dict.

    Returns:
        The publicKeyHex string of the first matching key.

    Raises:
        KeyNotFoundError: If no Ed25519 public key is found.
    """
    vm_list = did_doc.get("verificationMethod") or did_doc.get("publicKey") or []

    ed25519_types = {
        "Ed25519VerificationKey2018",
        "Ed25519VerificationKey2020",
    }

    for vm in vm_list:
        if not isinstance(vm, dict):
            continue
        if vm.get("type") in ed25519_types:
            key_hex = vm.get("publicKeyHex")
            if key_hex:
                return key_hex

    raise KeyNotFoundError(
        "DID document contains no Ed25519VerificationKey with a publicKeyHex field"
    )
