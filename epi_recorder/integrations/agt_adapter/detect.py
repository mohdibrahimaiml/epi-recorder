"""Detect AGT artifact type from content — never from filename.

AGT exports come in multiple formats. Detection is by inspecting
the JSON structure, not parsing filenames.
"""

from __future__ import annotations

import json
from enum import Enum
from pathlib import Path
from typing import Any

from .errors import AGTArtifactError


class AGTArtifactType(str, Enum):
    """Supported AGT artifact export types."""

    EXPORT_BUNDLE = "export_bundle"  # audit.export() output
    FILE_AUDIT_SINK = "file_audit_sink"  # FileAuditSink JSONL
    CLOUDEVENTS = "cloudevents"  # export_cloudevents() output
    SINGLE_ENTRY = "single_entry"  # Single AuditEntry dict
    UNKNOWN = "unknown"


def detect_artifact_type(data: dict[str, Any] | list[Any]) -> AGTArtifactType:
    """Detect AGT artifact type from parsed JSON content.

    Detection rules (order matters):
    1. If has 'entries' key → EXPORT_BUNDLE
    2. If has 'specversion' == '1.0' → CLOUDEVENTS
    3. If has 'entry_id' + 'entry_hash' + 'event_type' → SINGLE_ENTRY
    4. Otherwise → UNKNOWN
    """
    if isinstance(data, dict):
        if "entries" in data and isinstance(data.get("entries"), list):
            return AGTArtifactType.EXPORT_BUNDLE
        if data.get("specversion") == "1.0" and "type" in data:
            return AGTArtifactType.CLOUDEVENTS
        if all(k in data for k in ("entry_id", "event_type")):
            return AGTArtifactType.SINGLE_ENTRY
    elif isinstance(data, list) and len(data) > 0:
        first = data[0]
        if isinstance(first, dict) and first.get("specversion") == "1.0":
            return AGTArtifactType.CLOUDEVENTS

    return AGTArtifactType.UNKNOWN


def detect_file_format(path: str | Path) -> tuple[AGTArtifactType, list[dict]]:
    """Read and detect AGT artifact file format.

    Supports .json (single object), .jsonl (one object per line),
    and .json with array at root.

    Returns: (artifact_type, list_of_entry_dicts)
    """
    path = Path(path)
    if not path.exists():
        raise AGTArtifactError(f"File not found: {path}")

    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        raise AGTArtifactError(f"Empty file: {path}")

    # Try JSONL first (FileAuditSink format)
    if "\n" in raw and all(line.strip() for line in raw.split("\n")):
        try:
            entries = [json.loads(line) for line in raw.split("\n") if line.strip()]
            if entries and all("entry_id" in e for e in entries):
                return AGTArtifactType.FILE_AUDIT_SINK, entries
        except json.JSONDecodeError:
            pass  # Not valid JSONL

    # Try single JSON object
    try:
        data = json.loads(raw)
        artifact_type = detect_artifact_type(data)

        if artifact_type == AGTArtifactType.EXPORT_BUNDLE:
            return artifact_type, data.get("entries", [])
        elif artifact_type == AGTArtifactType.CLOUDEVENTS:
            entries = data if isinstance(data, list) else [data]
            return artifact_type, entries
        elif artifact_type == AGTArtifactType.SINGLE_ENTRY:
            return artifact_type, [data]
        else:
            raise AGTArtifactError(f"Unrecognized AGT artifact format in {path}")
    except json.JSONDecodeError as e:
        raise AGTArtifactError(f"Invalid JSON in {path}: {e}")


def detect_agt_version(entries: list[dict]) -> str:
    """Detect AGT version from entry field presence.

    Version heuristics:
    - v4.1+: entries have 'policy_decision' field
    - v4.0: entries have 'data' but no 'policy_decision'
    - v3.x: entries have 'entry_hash' but simpler 'data'
    - unknown: minimal field set
    """
    if not entries:
        return "unknown"

    sample = entries[0]
    has_policy = "policy_decision" in sample
    has_data = "data" in sample
    has_hmac = "signature" in sample and "content_hash" in sample

    if has_hmac:
        return "4.1+" if has_policy else "4.0"
    if has_policy and has_data:
        return "4.1+"
    if has_data and not has_policy:
        return "4.0"
    if "entry_hash" in sample:
        return "3.x"

    return "unknown"
