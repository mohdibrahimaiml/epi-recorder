"""
Privacy-first opt-in telemetry helpers for EPI.

Telemetry is off by default. Importing this module must not create local state,
network traffic, or persistent identifiers.
"""

from __future__ import annotations

import json
import os
import platform
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from uuid import uuid4

from epi_core import __version__
from epi_core.time_utils import utc_now_iso

DEFAULT_TELEMETRY_URL = "https://api.epilabs.org/api/telemetry/events"
DEFAULT_PILOT_SIGNUP_URL = "https://api.epilabs.org/api/telemetry/pilot-signups"
TELEMETRY_SCHEMA_VERSION = "telemetry/v1"
PILOT_SIGNUP_SCHEMA_VERSION = "pilot-signup/v1"
TELEMETRY_QUEUE_MAX_FAILURES = 3

TELEMETRY_ALLOWED_METADATA_KEYS = frozenset(
    {
        "artifact_bytes",
        "artifact_count",
        "ci",
        "command",
        "error_type",
        "integration_type",
        "source",
        "source_command",
        "success",
        "target",
        "workflow_created",
    }
)
TELEMETRY_BANNED_FIELD_NAMES = frozenset(
    {
        "api_key",
        "artifact_content",
        "content",
        "customer_data",
        "file_path",
        "filename",
        "hostname",
        "input",
        "key",
        "message",
        "output",
        "path",
        "prompt",
        "repo",
        "repo_name",
        "repository",
        "secret",
        "token",
        "username",
    }
)
PILOT_USE_CASES = frozenset(
    {"debugging", "governance", "compliance", "agt integration", "ci/cd", "other"}
)
_EVENT_NAME_RE = re.compile(r"^[a-z][a-z0-9_.-]{1,80}$")


class TelemetryError(ValueError):
    """Raised when telemetry input is not safe to persist or send."""


def _truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def state_dir() -> Path:
    """Return the local EPI state directory without creating it."""

    override = os.getenv("EPI_HOME")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".epi"


def telemetry_config_path() -> Path:
    return state_dir() / "telemetry.json"


def pilot_signup_path() -> Path:
    return state_dir() / "pilot_signup.json"


def telemetry_queue_path() -> Path:
    return state_dir() / "telemetry_queue.jsonl"


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except Exception:
        return {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def load_config() -> dict[str, Any]:
    data = _read_json(telemetry_config_path())
    return data if isinstance(data, dict) else {}


def save_config(config: dict[str, Any]) -> None:
    _write_json(telemetry_config_path(), dict(config))


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, separators=(",", ":"), sort_keys=True) + "\n")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return []
    records: list[dict[str, Any]] = []
    for line in lines:
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict):
            records.append(record)
    return records


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    if not records:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    content = "\n".join(json.dumps(record, separators=(",", ":"), sort_keys=True) for record in records)
    path.write_text(content + "\n", encoding="utf-8")


def is_env_opted_in() -> bool:
    return _truthy(os.getenv("EPI_TELEMETRY_OPT_IN"))


def is_enabled() -> bool:
    if is_env_opted_in():
        return True
    return bool(load_config().get("enabled"))


def get_install_id(*, create: bool = False) -> str | None:
    config = load_config()
    install_id = config.get("install_id")
    if install_id:
        return str(install_id)
    if not create:
        return None
    install_id = str(uuid4())
    config["install_id"] = install_id
    save_config(config)
    return install_id


def enable() -> dict[str, Any]:
    config = load_config()
    config["enabled"] = True
    config["install_id"] = config.get("install_id") or str(uuid4())
    config["enabled_at"] = utc_now_iso()
    save_config(config)
    return config


def disable() -> dict[str, Any]:
    config = load_config()
    config["enabled"] = False
    config["disabled_at"] = utc_now_iso()
    save_config(config)
    return config


def status() -> dict[str, Any]:
    config = load_config()
    return {
        "enabled": is_enabled(),
        "enabled_by_env": is_env_opted_in(),
        "has_install_id": bool(config.get("install_id")),
        "install_id": config.get("install_id") if is_enabled() else None,
        "config_path": str(telemetry_config_path()),
        "telemetry_url": telemetry_url(),
        "queue_path": str(telemetry_queue_path()),
        "queued_events": len(_read_jsonl(telemetry_queue_path())),
        "pilot_signup_path": str(pilot_signup_path()),
        "pilot_signup_saved": pilot_signup_path().exists(),
    }


def telemetry_url() -> str:
    return os.getenv("EPI_TELEMETRY_URL") or DEFAULT_TELEMETRY_URL


def pilot_signup_url() -> str:
    return os.getenv("EPI_PILOT_SIGNUP_URL") or DEFAULT_PILOT_SIGNUP_URL


def detect_environment() -> str:
    if os.getenv("AWS_LAMBDA_FUNCTION_NAME"):
        return "aws_lambda"
    if os.getenv("GITHUB_ACTIONS"):
        return "github_actions"
    if os.getenv("CI"):
        return "ci"
    try:
        if Path("/.dockerenv").exists():
            return "docker"
    except Exception:
        pass
    return "local"


def _contains_banned_key(value: Any) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).lower() in TELEMETRY_BANNED_FIELD_NAMES:
                return True
            if _contains_banned_key(item):
                return True
    elif isinstance(value, list):
        return any(_contains_banned_key(item) for item in value)
    return False


def _safe_scalar(value: Any) -> Any:
    if isinstance(value, (bool, int, float)) or value is None:
        return value
    return str(value)[:200]


def sanitize_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    if not metadata:
        return {}
    if _contains_banned_key(metadata):
        raise TelemetryError("telemetry metadata contains a banned field name")
    clean: dict[str, Any] = {}
    for key, value in metadata.items():
        if key not in TELEMETRY_ALLOWED_METADATA_KEYS:
            continue
        clean[key] = _safe_scalar(value)
    return clean


def build_event(event_name: str, metadata: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Build a safe telemetry event, creating an install ID only after opt-in."""

    if not is_enabled():
        return None
    if not _EVENT_NAME_RE.match(event_name):
        raise TelemetryError(f"invalid telemetry event name: {event_name!r}")
    install_id = get_install_id(create=True)
    return {
        "schema_version": TELEMETRY_SCHEMA_VERSION,
        "install_id": install_id,
        "event_name": event_name,
        "timestamp": utc_now_iso(),
        "epi_version": __version__,
        "python_version": platform.python_version(),
        "os": platform.system() or "unknown",
        "environment": detect_environment(),
        "ci": bool(os.getenv("CI") or os.getenv("GITHUB_ACTIONS")),
        "metadata": sanitize_metadata(metadata),
    }


def validate_event_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize an inbound telemetry event for gateway storage."""

    if not isinstance(payload, dict):
        raise TelemetryError("telemetry payload must be an object")
    if _contains_banned_key(payload):
        raise TelemetryError("telemetry payload contains a banned field name")

    required = {"schema_version", "install_id", "event_name", "timestamp"}
    missing = sorted(required - set(payload))
    if missing:
        raise TelemetryError(f"telemetry payload missing required field(s): {', '.join(missing)}")
    if payload.get("schema_version") != TELEMETRY_SCHEMA_VERSION:
        raise TelemetryError("unsupported telemetry schema_version")
    event_name = str(payload.get("event_name") or "")
    if not _EVENT_NAME_RE.match(event_name):
        raise TelemetryError("invalid telemetry event_name")

    raw_metadata = payload.get("metadata") or {}
    clean_metadata = sanitize_metadata(raw_metadata if isinstance(raw_metadata, dict) else {})
    dropped = set(raw_metadata) - set(clean_metadata) if isinstance(raw_metadata, dict) else {"metadata"}
    if dropped:
        raise TelemetryError(f"unsupported telemetry metadata field(s): {', '.join(sorted(dropped))}")

    normalized = {
        "schema_version": TELEMETRY_SCHEMA_VERSION,
        "install_id": str(payload["install_id"]),
        "event_name": event_name,
        "timestamp": str(payload["timestamp"]),
        "epi_version": str(payload.get("epi_version") or ""),
        "python_version": str(payload.get("python_version") or ""),
        "os": str(payload.get("os") or ""),
        "environment": str(payload.get("environment") or ""),
        "ci": bool(payload.get("ci")),
        "metadata": clean_metadata,
        "received_at": utc_now_iso(),
    }
    return normalized


def send_json(url: str, payload: dict[str, Any], *, timeout: float = 2.0) -> bool:
    data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", "User-Agent": f"epi-recorder/{__version__}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return 200 <= getattr(response, "status", 200) < 300
    except (OSError, urllib.error.URLError, TimeoutError, Exception):
        return False


def queue_event(payload: dict[str, Any], *, failures: int = 0) -> None:
    """Queue one already-sanitized telemetry event for a later retry."""

    if not is_enabled():
        return
    try:
        normalized = validate_event_payload(payload)
    except TelemetryError:
        return
    _append_jsonl(
        telemetry_queue_path(),
        {
            "payload": normalized,
            "failures": int(failures),
            "queued_at": utc_now_iso(),
            "last_attempt_at": None,
        },
    )


def flush_queued_events(*, max_events: int = 20) -> dict[str, int]:
    """Retry queued telemetry events. Invalid or repeatedly failing records are dropped."""

    if not is_enabled():
        return {"sent": 0, "remaining": len(_read_jsonl(telemetry_queue_path())), "dropped": 0}

    records = _read_jsonl(telemetry_queue_path())
    if not records:
        return {"sent": 0, "remaining": 0, "dropped": 0}

    sent = 0
    dropped = 0
    processed = 0
    remaining: list[dict[str, Any]] = []
    for record in records:
        if processed >= max_events:
            remaining.append(record)
            continue
        processed += 1

        payload = record.get("payload")
        if not isinstance(payload, dict):
            dropped += 1
            continue
        try:
            normalized = validate_event_payload(payload)
        except TelemetryError:
            dropped += 1
            continue

        failures = int(record.get("failures") or 0)
        if failures >= TELEMETRY_QUEUE_MAX_FAILURES:
            dropped += 1
            continue

        if send_json(telemetry_url(), normalized):
            sent += 1
            continue

        failures += 1
        if failures >= TELEMETRY_QUEUE_MAX_FAILURES:
            dropped += 1
        else:
            remaining.append(
                {
                    "payload": normalized,
                    "failures": failures,
                    "queued_at": str(record.get("queued_at") or utc_now_iso()),
                    "last_attempt_at": utc_now_iso(),
                }
            )

    _write_jsonl(telemetry_queue_path(), remaining)
    return {"sent": sent, "remaining": len(remaining), "dropped": dropped}


def track_event(event_name: str, metadata: dict[str, Any] | None = None) -> bool:
    """Send one telemetry event if telemetry is enabled. Fail silently."""

    try:
        payload = build_event(event_name, metadata)
    except TelemetryError:
        return False
    if payload is None:
        return False
    flush_queued_events()
    if send_json(telemetry_url(), payload):
        return True
    queue_event(payload)
    return False


def build_pilot_signup(
    *,
    email: str,
    org: str = "",
    role: str = "",
    use_case: str = "other",
    consent_to_contact: bool,
    link_telemetry: bool = False,
) -> dict[str, Any]:
    email = str(email or "").strip()
    if "@" not in email or "." not in email.split("@")[-1]:
        raise TelemetryError("pilot signup needs a valid email")
    use_case_normalized = str(use_case or "other").strip().lower()
    if use_case_normalized not in PILOT_USE_CASES:
        raise TelemetryError(f"pilot signup use_case must be one of: {', '.join(sorted(PILOT_USE_CASES))}")
    if not consent_to_contact:
        raise TelemetryError("pilot signup requires consent to contact")
    return {
        "schema_version": PILOT_SIGNUP_SCHEMA_VERSION,
        "email": email,
        "org": str(org or "").strip()[:200],
        "role": str(role or "").strip()[:200],
        "use_case": use_case_normalized,
        "consent_to_contact": True,
        "link_telemetry": bool(link_telemetry),
        "install_id": get_install_id(create=bool(link_telemetry)) if link_telemetry else None,
        "created_at": utc_now_iso(),
    }


def validate_pilot_signup_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise TelemetryError("pilot signup payload must be an object")
    if _contains_banned_key(payload):
        raise TelemetryError("pilot signup payload contains a banned field name")
    if payload.get("schema_version") != PILOT_SIGNUP_SCHEMA_VERSION:
        raise TelemetryError("unsupported pilot signup schema_version")
    email = str(payload.get("email") or "").strip()
    if "@" not in email or "." not in email.split("@")[-1]:
        raise TelemetryError("pilot signup needs a valid email")
    use_case = str(payload.get("use_case") or "other").strip().lower()
    if use_case not in PILOT_USE_CASES:
        raise TelemetryError(f"pilot signup use_case must be one of: {', '.join(sorted(PILOT_USE_CASES))}")
    if not bool(payload.get("consent_to_contact")):
        raise TelemetryError("pilot signup requires consent to contact")
    link_telemetry = bool(payload.get("link_telemetry"))
    normalized = {
        "schema_version": PILOT_SIGNUP_SCHEMA_VERSION,
        "email": email,
        "org": str(payload.get("org") or "").strip()[:200],
        "role": str(payload.get("role") or "").strip()[:200],
        "use_case": use_case,
        "consent_to_contact": True,
        "link_telemetry": link_telemetry,
        "install_id": str(payload.get("install_id") or "") if link_telemetry else None,
        "created_at": str(payload.get("created_at") or utc_now_iso()),
    }
    normalized["received_at"] = utc_now_iso()
    return normalized


def save_pilot_signup(signup: dict[str, Any]) -> None:
    _write_json(pilot_signup_path(), signup)


def submit_pilot_signup(signup: dict[str, Any]) -> bool:
    """Persist locally and submit to the pilot endpoint. Submission may fail silently."""

    save_pilot_signup(signup)
    return send_json(pilot_signup_url(), signup)
