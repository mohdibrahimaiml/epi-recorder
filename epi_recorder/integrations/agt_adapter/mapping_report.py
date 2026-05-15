"""Build and manage mapping reports for AGT → EPI imports.

Every transformation is recorded. The report is stored inside the
.epi artifact as mapping_report.json.
"""

from __future__ import annotations

from datetime import datetime, timezone

from .schemas import FieldMapping, MappingReport


def create_report(agt_version: str = "") -> MappingReport:
    """Create a fresh mapping report."""
    return MappingReport(
        agt_version_detected=agt_version,
        import_timestamp=datetime.now(timezone.utc),
    )


def add_exact(report: MappingReport, source: str, target: str, value: str = "") -> None:
    """Record an exact 1:1 field mapping."""
    report.field_mappings.append(
        FieldMapping(
            source_field=source,
            target_field=target,
            mapping_type="exact",
            source_value=value,
            target_value=value,
        )
    )


def add_dropped(report: MappingReport, field: str, reason: str = "") -> None:
    """Record a dropped field with reason."""
    report.field_mappings.append(
        FieldMapping(
            source_field=field,
            target_field="(none)",
            mapping_type="dropped",
            notes=reason or "No EPI equivalent",
        )
    )


def add_preserved_raw(report: MappingReport, field: str, count: int = 0) -> None:
    """Record a field preserved raw (unknown fields from AGT)."""
    report.field_mappings.append(
        FieldMapping(
            source_field=field,
            target_field="raw_agt_evidence",
            mapping_type="preserved_raw",
            notes=f"{count} raw fields preserved" if count else "Preserved as raw data",
        )
    )
    report.unknown_fields_preserved.append(field)


def finalize_report(report: MappingReport) -> MappingReport:
    """Finalize report with counts and warnings."""
    report.total_target_fields = len(report.field_mappings)

    dropped = report.dropped_count
    if dropped > 0:
        report.warnings.append(
            f"{dropped} fields dropped — see mapping report for details"
        )

    return report
