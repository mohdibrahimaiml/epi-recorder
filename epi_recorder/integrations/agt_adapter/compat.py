"""Version compatibility helpers for AGT artifact evolution.

AGT is a moving target (Public Preview). This module handles:
- Version detection from field presence
- Safe loading of unknown formats
- Backward compatibility with older exports
- Forward compatibility (preserving unknown fields)
"""

from __future__ import annotations

from .errors import AGTVersionError


# Minimum supported AGT export version
MIN_SUPPORTED_VERSION = "3.0"

# Field sets by version (for detection, not validation)
V3_FIELDS = {"entry_id", "timestamp", "event_type", "agent_did", "action", "outcome"}
V4_FIELDS = V3_FIELDS | {"resource", "data", "policy_decision", "trace_id", "entry_hash"}
V4_1_FIELDS = V4_FIELDS | {"content_hash", "previous_hash", "signature"}  # FileAuditSink


def check_version_support(version: str) -> None:
    """Raise if version is below minimum supported."""
    if version == "unknown":
        return  # Allow unknown — detection was inconclusive

    try:
        major = int(version.split(".")[0])
    except (ValueError, IndexError):
        return

    min_major = int(MIN_SUPPORTED_VERSION.split(".")[0])
    if major < min_major:
        raise AGTVersionError(
            f"AGT version {version} is below minimum supported {MIN_SUPPORTED_VERSION}. "
            f"Upgrade AGT or use a compatibility shim."
        )


def get_known_fields(version: str) -> set[str]:
    """Get the set of known fields for a given AGT version."""
    if version.startswith("3."):
        return V3_FIELDS
    elif version == "4.0":
        return V4_FIELDS
    else:
        return V4_1_FIELDS  # 4.1+ includes FileAuditSink fields


def is_forward_compatible(detected_version: str, target_version: str) -> bool:
    """Check if detected version is forward-compatible with target."""
    # Same major version = forward compatible (extra="allow" handles new fields)
    detected_major = detected_version.split(".")[0] if "." in detected_version else ""
    target_major = target_version.split(".")[0] if "." in target_version else ""
    return detected_major == target_major
