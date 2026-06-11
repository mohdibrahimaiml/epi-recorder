"""
Generate edge-case canonical hash vectors for the golden fixture.
Run this script to append new vectors to canonical_hash_vectors.json.
"""

import json
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from epi_core.schemas import ManifestModel, StepModel
from epi_core.serialize import get_canonical_hash

GOLDEN_PATH = Path(__file__).with_suffix("").parent / "golden" / "canonical_hash_vectors.json"


def _make_vector(name: str, input_dict: dict, expected_hash: str, canonical_json: str | None = None):
    return {
        "name": name,
        "input": input_dict,
        **({"canonical_json": canonical_json} if canonical_json else {}),
        "expected_hash": expected_hash,
    }


def main():
    data = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    existing_names = {v["name"] for v in data["vectors"]}
    new_vectors = []

    # Vector 4: Empty file_manifest (empty dict edge case)
    m4 = ManifestModel(
        spec_version="v2.0",
        workflow_id=UUID("550e8400-e29b-41d4-a716-446655440000"),
        created_at=datetime(2025, 6, 8, 12, 0, 0, tzinfo=timezone.utc),
        file_manifest={},
    )
    h4 = get_canonical_hash(m4)
    d4 = m4.model_dump()
    d4["created_at"] = "2025-06-08T12:00:00Z"
    d4["workflow_id"] = str(m4.workflow_id)
    new_vectors.append(_make_vector("Empty_file_manifest", d4, h4))

    # Vector 5: Nested deep content (in StepModel.content which is Dict[str, Any])
    s5 = StepModel(
        index=2,
        timestamp=datetime(2025, 6, 8, 12, 0, 0, tzinfo=timezone.utc),
        kind="llm.request",
        content={
            "nested": {
                "deep": {
                    "value": 42,
                    "list": [1, 2, {"inner": "text"}],
                }
            }
        },
    )
    h5 = get_canonical_hash(s5)
    d5 = s5.model_dump()
    d5["timestamp"] = "2025-06-08T12:00:00Z"
    d5.pop("source_type", None)  # excluded from hash
    new_vectors.append(_make_vector("Nested_deep_content", d5, h5))

    # Vector 6: Empty collections in step content
    s6 = StepModel(
        index=1,
        timestamp=datetime(2025, 6, 8, 12, 0, 0, tzinfo=timezone.utc),
        kind="validation.start",
        content={"rules": [], "metadata": {}},
    )
    h6 = get_canonical_hash(s6)
    d6 = s6.model_dump()
    d6["timestamp"] = "2025-06-08T12:00:00Z"
    d6.pop("source_type", None)  # excluded from hash
    new_vectors.append(_make_vector("Empty_collections_in_step", d6, h6))

    # Vector 7: Long string value
    m7 = ManifestModel(
        spec_version="v2.0",
        workflow_id=UUID("550e8400-e29b-41d4-a716-446655440000"),
        created_at=datetime(2025, 6, 8, 12, 0, 0, tzinfo=timezone.utc),
        notes="A" * 1000,
    )
    h7 = get_canonical_hash(m7)
    d7 = m7.model_dump()
    d7["created_at"] = "2025-06-08T12:00:00Z"
    d7["workflow_id"] = str(m7.workflow_id)
    new_vectors.append(_make_vector("Long_string_value", d7, h7))

    # Vector 8: Minimal manifest (only required fields, everything else null/default)
    m8 = ManifestModel(
        spec_version="v2.0",
        workflow_id=UUID(int=0),
        created_at=datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
    )
    h8 = get_canonical_hash(m8)
    d8 = m8.model_dump()
    d8["created_at"] = "2025-01-01T00:00:00Z"
    d8["workflow_id"] = str(m8.workflow_id)
    new_vectors.append(_make_vector("Minimal_manifest", d8, h8))

    # Filter out any that already exist
    for v in new_vectors:
        if v["name"] in existing_names:
            print(f"Skipping existing vector: {v['name']}")
            continue
        data["vectors"].append(v)
        print(f"Added vector: {v['name']} -> {v['expected_hash']}")

    # Write back with deterministic formatting
    GOLDEN_PATH.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"\nUpdated: {GOLDEN_PATH}")


if __name__ == "__main__":
    main()
