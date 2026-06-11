"""
Generate deterministic canonical-hash conformance vectors.

Run this script manually whenever the canonicalization contract intentionally changes:

    python tests/compatibility/_generate_canonical_vectors.py

The output is written to tests/compatibility/golden/canonical_hash_vectors.json
"""

import json
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from epi_core.schemas import ManifestModel, StepModel
from epi_core.serialize import get_canonical_hash


def _normalize_value(value):
    """Mirror of epi_core.serialize.normalize_value for vector generation."""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            normalized_dt = value.replace(microsecond=0, tzinfo=timezone.utc)
        else:
            normalized_dt = value.astimezone(timezone.utc).replace(microsecond=0)
        return normalized_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, dict):
        return {k: _normalize_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_normalize_value(item) for item in value]
    return value


def _canonical_json(data: dict) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def main() -> None:
    out_dir = Path(__file__).with_suffix("").parent / "golden"
    out_dir.mkdir(parents=True, exist_ok=True)

    vectors = []

    # Vector 1: ManifestModel (basic)
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
    d1 = _normalize_value(m1.model_dump())
    canon1 = _canonical_json(d1)
    hash1 = get_canonical_hash(m1)
    vectors.append(
        {
            "name": "ManifestModel_basic",
            "input": d1,
            "canonical_json": canon1,
            "expected_hash": hash1,
        }
    )

    # Vector 2: StepModel (source_type excluded)
    s2 = StepModel(
        index=0,
        timestamp=datetime(2025, 6, 8, 12, 0, 0, tzinfo=timezone.utc),
        kind="llm.request",
        content={"prompt": "Hello"},
    )
    d2 = _normalize_value(s2.model_dump())
    d2.pop("source_type", None)
    canon2 = _canonical_json(d2)
    hash2 = get_canonical_hash(s2)
    vectors.append(
        {
            "name": "StepModel_source_type_excluded",
            "input": d2,
            "canonical_json": canon2,
            "expected_hash": hash2,
        }
    )

    # Vector 3: Unicode ensure_ascii
    d3 = {"name": "Müller", "score": 100}
    canon3 = _canonical_json(d3)
    hash3 = hashlib.sha256(canon3.encode("utf-8")).hexdigest()
    vectors.append(
        {
            "name": "Unicode_ensure_ascii",
            "input": d3,
            "canonical_json": canon3,
            "expected_hash": hash3,
        }
    )

    out_path = out_dir / "canonical_hash_vectors.json"
    out_path.write_text(
        json.dumps({"vectors": vectors}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"Wrote {len(vectors)} vectors to {out_path}")
    for v in vectors:
        print(f"  {v['name']}: {v['expected_hash']}")


if __name__ == "__main__":
    main()
