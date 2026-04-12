"""
Normalization helpers for converting AGT evidence into EPI-compatible payloads.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from epi_core.schemas import StepModel
from epi_core.time_utils import utc_now

from .report import AnalysisMode, DedupStrategy, MappingReportBuilder
from .schema import AGTBundleModel

IMPORT_ANALYZER_VERSION = "agt-import-1.1.0"
IMPORT_ANALYSIS_WARNING = "Synthesized from AGT evidence; not native EPI analysis."
IMPORT_DISCLAIMER = (
    "This analysis was synthesized from Microsoft Agent Governance Toolkit evidence during import. "
    "steps.jsonl remains the ground truth, and reviewers should treat this as imported "
    "compliance evidence rather than a native EPI analyzer output."
)

_SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def _normalize_token(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip().lower().replace(" ", "_")


def _ensure_timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)

    if isinstance(value, str) and value.strip():
        text = value.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(text)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
        except Exception:
            pass

    return utc_now()


def _timestamp_key(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat()


def _maybe_json(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    text = value.strip()
    if not text or text[0] not in "[{":
        return value
    try:
        return json.loads(text)
    except Exception:
        return value


def _canonical_outcome(value: Any) -> str:
    token = _normalize_token(value)
    if token in {"allow", "allowed", "approved", "approve", "success", "passed"}:
        return "allowed"
    if token in {"deny", "denied", "blocked", "reject", "rejected", "refused"}:
        return "blocked"
    if token in {"error", "failure", "failed"}:
        return "error"
    return token


def _audit_trace_id(entry: dict[str, Any]) -> str | None:
    return entry.get("trace_id") or entry.get("session_id")


def _flight_trace_id(entry: dict[str, Any]) -> str | None:
    return (
        entry.get("trace_id") or entry.get("session_id") or entry.get("entry_id") or entry.get("id")
    )


def _audit_entry_id(entry: dict[str, Any]) -> str | None:
    value = entry.get("entry_id")
    return str(value) if value is not None else None


def _flight_entry_id(entry: dict[str, Any]) -> str | None:
    value = entry.get("id") or entry.get("entry_id") or entry.get("trace_id")
    return str(value) if value is not None else None


def _audit_tool_name(entry: dict[str, Any]) -> str:
    data = entry.get("data") if isinstance(entry.get("data"), dict) else {}
    for key in ("tool_name", "tool", "name", "resource_name"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value
    action = entry.get("action")
    return str(action) if action is not None else "agt_action"


def _approval_bool(entry: dict[str, Any]) -> bool | None:
    data = entry.get("data") if isinstance(entry.get("data"), dict) else {}
    for value in (data.get("approved"), data.get("allow"), data.get("granted")):
        if isinstance(value, bool):
            return value
    token = _normalize_token(
        entry.get("outcome") or entry.get("policy_decision") or data.get("decision")
    )
    if token in {"approved", "allow", "allowed", "granted", "accepted", "success"}:
        return True
    if token in {"denied", "deny", "blocked", "rejected", "refused", "failure", "error"}:
        return False
    return None


def _map_audit_kind(entry: dict[str, Any]) -> tuple[str, bool]:
    event_type = _normalize_token(entry.get("event_type"))
    action = _normalize_token(entry.get("action"))
    outcome = _normalize_token(entry.get("outcome"))

    if "approval" in event_type or "approval" in action:
        if any(
            token in event_type or token in action
            for token in ("response", "approved", "denied", "resolved")
        ):
            return "agent.approval.response", True
        return "agent.approval.request", True

    if event_type in {"tool_invocation", "tool_invoked", "tool_call", "tool_called"}:
        return "tool.call", True

    if event_type in {"tool_response", "tool_result", "tool_completed"}:
        return "tool.response", True

    if (
        event_type in {"policy_evaluation", "policy_violation"}
        or entry.get("matched_rule")
        or entry.get("policy_decision")
    ):
        return "policy.check", True

    if event_type.endswith("decision") or action in {
        "approve",
        "deny",
        "decline",
        "accept",
        "escalate",
    }:
        return "agent.decision", True

    if outcome in {"error", "failure"}:
        return "agent.run.error", True

    return f"agt.audit.{event_type or 'event'}", False


def _map_flight_kind(entry: dict[str, Any]) -> tuple[str, bool]:
    verdict = _normalize_token(entry.get("policy_verdict"))
    tool_name = _normalize_token(entry.get("tool_name"))

    if "approval" in tool_name:
        if verdict in {"allowed", "blocked", "error"}:
            return "agent.approval.response", True
        return "agent.approval.request", True

    if verdict == "pending":
        return "tool.call", True
    if verdict == "allowed":
        return "tool.response", True
    if verdict == "blocked":
        return "policy.check", True
    if verdict == "error":
        return "agent.run.error", True
    return f"agt.flight.{verdict or 'event'}", False


def _audit_fingerprint(entry: dict[str, Any], timestamp: datetime) -> str:
    outcome = _canonical_outcome(entry.get("outcome") or entry.get("policy_decision"))
    parts = [
        _timestamp_key(timestamp),
        str(entry.get("trace_id") or entry.get("session_id") or ""),
        str(entry.get("action") or _audit_tool_name(entry) or ""),
        str(outcome or ""),
    ]
    return hashlib.sha256("||".join(parts).lower().encode("utf-8")).hexdigest()


def _flight_fingerprint(entry: dict[str, Any], timestamp: datetime) -> str:
    parts = [
        _timestamp_key(timestamp),
        str(entry.get("trace_id") or entry.get("session_id") or ""),
        str(entry.get("tool_name") or ""),
        str(_canonical_outcome(entry.get("policy_verdict")) or ""),
    ]
    return hashlib.sha256("||".join(parts).lower().encode("utf-8")).hexdigest()


def _step_content(
    entry: dict[str, Any],
    *,
    source: str,
    section: str,
    kind: str,
    raw: dict[str, Any],
    transformation: str,
    dedupe_group: str,
    dedupe_resolution: str,
) -> dict[str, Any]:
    content: dict[str, Any] = {
        "source": source,
        "raw": raw,
        "source_ref": {
            "system": "AGT",
            "section": section,
            "entry_id": (
                _audit_entry_id(entry) if section == "audit_logs" else _flight_entry_id(entry)
            ),
            "trace_id": (
                _audit_trace_id(entry) if section == "audit_logs" else _flight_trace_id(entry)
            ),
            "transformation": transformation,
            "dedupe_group": dedupe_group,
            "dedupe_resolution": dedupe_resolution,
        },
    }

    if section == "audit_logs":
        data = entry.get("data") if isinstance(entry.get("data"), dict) else {}
        tool_name = _audit_tool_name(entry)
        content.update(
            {
                "event_type": entry.get("event_type"),
                "action": entry.get("action"),
                "outcome": entry.get("outcome"),
                "agent_did": entry.get("agent_did"),
                "resource": entry.get("resource"),
                "target_did": entry.get("target_did"),
                "policy_decision": entry.get("policy_decision"),
                "matched_rule": entry.get("matched_rule"),
                "entry_id": entry.get("entry_id"),
                "session_id": entry.get("session_id"),
            }
        )
        if kind in {"tool.call", "tool.response"}:
            content["tool"] = tool_name
            content["arguments"] = data.get("arguments") or data.get("tool_args") or data
            if kind == "tool.response":
                content["status"] = (
                    entry.get("outcome") or entry.get("policy_decision") or "recorded"
                )
                if "result" in data:
                    content["result"] = data.get("result")
        elif kind == "agent.approval.request":
            content["action"] = entry.get("action") or tool_name
            content["requested_by"] = entry.get("agent_did")
            content["reason"] = data.get("reason") or data.get("message")
        elif kind == "agent.approval.response":
            content["action"] = entry.get("action") or tool_name
            content["approved"] = _approval_bool(entry)
            content["reviewer"] = data.get("reviewer")
            content["reason"] = data.get("reason") or data.get("reviewer_note")
        elif kind == "agent.decision":
            content["decision"] = (
                data.get("decision") or entry.get("action") or entry.get("outcome")
            )
            content["reason"] = data.get("reason") or data.get("message")
        elif kind == "policy.check":
            content["control_id"] = entry.get("matched_rule")
            content["status"] = entry.get("policy_decision") or entry.get("outcome")
            content["message"] = data.get("message") or data.get("reason")
        elif kind == "agent.run.error":
            content["error"] = data.get("error") or data.get("message") or entry.get("action")
        return {key: value for key, value in content.items() if value is not None}

    tool_args = _maybe_json(entry.get("tool_args"))
    result = _maybe_json(entry.get("result"))
    content.update(
        {
            "tool": entry.get("tool_name"),
            "arguments": tool_args,
            "input_prompt": entry.get("input_prompt"),
            "policy_verdict": entry.get("policy_verdict"),
            "violation_reason": entry.get("violation_reason"),
            "result": result,
            "execution_time_ms": entry.get("execution_time_ms"),
            "agent_id": entry.get("agent_id"),
            "entry_id": entry.get("id") or entry.get("trace_id"),
        }
    )
    if kind == "agent.approval.response":
        content["approved"] = _normalize_token(entry.get("policy_verdict")) == "allowed"
    if kind == "agent.run.error":
        content["error"] = entry.get("violation_reason") or entry.get("result")
    if kind == "policy.check":
        content["status"] = entry.get("policy_verdict")
        content["message"] = entry.get("violation_reason")
    if kind == "tool.response":
        content["status"] = entry.get("policy_verdict")
    return {key: value for key, value in content.items() if value is not None}


def _candidate_to_step(candidate: dict[str, Any], index: int, dedupe_resolution: str) -> StepModel:
    entry = candidate["entry"]
    return StepModel(
        index=index,
        timestamp=candidate["timestamp"],
        kind=candidate["kind"],
        trace_id=candidate["trace_id"],
        content=_step_content(
            entry,
            source=candidate["source"],
            section=candidate["section"],
            kind=candidate["kind"],
            raw=entry,
            transformation=candidate["transformation"],
            dedupe_group=candidate["fingerprint"],
            dedupe_resolution=dedupe_resolution,
        ),
    )


def _build_audit_candidate(
    entry: dict[str, Any],
    *,
    position: int,
    report_builder: MappingReportBuilder | None = None,
) -> dict[str, Any]:
    timestamp = _ensure_timestamp(entry.get("timestamp"))
    kind, recognized = _map_audit_kind(entry)
    if report_builder is not None:
        report_builder.record_event_mapping(
            section="audit_logs",
            source_type=_normalize_token(entry.get("event_type")) or "event",
            mapped_kind=kind,
            recognized=recognized,
            entry_id=_audit_entry_id(entry),
        )
    return {
        "section": "audit_logs",
        "source": "agt.audit_logs",
        "priority": 0,
        "position": position,
        "timestamp": timestamp,
        "fingerprint": _audit_fingerprint(entry, timestamp),
        "kind": kind,
        "recognized": recognized,
        "transformation": "translated" if recognized else "derived",
        "entry_id": _audit_entry_id(entry),
        "trace_id": _audit_trace_id(entry),
        "entry": entry,
    }


def _build_flight_candidate(
    entry: dict[str, Any],
    *,
    position: int,
    report_builder: MappingReportBuilder | None = None,
) -> dict[str, Any]:
    timestamp = _ensure_timestamp(entry.get("timestamp"))
    kind, recognized = _map_flight_kind(entry)
    if report_builder is not None:
        report_builder.record_event_mapping(
            section="flight_recorder",
            source_type=_normalize_token(entry.get("policy_verdict")) or "event",
            mapped_kind=kind,
            recognized=recognized,
            entry_id=_flight_entry_id(entry),
        )
    return {
        "section": "flight_recorder",
        "source": "agt.flight_recorder",
        "priority": 1,
        "position": position,
        "timestamp": timestamp,
        "fingerprint": _flight_fingerprint(entry, timestamp),
        "kind": kind,
        "recognized": recognized,
        "transformation": "translated" if recognized else "derived",
        "entry_id": _flight_entry_id(entry),
        "trace_id": _flight_trace_id(entry),
        "entry": entry,
    }


def map_audit_logs(
    entries: list[dict[str, Any]],
    *,
    report_builder: MappingReportBuilder | None = None,
) -> list[StepModel]:
    """Normalize AGT audit entries into EPI steps without dedupe."""

    return [
        _candidate_to_step(
            _build_audit_candidate(entry, position=index, report_builder=report_builder),
            index,
            "kept",
        )
        for index, entry in enumerate(entries)
    ]


def map_flight_recorder(
    entries: list[dict[str, Any]],
    *,
    report_builder: MappingReportBuilder | None = None,
) -> list[StepModel]:
    """Normalize AGT Flight Recorder rows into EPI steps without dedupe."""

    return [
        _candidate_to_step(
            _build_flight_candidate(entry, position=index, report_builder=report_builder),
            index,
            "kept",
        )
        for index, entry in enumerate(entries)
    ]


def _group_conflict_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "section": candidate["section"],
            "entry_id": candidate["entry_id"],
            "trace_id": candidate["trace_id"],
        }
        for candidate in candidates
    ]


def normalize_agt_steps(
    bundle: AGTBundleModel,
    *,
    report_builder: MappingReportBuilder | None = None,
    strict: bool = False,
    dedupe_strategy: DedupStrategy = "prefer-audit",
) -> list[StepModel]:
    """Normalize AGT audit evidence into EPI steps and dedupe overlapping records."""

    if strict and dedupe_strategy != "fail":
        raise ValueError("Strict AGT import requires --dedupe fail")

    normalized: list[dict[str, Any]] = []
    for position, entry in enumerate(bundle.audit_logs):
        normalized.append(
            _build_audit_candidate(entry, position=position, report_builder=report_builder)
        )
    start_index = len(normalized)
    for offset, entry in enumerate(bundle.flight_recorder):
        normalized.append(
            _build_flight_candidate(
                entry,
                position=start_index + offset,
                report_builder=report_builder,
            )
        )

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in normalized:
        grouped[item["fingerprint"]].append(item)

    ordered_groups = sorted(
        grouped.items(),
        key=lambda item: (
            min(candidate["timestamp"] for candidate in item[1]),
            min(candidate["position"] for candidate in item[1]),
            item[0],
        ),
    )

    kept: list[tuple[dict[str, Any], str]] = []
    duplicates_removed = 0
    kept_both_count = 0
    ambiguous_conflicts = 0

    for fingerprint, group in ordered_groups:
        sorted_group = sorted(
            group,
            key=lambda item: (
                item["timestamp"],
                item["priority"],
                item["position"],
                item["section"],
                item["entry_id"] or "",
            ),
        )
        if len(sorted_group) == 1:
            kept.append((sorted_group[0], "kept"))
            continue

        has_audit = any(item["section"] == "audit_logs" for item in sorted_group)
        has_flight = any(item["section"] == "flight_recorder" for item in sorted_group)
        unambiguous_preference = (
            has_audit
            and has_flight
            and sum(1 for item in sorted_group if item["section"] == "audit_logs") == 1
        )

        if not unambiguous_preference:
            ambiguous_conflicts += 1

        if dedupe_strategy == "fail":
            if report_builder is not None:
                report_builder.record_dedupe_conflict(
                    group=fingerprint,
                    candidates=_group_conflict_candidates(sorted_group),
                    resolution="failed",
                    reason="dedupe_strategy=fail",
                )
            raise ValueError(f"AGT import encountered dedupe conflict group {fingerprint}")

        if dedupe_strategy == "keep-both":
            if report_builder is not None:
                report_builder.record_dedupe_conflict(
                    group=fingerprint,
                    candidates=_group_conflict_candidates(sorted_group),
                    resolution="kept_both",
                    reason="dedupe_strategy=keep-both",
                )
            kept_both_count += len(sorted_group)
            kept.extend((candidate, "kept_both") for candidate in sorted_group)
            continue

        winner = sorted_group[0]
        resolution = "preferred_audit" if unambiguous_preference else "kept"
        reason = (
            "preferred_audit_over_flight" if unambiguous_preference else "stable_first_candidate"
        )
        duplicates_removed += len(sorted_group) - 1
        if report_builder is not None:
            report_builder.record_dedupe_conflict(
                group=fingerprint,
                candidates=_group_conflict_candidates(sorted_group),
                resolution=resolution,
                reason=reason,
            )
            if not unambiguous_preference:
                report_builder.add_warning(
                    f"Ambiguous dedupe group {fingerprint} resolved by stable ordering."
                )
        kept.append((winner, resolution))

    ordered_kept = sorted(
        kept,
        key=lambda item: (
            item[0]["timestamp"],
            item[0]["priority"],
            item[0]["position"],
            item[0]["section"],
            item[0]["entry_id"] or "",
        ),
    )

    steps = [
        _candidate_to_step(candidate, index, resolution)
        for index, (candidate, resolution) in enumerate(ordered_kept)
    ]

    if report_builder is not None:
        report_builder.record_step_transformation(
            audit_input_count=len(bundle.audit_logs),
            flight_input_count=len(bundle.flight_recorder),
            output_count=len(steps),
            dedupe_strategy=dedupe_strategy,
            duplicates_removed=duplicates_removed,
            kept_both_count=kept_both_count,
            ambiguous_conflicts=ambiguous_conflicts,
        )

    return steps


def map_policy_document(document: dict[str, Any]) -> dict[str, Any]:
    """Preserve the AGT policy document while adding lightweight source metadata."""

    mapped = dict(document)
    mapped.setdefault("profile_id", document.get("name") or document.get("id") or "agt-policy")
    mapped.setdefault("source_system", "microsoft-agent-governance-toolkit")
    mapped.setdefault("source_format", "PolicyDocument")
    return mapped


def map_environment(runtime_context: dict[str, Any]) -> dict[str, Any]:
    """Preserve runtime context with source metadata for imported artifacts."""

    mapped = dict(runtime_context)
    mapped.setdefault("source_system", "microsoft-agent-governance-toolkit")
    mapped.setdefault("source_format", "runtime_context")
    return mapped


def _link_step_numbers(
    raw_item: dict[str, Any],
    steps: list[StepModel],
    *,
    default_to_last: bool = True,
) -> list[int]:
    trace_id = (
        raw_item.get("trace_id")
        or raw_item.get("entry_id")
        or (raw_item.get("evidence") or {}).get("trace_id")
        or (raw_item.get("evidence") or {}).get("entry_id")
    )
    control_id = (
        raw_item.get("control_id")
        or raw_item.get("matched_rule")
        or (raw_item.get("evidence") or {}).get("matched_rule")
    )

    matches: list[int] = []
    for step in steps:
        content = step.content if isinstance(step.content, dict) else {}
        raw = content.get("raw") if isinstance(content.get("raw"), dict) else {}
        if trace_id and (
            step.trace_id == trace_id
            or raw.get("trace_id") == trace_id
            or raw.get("entry_id") == trace_id
            or content.get("entry_id") == trace_id
        ):
            matches.append(step.index + 1)
            continue
        if control_id and (
            content.get("matched_rule") == control_id
            or content.get("control_id") == control_id
            or raw.get("matched_rule") == control_id
        ):
            matches.append(step.index + 1)

    if matches:
        return sorted(set(matches))

    if default_to_last and steps:
        return [steps[-1].index + 1]
    return []


def _highest_severity(values: list[str]) -> str:
    if not values:
        return "medium"
    return sorted(values, key=lambda value: _SEVERITY_ORDER.get(_normalize_token(value), 9))[0]


def map_policy_evaluation(
    report: dict[str, Any],
    steps: list[StepModel],
    *,
    policy_document: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Create an EPI-viewer-friendly policy_evaluation.json from AGT evidence.

    Supports direct results when present and falls back to grouped violations
    when AGT only exports summary + violations.
    """

    raw_results = report.get("results") if isinstance(report.get("results"), list) else []
    results: list[dict[str, Any]] = []

    for raw_result in raw_results:
        if not isinstance(raw_result, dict):
            continue
        status_token = _normalize_token(raw_result.get("status"))
        failed = (
            status_token in {"failed", "fail", "blocked", "denied", "error"}
            or raw_result.get("passed") is False
        )
        step_numbers = raw_result.get("step_numbers")
        if not isinstance(step_numbers, list):
            step_numbers = _link_step_numbers(raw_result, steps)
        plain = (
            raw_result.get("plain_english")
            or raw_result.get("message")
            or raw_result.get("description")
            or (
                "AGT reported control "
                f"{raw_result.get('control_id') or raw_result.get('rule_id') or 'unknown'}."
            )
        )
        rule_id = raw_result.get("control_id") or raw_result.get("rule_id") or raw_result.get("id")
        rule_name = (
            raw_result.get("rule_name")
            or raw_result.get("name")
            or raw_result.get("description")
            or rule_id
        )
        results.append(
            {
                "rule_id": rule_id,
                "name": rule_name,
                "rule_name": rule_name,
                "rule_type": raw_result.get("rule_type")
                or report.get("framework")
                or "agt_control",
                "severity": raw_result.get("severity") or ("high" if failed else "low"),
                "mode": raw_result.get("mode") or "imported",
                "applies_at": raw_result.get("applies_at") or "runtime",
                "status": "failed" if failed else "passed",
                "review_required": bool(raw_result.get("review_required", failed)),
                "match_count": raw_result.get("match_count")
                or (len(step_numbers) if failed else 0),
                "step_numbers": step_numbers,
                "plain_english": plain,
                "matched_findings": raw_result.get("matched_findings") or [],
            }
        )

    if not results:
        grouped: dict[str, list[dict[str, Any]]] = {}
        violations = report.get("violations") if isinstance(report.get("violations"), list) else []
        for violation in violations:
            if not isinstance(violation, dict):
                continue
            key = str(
                violation.get("control_id") or violation.get("violation_id") or "agt_violation"
            )
            grouped.setdefault(key, []).append(violation)

        for control_id, grouped_violations in grouped.items():
            first = grouped_violations[0]
            step_numbers = _link_step_numbers(first, steps)
            severity = _highest_severity(
                [str(item.get("severity") or "medium") for item in grouped_violations]
            )
            plain = first.get("description") or f"AGT reported a failed control for {control_id}."
            results.append(
                {
                    "rule_id": control_id,
                    "name": first.get("name") or first.get("control_name") or control_id,
                    "rule_name": first.get("name") or first.get("control_name") or control_id,
                    "rule_type": first.get("framework") or report.get("framework") or "agt_control",
                    "severity": severity,
                    "mode": "imported",
                    "applies_at": "runtime",
                    "status": "failed",
                    "review_required": _normalize_token(severity) in {"critical", "high", "medium"},
                    "match_count": len(grouped_violations),
                    "step_numbers": step_numbers,
                    "plain_english": plain,
                    "matched_findings": grouped_violations,
                }
            )

    artifact_review_required = any(bool(result.get("review_required")) for result in results)
    controls_failed = sum(1 for result in results if result.get("status") == "failed")
    controls_evaluated = int(report.get("total_controls") or len(results))

    return {
        "policy_format_version": "agt-import-v1",
        "policy_id": (
            report.get("report_id")
            or (policy_document or {}).get("name")
            or report.get("framework")
            or "agt-import"
        ),
        "policy_version": (policy_document or {}).get("version"),
        "policy_scope": {
            "framework": report.get("framework"),
            "period_start": report.get("period_start"),
            "period_end": report.get("period_end"),
            "organization_id": report.get("organization_id"),
            "agents_covered": report.get("agents_covered") or [],
        },
        "evaluation_timestamp": report.get("generated_at") or utc_now().isoformat(),
        "evaluation_mode": "agt_import",
        "controls_evaluated": controls_evaluated,
        "controls_failed": int(report.get("controls_failed") or controls_failed),
        "controls_partial": int(report.get("controls_partial") or 0),
        "controls_met": int(
            report.get("controls_met") or max(controls_evaluated - controls_failed, 0)
        ),
        "compliance_score": report.get("compliance_score"),
        "artifact_review_required": artifact_review_required,
        "results": results,
        "source_system": "microsoft-agent-governance-toolkit",
        "source_format": "ComplianceReport",
    }


def _policy_fault_from_result(result: dict[str, Any], steps: list[StepModel]) -> dict[str, Any]:
    step_numbers = (
        result.get("step_numbers") if isinstance(result.get("step_numbers"), list) else []
    )
    if step_numbers:
        primary_step_number = int(step_numbers[0])
        step_index = max(primary_step_number - 1, 0)
    elif steps:
        step_index = steps[-1].index
        primary_step_number = step_index + 1
    else:
        step_index = 0
        primary_step_number = 1

    detail = (
        result.get("plain_english") or f"AGT reported control {result.get('rule_id')} as failed."
    )
    fault_chain = [
        {
            "step_index": step_index,
            "step_number": primary_step_number,
            "role": "source_event",
            "detail": detail,
        }
    ]
    if result.get("rule_id"):
        fault_chain.append(
            {
                "step_index": step_index,
                "step_number": primary_step_number,
                "role": "policy_match",
                "detail": f"AGT compliance evidence marked control {result['rule_id']} as failed.",
            }
        )

    return {
        "step_index": step_index,
        "step_number": primary_step_number,
        "fault_type": "POLICY_VIOLATION",
        "category": "policy_violation",
        "severity": _normalize_token(result.get("severity") or "medium"),
        "plain_english": detail,
        "why_it_matters": (
            "This run broke an AGT-reported compliance control and should be reviewed "
            "before the outcome is trusted."
        ),
        "review_required": bool(result.get("review_required", True)),
        "fault_chain": fault_chain,
        "rule_id": result.get("rule_id"),
        "rule_name": result.get("rule_name") or result.get("name"),
        "policy_type": result.get("rule_type"),
        "policy_mode": result.get("mode"),
        "policy_applies_at": result.get("applies_at"),
    }


def _fallback_faults_from_steps(steps: list[StepModel]) -> list[dict[str, Any]]:
    faults: list[dict[str, Any]] = []
    for step in steps:
        content = step.content if isinstance(step.content, dict) else {}
        status = _normalize_token(
            content.get("status")
            or content.get("policy_decision")
            or content.get("policy_verdict")
            or content.get("outcome")
        )
        matched_rule = content.get("matched_rule") or content.get("control_id")
        if step.kind == "policy.check" and status in {
            "blocked",
            "deny",
            "denied",
            "error",
            "failed",
        }:
            detail = (
                content.get("message")
                or f"AGT recorded a blocked policy check at step {step.index + 1}."
            )
            faults.append(
                {
                    "step_index": step.index,
                    "step_number": step.index + 1,
                    "fault_type": "POLICY_VIOLATION",
                    "category": "policy_violation",
                    "severity": "high" if status in {"blocked", "deny", "denied"} else "medium",
                    "plain_english": detail,
                    "why_it_matters": (
                        "AGT recorded a blocked or denied policy action in the imported evidence."
                    ),
                    "review_required": True,
                    "fault_chain": [
                        {
                            "step_index": step.index,
                            "step_number": step.index + 1,
                            "role": "source_event",
                            "detail": detail,
                        }
                    ],
                    "rule_id": matched_rule,
                    "rule_name": matched_rule,
                }
            )
        elif step.kind == "agent.run.error":
            detail = (
                content.get("error") or f"AGT recorded an execution error at step {step.index + 1}."
            )
            faults.append(
                {
                    "step_index": step.index,
                    "step_number": step.index + 1,
                    "fault_type": "HEURISTIC_OBSERVATION",
                    "category": "execution_risk",
                    "severity": "medium",
                    "plain_english": detail,
                    "why_it_matters": (
                        "Execution errors should be inspected before the imported outcome "
                        "is trusted."
                    ),
                    "review_required": True,
                    "fault_chain": [
                        {
                            "step_index": step.index,
                            "step_number": step.index + 1,
                            "role": "source_event",
                            "detail": detail,
                        }
                    ],
                }
            )
    return faults


def synthesize_analysis(
    bundle: AGTBundleModel,
    steps: list[StepModel],
    *,
    policy_evaluation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a review-friendly analysis.json from imported AGT evidence."""

    policy_evaluation = policy_evaluation or {}
    failed_results = [
        result
        for result in policy_evaluation.get("results", [])
        if isinstance(result, dict) and _normalize_token(result.get("status")) == "failed"
    ]
    faults = [_policy_fault_from_result(result, steps) for result in failed_results]

    if not faults:
        faults = _fallback_faults_from_steps(steps)

    faults.sort(
        key=lambda fault: (
            _SEVERITY_ORDER.get(_normalize_token(fault.get("severity")), 9),
            int(fault.get("step_index") or 0),
        )
    )

    primary_fault = faults[0] if faults else None
    secondary_flags = faults[1:] if len(faults) > 1 else []
    review_payload = bundle.review if isinstance(bundle.review, dict) else None
    review_status = (
        "complete"
        if review_payload and review_payload.get("reviews")
        else ("pending" if faults else "not_required")
    )

    return {
        "analyzer_version": IMPORT_ANALYZER_VERSION,
        "analysis_timestamp": utc_now().isoformat(),
        "policy_used": bool(bundle.policy_document or bundle.compliance_report),
        "policy_format_version": (
            "agt-import-v1" if bundle.policy_document or bundle.compliance_report else None
        ),
        "policy_id": (
            (bundle.compliance_report or {}).get("report_id")
            or (bundle.policy_document or {}).get("name")
            or (bundle.compliance_report or {}).get("framework")
        ),
        "policy_version": (bundle.policy_document or {}).get("version"),
        "policy_scope": policy_evaluation.get("policy_scope"),
        "mode": "agt_import",
        "synthesized": True,
        "source_system": "AGT",
        "source_artifacts": ["compliance_report", "steps.jsonl"],
        "warning": IMPORT_ANALYSIS_WARNING,
        "fault_taxonomy_version": "1.0",
        "coverage": {
            "status": "complete",
            "steps_recorded": len(steps),
            "steps_with_full_data": sum(
                1 for step in steps if isinstance(step.content, dict) and len(step.content) > 0
            ),
            "coverage_percentage": 100 if steps else 0,
        },
        "fault_detected": bool(primary_fault),
        "confidence": "derived",
        "review_required": bool(
            (primary_fault and primary_fault.get("review_required"))
            or any(flag.get("review_required") for flag in secondary_flags)
        ),
        "primary_fault": primary_fault,
        "secondary_flags": secondary_flags,
        "summary": {
            "headline": (
                primary_fault.get("plain_english")
                if primary_fault
                else "No AGT compliance failures were detected in the imported evidence."
            ),
            "primary_category": primary_fault.get("category") if primary_fault else None,
            "primary_step": primary_fault.get("step_number") if primary_fault else None,
            "secondary_count": len(secondary_flags),
        },
        "human_review": {
            "status": review_status,
            "reviewed_by": review_payload.get("reviewed_by") if review_payload else None,
            "reviewed_at": review_payload.get("reviewed_at") if review_payload else None,
            "outcome": (
                review_payload.get("reviews", [{}])[-1].get("outcome")
                if review_payload and review_payload.get("reviews")
                else None
            ),
            "notes": (
                review_payload.get("reviews", [{}])[-1].get("notes")
                if review_payload and review_payload.get("reviews")
                else None
            ),
        },
        "disclaimer": IMPORT_DISCLAIMER,
    }


def map_review(review: dict[str, Any]) -> dict[str, Any]:
    """Normalize an imported review into review.json shape when possible."""

    if review.get("reviewed_by") and isinstance(review.get("reviews"), list):
        mapped = dict(review)
        mapped.setdefault("review_version", "agt-import-v1")
        mapped.setdefault("review_signature", None)
        return mapped

    reviewer = review.get("reviewed_by") or review.get("reviewer") or "AGT reviewer"
    reviewed_at = review.get("reviewed_at") or review.get("timestamp") or utc_now().isoformat()

    outcome_token = _normalize_token(review.get("outcome") or review.get("status"))
    if outcome_token in {"dismissed", "approved", "approve", "accepted", "allow", "allowed"}:
        outcome = "dismissed"
    elif outcome_token in {
        "confirmed_fault",
        "confirmed",
        "rejected",
        "deny",
        "denied",
        "blocked",
    }:
        outcome = "confirmed_fault"
    else:
        outcome = "skipped"

    return {
        "review_version": "agt-import-v1",
        "reviewed_by": reviewer,
        "reviewed_at": reviewed_at,
        "reviews": [
            {
                "fault_step": review.get("fault_step") or review.get("step_number"),
                "rule_id": review.get("rule_id"),
                "fault_type": review.get("fault_type") or "POLICY_VIOLATION",
                "outcome": outcome,
                "notes": review.get("notes") or review.get("reason") or "",
                "reviewer": reviewer,
                "timestamp": reviewed_at,
            }
        ],
        "review_signature": review.get("review_signature"),
    }


def extract_manifest_metrics(slo_data: dict[str, Any] | None) -> dict[str, float | str] | None:
    """Extract manifest-safe scalar metrics from AGT SLO payloads."""

    if not isinstance(slo_data, dict):
        return None

    metrics: dict[str, float | str] = {}
    for key, value in slo_data.items():
        if isinstance(value, bool):
            metrics[key] = "true" if value else "false"
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            metrics[key] = float(value)
        elif isinstance(value, str):
            metrics[key] = value

    return metrics or None


def classify_bundle_fields(
    bundle: AGTBundleModel,
    report_builder: MappingReportBuilder,
    *,
    attach_raw: bool,
    analysis_mode: AnalysisMode,
) -> None:
    """Classify source fields for the mapping report."""

    for field, mapped_to in (
        ("workflow_id", "manifest.workflow_id"),
        ("created_at", "manifest.created_at"),
        ("cli_command", "manifest.cli_command"),
        ("goal", "manifest.goal"),
        ("notes", "manifest.notes"),
        ("approved_by", "manifest.approved_by"),
        ("tags[]", "manifest.tags[]"),
    ):
        report_builder.classify_field("metadata", field, "exact", mapped_to=mapped_to)

    report_builder.classify_field("audit_logs", "timestamp", "exact", mapped_to="steps[].timestamp")
    report_builder.classify_field("audit_logs", "trace_id", "exact", mapped_to="steps[].trace_id")
    report_builder.classify_field(
        "audit_logs", "session_id", "exact", mapped_to="steps[].content.session_id"
    )
    report_builder.classify_field(
        "audit_logs", "entry_id", "exact", mapped_to="steps[].content.entry_id"
    )
    report_builder.classify_field(
        "audit_logs", "agent_did", "exact", mapped_to="steps[].content.agent_did"
    )
    report_builder.classify_field(
        "audit_logs", "resource", "exact", mapped_to="steps[].content.resource"
    )
    report_builder.classify_field(
        "audit_logs", "target_did", "exact", mapped_to="steps[].content.target_did"
    )
    report_builder.classify_field(
        "audit_logs", "event_type", "translated", mapped_to="steps[].kind"
    )
    report_builder.classify_field(
        "audit_logs", "action", "translated", mapped_to="steps[].content.action"
    )
    report_builder.classify_field(
        "audit_logs", "outcome", "translated", mapped_to="steps[].content.status"
    )
    report_builder.classify_field(
        "audit_logs",
        "policy_decision",
        "translated",
        mapped_to="steps[].content.policy_decision",
    )
    report_builder.classify_field(
        "audit_logs",
        "matched_rule",
        "translated",
        mapped_to="steps[].content.control_id",
    )
    report_builder.classify_prefix("audit_logs", "data", "translated", mapped_to="steps[].content")

    report_builder.classify_field(
        "flight_recorder", "timestamp", "exact", mapped_to="steps[].timestamp"
    )
    report_builder.classify_field(
        "flight_recorder", "trace_id", "exact", mapped_to="steps[].trace_id"
    )
    report_builder.classify_field(
        "flight_recorder", "session_id", "exact", mapped_to="steps[].content.session_id"
    )
    report_builder.classify_field(
        "flight_recorder", "agent_id", "exact", mapped_to="steps[].content.agent_id"
    )
    report_builder.classify_field(
        "flight_recorder",
        "execution_time_ms",
        "exact",
        mapped_to="steps[].content.execution_time_ms",
    )
    report_builder.classify_field(
        "flight_recorder", "id", "translated", mapped_to="steps[].content.entry_id"
    )
    report_builder.classify_field(
        "flight_recorder", "tool_name", "translated", mapped_to="steps[].content.tool"
    )
    report_builder.classify_field(
        "flight_recorder",
        "input_prompt",
        "translated",
        mapped_to="steps[].content.input_prompt",
    )
    report_builder.classify_field(
        "flight_recorder",
        "policy_verdict",
        "translated",
        mapped_to="steps[].kind",
    )
    report_builder.classify_field(
        "flight_recorder",
        "violation_reason",
        "translated",
        mapped_to="steps[].content.message",
    )
    report_builder.classify_prefix(
        "flight_recorder", "tool_args", "translated", mapped_to="steps[].content.arguments"
    )
    report_builder.classify_prefix(
        "flight_recorder", "result", "translated", mapped_to="steps[].content.result"
    )

    if attach_raw:
        report_builder.classify_field(
            "flight_recorder",
            "entry_hash",
            "preserved_raw",
            mapped_to="artifacts/agt/flight_recorder.json",
        )
        report_builder.classify_field(
            "flight_recorder",
            "previous_hash",
            "preserved_raw",
            mapped_to="artifacts/agt/flight_recorder.json",
        )
        report_builder.classify_remaining(
            "metadata",
            "preserved_raw",
            mapped_to="artifacts/agt/bundle.json",
            notes="Preserved in the raw AGT bundle attachment.",
        )
    else:
        report_builder.classify_field(
            "flight_recorder",
            "entry_hash",
            "dropped",
            notes="Raw attachment disabled.",
        )
        report_builder.classify_field(
            "flight_recorder",
            "previous_hash",
            "dropped",
            notes="Raw attachment disabled.",
        )
        report_builder.classify_remaining(
            "metadata",
            "dropped",
            notes="Raw attachment disabled.",
        )

    if bundle.compliance_report:
        for field, mapped_to in (
            ("report_id", "policy_evaluation.json.policy_id"),
            ("generated_at", "policy_evaluation.json.evaluation_timestamp"),
            ("framework", "policy_evaluation.json.policy_scope.framework"),
            ("period_start", "policy_evaluation.json.policy_scope.period_start"),
            ("period_end", "policy_evaluation.json.policy_scope.period_end"),
            ("organization_id", "policy_evaluation.json.policy_scope.organization_id"),
            ("total_controls", "policy_evaluation.json.controls_evaluated"),
            ("controls_failed", "policy_evaluation.json.controls_failed"),
            ("controls_partial", "policy_evaluation.json.controls_partial"),
            ("controls_met", "policy_evaluation.json.controls_met"),
            ("compliance_score", "policy_evaluation.json.compliance_score"),
        ):
            report_builder.classify_field(
                "compliance_report", field, "translated", mapped_to=mapped_to
            )
        report_builder.classify_prefix(
            "compliance_report",
            "agents_covered",
            "translated",
            mapped_to="policy_evaluation.json.policy_scope.agents_covered",
        )
        report_builder.classify_prefix(
            "compliance_report",
            "results",
            "translated",
            mapped_to="policy_evaluation.json.results",
        )
        report_builder.classify_prefix(
            "compliance_report",
            "violations",
            "derived",
            mapped_to="policy_evaluation.json.results",
            notes="Grouped into failed controls during import fallback.",
        )
        report_builder.classify_remaining(
            "compliance_report",
            "preserved_raw" if attach_raw else "dropped",
            mapped_to="artifacts/agt/compliance_report.json" if attach_raw else None,
            notes=(
                "Preserved in the raw AGT compliance report attachment."
                if attach_raw
                else "Raw attachment disabled."
            ),
        )

    if bundle.policy_document:
        report_builder.classify_remaining(
            "policy_document",
            "exact",
            mapped_to="policy.json",
            notes="Imported directly into policy.json with source metadata added by EPI.",
        )
    if bundle.runtime_context:
        report_builder.classify_remaining(
            "runtime_context",
            "exact",
            mapped_to="environment.json",
        )
    if bundle.slo_data:
        report_builder.classify_remaining(
            "slo_data",
            "exact",
            mapped_to="artifacts/slo.json",
            notes="Also surfaced into manifest.metrics when scalar-safe.",
        )
    if bundle.review:
        report_builder.classify_remaining(
            "review",
            "translated",
            mapped_to="review.json",
        )

    if bundle.annex_markdown:
        report_builder.classify_field(
            "annex_markdown", "value", "exact", mapped_to="artifacts/annex_iv.md"
        )
    if bundle.annex_json is not None:
        report_builder.classify_remaining(
            "annex_json", "exact", mapped_to="artifacts/annex_iv.json"
        )

    for extra_section in (
        section
        for section in report_builder.observed_sections()
        if section
        not in {
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
    ):
        report_builder.classify_remaining(
            extra_section,
            "preserved_raw" if attach_raw else "dropped",
            mapped_to="artifacts/agt/bundle.json" if attach_raw else None,
            notes=(
                "Preserved only in the raw AGT bundle attachment."
                if attach_raw
                else "Raw attachment disabled."
            ),
        )

    if analysis_mode == "synthesized":
        report_builder.record_synthesized(
            "analysis.json",
            mapped_to="analysis.json",
            notes=(
                "Synthesized from AGT compliance evidence so epi review can operate "
                "on imported artifacts."
            ),
        )
