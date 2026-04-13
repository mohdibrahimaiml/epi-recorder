"""
Shared connector record loading used by runtime-safe modules and CLI flows.
"""

from __future__ import annotations

import base64
import csv
import json
from pathlib import Path
from typing import Any
from urllib import error as urlerror
from urllib import request as urlrequest


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on", "sample", "mock"}


def _required(mapping: dict[str, Any], *keys: str) -> list[str]:
    missing = [key for key in keys if not _clean(mapping.get(key))]
    if missing:
        raise ValueError(f"Missing required connector field(s): {', '.join(missing)}")
    return [_clean(mapping.get(key)) for key in keys]


def _http_json(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    basic_auth: tuple[str, str] | None = None,
    timeout: float = 30.0,
) -> dict[str, Any]:
    final_headers = {"Accept": "application/json"}
    if headers:
        final_headers.update(headers)

    if basic_auth is not None:
        username, password = basic_auth
        token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
        final_headers["Authorization"] = f"Basic {token}"

    request = urlrequest.Request(url, headers=final_headers, method="GET")
    try:
        with urlrequest.urlopen(request, timeout=timeout) as response:
            payload = response.read().decode("utf-8")
    except urlerror.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{exc.code} {exc.reason}: {detail}") from exc
    except urlerror.URLError as exc:
        raise RuntimeError(f"Could not reach {url}: {exc.reason}") from exc

    try:
        return json.loads(payload)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Received non-JSON response from {url}") from exc


def _mock_zendesk_record(case_input: dict[str, Any]) -> dict[str, Any]:
    ticket_id = _clean(case_input.get("ticket_id") or case_input.get("case_id") or "12345")
    return {
        "status": "loaded",
        "ticket_id": ticket_id,
        "subject": "High-value refund request needs approval",
        "priority": "high",
        "raw_status": "open",
        "source_system": "Zendesk",
        "decision_state": "pending_review",
    }


def _mock_salesforce_record(case_input: dict[str, Any]) -> dict[str, Any]:
    record_id = _clean(case_input.get("record_id") or case_input.get("case_id") or "500000000000001")
    return {
        "status": "loaded",
        "record_id": record_id,
        "object_name": _clean(case_input.get("object_name") or "Case"),
        "subject": "Policy exception requires approval",
        "priority": "High",
        "owner_id": "005000000000001",
        "source_system": "Salesforce",
        "decision_state": "pending_review",
    }


def _mock_servicenow_record(case_input: dict[str, Any]) -> dict[str, Any]:
    sys_id = _clean(case_input.get("sys_id") or case_input.get("case_id") or "46d44b40db7f2010a8d75f48dc9619f4")
    return {
        "status": "loaded",
        "sys_id": sys_id,
        "table": _clean(case_input.get("table") or "incident"),
        "number": "INC0012456",
        "short_description": "Access request requires manual verification",
        "assignment_group": "Security operations",
        "source_system": "ServiceNow",
        "decision_state": "pending_review",
    }


def _mock_internal_app_record(case_input: dict[str, Any]) -> dict[str, Any]:
    record_id = _clean(case_input.get("record_id") or case_input.get("case_id") or "approval-123")
    return {
        "status": "loaded",
        "record_id": record_id,
        "decision_state": "awaiting_human_review",
        "summary": "Internal approval request exceeds the automatic threshold",
        "source_system": "Internal app",
    }


def _mock_csv_export_record(case_input: dict[str, Any]) -> dict[str, Any]:
    case_id = _clean(case_input.get("case_id") or "refund-001")
    return {
        "status": "loaded",
        "case_id": case_id,
        "summary": "Imported CSV row needs review before it moves forward",
        "decision_state": "pending_review",
        "source_system": "CSV export",
    }


def build_mock_record(system: str, case_input: dict[str, Any], *, reason: str | None = None, mode: str = "mock") -> dict[str, Any]:
    system_name = _clean(system).lower()
    builders = {
        "zendesk": _mock_zendesk_record,
        "salesforce": _mock_salesforce_record,
        "servicenow": _mock_servicenow_record,
        "internal-app": _mock_internal_app_record,
        "csv-export": _mock_csv_export_record,
    }
    if system_name not in builders:
        raise ValueError(f"Unsupported connector system: {system}")

    record = builders[system_name](case_input or {})
    record["bridge_mode"] = mode
    record["is_mock"] = True
    if reason:
        record["bridge_warning"] = reason
    return record


def _fetch_zendesk(connector_profile: dict[str, Any], case_input: dict[str, Any]) -> dict[str, Any]:
    subdomain, email, api_token = _required(connector_profile, "subdomain", "email", "api_token")
    ticket_id = _clean(case_input.get("ticket_id") or case_input.get("case_id"))
    if not ticket_id:
        raise ValueError("sample_input.json must include ticket_id or case_id for Zendesk")

    payload = _http_json(
        f"https://{subdomain}.zendesk.com/api/v2/tickets/{ticket_id}.json",
        basic_auth=(f"{email}/token", api_token),
    )
    ticket = payload.get("ticket") or {}
    return {
        "status": "loaded",
        "ticket_id": ticket.get("id"),
        "subject": ticket.get("subject"),
        "priority": ticket.get("priority"),
        "raw_status": ticket.get("status"),
        "source_system": "Zendesk",
    }


def _fetch_salesforce(connector_profile: dict[str, Any], case_input: dict[str, Any]) -> dict[str, Any]:
    instance_url, access_token = _required(connector_profile, "instance_url", "access_token")
    api_version = _clean(connector_profile.get("api_version") or "v61.0")
    record_id = _clean(case_input.get("record_id") or case_input.get("case_id"))
    object_name = _clean(case_input.get("object_name") or "Case")
    if not record_id:
        raise ValueError("sample_input.json must include record_id or case_id for Salesforce")

    payload = _http_json(
        f"{instance_url.rstrip('/')}/services/data/{api_version}/sobjects/{object_name}/{record_id}",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    return {
        "status": "loaded",
        "record_id": payload.get("Id"),
        "object_name": object_name,
        "subject": payload.get("Subject") or payload.get("Name"),
        "priority": payload.get("Priority"),
        "owner_id": payload.get("OwnerId"),
        "source_system": "Salesforce",
    }


def _fetch_servicenow(connector_profile: dict[str, Any], case_input: dict[str, Any]) -> dict[str, Any]:
    instance_url, username, password = _required(connector_profile, "instance_url", "username", "password")
    table = _clean(case_input.get("table") or "incident")
    sys_id = _clean(case_input.get("sys_id") or case_input.get("case_id"))
    if not sys_id:
        raise ValueError("sample_input.json must include sys_id or case_id for ServiceNow")

    payload = _http_json(
        f"{instance_url.rstrip('/')}/api/now/table/{table}/{sys_id}",
        basic_auth=(username, password),
    )
    record = payload.get("result") or {}
    return {
        "status": "loaded",
        "sys_id": record.get("sys_id"),
        "table": table,
        "number": record.get("number"),
        "short_description": record.get("short_description"),
        "assignment_group": record.get("assignment_group"),
        "source_system": "ServiceNow",
    }


def _fetch_internal_app(connector_profile: dict[str, Any], case_input: dict[str, Any]) -> dict[str, Any]:
    (base_url,) = _required(connector_profile, "base_url")
    bearer_token = _clean(connector_profile.get("bearer_token"))
    api_path = _clean(case_input.get("api_path") or connector_profile.get("api_path") or "/api/v1/records")
    record_id = _clean(case_input.get("record_id") or case_input.get("case_id"))
    if not record_id:
        raise ValueError("sample_input.json must include record_id or case_id for the internal app connector")

    headers = {}
    if bearer_token:
        headers["Authorization"] = f"Bearer {bearer_token}"

    payload = _http_json(
        f"{base_url.rstrip('/')}{api_path.rstrip('/')}/{record_id}",
        headers=headers,
    )
    return {
        "status": "loaded",
        "record_id": payload.get("id") or payload.get("record_id"),
        "decision_state": payload.get("status") or payload.get("decision_state"),
        "summary": payload.get("summary") or payload.get("title"),
        "source_system": "Internal app",
    }


def _fetch_csv_export(connector_profile: dict[str, Any], case_input: dict[str, Any]) -> dict[str, Any]:
    csv_path = Path(_clean(case_input.get("csv_path") or connector_profile.get("csv_path") or "source_export.csv"))
    id_column = _clean(case_input.get("id_column") or connector_profile.get("id_column") or "case_id")
    case_id = _clean(case_input.get("case_id"))
    if not case_id:
        raise ValueError("sample_input.json must include case_id for CSV imports")
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            if _clean(row.get(id_column)) == case_id:
                return {
                    "status": "loaded",
                    "case_id": row.get("case_id") or row.get("id"),
                    "summary": row.get("summary") or row.get("title"),
                    "decision_state": row.get("status") or row.get("decision_state"),
                    "source_system": "CSV export",
                }

    raise ValueError(f"No row found for {case_id!r} using column {id_column!r}")


def fetch_live_record(system: str, connector_profile: dict[str, Any], case_input: dict[str, Any]) -> dict[str, Any]:
    system_name = _clean(system).lower()
    handlers = {
        "zendesk": _fetch_zendesk,
        "salesforce": _fetch_salesforce,
        "servicenow": _fetch_servicenow,
        "internal-app": _fetch_internal_app,
        "csv-export": _fetch_csv_export,
    }
    if system_name not in handlers:
        raise ValueError(f"Unsupported connector system: {system}")

    connector_profile = connector_profile or {}
    case_input = case_input or {}
    requested_preview_mode = _clean(case_input.get("preview_mode") or connector_profile.get("preview_mode")).lower()
    allow_mock_fallback = _truthy(case_input.get("allow_mock_fallback") or connector_profile.get("allow_mock_fallback"))

    if requested_preview_mode in {"mock", "sample", "safe-sample"}:
        record = build_mock_record(system_name, case_input, mode="mock")
    else:
        try:
            record = handlers[system_name](connector_profile, case_input)
            record["bridge_mode"] = "live"
            record["is_mock"] = False
        except (ValueError, FileNotFoundError, RuntimeError) as exc:
            if not allow_mock_fallback:
                raise
            record = build_mock_record(system_name, case_input, reason=str(exc), mode="mock-fallback")

    record["bridge_system"] = system_name
    return record


__all__ = ["build_mock_record", "fetch_live_record"]
