"""
Typed bundle contract for importing Microsoft Agent Governance Toolkit evidence.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AGTBundleMetadataModel(BaseModel):
    """Optional bundle metadata used to populate the EPI manifest."""

    workflow_id: UUID | None = None
    created_at: datetime | None = None
    cli_command: str | None = None
    goal: str | None = None
    notes: str | None = None
    approved_by: str | None = None
    tags: list[str] = Field(default_factory=list)
    system_name: str | None = None
    provider: str | None = None

    model_config = ConfigDict(extra="allow")


class AGTBundleModel(BaseModel):
    """
    Neutral JSON contract for AGT evidence imports.

    The bridge intentionally accepts plain exported data instead of AGT runtime
    classes so the importer stays decoupled from AGT package internals.
    """

    metadata: AGTBundleMetadataModel = Field(default_factory=AGTBundleMetadataModel)
    audit_logs: list[dict[str, Any]] = Field(default_factory=list)
    flight_recorder: list[dict[str, Any]] = Field(default_factory=list)
    compliance_report: dict[str, Any] | None = None
    policy_document: dict[str, Any] | None = None
    runtime_context: dict[str, Any] | None = None
    slo_data: dict[str, Any] | None = None
    annex_markdown: str | None = None
    annex_json: dict[str, Any] | list[Any] | None = None
    review: dict[str, Any] | None = None

    model_config = ConfigDict(extra="allow")

    @model_validator(mode="after")
    def _require_evidence(self) -> AGTBundleModel:
        if self.audit_logs or self.flight_recorder:
            return self
        raise ValueError("AGT bundle must include at least one of audit_logs or flight_recorder")


def coerce_agt_bundle(
    value: AGTBundleModel | Mapping[str, Any] | str | bytes | Path,
) -> AGTBundleModel:
    """Validate a bundle from an in-memory mapping or JSON payload."""

    if isinstance(value, AGTBundleModel):
        return value

    if isinstance(value, Path):
        value = value.read_text(encoding="utf-8")

    if isinstance(value, bytes):
        value = value.decode("utf-8")

    if isinstance(value, str):
        value = json.loads(value)

    if isinstance(value, Mapping):
        return AGTBundleModel.model_validate(dict(value))

    raise TypeError("AGT bundle input must be a mapping, JSON string, bytes, or Path")
