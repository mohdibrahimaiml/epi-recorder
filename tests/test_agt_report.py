from datetime import UTC, datetime

import pytest

from epi_recorder.integrations.agt.report import MappingReportBuilder
from epi_recorder.integrations.agt.schema import AGTBundleModel

FIXED_REPORT_TIME = datetime(2026, 4, 7, 12, 0, 0, tzinfo=UTC)


def _builder() -> MappingReportBuilder:
    return MappingReportBuilder(generated_at=FIXED_REPORT_TIME, importer_version="test-importer")


def _minimal_bundle() -> AGTBundleModel:
    return AGTBundleModel.model_validate(
        {
            "audit_logs": [
                {
                    "entry_id": "evt-1",
                    "timestamp": "2026-04-06T10:00:00Z",
                    "event_type": "tool_invocation",
                    "action": "lookup",
                    "trace_id": "trace-1",
                    "data": {"tool_name": "lookup"},
                    "outcome": "success",
                }
            ]
        }
    )


def test_report_builder_serializes_all_categories():
    builder = _builder()
    builder.observe_bundle(_minimal_bundle())
    builder.classify_field("audit_logs", "timestamp", "exact", mapped_to="steps[].timestamp")
    builder.classify_field("audit_logs", "event_type", "translated", mapped_to="steps[].kind")
    builder.classify_field("audit_logs", "outcome", "derived", mapped_to="analysis.json")
    builder.classify_field(
        "audit_logs",
        "trace_id",
        "preserved_raw",
        mapped_to="artifacts/agt/bundle.json",
    )
    builder.classify_field("audit_logs", "entry_id", "dropped", notes="test drop")
    builder.record_synthesized("analysis.json", mapped_to="analysis.json")
    report = builder.build(strict=False)

    assert report.report_version == "agt-mapping-report/v1"
    assert report.generated_at == FIXED_REPORT_TIME
    assert report.field_handling.exact[0].field == "timestamp"
    assert report.field_handling.translated[0].field == "event_type"
    assert report.field_handling.derived[0].field == "outcome"
    assert report.field_handling.preserved_raw[0].field == "trace_id"
    assert report.field_handling.dropped[0].field == "entry_id"
    assert report.field_handling.synthesized[0].field == "analysis.json"


def test_report_builder_detects_unknown_events():
    builder = _builder()
    builder.observe_bundle(_minimal_bundle())
    builder.record_event_mapping(
        section="audit_logs",
        source_type="custom_event",
        mapped_kind="agt.audit.custom_event",
        recognized=False,
        entry_id="evt-1",
    )

    report = builder.build(strict=False)
    assert report.event_mapping.unknown[0].source_type == "custom_event"
    assert report.event_mapping.unknown[0].example_entry_ids == ["evt-1"]


def test_report_builder_detects_unclassified_fields():
    builder = _builder()
    builder.observe_bundle(_minimal_bundle())
    builder.classify_field("audit_logs", "timestamp", "exact", mapped_to="steps[].timestamp")
    report = builder.build(strict=False)

    assert any(item.field == "event_type" for item in report.field_handling.unclassified)
    with pytest.raises(ValueError, match="unclassified field"):
        builder.build(strict=True)


def test_report_builder_records_dedupe_conflicts():
    builder = _builder()
    builder.record_dedupe_conflict(
        group="group-1",
        candidates=[
            {"section": "audit_logs", "entry_id": "evt-1", "trace_id": "trace-1"},
            {"section": "flight_recorder", "entry_id": "42", "trace_id": "trace-1"},
        ],
        resolution="preferred_audit",
        reason="preferred_audit_over_flight",
    )
    builder.record_step_transformation(
        audit_input_count=1,
        flight_input_count=1,
        output_count=1,
        dedupe_strategy="prefer-audit",
        duplicates_removed=1,
        kept_both_count=0,
        ambiguous_conflicts=0,
    )

    report = builder.build(strict=False)
    assert report.step_transformation.duplicates_removed == 1
    assert report.dedupe_conflicts[0].group == "group-1"
    assert report.dedupe_conflicts[0].candidates[0].section == "audit_logs"
