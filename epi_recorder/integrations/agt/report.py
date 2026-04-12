"""
Structured transformation audit for AGT -> EPI imports.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from epi_core._version import get_version
from epi_core.time_utils import utc_now

FieldHandlingCategory = Literal[
    "exact",
    "translated",
    "derived",
    "synthesized",
    "preserved_raw",
    "dropped",
    "unclassified",
]
ClassifiedFieldCategory = Literal[
    "exact",
    "translated",
    "derived",
    "synthesized",
    "preserved_raw",
    "dropped",
]

DedupStrategy = Literal["prefer-audit", "keep-both", "fail"]
AnalysisMode = Literal["synthesized", "none"]

REPORT_VERSION = "agt-mapping-report/v1"


class FieldHandlingEntryModel(BaseModel):
    section: str
    field: str
    mapped_to: str | None = None
    count: int = 1
    notes: str | None = None

    model_config = ConfigDict(extra="forbid")


class RecognizedEventMappingModel(BaseModel):
    section: str
    source_type: str
    mapped_kind: str
    count: int = 1

    model_config = ConfigDict(extra="forbid")


class UnknownEventMappingModel(BaseModel):
    section: str
    source_type: str
    count: int = 1
    example_entry_ids: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class DedupeCandidateModel(BaseModel):
    section: str
    entry_id: str | None = None
    trace_id: str | None = None

    model_config = ConfigDict(extra="forbid")


class DedupeConflictModel(BaseModel):
    group: str
    candidates: list[DedupeCandidateModel] = Field(default_factory=list)
    resolution: str
    reason: str

    model_config = ConfigDict(extra="forbid")


class AnalysisProvenanceModel(BaseModel):
    mode: str = "none"
    synthesized: bool = False
    source_system: str = "AGT"
    confidence: str = "n/a"
    warning: str | None = None
    source_artifacts: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class SourceSummaryModel(BaseModel):
    has_audit_logs: bool = False
    has_flight_recorder: bool = False
    has_compliance_report: bool = False
    has_policy_document: bool = False
    has_runtime_context: bool = False
    section_counts: dict[str, int] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


class StepTransformationModel(BaseModel):
    audit_input_count: int = 0
    flight_input_count: int = 0
    combined_input_count: int = 0
    output_count: int = 0
    dedupe_strategy: DedupStrategy = "prefer-audit"
    duplicates_removed: int = 0
    kept_both_count: int = 0
    ambiguous_conflicts: int = 0

    model_config = ConfigDict(extra="forbid")


class EventMappingSummaryModel(BaseModel):
    recognized: list[RecognizedEventMappingModel] = Field(default_factory=list)
    unknown: list[UnknownEventMappingModel] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class FieldHandlingSummaryModel(BaseModel):
    exact: list[FieldHandlingEntryModel] = Field(default_factory=list)
    translated: list[FieldHandlingEntryModel] = Field(default_factory=list)
    derived: list[FieldHandlingEntryModel] = Field(default_factory=list)
    synthesized: list[FieldHandlingEntryModel] = Field(default_factory=list)
    preserved_raw: list[FieldHandlingEntryModel] = Field(default_factory=list)
    dropped: list[FieldHandlingEntryModel] = Field(default_factory=list)
    unclassified: list[FieldHandlingEntryModel] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class MappingReportModel(BaseModel):
    report_version: str = REPORT_VERSION
    generated_at: datetime
    importer_version: str
    source_summary: SourceSummaryModel
    step_transformation: StepTransformationModel
    event_mapping: EventMappingSummaryModel
    field_handling: FieldHandlingSummaryModel
    dedupe_conflicts: list[DedupeConflictModel] = Field(default_factory=list)
    analysis: AnalysisProvenanceModel = Field(default_factory=AnalysisProvenanceModel)
    warnings: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


def _normalize_generated_at(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _iter_leaf_paths(value: Any, prefix: str = "") -> list[str]:
    if isinstance(value, Mapping):
        paths: list[str] = []
        for key, nested in value.items():
            next_prefix = f"{prefix}.{key}" if prefix else str(key)
            paths.extend(_iter_leaf_paths(nested, next_prefix))
        return paths

    if isinstance(value, list):
        paths: list[str] = []
        for item in value:
            next_prefix = f"{prefix}[]" if prefix else "[]"
            paths.extend(_iter_leaf_paths(item, next_prefix))
        return paths

    return [prefix or "value"]


def _sorted_field_entries(
    counter: Counter[tuple[str, str, str, str]],
) -> list[FieldHandlingEntryModel]:
    items = sorted(counter.items(), key=lambda item: item[0])
    return [
        FieldHandlingEntryModel(
            section=section,
            field=field,
            mapped_to=mapped_to or None,
            count=count,
            notes=notes or None,
        )
        for (section, field, mapped_to, notes), count in items
    ]


class MappingReportBuilder:
    """
    Collect a deterministic transformation audit while importing AGT evidence.
    """

    def __init__(
        self,
        *,
        generated_at: datetime | None = None,
        importer_version: str | None = None,
    ) -> None:
        self.generated_at = _normalize_generated_at(generated_at or utc_now())
        self.importer_version = importer_version or get_version()
        self._observed_fields: dict[str, Counter[str]] = defaultdict(Counter)
        self._allocated_fields: dict[str, Counter[str]] = defaultdict(Counter)
        self._field_entries: dict[str, Counter[tuple[str, str, str, str]]] = {
            "exact": Counter(),
            "translated": Counter(),
            "derived": Counter(),
            "synthesized": Counter(),
            "preserved_raw": Counter(),
            "dropped": Counter(),
        }
        self._recognized_events: Counter[tuple[str, str, str]] = Counter()
        self._unknown_events: dict[tuple[str, str], dict[str, Any]] = {}
        self._dedupe_conflicts: list[DedupeConflictModel] = []
        self._warnings: list[str] = []
        self._source_summary = SourceSummaryModel()
        self._step_transformation = StepTransformationModel()
        self._analysis = AnalysisProvenanceModel()

    def observe_bundle(self, payload: Any) -> None:
        data = (
            payload.model_dump(mode="json", exclude_none=True)
            if hasattr(payload, "model_dump")
            else payload
        )
        if not isinstance(data, Mapping):
            return

        known_sections = {
            "metadata",
            "audit_logs",
            "flight_recorder",
            "compliance_report",
            "policy_document",
            "runtime_context",
            "slo_data",
            "annex_markdown",
            "annex_json",
            "review",
        }

        metadata = data.get("metadata")
        if isinstance(metadata, Mapping):
            self._observe_mapping("metadata", metadata)
        elif metadata not in (None, "", [], {}):
            self._observe_scalar("metadata", metadata)

        audit_logs = data.get("audit_logs")
        if isinstance(audit_logs, list):
            self._source_summary.has_audit_logs = bool(audit_logs)
            self._source_summary.section_counts["audit_logs"] = len(audit_logs)
            for entry in audit_logs:
                if isinstance(entry, Mapping):
                    self._observe_mapping("audit_logs", entry, track_count=False)
        flight_recorder = data.get("flight_recorder")
        if isinstance(flight_recorder, list):
            self._source_summary.has_flight_recorder = bool(flight_recorder)
            self._source_summary.section_counts["flight_recorder"] = len(flight_recorder)
            for entry in flight_recorder:
                if isinstance(entry, Mapping):
                    self._observe_mapping("flight_recorder", entry, track_count=False)

        for section in (
            "compliance_report",
            "policy_document",
            "runtime_context",
            "slo_data",
            "annex_json",
            "review",
        ):
            value = data.get(section)
            if isinstance(value, Mapping):
                if section == "compliance_report":
                    self._source_summary.has_compliance_report = True
                if section == "policy_document":
                    self._source_summary.has_policy_document = True
                if section == "runtime_context":
                    self._source_summary.has_runtime_context = True
                self._observe_mapping(section, value)
            elif isinstance(value, list):
                self._observe_list(section, value)

        annex_markdown = data.get("annex_markdown")
        if annex_markdown not in (None, ""):
            self._observe_scalar("annex_markdown", annex_markdown)

        for key, value in data.items():
            if key in known_sections:
                continue
            if isinstance(value, Mapping):
                self._observe_mapping(key, value)
            elif isinstance(value, list):
                self._observe_list(key, value)
            elif value not in (None, ""):
                self._observe_scalar(key, value)

    def _observe_mapping(
        self,
        section: str,
        payload: Mapping[str, Any],
        *,
        track_count: bool = True,
    ) -> None:
        leaf_paths = _iter_leaf_paths(payload)
        if track_count:
            self._source_summary.section_counts[section] = self._source_summary.section_counts.get(
                section, 0
            ) + len(leaf_paths)
        for path in leaf_paths:
            self._observed_fields[section][path] += 1

    def _observe_list(self, section: str, payload: list[Any]) -> None:
        leaf_paths = _iter_leaf_paths(payload)
        self._source_summary.section_counts[section] = self._source_summary.section_counts.get(
            section, 0
        ) + len(leaf_paths)
        for path in leaf_paths:
            self._observed_fields[section][path] += 1

    def _observe_scalar(self, section: str, value: Any) -> None:
        _ = value
        self._source_summary.section_counts[section] = (
            self._source_summary.section_counts.get(section, 0) + 1
        )
        self._observed_fields[section]["value"] += 1

    def record_event_mapping(
        self,
        *,
        section: str,
        source_type: str,
        mapped_kind: str,
        recognized: bool,
        entry_id: str | None = None,
    ) -> None:
        source_key = source_type or "event"
        if recognized:
            self._recognized_events[(section, source_key, mapped_kind)] += 1
            return

        bucket = self._unknown_events.setdefault(
            (section, source_key),
            {"count": 0, "example_entry_ids": []},
        )
        bucket["count"] += 1
        if (
            entry_id
            and entry_id not in bucket["example_entry_ids"]
            and len(bucket["example_entry_ids"]) < 3
        ):
            bucket["example_entry_ids"].append(entry_id)

    def record_step_transformation(
        self,
        *,
        audit_input_count: int,
        flight_input_count: int,
        output_count: int,
        dedupe_strategy: DedupStrategy,
        duplicates_removed: int,
        kept_both_count: int,
        ambiguous_conflicts: int,
    ) -> None:
        self._step_transformation = StepTransformationModel(
            audit_input_count=audit_input_count,
            flight_input_count=flight_input_count,
            combined_input_count=audit_input_count + flight_input_count,
            output_count=output_count,
            dedupe_strategy=dedupe_strategy,
            duplicates_removed=duplicates_removed,
            kept_both_count=kept_both_count,
            ambiguous_conflicts=ambiguous_conflicts,
        )

    def record_dedupe_conflict(
        self,
        *,
        group: str,
        candidates: list[dict[str, Any]],
        resolution: str,
        reason: str,
    ) -> None:
        self._dedupe_conflicts.append(
            DedupeConflictModel(
                group=group,
                candidates=[
                    DedupeCandidateModel(
                        section=str(candidate.get("section") or ""),
                        entry_id=(
                            str(candidate["entry_id"])
                            if candidate.get("entry_id") is not None
                            else None
                        ),
                        trace_id=(
                            str(candidate["trace_id"])
                            if candidate.get("trace_id") is not None
                            else None
                        ),
                    )
                    for candidate in candidates
                ],
                resolution=resolution,
                reason=reason,
            )
        )

    def add_warning(self, message: str) -> None:
        if message and message not in self._warnings:
            self._warnings.append(message)

    def classify_field(
        self,
        section: str,
        field: str,
        category: ClassifiedFieldCategory,
        *,
        mapped_to: str | None = None,
        notes: str | None = None,
        count: int | None = None,
    ) -> int:
        return self._claim(section, lambda item: item == field, category, mapped_to, notes, count)

    def classify_prefix(
        self,
        section: str,
        prefix: str,
        category: ClassifiedFieldCategory,
        *,
        mapped_to: str | None = None,
        notes: str | None = None,
    ) -> int:
        prefix_token = f"{prefix}."
        list_prefix = f"{prefix}["
        return self._claim(
            section,
            lambda item: item == prefix
            or item.startswith(prefix_token)
            or item.startswith(list_prefix),
            category,
            mapped_to,
            notes,
            None,
        )

    def classify_remaining(
        self,
        section: str,
        category: ClassifiedFieldCategory,
        *,
        mapped_to: str | None = None,
        notes: str | None = None,
    ) -> int:
        return self._claim(section, lambda item: True, category, mapped_to, notes, None)

    def record_synthesized(
        self,
        field: str,
        *,
        mapped_to: str | None = None,
        notes: str | None = None,
        section: str = "artifacts",
        count: int = 1,
    ) -> None:
        key = (section, field, mapped_to or "", notes or "")
        self._field_entries["synthesized"][key] += count

    def _claim(
        self,
        section: str,
        predicate: Callable[[str], bool],
        category: ClassifiedFieldCategory,
        mapped_to: str | None,
        notes: str | None,
        count: int | None,
    ) -> int:
        claimed_total = 0
        fields = sorted(self._observed_fields.get(section, {}).items())
        for field, observed_count in fields:
            if not predicate(field):
                continue
            remaining = observed_count - self._allocated_fields[section][field]
            if remaining <= 0:
                continue
            to_claim = remaining if count is None else min(remaining, count - claimed_total)
            if to_claim <= 0:
                continue
            key = (section, field, mapped_to or "", notes or "")
            self._field_entries[category][key] += to_claim
            self._allocated_fields[section][field] += to_claim
            claimed_total += to_claim
            if count is not None and claimed_total >= count:
                break
        return claimed_total

    def record_analysis(
        self,
        *,
        mode: str,
        synthesized: bool,
        confidence: str,
        warning: str | None,
        source_artifacts: list[str],
    ) -> None:
        self._analysis = AnalysisProvenanceModel(
            mode=mode,
            synthesized=synthesized,
            source_system="AGT",
            confidence=confidence,
            warning=warning,
            source_artifacts=source_artifacts,
        )

    def observed_sections(self) -> list[str]:
        return sorted(self._observed_fields)

    def unclassified_entries(self) -> list[FieldHandlingEntryModel]:
        counter: Counter[tuple[str, str, str, str]] = Counter()
        for section, fields in sorted(self._observed_fields.items()):
            for field, observed_count in sorted(fields.items()):
                remaining = observed_count - self._allocated_fields[section][field]
                if remaining <= 0:
                    continue
                counter[(section, field, "", "")] += remaining
        return _sorted_field_entries(counter)

    def unknown_events(self) -> list[UnknownEventMappingModel]:
        items = sorted(self._unknown_events.items(), key=lambda item: item[0])
        return [
            UnknownEventMappingModel(
                section=section,
                source_type=source_type,
                count=payload["count"],
                example_entry_ids=list(payload["example_entry_ids"]),
            )
            for (section, source_type), payload in items
        ]

    def build(self, *, strict: bool = False) -> MappingReportModel:
        unknown_events = self.unknown_events()
        unclassified = self.unclassified_entries()
        if strict and unknown_events:
            source = unknown_events[0]
            raise ValueError(
                "Strict import rejected unknown AGT event type "
                f"'{source.source_type}' from {source.section}"
            )
        if strict and unclassified:
            first = unclassified[0]
            raise ValueError(
                f"Strict import rejected unclassified field '{first.section}.{first.field}'"
            )

        recognized = [
            RecognizedEventMappingModel(
                section=section,
                source_type=source_type,
                mapped_kind=mapped_kind,
                count=count,
            )
            for (section, source_type, mapped_kind), count in sorted(
                self._recognized_events.items()
            )
        ]
        field_handling = FieldHandlingSummaryModel(
            exact=_sorted_field_entries(self._field_entries["exact"]),
            translated=_sorted_field_entries(self._field_entries["translated"]),
            derived=_sorted_field_entries(self._field_entries["derived"]),
            synthesized=_sorted_field_entries(self._field_entries["synthesized"]),
            preserved_raw=_sorted_field_entries(self._field_entries["preserved_raw"]),
            dropped=_sorted_field_entries(self._field_entries["dropped"]),
            unclassified=unclassified,
        )

        return MappingReportModel(
            generated_at=self.generated_at,
            importer_version=self.importer_version,
            source_summary=SourceSummaryModel.model_validate(self._source_summary.model_dump()),
            step_transformation=StepTransformationModel.model_validate(
                self._step_transformation.model_dump()
            ),
            event_mapping=EventMappingSummaryModel(recognized=recognized, unknown=unknown_events),
            field_handling=field_handling,
            dedupe_conflicts=list(self._dedupe_conflicts),
            analysis=AnalysisProvenanceModel.model_validate(self._analysis.model_dump()),
            warnings=list(self._warnings),
        )
