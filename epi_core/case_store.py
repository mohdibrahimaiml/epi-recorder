"""
Shared gateway-backed case store for Decision Ops.

This module provides a lightweight single-node SQLite store backed by an
append-only event spool on disk. The goal is to keep live shared review state
and portable `.epi` export on the same evidence model.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import BaseModel, ConfigDict, Field

from epi_core.auth_local import build_session_token, hash_session_token, verify_password
from epi_core.capture import CaptureBatchModel, CaptureEventModel, coerce_capture_event
from epi_core.container import EPIContainer
from epi_core.schemas import ManifestModel
from epi_core.time_utils import utc_now_iso


WORKFLOW_STATUSES = {"unassigned", "assigned", "in_review", "blocked", "resolved"}


def _clean(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _slugify(value: str) -> str:
    text = "".join(ch.lower() if ch.isalnum() else "-" for ch in str(value or "case"))
    text = "-".join(part for part in text.split("-") if part)
    return text or "case"


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _decode_json(value: str | None, default: Any = None) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except Exception:
        return default


def _safe_datetime(value: Any) -> str:
    text = _clean(value)
    return text or utc_now_iso()


def _safe_due_at(value: Any) -> str | None:
    text = _clean(value)
    return text or None


def _first_nonempty(*values: Any) -> str | None:
    for value in values:
        text = _clean(value)
        if text:
            return text
    return None


def _extract_output_text(content: dict[str, Any]) -> str | None:
    if not isinstance(content, dict):
        return None

    direct = _clean(content.get("output_text") or content.get("summary") or content.get("decision"))
    if direct:
        return direct

    choices = content.get("choices")
    if isinstance(choices, list):
        for choice in choices:
            if not isinstance(choice, dict):
                continue
            message = choice.get("message") or {}
            if isinstance(message, dict):
                text = _clean(message.get("content"))
                if text:
                    return text
    return None


def _normalize_workflow_status(
    value: Any,
    *,
    review_required: bool = False,
    has_review: bool = False,
) -> str:
    text = _clean(value)
    if text in WORKFLOW_STATUSES:
        return text
    if has_review:
        return "resolved"
    if review_required:
        return "unassigned"
    return "resolved"


def _review_outcome_to_status(review_payload: dict[str, Any], fallback: str) -> str:
    reviews = review_payload.get("reviews")
    if not isinstance(reviews, list) or not reviews:
        return fallback
    outcome = _clean(reviews[-1].get("outcome"))
    if outcome in {"confirmed_fault", "dismissed"}:
        return "resolved"
    if outcome == "skipped":
        return "blocked"
    return fallback


def _parse_datetime(value: str | None) -> datetime | None:
    text = _clean(value)
    if not text:
        return None
    try:
        if len(text) == 10 and text.count("-") == 2:
            parsed_date = date.fromisoformat(text)
            return datetime(parsed_date.year, parsed_date.month, parsed_date.day, tzinfo=timezone.utc)
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        return None


def _is_overdue(due_at: str | None, status: str | None) -> bool:
    if _clean(status) == "resolved":
        return False
    parsed = _parse_datetime(due_at)
    if not parsed:
        return False
    now = datetime.now(timezone.utc)
    if len(str(due_at or "").strip()) == 10:
        return parsed.date() < now.date()
    return parsed < now


def derive_case_key(event: CaptureEventModel | dict[str, Any]) -> str:
    item = coerce_capture_event(event)

    if item.case_id:
        return item.case_id
    if item.decision_id:
        return f"decision::{item.decision_id}"
    if item.trace_id:
        return f"trace::{item.trace_id}"

    fingerprint = hashlib.sha256(
        _json(
            {
                "provider": item.provider,
                "model": item.model,
                "workflow_name": item.workflow_name,
                "source_app": item.source_app,
                "kind": item.kind,
                "content": item.content,
            }
        ).encode("utf-8")
    ).hexdigest()[:16]
    provider = _slugify(item.provider or item.meta.get("provider_profile") or "case")
    return f"case::{provider}::{fingerprint}"


class CaseReviewModel(BaseModel):
    review_version: str = "1.0.0"
    reviewed_by: str
    reviewed_at: str
    reviews: list[dict[str, Any]] = Field(default_factory=list)
    review_signature: str | None = None

    model_config = ConfigDict(extra="allow")


class CaseSummaryModel(BaseModel):
    id: str
    title: str
    workflow: str
    created_at: str
    updated_at: str
    status: str
    priority: str
    review_required: bool
    risk_state: str
    source_trust_state: dict[str, Any]
    preview_only: bool = False
    decision_id: str | None = None
    trace_id: str | None = None
    source_name: str | None = None
    assignee: str | None = None
    due_at: str | None = None
    comment_count: int = 0
    last_comment_at: str | None = None
    review_state: str | None = None
    is_overdue: bool = False

    model_config = ConfigDict(extra="allow")


class CaseCommentModel(BaseModel):
    id: int
    case_id: str
    author: str
    body: str
    created_at: str

    model_config = ConfigDict(extra="allow")


class CaseActivityModel(BaseModel):
    id: int
    case_id: str
    kind: str
    title: str
    message: str = Field(alias="copy", serialization_alias="copy")
    actor: str | None = None
    created_at: str
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="allow", populate_by_name=True)


class DecisionCaseModel(BaseModel):
    id: str
    source_name: str
    manifest: dict[str, Any] = Field(default_factory=dict)
    steps: list[dict[str, Any]] = Field(default_factory=list)
    analysis: dict[str, Any] | None = None
    policy: dict[str, Any] | None = None
    policy_evaluation: dict[str, Any] | None = None
    review: dict[str, Any] | None = None
    environment: dict[str, Any] | None = None
    stdout: str | None = None
    stderr: str | None = None
    integrity: dict[str, Any] = Field(default_factory=dict)
    signature: dict[str, Any] = Field(default_factory=dict)
    shared_workspace_case: bool = True
    backend_case: bool = True
    preview_only: bool = False
    source_trust_state: dict[str, Any] = Field(default_factory=dict)
    decision_id: str | None = None
    trace_id: str | None = None
    workflow_name: str | None = None
    source_app: str | None = None
    provider: str | None = None
    model: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    status: str | None = None
    priority_override: str | None = None
    assignee: str | None = None
    due_at: str | None = None
    comment_count: int = 0
    last_comment_at: str | None = None
    review_state: str | None = None
    is_overdue: bool = False
    comments: list[CaseCommentModel] = Field(default_factory=list)
    activity: list[CaseActivityModel] = Field(default_factory=list)

    model_config = ConfigDict(extra="allow")


class CaseExportResultModel(BaseModel):
    case_id: str
    output_path: str
    filename: str
    signed: bool

    model_config = ConfigDict(extra="allow")


class ReplaySpoolResultModel(BaseModel):
    applied_batches: int = 0
    skipped_batches: int = 0
    corrupt_batch_count: int = 0
    corrupt_files: list[str] = Field(default_factory=list)
    moved_corrupt_files: list[str] = Field(default_factory=list)
    last_error: str | None = None

    model_config = ConfigDict(extra="allow")


class AuthUserModel(BaseModel):
    username: str
    display_name: str
    role: str
    source: str | None = None

    model_config = ConfigDict(extra="allow")


class AuthSessionModel(BaseModel):
    username: str
    display_name: str
    role: str
    created_at: str
    expires_at: str
    auth_mode: str = "session"

    model_config = ConfigDict(extra="allow")


class OpenSessionModel(BaseModel):
    workflow_id: str
    case_id: str | None = None
    started_at: str
    last_event_at: str

    model_config = ConfigDict(extra="allow")


def _review_state_for_filters(review: dict[str, Any] | None, payload: dict[str, Any]) -> str:
    if review and isinstance(review.get("reviews"), list) and review["reviews"]:
        return "reviewed"
    if payload.get("analysis", {}).get("review_required") or payload.get("policy_evaluation", {}).get("artifact_review_required"):
        return "pending"
    return "not-required"


def _derive_source_trust(code: str, detail: str) -> dict[str, Any]:
    mapping = {
        "trusted": ("Trusted", "success"),
        "verify-source": ("Verify source", "warning"),
        "source-not-proven": ("Source not proven", "warning"),
        "do-not-use": ("Do not use", "danger"),
    }
    label, tone = mapping.get(code, ("Source not proven", "warning"))
    return {
        "code": code,
        "label": label,
        "tone": tone,
        "detail": detail,
    }


def summarize_case_payload(payload: dict[str, Any]) -> dict[str, Any]:
    manifest = payload.get("manifest") or {}
    steps = payload.get("steps") or []
    analysis = payload.get("analysis") or {}
    policy_evaluation = payload.get("policy_evaluation") or payload.get("policyEvaluation") or {}
    review = payload.get("review") or {}
    source_trust = payload.get("source_trust_state") or payload.get("sourceTrustState")

    created_at = _first_nonempty(payload.get("created_at"), manifest.get("created_at"))
    if not created_at and steps:
        created_at = _clean(steps[0].get("timestamp"))
    created_at = created_at or utc_now_iso()

    updated_at = _first_nonempty(payload.get("updated_at"), payload.get("shared_updated_at"))
    latest_review_ts = None
    if isinstance(review, dict):
        reviews = review.get("reviews")
        if isinstance(reviews, list) and reviews:
            latest_review_ts = _clean(reviews[-1].get("timestamp"))
        latest_review_ts = latest_review_ts or _clean(review.get("reviewed_at"))
    updated_at = updated_at or latest_review_ts or created_at

    workflow = (
        _first_nonempty(payload.get("workflow_name"), manifest.get("workflow_name"), manifest.get("system_name"))
        or "Decision captured"
    )
    title = (
        _first_nonempty(payload.get("title"), payload.get("decision", {}).get("title"), payload.get("analysis", {}).get("summary"), manifest.get("notes"))
        or workflow
    )
    preview_only = bool(payload.get("preview_only"))
    if not preview_only:
        preview_only = any(bool((step.get("content") or {}).get("preview_only")) for step in steps if isinstance(step, dict))

    review_required = bool(
        analysis.get("review_required")
        or policy_evaluation.get("artifact_review_required")
        or preview_only
    )
    has_review = bool(review and isinstance(review.get("reviews"), list) and review["reviews"])
    status = _normalize_workflow_status(
        payload.get("status"),
        review_required=review_required,
        has_review=has_review,
    )
    review_state = _review_state_for_filters(review, payload)
    assignee = _clean(payload.get("assignee"))
    due_at = _safe_due_at(payload.get("due_at"))
    comments = payload.get("comments") if isinstance(payload.get("comments"), list) else []
    comment_count = int(payload.get("comment_count") or len(comments) or 0)
    last_comment_at = _clean(payload.get("last_comment_at"))
    priority_override = _clean(payload.get("priority_override"))

    if analysis.get("primary_fault") or analysis.get("fault_detected"):
        priority = "high"
        risk_state = "high-risk"
    elif preview_only or review_required:
        priority = "medium"
        risk_state = "needs-review"
    else:
        priority = "normal"
        risk_state = "low-risk"
    if priority_override:
        priority = priority_override

    if not source_trust:
        integrity = payload.get("integrity") or {}
        signature = payload.get("signature") or {}
        if integrity.get("ok") is False:
            source_trust = _derive_source_trust("do-not-use", "Integrity verification failed for this case.")
        elif preview_only:
            source_trust = _derive_source_trust("source-not-proven", "Preview and imported cases are not artifact-verified yet.")
        elif signature.get("valid"):
            source_trust = _derive_source_trust("trusted", "This case came from a verified artifact export.")
        elif signature.get("pending") or integrity.get("pending"):
            source_trust = _derive_source_trust("verify-source", signature.get("reason") or "Export this case to .epi to verify signer and integrity.")
        else:
            source_trust = _derive_source_trust("source-not-proven", signature.get("reason") or "No verified artifact has been attached to this live case yet.")

    return {
        "id": _clean(payload.get("id")) or derive_case_key(
            {
                "case_id": payload.get("id"),
                "decision_id": payload.get("decision_id"),
                "trace_id": payload.get("trace_id"),
                "provider": payload.get("provider"),
                "model": payload.get("model"),
                "workflow_name": workflow,
                "content": {"title": title},
                "kind": "case.summary",
            }
        ),
        "title": title,
        "workflow": workflow,
        "created_at": created_at,
        "updated_at": updated_at,
        "status": status,
        "priority": priority,
        "review_required": review_required,
        "risk_state": risk_state,
        "source_trust_state": source_trust,
        "preview_only": preview_only,
        "decision_id": _clean(payload.get("decision_id")),
        "trace_id": _clean(payload.get("trace_id")),
        "source_name": _clean(payload.get("source_name") or payload.get("sourceName")) or f"{_slugify(workflow)}.epi",
        "source_app": _clean(payload.get("source_app")),
        "provider": _clean(payload.get("provider")),
        "model": _clean(payload.get("model")),
        "assignee": assignee,
        "due_at": due_at,
        "comment_count": comment_count,
        "last_comment_at": last_comment_at,
        "review_state": review_state,
        "is_overdue": _is_overdue(due_at, status),
        "priority_override": priority_override,
    }


def _event_to_step(event: CaptureEventModel, index: int) -> dict[str, Any]:
    step = {
        "index": index,
        "timestamp": event.captured_at.isoformat(),
        "kind": event.kind,
        "content": event.content,
    }
    if event.trace_id:
        step["trace_id"] = event.trace_id
    return step


def _derive_summary_from_events(events: list[CaptureEventModel]) -> tuple[str, str | None]:
    title = None
    summary = None
    for event in reversed(events):
        text = _extract_output_text(event.content)
        if text:
            title = text[:180]
            summary = text
            break
        if event.kind == "llm.error":
            title = "Model error"
            summary = _clean(event.content.get("error") or event.content.get("message")) or "The model interaction failed."
            break
        if event.kind == "source.record.loaded":
            record_id = _first_nonempty(
                event.content.get("record_id"),
                event.content.get("case_id"),
                event.content.get("ticket_id"),
                event.content.get("sys_id"),
            )
            title = f"Loaded {record_id}" if record_id else "Source record loaded"
            summary = _clean(event.content.get("summary")) or "A source record was loaded for review."
            break
    return title or "Decision captured", summary


def build_case_payload_from_events(
    case_id: str,
    events: list[CaptureEventModel],
    latest_review: dict[str, Any] | None = None,
    *,
    existing_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    events = sorted(events, key=lambda item: (item.captured_at.isoformat(), item.event_id))
    first = events[0]
    last = events[-1]
    existing_payload = existing_payload or {}

    workflow_name = _first_nonempty(*(event.workflow_name for event in events), first.source_app, "Captured decision")
    source_name = f"{_slugify(workflow_name)}-{_slugify(case_id)}.epi"

    title, summary = _derive_summary_from_events(events)
    has_error = any(event.kind == "llm.error" for event in events)
    has_recovery = any(event.kind == "agent.run.recovered" for event in events)
    has_policy_failure = any(
        event.kind == "policy.check"
        and (
            event.content.get("passed") is False
            or event.content.get("allowed") is False
            or str(event.content.get("status") or "").lower() in {"failed", "blocked", "error"}
        )
        for event in events
    )
    preview_only = any(bool((event.content or {}).get("preview_only")) for event in events)

    trust_classes = {event.provenance.trust_class for event in events if event.provenance and event.provenance.trust_class}
    if has_error and any(str((event.content or {}).get("projection_failed") or "").lower() == "true" for event in events):
        source_trust = _derive_source_trust("do-not-use", "A projection or replay failure left this case in an unsafe state.")
    elif preview_only or trust_classes.intersection({"verified_imported", "partial", "opaque_external"}):
        source_trust = _derive_source_trust("source-not-proven", "This case came from imported, preview, or partial capture and has not been artifact-verified.")
    else:
        source_trust = _derive_source_trust("verify-source", "This live case was captured directly. Export it to .epi for portable artifact verification.")

    review_required = bool(preview_only or has_error or has_policy_failure or has_recovery)
    review = latest_review
    has_review = bool(review and isinstance(review.get("reviews"), list) and review["reviews"])
    status = _normalize_workflow_status(
        existing_payload.get("status"),
        review_required=review_required,
        has_review=has_review,
    )
    assignee = _clean(existing_payload.get("assignee"))
    due_at = _safe_due_at(existing_payload.get("due_at"))
    priority_override = _clean(existing_payload.get("priority_override"))
    comments = existing_payload.get("comments") if isinstance(existing_payload.get("comments"), list) else []
    activity = existing_payload.get("activity") if isinstance(existing_payload.get("activity"), list) else []
    last_comment_at = _clean(existing_payload.get("last_comment_at"))

    if has_error or has_policy_failure:
        why_it_matters = "The captured events include an error or failed control that should be reviewed."
    elif has_recovery:
        why_it_matters = "The gateway recovered this run after a restart before a clean completion event was recorded."
    elif review_required:
        why_it_matters = "This case requires a human decision before it should be trusted."
    else:
        why_it_matters = "No active error or failed control was detected in the captured events."

    analysis = {
        "summary": summary or why_it_matters,
        "fault_detected": bool(has_error or has_policy_failure),
        "review_required": review_required,
        "why_it_matters": why_it_matters,
        "human_review": {
            "status": "pending" if review_required and not (review and review.get("reviews")) else "complete" if review and review.get("reviews") else "not_required",
        },
        "secondary_flags": [],
    }
    if preview_only:
        analysis["secondary_flags"].append(
            {
                "category": "Preview case",
                "fault_type": "review_guard",
                "description": "This case was created from a connector preview and should be checked before rollout.",
                "why_it_matters": "Preview cases are useful for validation, but they are not yet artifact-verified source evidence.",
            }
        )
    if has_recovery:
        analysis["secondary_flags"].append(
            {
                "category": "Crash recovery",
                "fault_type": "session_recovered",
                "description": "The gateway restarted before this run logged a clean completion event.",
                "why_it_matters": "Treat this case as blocked until someone confirms the recovered workflow state.",
            }
        )
        status = "blocked"

    steps = [_event_to_step(event, index) for index, event in enumerate(events)]
    if steps and steps[0]["kind"] != "session.start":
        steps.insert(
            0,
            {
                "index": 0,
                "timestamp": first.captured_at.isoformat(),
                "kind": "session.start",
                "content": {
                    "workflow": workflow_name,
                    "source_app": _first_nonempty(*(event.source_app for event in events)),
                    "case_id": case_id,
                },
            },
        )
        for index, step in enumerate(steps):
            step["index"] = index

    environment = dict(existing_payload.get("environment") or {})
    environment.update(
        {
            "capture_source": "epi_gateway",
            "event_count": len(events),
            "provider_profiles": sorted({event.meta.get("provider_profile") for event in events if event.meta.get("provider_profile")}),
        }
    )
    environment["shared_workflow"] = {
        "status": status,
        "assignee": assignee,
        "due_at": due_at,
        "comment_count": len(comments),
        "last_comment_at": last_comment_at,
    }

    payload = {
        "id": case_id,
        "source_name": source_name,
        "manifest": {
            "spec_version": "live-case/1.0",
            "created_at": first.captured_at.isoformat(),
            "workflow_id": _first_nonempty(*(event.workflow_id for event in events), case_id),
            "workflow_name": workflow_name,
            "notes": summary or why_it_matters,
            "file_manifest": {},
        },
        "steps": steps,
        "analysis": analysis,
        "policy": None,
        "policy_evaluation": {
            "artifact_review_required": review_required,
            "controls_evaluated": 0,
            "controls_failed": 1 if has_policy_failure else 0,
        },
        "review": review,
        "environment": environment,
        "stdout": None,
        "stderr": None,
        "integrity": {
            "ok": True,
            "pending": True,
            "checked": 0,
            "mismatches": [],
        },
        "signature": {
            "valid": False,
            "pending": True,
            "reason": "This is a live shared case. Export it to .epi to verify portable artifact trust.",
        },
        "shared_workspace_case": True,
        "backend_case": True,
        "preview_only": preview_only,
        "source_trust_state": source_trust,
        "decision_id": _first_nonempty(*(event.decision_id for event in events)),
        "trace_id": _first_nonempty(*(event.trace_id for event in events)),
        "workflow_name": workflow_name,
        "source_app": _first_nonempty(*(event.source_app for event in events)),
        "provider": _first_nonempty(*(event.provider for event in events)),
        "model": _first_nonempty(*(event.model for event in events)),
        "created_at": first.captured_at.isoformat(),
        "updated_at": last.captured_at.isoformat(),
        "status": status,
        "assignee": assignee,
        "due_at": due_at,
        "priority_override": priority_override,
        "comments": comments,
        "activity": activity,
        "comment_count": len(comments),
        "last_comment_at": last_comment_at,
        "review_state": _review_state_for_filters(review, {"analysis": analysis, "policy_evaluation": {"artifact_review_required": review_required}}),
    }
    return payload


def _uuid_from_case_id(case_id: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"https://epilabs.org/cases/{case_id}")


class CaseStore:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.projection_failure_count = 0
        self.last_projection_error: str | None = None
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS applied_batches (
                    batch_id TEXT PRIMARY KEY,
                    file_name TEXT,
                    applied_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS events (
                    event_id TEXT PRIMARY KEY,
                    case_id TEXT NOT NULL,
                    decision_id TEXT,
                    trace_id TEXT,
                    workflow_id TEXT,
                    workflow_name TEXT,
                    source_app TEXT,
                    actor_id TEXT,
                    provider TEXT,
                    model TEXT,
                    kind TEXT NOT NULL,
                    captured_at TEXT NOT NULL,
                    event_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS cases (
                    case_id TEXT PRIMARY KEY,
                    decision_id TEXT,
                    trace_id TEXT,
                    workflow_id TEXT,
                    workflow_name TEXT,
                    source_app TEXT,
                    actor_id TEXT,
                    provider TEXT,
                    model TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    event_count INTEGER NOT NULL DEFAULT 0,
                    title TEXT NOT NULL,
                    status TEXT NOT NULL,
                    priority TEXT NOT NULL,
                    review_required INTEGER NOT NULL DEFAULT 0,
                    risk_state TEXT NOT NULL,
                    source_trust_code TEXT NOT NULL,
                    preview_only INTEGER NOT NULL DEFAULT 0,
                    latest_review_json TEXT,
                    payload_json TEXT NOT NULL,
                    source_name TEXT
                );
                CREATE TABLE IF NOT EXISTS case_reviews (
                    review_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    case_id TEXT NOT NULL,
                    reviewed_at TEXT NOT NULL,
                    review_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS case_comments (
                    comment_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    case_id TEXT NOT NULL,
                    author TEXT NOT NULL,
                    body TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS case_activity (
                    activity_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    case_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    title TEXT NOT NULL,
                    copy TEXT NOT NULL,
                    actor TEXT,
                    created_at TEXT NOT NULL,
                    metadata_json TEXT
                );
                CREATE TABLE IF NOT EXISTS auth_users (
                    username TEXT PRIMARY KEY,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    disabled INTEGER NOT NULL DEFAULT 0,
                    source TEXT,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS auth_sessions (
                    token_hash TEXT PRIMARY KEY,
                    username TEXT NOT NULL,
                    role TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    revoked_at TEXT
                );
                CREATE TABLE IF NOT EXISTS open_sessions (
                    workflow_id TEXT PRIMARY KEY,
                    case_id TEXT,
                    started_at TEXT NOT NULL,
                    last_event_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_events_case_id ON events(case_id);
                CREATE INDEX IF NOT EXISTS idx_events_captured_at ON events(captured_at);
                CREATE INDEX IF NOT EXISTS idx_cases_updated_at ON cases(updated_at);
                CREATE INDEX IF NOT EXISTS idx_case_comments_case_id ON case_comments(case_id, comment_id);
                CREATE INDEX IF NOT EXISTS idx_case_activity_case_id ON case_activity(case_id, activity_id);
                CREATE INDEX IF NOT EXISTS idx_auth_sessions_expires_at ON auth_sessions(expires_at);
                CREATE INDEX IF NOT EXISTS idx_open_sessions_last_event_at ON open_sessions(last_event_at);
                CREATE TABLE IF NOT EXISTS schema_version (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT NOT NULL
                );
                """
            )
            self._ensure_case_columns(connection)
            self._run_migrations(connection)
            connection.commit()

    # Schema version history:
    #   1 — initial schema (applied_batches, events, cases, reviews, comments, activity, auth_users, auth_sessions)
    #   2 — extra case columns (assignee, due_at, priority_override, comment_count, last_comment_at) via _ensure_case_columns
    _SCHEMA_VERSION = 3

    def _run_migrations(self, connection: sqlite3.Connection) -> None:
        """Apply outstanding schema migrations in order. Idempotent."""
        row = connection.execute("SELECT MAX(version) FROM schema_version").fetchone()
        current = row[0] if row and row[0] is not None else 0

        from epi_core.time_utils import utc_now_iso

        if current < 1:
            # Version 1: baseline — tables already created above, just stamp.
            connection.execute(
                "INSERT OR IGNORE INTO schema_version (version, applied_at) VALUES (1, ?)",
                (utc_now_iso(),),
            )
            current = 1

        if current < 2:
            # Version 2: extra case columns (may already exist via _ensure_case_columns — that's fine).
            connection.execute(
                "INSERT OR IGNORE INTO schema_version (version, applied_at) VALUES (2, ?)",
                (utc_now_iso(),),
            )
            current = 2

        if current < 3:
            connection.execute(
                "INSERT OR IGNORE INTO schema_version (version, applied_at) VALUES (3, ?)",
                (utc_now_iso(),),
            )
            current = 3  # noqa: F841

    def _ensure_case_columns(self, connection: sqlite3.Connection) -> None:
        rows = connection.execute("PRAGMA table_info(cases)").fetchall()
        columns = {row["name"] for row in rows}
        additions = {
            "assignee": "ALTER TABLE cases ADD COLUMN assignee TEXT",
            "due_at": "ALTER TABLE cases ADD COLUMN due_at TEXT",
            "priority_override": "ALTER TABLE cases ADD COLUMN priority_override TEXT",
            "comment_count": "ALTER TABLE cases ADD COLUMN comment_count INTEGER NOT NULL DEFAULT 0",
            "last_comment_at": "ALTER TABLE cases ADD COLUMN last_comment_at TEXT",
        }
        for column, statement in additions.items():
            if column not in columns:
                connection.execute(statement)

    def sync_auth_users(self, users: list[dict[str, Any]], *, source: str | None = None) -> int:
        normalized_source = _clean(source) or "users_file"
        usernames = [str(item.get("username") or "").strip().lower() for item in users if str(item.get("username") or "").strip()]
        now = utc_now_iso()
        with self._connect() as connection:
            if usernames:
                placeholders = ",".join("?" for _ in usernames)
                connection.execute(
                    f"DELETE FROM auth_users WHERE source = ? AND username NOT IN ({placeholders})",
                    (normalized_source, *usernames),
                )
            else:
                connection.execute("DELETE FROM auth_users WHERE source = ?", (normalized_source,))

            for item in users:
                username = str(item.get("username") or "").strip().lower()
                if not username:
                    continue
                connection.execute(
                    """
                    INSERT INTO auth_users (username, password_hash, role, display_name, disabled, source, updated_at)
                    VALUES (?, ?, ?, ?, 0, ?, ?)
                    ON CONFLICT(username) DO UPDATE SET
                        password_hash = excluded.password_hash,
                        role = excluded.role,
                        display_name = excluded.display_name,
                        disabled = 0,
                        source = excluded.source,
                        updated_at = excluded.updated_at
                    """,
                    (
                        username,
                        str(item.get("password_hash") or ""),
                        _clean(item.get("role")) or "reviewer",
                        _clean(item.get("display_name")) or username,
                        normalized_source,
                        now,
                    ),
                )
            connection.commit()
        return len(usernames)

    def list_auth_users(self) -> list[AuthUserModel]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT username, display_name, role, source
                FROM auth_users
                WHERE disabled = 0
                ORDER BY username ASC
                """
            ).fetchall()
        return [
            AuthUserModel(
                username=row["username"],
                display_name=row["display_name"],
                role=row["role"],
                source=row["source"],
            )
            for row in rows
        ]

    def authenticate_user(self, username: str, password: str) -> AuthUserModel | None:
        normalized_username = str(username or "").strip().lower()
        if not normalized_username or not str(password or ""):
            return None
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT username, password_hash, role, display_name
                FROM auth_users
                WHERE username = ? AND disabled = 0
                """,
                (normalized_username,),
            ).fetchone()
        if not row or not verify_password(password, row["password_hash"]):
            return None
        return AuthUserModel(
            username=row["username"],
            display_name=row["display_name"],
            role=row["role"],
        )

    def create_auth_session(self, user: AuthUserModel, *, ttl_hours: float = 12.0) -> tuple[str, AuthSessionModel]:
        raw_token = build_session_token()
        created_at = utc_now_iso()
        expires_at = (datetime.now(timezone.utc) + timedelta(hours=max(1.0, float(ttl_hours)))).isoformat()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO auth_sessions (token_hash, username, role, display_name, created_at, expires_at, revoked_at)
                VALUES (?, ?, ?, ?, ?, ?, NULL)
                """,
                (
                    hash_session_token(raw_token),
                    user.username,
                    user.role,
                    user.display_name,
                    created_at,
                    expires_at,
                ),
            )
            connection.commit()
        return raw_token, AuthSessionModel(
            username=user.username,
            display_name=user.display_name,
            role=user.role,
            created_at=created_at,
            expires_at=expires_at,
        )

    def get_auth_session(self, token: str) -> AuthSessionModel | None:
        token_hash = hash_session_token(token)
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT username, role, display_name, created_at, expires_at, revoked_at
                FROM auth_sessions
                WHERE token_hash = ?
                """,
                (token_hash,),
            ).fetchone()
        if not row or _clean(row["revoked_at"]):
            return None
        expires_at = _parse_datetime(row["expires_at"])
        if not expires_at or expires_at <= datetime.now(timezone.utc):
            return None
        return AuthSessionModel(
            username=row["username"],
            display_name=row["display_name"],
            role=row["role"],
            created_at=row["created_at"],
            expires_at=row["expires_at"],
        )

    def revoke_auth_session(self, token: str) -> None:
        token_hash = hash_session_token(token)
        with self._connect() as connection:
            connection.execute(
                "UPDATE auth_sessions SET revoked_at = ? WHERE token_hash = ? AND revoked_at IS NULL",
                (utc_now_iso(), token_hash),
            )
            connection.commit()

    def list_open_sessions(self) -> list[OpenSessionModel]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT workflow_id, case_id, started_at, last_event_at
                FROM open_sessions
                ORDER BY last_event_at ASC, workflow_id ASC
                """
            ).fetchall()
        return [
            OpenSessionModel(
                workflow_id=row["workflow_id"],
                case_id=_clean(row["case_id"]),
                started_at=row["started_at"],
                last_event_at=row["last_event_at"],
            )
            for row in rows
        ]

    def delete_open_session(self, workflow_id: str) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM open_sessions WHERE workflow_id = ?", (_clean(workflow_id),))
            connection.commit()

    def find_case_id_for_workflow(self, workflow_id: str) -> str | None:
        workflow_key = _clean(workflow_id)
        if not workflow_key:
            return None
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT case_id
                FROM cases
                WHERE workflow_id = ? OR case_id = ?
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (workflow_key, workflow_key),
            ).fetchone()
            if row and _clean(row["case_id"]):
                return _clean(row["case_id"])
            row = connection.execute(
                """
                SELECT case_id
                FROM open_sessions
                WHERE workflow_id = ?
                LIMIT 1
                """,
                (workflow_key,),
            ).fetchone()
        return _clean(row["case_id"]) if row else None

    def find_approval_request(self, workflow_id: str, approval_id: str) -> dict[str, Any] | None:
        workflow_key = _clean(workflow_id)
        approval_key = _clean(approval_id)
        if not workflow_key or not approval_key:
            return None
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT case_id, workflow_id, event_json
                FROM events
                WHERE kind = 'agent.approval.request'
                  AND (workflow_id = ? OR case_id = ?)
                ORDER BY captured_at DESC, event_id DESC
                """,
                (workflow_key, workflow_key),
            ).fetchall()
        for row in rows:
            payload = _decode_json(row["event_json"], {})
            content = payload.get("content") or {}
            if _clean(content.get("approval_id")) != approval_key:
                continue
            return {
                "case_id": _clean(row["case_id"]),
                "workflow_id": _clean(row["workflow_id"]) or workflow_key,
                "content": content,
                "event": payload,
            }
        return None

    def replay_spool(self, events_dir: Path) -> ReplaySpoolResultModel:
        events_dir = Path(events_dir)
        events_dir.mkdir(parents=True, exist_ok=True)
        corrupt_dir = events_dir / "corrupt"
        corrupt_dir.mkdir(parents=True, exist_ok=True)
        result = ReplaySpoolResultModel()
        for batch_path in sorted(events_dir.glob("evidence_*.json")):
            try:
                payload = json.loads(batch_path.read_text(encoding="utf-8"))
                batch = CaptureBatchModel.model_validate(payload)
            except Exception as exc:
                moved_to = self._quarantine_spool_file(batch_path, corrupt_dir)
                result.corrupt_batch_count += 1
                result.corrupt_files.append(batch_path.name)
                result.moved_corrupt_files.append(moved_to.name)
                result.last_error = str(exc)
                continue

            if self.batch_applied(batch.batch_id):
                result.skipped_batches += 1
                continue
            try:
                self.apply_batch(batch, file_name=batch_path.name)
                result.applied_batches += 1
            except Exception as exc:
                moved_to = self._quarantine_spool_file(batch_path, corrupt_dir)
                result.corrupt_batch_count += 1
                result.corrupt_files.append(batch_path.name)
                result.moved_corrupt_files.append(moved_to.name)
                result.last_error = str(exc)
        return result

    def _quarantine_spool_file(self, batch_path: Path, corrupt_dir: Path) -> Path:
        corrupt_dir.mkdir(parents=True, exist_ok=True)
        target = corrupt_dir / f"{batch_path.name}.corrupt"
        counter = 1
        while target.exists():
            target = corrupt_dir / f"{batch_path.name}.corrupt.{counter}"
            counter += 1
        batch_path.replace(target)
        return target

    def batch_applied(self, batch_id: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM applied_batches WHERE batch_id = ?",
                (batch_id,),
            ).fetchone()
        return row is not None

    def apply_batch(self, batch: CaptureBatchModel | dict[str, Any], *, file_name: str | None = None) -> list[str]:
        model = CaptureBatchModel.model_validate(batch)
        touched_case_ids: set[str] = set()

        with self._connect() as connection:
            if connection.execute("SELECT 1 FROM applied_batches WHERE batch_id = ?", (model.batch_id,)).fetchone():
                return []

            for raw_item in model.items:
                event = coerce_capture_event(raw_item)
                case_id = derive_case_key(event)
                event.case_id = case_id
                event.meta["case_id"] = case_id
                payload = event.model_dump(mode="json")
                cursor = connection.execute(
                    """
                    INSERT OR IGNORE INTO events (
                        event_id, case_id, decision_id, trace_id, workflow_id, workflow_name,
                        source_app, actor_id, provider, model, kind, captured_at, event_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event.event_id,
                        case_id,
                        event.decision_id,
                        event.trace_id,
                        event.workflow_id,
                        event.workflow_name,
                        event.source_app,
                        event.actor_id,
                        event.provider,
                        event.model,
                        event.kind,
                        event.captured_at.isoformat(),
                        _json(payload),
                    ),
                )
                if cursor.rowcount:
                    touched_case_ids.add(case_id)
                    self._track_open_session_event(connection, event, case_id)

            connection.execute(
                "INSERT INTO applied_batches (batch_id, file_name, applied_at) VALUES (?, ?, ?)",
                (model.batch_id, file_name, utc_now_iso()),
            )
            connection.commit()

        for case_id in touched_case_ids:
            try:
                self.rebuild_case(case_id)
            except Exception as exc:
                self._record_projection_failure(case_id, exc)
        return sorted(touched_case_ids)

    def rebuild_case(self, case_id: str) -> dict[str, Any] | None:
        events = self.list_events(case_id)
        if not events:
            return None

        latest_review = self.get_latest_review(case_id)
        existing_payload = self._load_case_payload(case_id)
        payload = build_case_payload_from_events(
            case_id,
            events,
            latest_review=latest_review,
            existing_payload=existing_payload,
        )
        self._refresh_case_payload(case_id, payload, preserve_workflow_state=True)
        return payload

    def list_events(self, case_id: str) -> list[CaptureEventModel]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT event_json FROM events WHERE case_id = ? ORDER BY captured_at ASC, event_id ASC",
                (case_id,),
            ).fetchall()
        return [CaptureEventModel.model_validate(_decode_json(row["event_json"], {})) for row in rows]

    def get_latest_review(self, case_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT review_json FROM case_reviews WHERE case_id = ? ORDER BY review_id DESC LIMIT 1",
                (case_id,),
            ).fetchone()
        return _decode_json(row["review_json"], None) if row else None

    def _load_case_payload(self, case_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT payload_json, assignee, due_at, comment_count, last_comment_at, priority_override, status
                FROM cases
                WHERE case_id = ?
                """,
                (case_id,),
            ).fetchone()
        if not row:
            return None
        payload = _decode_json(row["payload_json"], {})
        payload.setdefault("id", case_id)
        payload["assignee"] = _clean(payload.get("assignee")) or _clean(row["assignee"])
        payload["due_at"] = _safe_due_at(payload.get("due_at")) or _safe_due_at(row["due_at"])
        payload["priority_override"] = _clean(payload.get("priority_override")) or _clean(row["priority_override"])
        payload["status"] = _clean(payload.get("status")) or _clean(row["status"])
        payload["comment_count"] = int(payload.get("comment_count") or row["comment_count"] or 0)
        payload["last_comment_at"] = _clean(payload.get("last_comment_at")) or _clean(row["last_comment_at"])
        return payload

    def list_comments(self, case_id: str) -> list[CaseCommentModel]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT comment_id, case_id, author, body, created_at
                FROM case_comments
                WHERE case_id = ?
                ORDER BY comment_id ASC
                """,
                (case_id,),
            ).fetchall()
        return [
            CaseCommentModel(
                id=row["comment_id"],
                case_id=row["case_id"],
                author=row["author"],
                body=row["body"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def list_activity(self, case_id: str) -> list[CaseActivityModel]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT activity_id, case_id, kind, title, copy, actor, created_at, metadata_json
                FROM case_activity
                WHERE case_id = ?
                ORDER BY activity_id ASC
                """,
                (case_id,),
            ).fetchall()
        return [
            CaseActivityModel(
                id=row["activity_id"],
                case_id=row["case_id"],
                kind=row["kind"],
                title=row["title"],
                message=row["copy"],
                actor=row["actor"],
                created_at=row["created_at"],
                metadata=_decode_json(row["metadata_json"], {}) or {},
            )
            for row in rows
        ]

    def record_system_activity(
        self,
        case_id: str,
        *,
        kind: str,
        title: str,
        copy: str,
        actor: str = "epi-gateway",
        created_at: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not self._load_case_payload(case_id):
            raise KeyError(case_id)
        self._append_activity(
            case_id,
            kind=kind,
            title=title,
            copy=copy,
            actor=actor,
            created_at=created_at,
            metadata=metadata,
        )
        return self._refresh_case_payload(case_id)

    def _append_activity(
        self,
        case_id: str,
        *,
        kind: str,
        title: str,
        copy: str,
        actor: str | None = None,
        created_at: str | None = None,
        metadata: dict[str, Any] | None = None,
        connection: sqlite3.Connection | None = None,
    ) -> None:
        params = (
            case_id,
            kind,
            title,
            copy,
            _clean(actor),
            _safe_datetime(created_at),
            _json(metadata or {}),
        )
        if connection is not None:
            connection.execute(
                """
                INSERT INTO case_activity (case_id, kind, title, copy, actor, created_at, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                params,
            )
            return

        with self._connect() as new_connection:
            new_connection.execute(
                """
                INSERT INTO case_activity (case_id, kind, title, copy, actor, created_at, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                params,
            )
            new_connection.commit()

    def _track_open_session_event(
        self,
        connection: sqlite3.Connection,
        event: CaptureEventModel,
        case_id: str,
    ) -> None:
        workflow_id = _clean(event.workflow_id)
        if not workflow_id:
            return

        captured_at = event.captured_at.isoformat()
        if event.kind in {"agent.run.end", "agent.run.recovered"}:
            connection.execute("DELETE FROM open_sessions WHERE workflow_id = ?", (workflow_id,))
            return

        if event.kind == "agent.run.start":
            connection.execute(
                """
                INSERT INTO open_sessions (workflow_id, case_id, started_at, last_event_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(workflow_id) DO UPDATE SET
                    case_id = COALESCE(excluded.case_id, open_sessions.case_id),
                    started_at = excluded.started_at,
                    last_event_at = excluded.last_event_at
                """,
                (workflow_id, case_id, captured_at, captured_at),
            )
            return

        connection.execute(
            """
            INSERT INTO open_sessions (workflow_id, case_id, started_at, last_event_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(workflow_id) DO UPDATE SET
                case_id = COALESCE(excluded.case_id, open_sessions.case_id),
                last_event_at = excluded.last_event_at
            """,
            (workflow_id, case_id, captured_at, captured_at),
        )

    def _refresh_case_payload(
        self,
        case_id: str,
        payload: dict[str, Any] | None = None,
        *,
        preserve_workflow_state: bool = False,
    ) -> dict[str, Any]:
        payload = dict(payload or self._load_case_payload(case_id) or {})
        if not payload:
            raise KeyError(case_id)

        if preserve_workflow_state:
            current_payload = self._load_case_payload(case_id) or {}
            current_status = _clean(current_payload.get("status"))
            current_assignee = _clean(current_payload.get("assignee"))
            current_due_at = _safe_due_at(current_payload.get("due_at"))
            current_priority_override = _clean(current_payload.get("priority_override"))
            current_comment_count = int(current_payload.get("comment_count") or 0)
            current_last_comment_at = _clean(current_payload.get("last_comment_at"))

            if current_status and _clean(payload.get("status")) != "blocked":
                payload["status"] = current_status
            if current_assignee:
                payload["assignee"] = current_assignee
            if current_due_at:
                payload["due_at"] = current_due_at
            if current_priority_override:
                payload["priority_override"] = current_priority_override
            if current_comment_count:
                payload["comment_count"] = max(int(payload.get("comment_count") or 0), current_comment_count)
            if current_last_comment_at:
                payload["last_comment_at"] = current_last_comment_at

        comments = [item.model_dump(mode="json") for item in self.list_comments(case_id)]
        activity = [item.model_dump(mode="json", by_alias=True) for item in self.list_activity(case_id)]
        payload["comments"] = comments
        payload["activity"] = activity
        payload["comment_count"] = len(comments)
        payload["last_comment_at"] = comments[-1]["created_at"] if comments else None
        payload["assignee"] = _clean(payload.get("assignee"))
        payload["due_at"] = _safe_due_at(payload.get("due_at"))
        payload["priority_override"] = _clean(payload.get("priority_override"))
        payload["review_state"] = _review_state_for_filters(payload.get("review"), payload)
        payload["status"] = _normalize_workflow_status(
            payload.get("status"),
            review_required=bool(
                payload.get("analysis", {}).get("review_required")
                or payload.get("policy_evaluation", {}).get("artifact_review_required")
                or payload.get("preview_only")
            ),
            has_review=bool(
                payload.get("review")
                and isinstance(payload.get("review", {}).get("reviews"), list)
                and payload["review"]["reviews"]
            ),
        )
        environment = dict(payload.get("environment") or {})
        environment["shared_workflow"] = {
            "status": payload.get("status"),
            "assignee": payload.get("assignee"),
            "due_at": payload.get("due_at"),
            "comment_count": payload.get("comment_count"),
            "last_comment_at": payload.get("last_comment_at"),
        }
        payload["environment"] = environment
        summary = summarize_case_payload(payload)
        self._upsert_case(summary, payload)
        return payload

    def _record_projection_failure(self, case_id: str, exc: Exception) -> None:
        self.projection_failure_count += 1
        self.last_projection_error = str(exc)

        existing_payload = self._load_case_payload(case_id) or {}
        try:
            events = self.list_events(case_id)
        except Exception:
            events = []

        created_at = _first_nonempty(
            existing_payload.get("created_at"),
            events[0].captured_at.isoformat() if events else None,
            utc_now_iso(),
        )
        updated_at = utc_now_iso()
        workflow_name = _first_nonempty(
            existing_payload.get("workflow_name"),
            *(event.workflow_name for event in events),
            "Captured decision",
        )
        source_name = _first_nonempty(
            existing_payload.get("source_name"),
            f"{_slugify(workflow_name)}-{_slugify(case_id)}.epi",
        )
        review = existing_payload.get("review")
        review_required = True
        fallback_status = _normalize_workflow_status(
            existing_payload.get("status"),
            review_required=review_required,
            has_review=bool(review and isinstance(review.get("reviews"), list) and review["reviews"]),
        )
        payload = {
            "id": case_id,
            "source_name": source_name,
            "manifest": {
                "spec_version": "live-case/1.0",
                "created_at": created_at,
                "workflow_id": _first_nonempty(existing_payload.get("manifest", {}).get("workflow_id"), case_id),
                "workflow_name": workflow_name,
                "notes": "EPI hit a projection or replay failure while rebuilding this live case.",
                "file_manifest": {},
            },
            "steps": existing_payload.get("steps") or [],
            "analysis": {
                "summary": "EPI hit a projection or replay failure while rebuilding this live case.",
                "fault_detected": True,
                "review_required": True,
                "why_it_matters": "Treat this case as unsafe until the underlying capture batch is repaired or replayed successfully.",
                "human_review": {
                    "status": "pending",
                },
                "secondary_flags": [
                    {
                        "category": "Gateway projection",
                        "fault_type": "projection_failure",
                        "description": str(exc),
                        "why_it_matters": "The shared case store could not fully rebuild this case from the append-only spool.",
                    }
                ],
            },
            "policy": existing_payload.get("policy"),
            "policy_evaluation": {
                "artifact_review_required": True,
                "controls_evaluated": 0,
                "controls_failed": 1,
            },
            "review": review,
            "environment": {
                **dict(existing_payload.get("environment") or {}),
                "capture_source": "epi_gateway",
                "projection_failure": {
                    "failed": True,
                    "message": str(exc),
                    "updated_at": updated_at,
                },
            },
            "stdout": existing_payload.get("stdout"),
            "stderr": str(exc),
            "integrity": {
                "ok": False,
                "pending": False,
                "checked": 0,
                "mismatches": [],
            },
            "signature": {
                "valid": False,
                "pending": False,
                "reason": "Projection failed. Repair the shared store or re-export to recover a trustworthy artifact.",
            },
            "shared_workspace_case": True,
            "backend_case": True,
            "preview_only": bool(existing_payload.get("preview_only")),
            "source_trust_state": _derive_source_trust(
                "do-not-use",
                "A projection or replay failure left this case in an unsafe state.",
            ),
            "decision_id": _first_nonempty(existing_payload.get("decision_id"), *(event.decision_id for event in events)),
            "trace_id": _first_nonempty(existing_payload.get("trace_id"), *(event.trace_id for event in events)),
            "workflow_name": workflow_name,
            "source_app": _first_nonempty(existing_payload.get("source_app"), *(event.source_app for event in events)),
            "provider": _first_nonempty(existing_payload.get("provider"), *(event.provider for event in events)),
            "model": _first_nonempty(existing_payload.get("model"), *(event.model for event in events)),
            "created_at": created_at,
            "updated_at": updated_at,
            "status": fallback_status,
            "assignee": _clean(existing_payload.get("assignee")),
            "due_at": _safe_due_at(existing_payload.get("due_at")),
            "priority_override": _clean(existing_payload.get("priority_override")),
            "comments": existing_payload.get("comments") or [],
            "activity": existing_payload.get("activity") or [],
            "comment_count": int(existing_payload.get("comment_count") or 0),
            "last_comment_at": _clean(existing_payload.get("last_comment_at")),
            "review_state": _review_state_for_filters(review, {"analysis": {"review_required": True}, "policy_evaluation": {"artifact_review_required": True}}),
        }
        self._refresh_case_payload(case_id, payload)
        self._append_activity(
            case_id,
            kind="projection_failed",
            title="Projection failed",
            copy="EPI marked this case as unsafe after a projection or replay failure.",
            actor="epi-gateway",
            created_at=updated_at,
            metadata={"error": str(exc)},
        )

    def _upsert_case(self, summary: dict[str, Any], payload: dict[str, Any]) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO cases (
                    case_id, decision_id, trace_id, workflow_id, workflow_name, source_app, actor_id,
                    provider, model, created_at, updated_at, event_count, title, status, priority,
                    review_required, risk_state, source_trust_code, preview_only, latest_review_json,
                    payload_json, source_name, assignee, due_at, priority_override, comment_count, last_comment_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(case_id) DO UPDATE SET
                    decision_id = excluded.decision_id,
                    trace_id = excluded.trace_id,
                    workflow_id = excluded.workflow_id,
                    workflow_name = excluded.workflow_name,
                    source_app = excluded.source_app,
                    actor_id = excluded.actor_id,
                    provider = excluded.provider,
                    model = excluded.model,
                    created_at = excluded.created_at,
                    updated_at = excluded.updated_at,
                    event_count = excluded.event_count,
                    title = excluded.title,
                    status = excluded.status,
                    priority = excluded.priority,
                    review_required = excluded.review_required,
                    risk_state = excluded.risk_state,
                    source_trust_code = excluded.source_trust_code,
                    preview_only = excluded.preview_only,
                    latest_review_json = excluded.latest_review_json,
                    payload_json = excluded.payload_json,
                    source_name = excluded.source_name,
                    assignee = excluded.assignee,
                    due_at = excluded.due_at,
                    priority_override = excluded.priority_override,
                    comment_count = excluded.comment_count,
                    last_comment_at = excluded.last_comment_at
                """,
                (
                    summary["id"],
                    summary.get("decision_id"),
                    summary.get("trace_id"),
                    payload.get("manifest", {}).get("workflow_id"),
                    summary.get("workflow"),
                    summary.get("source_app"),
                    payload.get("actor_id"),
                    summary.get("provider"),
                    summary.get("model"),
                    summary["created_at"],
                    summary["updated_at"],
                    len(payload.get("steps") or []),
                    summary["title"],
                    summary["status"],
                    summary["priority"],
                    1 if summary["review_required"] else 0,
                    summary["risk_state"],
                    summary["source_trust_state"]["code"],
                    1 if summary["preview_only"] else 0,
                    _json(payload.get("review")) if payload.get("review") else None,
                    _json(payload),
                    summary.get("source_name"),
                    summary.get("assignee"),
                    summary.get("due_at"),
                    summary.get("priority_override"),
                    summary.get("comment_count") or 0,
                    summary.get("last_comment_at"),
                ),
            )
            connection.commit()

    def upsert_case_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        summary = summarize_case_payload(payload)
        payload = {
            **payload,
            "id": summary["id"],
            "source_name": summary["source_name"],
            "shared_workspace_case": True,
            "backend_case": True,
            "preview_only": summary["preview_only"],
            "source_trust_state": summary["source_trust_state"],
            "created_at": summary["created_at"],
            "updated_at": summary["updated_at"],
            "status": summary["status"],
            "assignee": summary.get("assignee"),
            "due_at": summary.get("due_at"),
            "priority_override": summary.get("priority_override"),
        }
        self._refresh_case_payload(summary["id"], payload)
        if payload.get("review"):
            self.save_review(summary["id"], payload["review"], rebuild=False)
        return self.get_case(summary["id"])

    def list_cases(
        self,
        *,
        status: str | None = None,
        trust: str | None = None,
        review: str | None = None,
        workflow: str | None = None,
        search: str | None = None,
        assignee: str | None = None,
        overdue: bool | None = None,
    ) -> list[CaseSummaryModel]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT case_id, title, workflow_name, created_at, updated_at, status, priority,
                       review_required, risk_state, source_trust_code, preview_only,
                       decision_id, trace_id, source_name, payload_json,
                       assignee, due_at, comment_count, last_comment_at, priority_override
                FROM cases
                ORDER BY updated_at DESC, created_at DESC
                """
            ).fetchall()

        items: list[CaseSummaryModel] = []
        search_term = str(search or "").strip().lower()
        for row in rows:
            payload = _decode_json(row["payload_json"], {})
            source_trust = payload.get("source_trust_state") or _derive_source_trust(
                row["source_trust_code"],
                "This case came from the shared gateway store.",
            )
            review_state = _review_state_for_filters(payload.get("review"), payload)
            item = CaseSummaryModel(
                id=row["case_id"],
                title=row["title"],
                workflow=row["workflow_name"] or "Decision captured",
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                status=row["status"],
                priority=row["priority"],
                review_required=bool(row["review_required"]),
                risk_state=row["risk_state"],
                source_trust_state=source_trust,
                preview_only=bool(row["preview_only"]),
                decision_id=row["decision_id"],
                trace_id=row["trace_id"],
                source_name=row["source_name"],
                review_state=review_state,
                assignee=row["assignee"],
                due_at=row["due_at"],
                comment_count=int(row["comment_count"] or 0),
                last_comment_at=row["last_comment_at"],
                is_overdue=_is_overdue(row["due_at"], row["status"]),
                priority_override=row["priority_override"],
            )
            haystack = " ".join(
                part
                for part in [
                    item.title,
                    item.workflow,
                    item.source_name or "",
                    str(payload.get("source_app") or ""),
                    str(payload.get("manifest", {}).get("notes") or ""),
                ]
                if part
            ).lower()

            if status and item.status != status:
                continue
            if trust and source_trust.get("code") != trust:
                continue
            if review and review_state != review:
                continue
            if workflow and item.workflow != workflow:
                continue
            if assignee and (item.assignee or "") != assignee:
                continue
            if overdue is True and not item.is_overdue:
                continue
            if overdue is False and item.is_overdue:
                continue
            if search_term and search_term not in haystack:
                continue
            items.append(item)
        return items

    def get_case(self, case_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT payload_json, assignee, due_at, comment_count, last_comment_at, priority_override, status
                FROM cases
                WHERE case_id = ?
                """,
                (case_id,),
            ).fetchone()
        if not row:
            return None
        payload = _decode_json(row["payload_json"], {})
        payload.setdefault("id", case_id)
        payload.setdefault("shared_workspace_case", True)
        payload.setdefault("backend_case", True)
        payload["assignee"] = _clean(payload.get("assignee")) or _clean(row["assignee"])
        payload["due_at"] = _safe_due_at(payload.get("due_at")) or _safe_due_at(row["due_at"])
        payload["priority_override"] = _clean(payload.get("priority_override")) or _clean(row["priority_override"])
        payload["status"] = _clean(payload.get("status")) or _clean(row["status"])
        payload["comment_count"] = int(payload.get("comment_count") or row["comment_count"] or 0)
        payload["last_comment_at"] = _clean(payload.get("last_comment_at")) or _clean(row["last_comment_at"])
        payload["comments"] = [item.model_dump(mode="json") for item in self.list_comments(case_id)]
        payload["activity"] = [item.model_dump(mode="json", by_alias=True) for item in self.list_activity(case_id)]
        payload["review_state"] = _review_state_for_filters(payload.get("review"), payload)
        payload["is_overdue"] = _is_overdue(payload.get("due_at"), payload.get("status"))
        environment = dict(payload.get("environment") or {})
        environment["shared_workflow"] = {
            "status": payload.get("status"),
            "assignee": payload.get("assignee"),
            "due_at": payload.get("due_at"),
            "comment_count": payload.get("comment_count"),
            "last_comment_at": payload.get("last_comment_at"),
        }
        payload["environment"] = environment
        return payload

    def save_review(self, case_id: str, review_payload: dict[str, Any], *, rebuild: bool = True) -> dict[str, Any]:
        reviewed_at = _safe_datetime(review_payload.get("reviewed_at"))
        existing_payload = self._load_case_payload(case_id)
        if not existing_payload:
            raise KeyError(case_id)

        reviewer = _clean(review_payload.get("reviewed_by"))
        if not reviewer:
            reviews = review_payload.get("reviews") or []
            reviewer = _clean(reviews[-1].get("reviewer")) if reviews else None
        reviewer = reviewer or "reviewer"
        previous_status = _normalize_workflow_status(
            existing_payload.get("status"),
            review_required=bool(
                existing_payload.get("analysis", {}).get("review_required")
                or existing_payload.get("policy_evaluation", {}).get("artifact_review_required")
                or existing_payload.get("preview_only")
            ),
            has_review=bool(
                existing_payload.get("review")
                and isinstance(existing_payload.get("review", {}).get("reviews"), list)
                and existing_payload["review"]["reviews"]
            ),
        )
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO case_reviews (case_id, reviewed_at, review_json) VALUES (?, ?, ?)",
                (case_id, reviewed_at, _json(review_payload)),
            )
            reviews = review_payload.get("reviews") or []
            outcome = _clean(reviews[-1].get("outcome")) if reviews else None
            self._append_activity(
                case_id,
                kind="review_saved",
                title="Review saved",
                copy=f"{reviewer} recorded {outcome or 'a review'} for this case.",
                actor=reviewer,
                created_at=reviewed_at,
                metadata={"outcome": outcome, "reviewed_by": reviewer},
                connection=connection,
            )
            connection.commit()

        payload = {
            **existing_payload,
            "review": review_payload,
            "updated_at": reviewed_at,
            "status": _review_outcome_to_status(review_payload, previous_status),
        }

        if payload["status"] != previous_status:
            self._append_activity(
                case_id,
                kind="status_changed",
                title="Workflow status updated",
                copy=f"Status changed from {previous_status.replace('_', ' ')} to {payload['status'].replace('_', ' ')} after review.",
                actor=reviewer,
                created_at=reviewed_at,
                metadata={"from": previous_status, "to": payload["status"]},
            )

        if rebuild and self.list_events(case_id):
            self.rebuild_case(case_id)
            self.update_case_workflow(
                case_id,
                {
                    "status": payload["status"],
                    "updated_by": reviewer,
                    "reason": "Review outcome applied",
                },
                log_status_activity=False,
            )
        else:
            self._refresh_case_payload(case_id, payload)
        return self.get_case(case_id)

    def update_case_workflow(self, case_id: str, updates: dict[str, Any], *, log_status_activity: bool = True) -> dict[str, Any]:
        payload = self._load_case_payload(case_id)
        if not payload:
            raise KeyError(case_id)

        actor = _clean(updates.get("updated_by")) or "reviewer"
        reason = _clean(updates.get("reason"))
        timestamp = utc_now_iso()
        status_before = _normalize_workflow_status(
            payload.get("status"),
            review_required=bool(
                payload.get("analysis", {}).get("review_required")
                or payload.get("policy_evaluation", {}).get("artifact_review_required")
                or payload.get("preview_only")
            ),
            has_review=bool(
                payload.get("review")
                and isinstance(payload.get("review", {}).get("reviews"), list)
                and payload["review"]["reviews"]
            ),
        )
        status_after = status_before

        with self._connect() as connection:
            if "assignee" in updates:
                previous = _clean(payload.get("assignee"))
                current = _clean(updates.get("assignee"))
                payload["assignee"] = current
                if current != previous:
                    self._append_activity(
                        case_id,
                        kind="assignment_changed",
                        title="Assignee updated",
                        copy=(f"Assigned to {current}." if current else "Assignee cleared.") + (f" {reason}" if reason else ""),
                        actor=actor,
                        created_at=timestamp,
                        metadata={"from": previous, "to": current},
                        connection=connection,
                    )
                    if "status" not in updates:
                        if current and status_before == "unassigned":
                            status_after = "assigned"
                        elif not current and status_before == "assigned":
                            status_after = "unassigned"

            if "due_at" in updates:
                previous_due = _safe_due_at(payload.get("due_at"))
                current_due = _safe_due_at(updates.get("due_at"))
                payload["due_at"] = current_due
                if current_due != previous_due:
                    self._append_activity(
                        case_id,
                        kind="due_date_changed",
                        title="Due date updated",
                        copy=(f"Due date set to {current_due}." if current_due else "Due date cleared.") + (f" {reason}" if reason else ""),
                        actor=actor,
                        created_at=timestamp,
                        metadata={"from": previous_due, "to": current_due},
                        connection=connection,
                    )

            if "priority_override" in updates:
                payload["priority_override"] = _clean(updates.get("priority_override"))

            if "status" in updates:
                status_after = _normalize_workflow_status(
                    updates.get("status"),
                    review_required=bool(
                        payload.get("analysis", {}).get("review_required")
                        or payload.get("policy_evaluation", {}).get("artifact_review_required")
                        or payload.get("preview_only")
                    ),
                    has_review=bool(
                        payload.get("review")
                        and isinstance(payload.get("review", {}).get("reviews"), list)
                        and payload["review"]["reviews"]
                    ),
                )

            if status_after != status_before and log_status_activity:
                self._append_activity(
                    case_id,
                    kind="status_changed",
                    title="Workflow status updated",
                    copy=f"Status changed from {status_before.replace('_', ' ')} to {status_after.replace('_', ' ')}." + (f" {reason}" if reason else ""),
                    actor=actor,
                    created_at=timestamp,
                    metadata={"from": status_before, "to": status_after},
                    connection=connection,
                )

            connection.commit()

        payload["status"] = status_after
        payload["updated_at"] = timestamp
        self._refresh_case_payload(case_id, payload)
        return self.get_case(case_id)

    def add_comment(self, case_id: str, author: str, body: str, *, created_at: str | None = None) -> dict[str, Any]:
        payload = self._load_case_payload(case_id)
        if not payload:
            raise KeyError(case_id)

        clean_author = _clean(author) or "reviewer"
        clean_body = _clean(body)
        if not clean_body:
            raise ValueError("Comment body is required")
        comment_time = _safe_datetime(created_at)

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO case_comments (case_id, author, body, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (case_id, clean_author, clean_body, comment_time),
            )
            self._append_activity(
                case_id,
                kind="comment_added",
                title="Comment added",
                copy=f"{clean_author} added a comment.",
                actor=clean_author,
                created_at=comment_time,
                metadata={"body": clean_body},
                connection=connection,
            )
            connection.commit()

        payload["updated_at"] = comment_time
        self._refresh_case_payload(case_id, payload)
        return self.get_case(case_id)

    def export_case_to_artifact(
        self,
        case_id: str,
        output_path: Path,
        *,
        signer_function: Any | None = None,
    ) -> CaseExportResultModel:
        case_payload = self.get_case(case_id)
        if not case_payload:
            raise KeyError(case_id)

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        manifest = ManifestModel(
            workflow_id=_uuid_from_case_id(case_id),
            cli_command=f"epi gateway export --case-id {case_id}",
            goal=_first_nonempty(case_payload.get("decision", {}).get("summary"), case_payload.get("analysis", {}).get("summary")),
            notes=_first_nonempty(case_payload.get("manifest", {}).get("notes"), case_payload.get("analysis", {}).get("why_it_matters")),
        )

        temp_dir = EPIContainer._make_temp_dir("epi_gateway_export_")
        try:
            steps = case_payload.get("steps") or []
            if steps:
                steps_path = temp_dir / "steps.jsonl"
                lines = [json.dumps(step, ensure_ascii=False) for step in steps]
                steps_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

            if case_payload.get("analysis") is not None:
                (temp_dir / "analysis.json").write_text(json.dumps(case_payload["analysis"], indent=2, ensure_ascii=False), encoding="utf-8")
            if case_payload.get("policy") is not None:
                (temp_dir / "policy.json").write_text(json.dumps(case_payload["policy"], indent=2, ensure_ascii=False), encoding="utf-8")
            if case_payload.get("policy_evaluation") is not None:
                (temp_dir / "policy_evaluation.json").write_text(
                    json.dumps(case_payload["policy_evaluation"], indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
            if case_payload.get("review") is not None:
                (temp_dir / "review.json").write_text(json.dumps(case_payload["review"], indent=2, ensure_ascii=False), encoding="utf-8")
            if case_payload.get("environment") is not None:
                (temp_dir / "environment.json").write_text(
                    json.dumps(case_payload["environment"], indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
            if case_payload.get("stdout"):
                (temp_dir / "stdout.log").write_text(str(case_payload["stdout"]), encoding="utf-8")
            if case_payload.get("stderr"):
                (temp_dir / "stderr.log").write_text(str(case_payload["stderr"]), encoding="utf-8")

            EPIContainer.pack(
                temp_dir,
                manifest,
                output_path,
                signer_function=signer_function,
                preserve_generated=True,
            )
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

        signed = bool(EPIContainer.read_manifest(output_path).signature)
        return CaseExportResultModel(
            case_id=case_id,
            output_path=str(output_path),
            filename=output_path.name,
            signed=signed,
        )
