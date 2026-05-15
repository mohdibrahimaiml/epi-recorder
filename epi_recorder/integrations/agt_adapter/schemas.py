"""Pydantic schemas for AGT AuditEntry, EEOAP envelope, and mapping reports.

All AGT-facing models use extra="allow" to preserve unknown fields from
future AGT versions without breaking parsing.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from epi_core._version import get_version


# ─────────────────────────────────────────────────────────────
# AGT AuditEntry Models
# ─────────────────────────────────────────────────────────────


class AGTAction(str, Enum):
    """AGT action values from audit.log() API."""

    ALLOW = "allow"
    DENY = "deny"
    AUDIT = "audit"
    QUARANTINE = "quarantine"
    WARNING = "warning"


class AGTOutcome(str, Enum):
    """AGT outcome values from audit.log() API."""

    SUCCESS = "success"
    FAILURE = "failure"
    DENIED = "denied"
    ERROR = "error"


class AGTEventType(str, Enum):
    """AGT event types from Tutorial 04."""

    TOOL_INVOCATION = "tool_invocation"
    TOOL_BLOCKED = "tool_blocked"
    POLICY_EVALUATION = "policy_evaluation"
    POLICY_VIOLATION = "policy_violation"
    ROGUE_DETECTION = "rogue_detection"
    AGENT_INVOCATION = "agent_invocation"


class AGTFileAuditEntry(BaseModel):
    """A single entry from FileAuditSink JSONL output.

    Contains HMAC signature and chain hashes in addition to
    the base AuditEntry fields.
    """

    model_config = {"extra": "allow"}

    entry_id: str
    timestamp: datetime
    event_type: str  # Not enum — future types must parse
    agent_did: str
    action: str
    resource: str = ""
    data: dict[str, Any] = Field(default_factory=dict)
    outcome: str
    policy_decision: str = ""
    trace_id: str = ""
    entry_hash: str = ""
    content_hash: str = ""
    previous_hash: str = ""
    signature: str = ""  # HMAC signature from FileAuditSink


class AGTExportEntry(BaseModel):
    """A single entry from audit.export() dict output."""

    model_config = {"extra": "allow"}

    entry_id: str
    timestamp: datetime
    event_type: str
    agent_did: str
    action: str
    resource: str = ""
    data: dict[str, Any] = Field(default_factory=dict)
    outcome: str
    policy_decision: str = ""
    trace_id: str = ""
    entry_hash: str = ""


class AGTExportBundle(BaseModel):
    """Full output of audit.export() — entries + metadata."""

    model_config = {"extra": "allow"}

    entries: list[AGTExportEntry | AGTFileAuditEntry]
    metadata: dict[str, Any] = Field(default_factory=dict)


class AGTCloudEvent(BaseModel):
    """CloudEvents v1.0 envelope from export_cloudevents()."""

    model_config = {"extra": "allow"}

    specversion: str = "1.0"
    type: str  # e.g. "ai.agentmesh.tool.invoked"
    source: str  # agent DID
    id: str
    time: datetime
    datacontenttype: str = "application/json"
    data: dict[str, Any] = Field(default_factory=dict)


# ─────────────────────────────────────────────────────────────
# EEOAP Envelope (AGT-accepted external accountability shape)
# ─────────────────────────────────────────────────────────────


class EEOAPEvidenceRef(BaseModel):
    """Reference to an evidence artifact."""

    ref_type: Literal["agt_audit", "epi_receipt", "acta_signed"]
    artifact_hash: str  # SHA-256 of the evidence artifact
    source_uri: str = ""  # Where to retrieve the artifact
    description: str = ""


class EEOAPStatement(BaseModel):
    """External accountability statement shape accepted by AGT.

    From issue #1314: subject/actor refs, policy digest, decision,
    occurred_at, input/output refs, evidence refs.
    """

    model_config = {"extra": "allow"}

    statement_id: str
    profile_version: str = "EEOAP-v0.1"
    created_at: datetime

    # Actor / subject
    actor_did: str = ""  # who performed the action
    subject_ref: str = ""  # what was acted upon

    # Policy context
    policy_digest: str = ""  # SHA-256 of applicable policy
    decision: str = ""  # allow | deny | quarantine | review
    decision_basis: str = ""  # human-readable reason

    # Timing
    occurred_at: datetime | None = None
    recorded_at: datetime | None = None

    # Evidence references (the key integration point)
    evidence_refs: list[EEOAPEvidenceRef] = Field(default_factory=list)

    # Raw preservation
    raw_agt_evidence_b64: str = ""  # Base64-encoded raw AGT export
    raw_epi_evidence_b64: str = ""  # Base64-encoded raw EPI artifact


# ─────────────────────────────────────────────────────────────
# Mapping Report
# ─────────────────────────────────────────────────────────────


class FieldMapping(BaseModel):
    """Single field mapping entry for the mapping report."""

    source_field: str
    target_field: str
    mapping_type: Literal[
        "exact",  # 1:1 copy (e.g., entry_id → step_id)
        "translated",  # transformed (e.g., event_type → step kind)
        "derived",  # computed from source (e.g., entry_hash → step_hash)
        "synthesized",  # invented with no source (e.g., default tags)
        "preserved_raw",  # stored but not mapped (unknown AGT fields)
        "dropped",  # intentionally discarded
    ]
    source_value: str = ""  # truncated for privacy
    target_value: str = ""
    notes: str = ""


class MappingReport(BaseModel):
    """Complete mapping report for an AGT → EPI import."""

    mapping_version: str = "1.0"
    agt_version_detected: str = ""
    epi_version: str = Field(default_factory=lambda: get_version())
    import_timestamp: datetime
    total_source_fields: int = 0
    total_target_fields: int = 0
    field_mappings: list[FieldMapping] = Field(default_factory=list)
    unknown_fields_preserved: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)

    @property
    def exact_count(self) -> int:
        return sum(1 for m in self.field_mappings if m.mapping_type == "exact")

    @property
    def dropped_count(self) -> int:
        return sum(1 for m in self.field_mappings if m.mapping_type == "dropped")

    @property
    def preserved_count(self) -> int:
        return sum(1 for m in self.field_mappings if m.mapping_type == "preserved_raw")
