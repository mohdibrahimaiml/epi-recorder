"""
Shared capture contracts for the open EPI ingestion layer.

These models sit below any future control plane so developers, gateways,
importers, and reviewer workflows can all speak the same event shape.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from epi_core.time_utils import utc_now

CAPTURE_SPEC_VERSION = "1.0"


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def _clean_str(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _first_meta_value(meta: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = _clean_str(meta.get(key))
        if value:
            return value
    return None


def _default_trust_class(capture_mode: str) -> str:
    mapping = {
        "direct": "verified_direct",
        "imported": "verified_imported",
        "manual": "partial",
    }
    return mapping.get(capture_mode, "partial")


class CaptureProvenanceModel(BaseModel):
    """Provenance and trust state for one captured event."""

    source: str = Field(default="epi_gateway", description="Capture source or adapter name.")
    capture_mode: Literal["direct", "imported", "manual"] = Field(
        default="direct",
        description="How the event reached EPI.",
    )
    trust_class: Literal[
        "verified_direct",
        "verified_imported",
        "partial",
        "opaque_external",
    ] | None = Field(
        default=None,
        description="Normalized trust label for reviewers and auditors.",
    )
    notes: str | None = Field(default=None, description="Optional caveat or bridge warning.")

    model_config = ConfigDict(extra="allow")

    @model_validator(mode="after")
    def _populate_default_trust(self) -> "CaptureProvenanceModel":
        if not self.trust_class:
            self.trust_class = _default_trust_class(self.capture_mode)
        return self


class CaptureEventModel(BaseModel):
    """
    Shared event shape for open capture paths.

    Gateways, SDKs, importers, and future connectors should all normalize
    incoming AI decision telemetry into this structure before it enters any
    storage or control-plane layer.
    """

    schema_version: str = Field(default=CAPTURE_SPEC_VERSION)
    event_id: str = Field(default_factory=lambda: _new_id("evt"))
    captured_at: datetime = Field(default_factory=utc_now)
    kind: str
    content: dict[str, Any] = Field(default_factory=dict)
    meta: dict[str, Any] = Field(default_factory=dict)
    trace_id: str | None = None
    decision_id: str | None = None
    case_id: str | None = None
    workflow_id: str | None = None
    workflow_name: str | None = None
    source_app: str | None = None
    actor_id: str | None = None
    provider: str | None = None
    model: str | None = None
    provenance: CaptureProvenanceModel = Field(default_factory=CaptureProvenanceModel)

    model_config = ConfigDict(extra="allow")

    @model_validator(mode="before")
    @classmethod
    def _lift_common_meta_fields(cls, raw: Any) -> Any:
        if isinstance(raw, cls):
            return raw.model_dump(mode="json")
        if raw is None:
            return raw

        data = dict(raw)
        meta = dict(data.get("meta") or {})

        mappings = {
            "trace_id": ("trace_id", "traceId"),
            "decision_id": ("decision_id", "decisionId"),
            "case_id": ("case_id", "caseId"),
            "workflow_id": ("workflow_id", "workflowId"),
            "workflow_name": ("workflow_name", "workflowName"),
            "source_app": ("source_app", "sourceApp", "app"),
            "actor_id": ("actor_id", "actorId", "user_id", "userId"),
            "provider": ("provider",),
            "model": ("model", "model_name", "modelName"),
        }

        for field_name, meta_keys in mappings.items():
            if _clean_str(data.get(field_name)):
                continue
            value = _first_meta_value(meta, *meta_keys)
            if value:
                data[field_name] = value

        provenance_payload = data.get("provenance")
        if isinstance(provenance_payload, dict):
            provenance = dict(provenance_payload)
        else:
            provenance = {}
        provenance.setdefault("source", _first_meta_value(meta, "source", "bridge_source") or "epi_gateway")
        provenance.setdefault("capture_mode", _first_meta_value(meta, "capture_mode") or "direct")
        notes = _first_meta_value(meta, "bridge_warning", "notes")
        if notes and not provenance.get("notes"):
            provenance["notes"] = notes
        data["provenance"] = provenance

        return data

    @model_validator(mode="after")
    def _mirror_fields_into_meta(self) -> "CaptureEventModel":
        meta = dict(self.meta or {})
        mirrored_fields = (
            "trace_id",
            "decision_id",
            "case_id",
            "workflow_id",
            "workflow_name",
            "source_app",
            "actor_id",
            "provider",
            "model",
        )
        for field_name in mirrored_fields:
            value = getattr(self, field_name)
            if value:
                meta.setdefault(field_name, value)
        meta.setdefault("capture_spec_version", self.schema_version)
        meta.setdefault("provenance", self.provenance.model_dump(mode="json"))
        self.meta = meta
        return self


class CaptureBatchModel(BaseModel):
    """Append-only storage batch for captured events."""

    schema_version: str = Field(default=CAPTURE_SPEC_VERSION)
    batch_id: str = Field(default_factory=lambda: _new_id("batch"))
    created_at: datetime = Field(default_factory=utc_now)
    count: int = 0
    items: list[CaptureEventModel] = Field(default_factory=list)

    model_config = ConfigDict(extra="allow")

    @model_validator(mode="after")
    def _sync_count(self) -> "CaptureBatchModel":
        self.count = len(self.items)
        return self

    @classmethod
    def from_items(cls, items: Iterable[CaptureEventModel | dict[str, Any]]) -> "CaptureBatchModel":
        return cls(items=[coerce_capture_event(item) for item in items])


def coerce_capture_event(item: CaptureEventModel | dict[str, Any]) -> CaptureEventModel:
    """Normalize a raw payload or already-built event into the shared schema."""
    if isinstance(item, CaptureEventModel):
        return item
    return CaptureEventModel.model_validate(item)


def build_capture_batch(items: Iterable[CaptureEventModel | dict[str, Any]]) -> CaptureBatchModel:
    """Convenience helper for turning a stream of events into one persisted batch."""
    return CaptureBatchModel.from_items(items)
