"""
EPI Core Serialization - Canonical CBOR hashing for tamper-evident records.

This module provides deterministic serialization using CBOR (RFC 8949) with
canonical encoding to ensure identical hashes across platforms and time.
"""

import hashlib
from datetime import datetime
from typing import Any
from uuid import UUID

import cbor2
from pydantic import BaseModel


def _cbor_default_encoder(encoder, value: Any) -> None:
    """
    Custom CBOR encoder for datetime and UUID types.
    
    Ensures consistent encoding across different Python environments:
    - datetime objects are encoded as ISO 8601 strings (UTC)
    - UUID objects are encoded as their canonical string representation
    
    Args:
        encoder: CBOR encoder instance
        value: Value to encode
    
    Raises:
        ValueError: If value type cannot be encoded
    """
    if isinstance(value, datetime):
        # Remove microseconds for stability
        normalized_dt = value.replace(microsecond=0)
        # Encode as ISO 8601 string with Z suffix for UTC
        encoder.encode(normalized_dt.isoformat() + "Z")
    elif isinstance(value, UUID):
        # Use canonical UUID string representation
        encoder.encode(str(value))
    else:
        raise ValueError(f"Cannot encode type {type(value)} to CBOR")


def get_canonical_hash(model: BaseModel, exclude_fields: set[str] | None = None) -> str:
    """
    Compute a deterministic SHA-256 hash of a Pydantic model using canonical CBOR encoding.
    
    This function ensures:
    1. Identical hashes across different Python versions and platforms
    2. Key ordering independence (CBOR canonical encoding sorts keys)
    3. Deterministic encoding of datetime/UUID types
    4. Tamper-evident records (any modification changes the hash)
    
    Args:
        model: Pydantic model instance to hash
        exclude_fields: Optional set of field names to exclude from hashing
                       (useful for excluding signature fields)
    
    Returns:
        str: Hexadecimal SHA-256 hash (64 characters)
    
    Example:
        >>> from epi_core.schemas import ManifestModel
        >>> manifest = ManifestModel(cli_command="epi record --out test.epi")
        >>> hash1 = get_canonical_hash(manifest)
        >>> # Same model with fields in different order
        >>> manifest2 = ManifestModel(cli_command="epi record --out test.epi")
        >>> hash2 = get_canonical_hash(manifest2)
        >>> assert hash1 == hash2  # Hashes are identical
    """
    # Convert model to dict
    model_dict = model.model_dump()
    
    # Normalize datetime and UUID fields to strings
    def normalize_value(value: Any) -> Any:
        if isinstance(value, datetime):
            # Remove microseconds and convert to ISO 8601 string with Z suffix
            normalized_dt = value.replace(microsecond=0)
            return normalized_dt.isoformat() + "Z"
        elif isinstance(value, UUID):
            # Convert UUID to canonical string representation
            return str(value)
        elif isinstance(value, dict):
            return {k: normalize_value(v) for k, v in value.items()}
        elif isinstance(value, list):
            return [normalize_value(item) for item in value]
        else:
            return value
    
    # Normalize datetime and UUID fields to strings
    model_dict = normalize_value(model_dict)
    
    if exclude_fields:
        for field in exclude_fields:
            model_dict.pop(field, None)

    # JSON Canonicalization for Spec v1.1+
    # Check if model has spec_version and if it indicates JSON usage
    # We default to CBOR for backward compatibility
    
    use_json = False
    
    # Check spec_version in model or dict
    spec_version = model_dict.get("spec_version")
    if spec_version and (spec_version.startswith("1.1") or "json" in spec_version):
        use_json = True
        
    if use_json:
        return _get_json_canonical_hash(model_dict)
    else:
        return _get_cbor_canonical_hash(model_dict)


def _get_json_canonical_hash(data: Any) -> str:
    """Compute canonical SHA-256 hash using JSON (RFC 8785 style)."""
    import json
    
    # Dump to JSON with sorted keys and no whitespace
    json_bytes = json.dumps(
        data,
        sort_keys=True,
        separators=(',', ':'),
        ensure_ascii=False
    ).encode("utf-8")
    
    return hashlib.sha256(json_bytes).hexdigest()


def _get_cbor_canonical_hash(data: Any) -> str:
    """Compute canonical SHA-256 hash using CBOR (Legacy v1.0)."""
    # Encode to canonical CBOR
    cbor_bytes = cbor2.dumps(
        data,
        canonical=True,
        default=_cbor_default_encoder
    )
    
    # Compute SHA-256 hash
    return hashlib.sha256(cbor_bytes).hexdigest()


def verify_hash(model: BaseModel, expected_hash: str, exclude_fields: set[str] | None = None) -> bool:
    """
    Verify that a model's canonical hash matches an expected value.
    
    Args:
        model: Pydantic model instance to verify
        expected_hash: Expected hexadecimal SHA-256 hash
        exclude_fields: Optional set of field names to exclude from hashing
    
    Returns:
        bool: True if hashes match, False otherwise
    
    Example:
        >>> manifest = ManifestModel(cli_command="epi record --out test.epi")
        >>> expected = get_canonical_hash(manifest)
        >>> assert verify_hash(manifest, expected) == True
    """
    actual_hash = get_canonical_hash(model, exclude_fields)
    return actual_hash == expected_hash


