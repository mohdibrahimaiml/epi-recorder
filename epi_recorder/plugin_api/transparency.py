"""SCITT statements and receipts."""
from __future__ import annotations

from epi_core.local_scitt import register_statement as register_local_statement
from epi_core.local_scitt import service_public_key as local_service_public_key
from epi_core.scitt import (
    SCITTVerificationError,
    create_scitt_statement,
    extract_scitt_artifacts,
    verify_scitt_receipt,
    verify_scitt_statement,
)

__all__ = [
    "SCITTVerificationError",
    "create_scitt_statement",
    "extract_scitt_artifacts",
    "local_service_public_key",
    "register_local_statement",
    "verify_scitt_receipt",
    "verify_scitt_statement",
]
