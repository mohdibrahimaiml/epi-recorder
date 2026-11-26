"""Manifest signing and signer trust."""
from __future__ import annotations

from epi_core.trust import (
    TrustRegistry,
    sign_manifest,
    verify_embedded_manifest_signature,
)

verify_manifest_signature = verify_embedded_manifest_signature

__all__ = [
    "TrustRegistry",
    "sign_manifest",
    "verify_embedded_manifest_signature",
    "verify_manifest_signature",
]
