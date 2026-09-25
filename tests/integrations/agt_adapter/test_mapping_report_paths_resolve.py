"""Every reported target path must resolve against the generated step.

Generic, not per-field: walks EVERY entry in the mapping report instead of
hardcoding entry_id/outcome, so a future mapping cannot drift without CI
catching it. Two directions:

(a) each reported target path resolves against the generated step —
    names the field and path on failure;
(b) inverse: every AGT-derived field present in the step appears in the
    report — a field with no provenance entry fails (catches silent writes).

Scope notes, not loopholes: targets "(none)" (dropped) and
"raw_agt_evidence" (file-level attachment, not a step path) are not step
paths and are skipped. Direction (b) checks top-level keys of
content/governance plus kind/timestamp/trace_id; container interiors
(agt_data, agt_unknown_fields) are documented as groups by their container
entries. EPI scaffolding (index, span_id, parent_span_id) is not
AGT-derived and is excluded from (b).
"""

from __future__ import annotations

from epi_recorder.integrations.agt_adapter.importer import _entry_to_step
from epi_recorder.integrations.agt_adapter.mapping_report import create_report
from epi_recorder.integrations.agt_adapter.schemas import AGTExportEntry

NON_STEP_TARGETS = {"(none)", "raw_agt_evidence"}

# EPI's own scaffolding: present in every step, not derived from AGT.
SCAFFOLD_TOP_LEVEL = {"index", "span_id", "parent_span_id"}


def _representative_entry() -> AGTExportEntry:
    return AGTExportEntry(
        entry_id="e-001",
        timestamp="2026-09-20T10:00:00Z",
        event_type="tool_invocation",
        agent_did="did:web:sales-assistant.example.com",
        action="allow",
        resource="crm.lookup",
        data={"order": "ORD-1"},
        outcome="success",
        policy_decision="allowed",
        trace_id="t-1",
        entry_hash="h" * 64,
        matched_rule="refund-cap",
        extra_note="kept-as-unknown",
    )


def _resolve(step: dict, path: str) -> bool:
    current: object = step
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return False
        current = current[part]
    return True


def _generate():
    report = create_report("test")
    step = _entry_to_step(0, _representative_entry(), report)
    return step, report


def test_every_reported_target_resolves_against_step():
    step, report = _generate()
    assert report.field_mappings, "representative entry produced no mappings"
    unresolved = [
        (m.source_field, m.target_field)
        for m in report.field_mappings
        if m.target_field not in NON_STEP_TARGETS
        and not _resolve(step, m.target_field)
    ]
    assert not unresolved, (
        "mapping report targets missing from the generated step: "
        + ", ".join(f"{src} -> {tgt}" for src, tgt in unresolved)
    )


def test_every_step_field_has_provenance_entry():
    step, report = _generate()
    targets = [m.target_field for m in report.field_mappings]

    def covered(key: str) -> bool:
        return any(t == key or t.endswith("." + key) for t in targets)

    checked: dict[str, bool] = {}
    for section in ("content", "governance"):
        for key in step.get(section, {}):
            checked[f"{section}.{key}"] = covered(key)
    for key in ("kind", "timestamp", "trace_id"):
        checked[key] = covered(key)

    missing = sorted(k for k, ok in checked.items() if not ok)
    assert not missing, (
        "step fields with no mapping-report provenance entry: "
        + ", ".join(missing)
    )
