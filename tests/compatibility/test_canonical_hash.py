"""
Lock the canonical hash algorithm. Any drift in serialization order,
datetime handling, or algorithm selection fails the test.
"""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from epi_core.schemas import ManifestModel
from epi_core.serialize import get_canonical_hash


GOLDEN_VECTORS_PATH = Path(__file__).with_suffix("").parent / "golden" / "canonical_hash_vectors.json"


def _load_vectors():
    data = json.loads(GOLDEN_VECTORS_PATH.read_text(encoding="utf-8"))
    return {v["name"]: v for v in data["vectors"]}


def test_v2_manifest_uses_json_canonicalization():
    """spec_version >= 2 must use JSON canonical hash (not CBOR)."""
    manifest = ManifestModel(spec_version="4.0.1")
    hash_hex = get_canonical_hash(manifest)

    # Reproduce the JSON canonicalization manually
    model_dict = manifest.model_dump()
    # normalize datetime/UUID
    model_dict["created_at"] = manifest.created_at.replace(microsecond=0, tzinfo=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    model_dict["workflow_id"] = str(manifest.workflow_id)
    json_bytes = json.dumps(model_dict, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    expected = hashlib.sha256(json_bytes).hexdigest()

    assert hash_hex == expected, "v2+ canonical hash does not match expected JSON canonicalization"


def test_v1_manifest_uses_cbor_canonicalization():
    """spec_version < 2 must use CBOR canonical hash."""
    manifest = ManifestModel(spec_version="1.0.0")
    hash_hex = get_canonical_hash(manifest)

    # Should not match JSON canonicalization
    model_dict = manifest.model_dump()
    model_dict["created_at"] = manifest.created_at.replace(microsecond=0, tzinfo=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    model_dict["workflow_id"] = str(manifest.workflow_id)
    json_bytes = json.dumps(model_dict, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    json_hash = hashlib.sha256(json_bytes).hexdigest()

    assert hash_hex != json_hash, "v1 manifest should use CBOR, not JSON"


def test_datetime_microseconds_are_stripped():
    """Microseconds must be stripped from datetime before hashing."""
    dt_with_us = datetime(2025, 1, 15, 10, 30, 45, 123456, tzinfo=timezone.utc)
    dt_without_us = datetime(2025, 1, 15, 10, 30, 45, 0, tzinfo=timezone.utc)
    fixed_uuid = UUID("550e8400-e29b-41d4-a716-446655440000")

    m1 = ManifestModel(spec_version="4.0.1", workflow_id=fixed_uuid, created_at=dt_with_us)
    m2 = ManifestModel(spec_version="4.0.1", workflow_id=fixed_uuid, created_at=dt_without_us)

    h1 = get_canonical_hash(m1)
    h2 = get_canonical_hash(m2)

    assert h1 == h2, "Datetime microseconds must be stripped for hash stability"


def test_signature_field_is_excluded_from_hash():
    """The signature field must never be part of the signed payload."""
    manifest = ManifestModel(spec_version="4.0.1")
    hash_without_sig = get_canonical_hash(manifest, exclude_fields={"signature"})
    hash_with_sig = get_canonical_hash(manifest)
    # When signature is None, excluding it (omitting the key) produces a different
    # hash than including it as null — this is expected and correct.
    assert hash_without_sig != hash_with_sig

    # Now set a signature and ensure exclusion works
    manifest.signature = "ed25519:test:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    hash_without_sig = get_canonical_hash(manifest, exclude_fields={"signature"})
    hash_with_sig = get_canonical_hash(manifest)
    assert hash_without_sig != hash_with_sig, "Signature field must affect hash when included"


def test_empty_manifest_hash_is_stable():
    """An empty-ish manifest must produce a deterministic, known hash."""
    manifest = ManifestModel(
        spec_version="4.0.1",
        workflow_id=UUID(int=0),
        created_at=datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
    )
    hash_hex = get_canonical_hash(manifest)
    assert len(hash_hex) == 64
    # The hash should be deterministic across runs
    hash_hex_2 = get_canonical_hash(manifest)
    assert hash_hex == hash_hex_2


def test_golden_vectors_match_reference_implementation():
    """Canonical hashes must match the published conformance vectors."""
    vectors = _load_vectors()

    # Vector 1: ManifestModel_basic
    v1 = vectors["ManifestModel_basic"]
    m1 = ManifestModel(
        spec_version="v2.0",
        workflow_id=UUID("550e8400-e29b-41d4-a716-446655440000"),
        created_at=datetime(2025, 6, 8, 12, 0, 0, tzinfo=timezone.utc),
        cli_command="epi record --out test.epi",
        file_manifest={
            "steps.jsonl": "a" * 64,
            "policy.json": "b" * 64,
        },
    )
    assert get_canonical_hash(m1) == v1["expected_hash"], "ManifestModel_basic vector mismatch"

    # Vector 2: StepModel_source_type_excluded
    from epi_core.schemas import StepModel
    v2 = vectors["StepModel_source_type_excluded"]
    s2 = StepModel(
        index=0,
        timestamp=datetime(2025, 6, 8, 12, 0, 0, tzinfo=timezone.utc),
        kind="llm.request",
        content={"prompt": "Hello"},
    )
    assert get_canonical_hash(s2) == v2["expected_hash"], "StepModel_source_type_excluded vector mismatch"

    # Vector 3: Unicode_ensure_ascii
    v3 = vectors["Unicode_ensure_ascii"]
    canon = json.dumps({"name": "Müller", "score": 100}, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    expected = hashlib.sha256(canon.encode("utf-8")).hexdigest()
    assert expected == v3["expected_hash"], "Unicode_ensure_ascii vector mismatch"


def test_non_ascii_uses_literal_utf8():
    r"""Non-ASCII characters are emitted as literal UTF-8 bytes for AlgoVoi cross-compatibility."""
    manifest = ManifestModel(spec_version="4.0.1", goal="Müller test")
    hash_hex = get_canonical_hash(manifest)

    model_dict = manifest.model_dump()
    model_dict["created_at"] = manifest.created_at.replace(microsecond=0, tzinfo=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    model_dict["workflow_id"] = str(manifest.workflow_id)
    # goal contains a non-ASCII character
    with_false = json.dumps(model_dict, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    with_true = json.dumps(model_dict, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")

    assert hash_hex == hashlib.sha256(with_false).hexdigest(), (
        "ensure_ascii=False (literal UTF-8) must match the canonical hash"
    )
    assert hash_hex != hashlib.sha256(with_true).hexdigest(), (
        "ensure_ascii=True (escaped) must produce a different hash for non-ASCII content"
    )
