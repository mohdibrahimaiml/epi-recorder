import collections
import logging
import json
import os
import shutil
import threading
import time
from contextlib import asynccontextmanager
from hashlib import sha256
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator
from starlette.background import BackgroundTask

from epi_cli.connect import fetch_live_record
from epi_cli.keys import KeyManager
from epi_core import __version__
from epi_core.auth_local import load_auth_users, normalize_role
from epi_core.capture import CAPTURE_SPEC_VERSION, CaptureEventModel
from epi_core.container import EPIContainer
from epi_core.llm_capture import LLMCaptureRequest, build_llm_capture_events
from epi_core.time_utils import utc_now_iso
from epi_core.trust import sign_manifest

from .proxy import (
    ProxyRelayError,
    build_anthropic_proxy_capture_request,
    build_openai_proxy_capture_request,
    relay_anthropic_messages,
    relay_openai_chat_completions,
)
from .worker import EvidenceWorker

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("epi-gateway")

RETENTION_MODES = {"redacted_hashes", "full_content"}
PROXY_FAILURE_MODES = {"fail-open", "fail-closed"}
CONTENT_REDACTION_KEYS = {
    "content",
    "contents",
    "error",
    "errors",
    "input",
    "instructions",
    "message",
    "messages",
    "output_text",
    "prompt",
    "summary",
    "system",
    "system_instruction",
    "text",
}
SAFE_STRING_KEYS = {
    "actor_id",
    "case_id",
    "decision_id",
    "finish_reason",
    "id",
    "kind",
    "model",
    "name",
    "provider",
    "provider_adapter",
    "provider_profile",
    "role",
    "source_app",
    "status",
    "stop_reason",
    "tool_choice",
    "trace_id",
    "type",
    "workflow_id",
    "workflow_name",
}


class GatewayRuntimeSettings(BaseModel):
    storage_dir: str = "./evidence_vault"
    batch_size: int = 50
    batch_timeout: float = 2.0
    retention_mode: str = "redacted_hashes"
    proxy_failure_mode: str = "fail-open"
    access_token: str | None = None
    users_file: str | None = None
    webhook_url: str | None = None
    session_ttl_hours: float = 12.0
    capture_scope: str = "consequential"
    allowed_origins: list[str] = Field(default_factory=lambda: ["*"])
    capture_rate_limit: int = 1000  # max capture requests per minute per IP (0 = disabled)
    max_request_body_bytes: int = 10 * 1024 * 1024  # 10 MB

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def _validate(self) -> "GatewayRuntimeSettings":
        if self.batch_size < 1:
            raise ValueError("EPI_GATEWAY_BATCH_SIZE must be at least 1")
        if self.batch_timeout < 0.1:
            raise ValueError("EPI_GATEWAY_BATCH_TIMEOUT must be at least 0.1 seconds")
        if self.retention_mode not in RETENTION_MODES:
            allowed = ", ".join(sorted(RETENTION_MODES))
            raise ValueError(f"EPI_GATEWAY_RETENTION_MODE must be one of: {allowed}")
        if self.proxy_failure_mode not in PROXY_FAILURE_MODES:
            allowed = ", ".join(sorted(PROXY_FAILURE_MODES))
            raise ValueError(f"EPI_GATEWAY_PROXY_FAILURE_MODE must be one of: {allowed}")
        if self.capture_scope != "consequential":
            raise ValueError("EPI_GATEWAY_CAPTURE_SCOPE currently supports only 'consequential'")
        if self.session_ttl_hours <= 0:
            raise ValueError("EPI_GATEWAY_SESSION_TTL_HOURS must be greater than 0")
        if self.capture_rate_limit < 0:
            raise ValueError("EPI_GATEWAY_CAPTURE_RATE_LIMIT must be >= 0 (0 = disabled)")
        if self.max_request_body_bytes < 1024:
            raise ValueError("EPI_GATEWAY_MAX_REQUEST_BODY_BYTES must be at least 1024")
        self.access_token = _clean(self.access_token)
        self.users_file = _clean(self.users_file)
        self.webhook_url = _clean(self.webhook_url)
        self.allowed_origins = [origin for origin in self.allowed_origins if _clean(origin)] or ["*"]
        return self

    @property
    def auth_required(self) -> bool:
        return bool(self.access_token or self.users_file)

    @property
    def local_user_auth_enabled(self) -> bool:
        return bool(self.users_file)

    @property
    def auth_mode(self) -> str:
        if self.access_token and self.users_file:
            return "token+local-users"
        if self.users_file:
            return "local-users"
        if self.access_token:
            return "access-token"
        return "disabled"


class CaptureBatchRequest(BaseModel):
    items: list[CaptureEventModel] = Field(default_factory=list)


class WorkspaceCaseRequest(BaseModel):
    case: dict[str, Any] = Field(default_factory=dict)


class FetchRecordRequest(BaseModel):
    system: str
    connector_profile: dict[str, Any] = Field(default_factory=dict)
    case_input: dict[str, Any] = Field(default_factory=dict)


class CaseWorkflowPatchRequest(BaseModel):
    status: str | None = None
    assignee: str | None = None
    due_at: str | None = None
    priority_override: str | None = None
    updated_by: str | None = None
    reason: str | None = None


class CaseCommentRequest(BaseModel):
    author: str
    body: str
    created_at: str | None = None


class AuthLoginRequest(BaseModel):
    username: str
    password: str


def _split_csv_env(raw: str | None) -> list[str]:
    text = str(raw or "").strip()
    if not text:
        return ["*"]
    parts = [item.strip() for item in text.split(",")]
    return [item for item in parts if item] or ["*"]


def _clean(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _first_nonempty(*values: Any) -> str | None:
    for value in values:
        text = _clean(value)
        if text:
            return text
    return None


def _safe_filename(value: str) -> str:
    text = "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "-" for ch in str(value or "case"))
    text = "-".join(part for part in text.split("-") if part)
    return text or "case"


def _build_settings_from_env() -> GatewayRuntimeSettings:
    return GatewayRuntimeSettings(
        storage_dir=os.getenv("EPI_GATEWAY_STORAGE_DIR", "./evidence_vault"),
        batch_size=int(os.getenv("EPI_GATEWAY_BATCH_SIZE", "50")),
        batch_timeout=float(os.getenv("EPI_GATEWAY_BATCH_TIMEOUT", "2.0")),
        retention_mode=os.getenv("EPI_GATEWAY_RETENTION_MODE", "redacted_hashes"),
        proxy_failure_mode=os.getenv("EPI_GATEWAY_PROXY_FAILURE_MODE", "fail-open"),
        access_token=os.getenv("EPI_GATEWAY_ACCESS_TOKEN"),
        users_file=os.getenv("EPI_GATEWAY_USERS_FILE"),
        webhook_url=os.getenv("EPI_GATEWAY_WEBHOOK_URL"),
        session_ttl_hours=float(os.getenv("EPI_GATEWAY_SESSION_TTL_HOURS", "12")),
        capture_scope=os.getenv("EPI_GATEWAY_CAPTURE_SCOPE", "consequential"),
        allowed_origins=_split_csv_env(os.getenv("EPI_GATEWAY_ALLOWED_ORIGINS")),
        capture_rate_limit=int(os.getenv("EPI_GATEWAY_CAPTURE_RATE_LIMIT", "1000")),
        max_request_body_bytes=int(os.getenv("EPI_GATEWAY_MAX_REQUEST_BODY_BYTES", str(10 * 1024 * 1024))),
    )


def _fire_webhook(webhook_url: str, payload: dict) -> None:
    """HTTP POST to webhook with up to 3 retries (1 s / 2 s / 4 s backoff).
    Failures are logged, never raised — always runs in a background thread."""
    import urllib.request
    import json as _json

    data = _json.dumps(payload).encode()
    delays = [0, 1, 2, 4]
    for attempt, delay in enumerate(delays):
        if delay:
            time.sleep(delay)
        try:
            req = urllib.request.Request(
                webhook_url,
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            urllib.request.urlopen(req, timeout=10)
            return  # success
        except Exception as exc:
            if attempt < len(delays) - 1:
                logger.warning("Webhook delivery attempt %d failed: %s — retrying", attempt + 1, exc)
            else:
                logger.warning("Webhook delivery failed after %d attempts: %s", len(delays), exc)


class _SlidingWindowRateLimiter:
    """Thread-safe per-key sliding window rate limiter (stdlib only)."""

    def __init__(self, max_requests: int, window_seconds: float = 60.0) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._windows: dict[str, collections.deque] = {}
        self._lock = threading.Lock()

    def is_allowed(self, key: str) -> bool:
        """Return True if the request is within the rate limit."""
        now = time.monotonic()
        cutoff = now - self.window_seconds
        with self._lock:
            if key not in self._windows:
                self._windows[key] = collections.deque()
            dq = self._windows[key]
            while dq and dq[0] <= cutoff:
                dq.popleft()
            if len(dq) >= self.max_requests:
                return False
            dq.append(now)
            return True

    def reset(self, key: str) -> None:
        with self._lock:
            self._windows.pop(key, None)


class _LoginThrottle:
    """Track failed login attempts per username and lock out repeat offenders."""

    MAX_FAILURES = 5
    LOCKOUT_SECONDS = 15 * 60  # 15 minutes

    def __init__(self) -> None:
        self._failures: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def record_failure(self, username: str) -> None:
        now = time.monotonic()
        with self._lock:
            if username not in self._failures:
                self._failures[username] = []
            self._failures[username].append(now)

    def is_locked_out(self, username: str) -> bool:
        now = time.monotonic()
        cutoff = now - self.LOCKOUT_SECONDS
        with self._lock:
            attempts = self._failures.get(username, [])
            recent = [t for t in attempts if t >= cutoff]
            self._failures[username] = recent
            return len(recent) >= self.MAX_FAILURES

    def record_success(self, username: str) -> None:
        with self._lock:
            self._failures.pop(username, None)


class _MetricsCounters:
    """Thread-safe in-process counters for Prometheus metrics export."""

    def __init__(self) -> None:
        self._data: dict[str, int] = {}
        self._lock = threading.Lock()

    def inc(self, key: str, amount: int = 1) -> None:
        with self._lock:
            self._data[key] = self._data.get(key, 0) + amount

    def get(self, key: str) -> int:
        with self._lock:
            return self._data.get(key, 0)


# Module-level singletons — shared across all app instances in a process.
_login_throttle = _LoginThrottle()
_gateway_metrics = _MetricsCounters()


def _build_worker_from_env(settings: GatewayRuntimeSettings | None = None) -> EvidenceWorker:
    runtime_settings = settings or _build_settings_from_env()
    return EvidenceWorker(
        storage_dir=runtime_settings.storage_dir,
        batch_size=runtime_settings.batch_size,
        batch_timeout=runtime_settings.batch_timeout,
    )


def _build_gateway_signer(settings: GatewayRuntimeSettings):
    if _truthy(os.getenv("EPI_GATEWAY_DISABLE_SIGNING")):
        return None

    key_name = os.getenv("EPI_GATEWAY_SIGNING_KEY_NAME", "default")
    keys_dir = _clean(os.getenv("EPI_GATEWAY_KEYS_DIR"))
    try:
        manager = KeyManager(Path(keys_dir) if keys_dir else None)
        if not manager.has_key(key_name):
            return None
        private_key = manager.load_private_key(key_name)
    except Exception as exc:  # pragma: no cover - depends on local key setup
        logger.warning("Gateway signing disabled: %s", exc)
        return None

    def _signer(manifest):
        return sign_manifest(manifest, private_key, key_name)

    return _signer


def _get_worker(app: FastAPI) -> EvidenceWorker:
    return app.state.worker


def _extract_bearer_token(header_value: str | None) -> str | None:
    text = str(header_value or "").strip()
    if not text:
        return None
    if text.lower().startswith("bearer "):
        return _clean(text[7:])
    return None


def _load_gateway_users(settings: GatewayRuntimeSettings) -> list[dict[str, str]]:
    if not settings.users_file:
        return []
    return load_auth_users(settings.users_file)


def _build_auth_principal(request: Request, settings: GatewayRuntimeSettings, worker: EvidenceWorker) -> dict[str, Any] | None:
    token = _extract_bearer_token(request.headers.get("authorization"))
    if not token:
        return None

    if settings.access_token and token == settings.access_token:
        return {
            "username": "gateway-admin",
            "display_name": "Gateway admin",
            "role": "admin",
            "auth_mode": "access-token",
        }

    if settings.local_user_auth_enabled:
        session = worker.get_auth_session(token)
        if session:
            return {
                "username": session.username,
                "display_name": session.display_name,
                "role": session.role,
                "auth_mode": session.auth_mode,
                "expires_at": session.expires_at,
            }
    return None


def _require_roles(request: Request, *roles: str) -> dict[str, Any]:
    principal = getattr(request.state, "auth", None)
    if not principal:
        raise HTTPException(status_code=401, detail="Unauthorized")
    normalized = {normalize_role(role) for role in roles}
    if principal.get("role") not in normalized:
        raise HTTPException(status_code=403, detail="Forbidden")
    return principal


def _should_redact_key(key: str | None) -> bool:
    text = str(key or "").strip().lower()
    if not text:
        return False
    if text in SAFE_STRING_KEYS:
        return False
    if text in CONTENT_REDACTION_KEYS:
        return True
    return any(hint in text for hint in ("secret", "token", "password", "prompt", "content", "message", "text"))


def _hash_payload(value: Any) -> str:
    if isinstance(value, str):
        raw = value
    else:
        raw = json.dumps(value, sort_keys=True, ensure_ascii=False)
    return sha256(raw.encode("utf-8")).hexdigest()


def _redacted_marker(value: str) -> str:
    digest = sha256(value.encode("utf-8")).hexdigest()[:12]
    return f"[redacted sha256={digest} len={len(value)}]"


def _sanitize_retained_value(value: Any, *, key: str | None = None) -> Any:
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for item_key, item_value in value.items():
            sanitized[item_key] = _sanitize_retained_value(item_value, key=item_key)
        return sanitized
    if isinstance(value, list):
        return [_sanitize_retained_value(item, key=key) for item in value]
    if isinstance(value, str):
        if _should_redact_key(key):
            return _redacted_marker(value)
        return value
    return value


def _apply_retention_mode(request: LLMCaptureRequest, retention_mode: str) -> LLMCaptureRequest:
    payload = request.model_copy(deep=True)
    meta = dict(payload.meta or {})
    meta["retention_mode"] = retention_mode
    meta["capture_scope"] = "consequential"
    if retention_mode == "full_content":
        payload.meta = meta
        return payload

    if payload.request:
        meta["request_sha256"] = _hash_payload(payload.request)
        payload.request = _sanitize_retained_value(payload.request)
    if payload.response:
        meta["response_sha256"] = _hash_payload(payload.response)
        payload.response = _sanitize_retained_value(payload.response)
    if payload.error:
        meta["error_sha256"] = _hash_payload(payload.error)
        payload.error = _sanitize_retained_value(payload.error)
    payload.meta = meta
    return payload


def _resolve_failure_mode(headers: dict[str, Any], settings: GatewayRuntimeSettings) -> str:
    override = _clean((headers or {}).get("x-epi-failure-mode"))
    if override in PROXY_FAILURE_MODES:
        return override
    return settings.proxy_failure_mode


def _capture_context(events: list[CaptureEventModel], request: LLMCaptureRequest) -> dict[str, Any]:
    meta = request.meta or {}
    event = events[0] if events else None
    return {
        "provider": request.provider,
        "trace_id": _first_nonempty(meta.get("trace_id"), event.trace_id if event else None),
        "decision_id": _first_nonempty(meta.get("decision_id"), event.decision_id if event else None),
        "case_id": _first_nonempty(meta.get("case_id"), event.case_id if event else None),
    }


def _log_capture_result(route_name: str, request: LLMCaptureRequest, events: list[CaptureEventModel], retention_mode: str) -> None:
    context = _capture_context(events, request)
    logger.info(
        "%s captured %s event(s) provider=%s trace_id=%s decision_id=%s case_id=%s retention=%s",
        route_name,
        len(events),
        context["provider"],
        context["trace_id"],
        context["decision_id"],
        context["case_id"],
        retention_mode,
    )


def _enqueue_llm_capture(
    worker: EvidenceWorker,
    request: LLMCaptureRequest,
    *,
    settings: GatewayRuntimeSettings,
    route_name: str,
) -> list[CaptureEventModel]:
    retained = _apply_retention_mode(request, settings.retention_mode)
    events = build_llm_capture_events(retained)
    for item in events:
        worker.enqueue(item)
    _log_capture_result(route_name, retained, events, settings.retention_mode)
    return events


def _build_proxy_response(result: Any, *, capture_status: str, settings: GatewayRuntimeSettings) -> JSONResponse:
    response = JSONResponse(status_code=result.status_code, content=result.body, headers=result.headers)
    response.headers["X-EPI-Capture-Status"] = capture_status
    response.headers["X-EPI-Retention-Mode"] = settings.retention_mode
    return response


def _capture_failure_response(message: str, *, settings: GatewayRuntimeSettings) -> JSONResponse:
    return JSONResponse(
        status_code=502,
        content={"detail": message},
        headers={
            "X-EPI-Capture-Status": "failed-closed",
            "X-EPI-Retention-Mode": settings.retention_mode,
        },
    )


def _build_preview_capture_event(
    system: str,
    record: dict[str, Any],
    *,
    connector_profile: dict[str, Any],
    case_input: dict[str, Any],
) -> CaptureEventModel:
    system_name = _clean(system) or "connector"
    record_id = _first_nonempty(
        case_input.get("case_id"),
        record.get("case_id"),
        record.get("record_id"),
        record.get("ticket_id"),
        record.get("sys_id"),
    )
    workflow_name = _first_nonempty(
        case_input.get("workflow_name"),
        case_input.get("workflow"),
        connector_profile.get("workflow_name"),
        f"{system_name.title()} preview",
    )
    bridge_mode = _clean(record.get("bridge_mode")) or "live"
    is_mock = bool(record.get("is_mock"))
    capture_mode = "manual" if is_mock else "imported"
    trust_class = "partial" if is_mock else "verified_imported"
    summary = _first_nonempty(
        record.get("summary"),
        record.get("subject"),
        record.get("short_description"),
        record.get("decision_state"),
        "Source record loaded for review.",
    )

    content = dict(record)
    content["preview_only"] = True
    content["connector_system"] = system_name
    content["summary"] = summary

    return CaptureEventModel.model_validate(
        {
            "kind": "source.record.loaded",
            "content": content,
            "trace_id": _first_nonempty(case_input.get("trace_id"), f"preview::{system_name}::{record_id or 'case'}"),
            "decision_id": _first_nonempty(case_input.get("decision_id"), f"preview::{system_name}::{record_id or 'case'}"),
            "case_id": _first_nonempty(case_input.get("case_id"), record_id),
            "workflow_name": workflow_name,
            "source_app": _first_nonempty(case_input.get("source_app"), system_name),
            "meta": {
                "preview_only": True,
                "bridge_mode": bridge_mode,
                "record_id": record_id,
                "connector_profile_summary": {
                    key: value
                    for key, value in (connector_profile or {}).items()
                    if key not in {"api_token", "access_token", "password", "bearer_token"}
                },
            },
            "provenance": {
                "source": "connector_preview",
                "capture_mode": capture_mode,
                "trust_class": trust_class,
                "notes": _clean(record.get("bridge_warning")),
            },
        }
    )


def create_app(
    worker: EvidenceWorker | None = None,
    settings: GatewayRuntimeSettings | None = None,
) -> FastAPI:
    runtime_settings = settings or _build_settings_from_env()
    runtime_worker = worker or _build_worker_from_env(runtime_settings)

    _capture_limiter: _SlidingWindowRateLimiter | None = (
        _SlidingWindowRateLimiter(runtime_settings.capture_rate_limit)
        if runtime_settings.capture_rate_limit > 0
        else None
    )
    _CAPTURE_PATHS = {"/capture", "/capture/batch", "/capture/llm", "/v1/chat/completions", "/v1/messages"}

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        logger.info("EPI Gateway starting")
        app.state.worker = runtime_worker
        app.state.settings = runtime_settings
        runtime_worker.start()
        if runtime_settings.local_user_auth_enabled:
            loaded_users = _load_gateway_users(runtime_settings)
            runtime_worker.sync_auth_users(loaded_users, source="users_file")
        yield
        logger.info("EPI Gateway stopping")
        runtime_worker.stop()

    app = FastAPI(
        title="EPI Gateway",
        description="Shared EPI capture backend with live cases and portable proof export.",
        version="1.0.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=runtime_settings.allowed_origins,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-EPI-Capture-Status", "X-EPI-Retention-Mode", "X-EPI-Auth-Required"],
    )

    @app.middleware("http")
    async def apply_runtime_guards(request: Request, call_next):
        # ── Request body size guard ───────────────────────────────────────────
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > runtime_settings.max_request_body_bytes:
            return JSONResponse(
                status_code=413,
                content={"ok": False, "error": "Request body too large"},
            )

        # ── Capture-endpoint rate limiting ────────────────────────────────────
        if _capture_limiter is not None and request.url.path in _CAPTURE_PATHS:
            client_ip = (request.client.host if request.client else None) or "unknown"
            if not _capture_limiter.is_allowed(client_ip):
                return JSONResponse(
                    status_code=429,
                    content={"ok": False, "error": "Rate limit exceeded — too many capture requests"},
                    headers={"Retry-After": "60"},
                )

        # ── Auth guard ────────────────────────────────────────────────────────
        if runtime_settings.auth_required:
            request.state.auth = None
        else:
            request.state.auth = {
                "username": "local-operator",
                "display_name": "Local operator",
                "role": "admin",
                "auth_mode": "disabled",
            }
        if runtime_settings.auth_required and request.method != "OPTIONS" and request.url.path.startswith("/api"):
            auth_exempt_paths = {"/api/auth/login"}
            if request.url.path not in auth_exempt_paths:
                principal = _build_auth_principal(request, runtime_settings, runtime_worker)
                if not principal:
                    return JSONResponse(status_code=401, content={"ok": False, "error": "Unauthorized"})
                request.state.auth = principal
        response = await call_next(request)
        response.headers.setdefault("X-EPI-Auth-Required", "true" if runtime_settings.auth_required else "false")
        response.headers.setdefault("X-EPI-Auth-Mode", runtime_settings.auth_mode)
        response.headers.setdefault("X-EPI-Retention-Mode", runtime_settings.retention_mode)
        if request.url.path in _CAPTURE_PATHS:
            _gateway_metrics.inc("capture_requests")
            if response.status_code >= 400:
                _gateway_metrics.inc("capture_errors")
        return response

    @app.get("/health")
    async def health_check():
        snapshot = runtime_worker.snapshot()
        return {
            "ok": True,
            "status": "healthy",
            "service": "epi-gateway",
            "version": __version__,
            "queue_size": snapshot["queue_size"],
            "processed_count": snapshot["processed_count"],
            "storage_dir": snapshot["storage_dir"],
            "events_dir": snapshot["events_dir"],
            "database_path": snapshot["database_path"],
            "batch_size": snapshot["batch_size"],
            "batch_timeout": snapshot["batch_timeout"],
            "replayed_batches": snapshot["replayed_batches"],
            "case_count": snapshot["case_count"],
            "ready": snapshot["ready"],
            "auth_required": runtime_settings.auth_required,
            "auth_mode": runtime_settings.auth_mode,
            "local_user_auth_enabled": runtime_settings.local_user_auth_enabled,
            "local_user_count": snapshot["auth_user_count"],
            "retention_mode": runtime_settings.retention_mode,
            "proxy_failure_mode": runtime_settings.proxy_failure_mode,
            "capture_scope": runtime_settings.capture_scope,
            "replay": {
                "applied_batches": snapshot["replayed_batches"],
                "skipped_batches": snapshot["skipped_replay_batches"],
                "corrupt_batch_count": snapshot["corrupt_batch_count"],
                "corrupt_files": snapshot["corrupt_files"],
                "moved_corrupt_files": snapshot["moved_corrupt_files"],
                "last_error": snapshot["replay_last_error"],
            },
            "projection": {
                "failure_count": snapshot["projection_failure_count"],
                "last_error": snapshot["last_projection_error"],
            },
            "capture_spec_version": CAPTURE_SPEC_VERSION,
            "capabilities": {
                "mock_records": True,
                "shared_workspace": True,
                "shared_cases": True,
                "artifact_export": True,
            },
            "workspace_file": snapshot["database_path"],
        }

    @app.get("/ready")
    async def readiness_check():
        snapshot = runtime_worker.snapshot()
        ok = bool(snapshot["ready"] and not snapshot["last_start_error"])
        degraded = bool(snapshot["corrupt_batch_count"] or snapshot["projection_failure_count"])
        status_code = 200 if ok else 503
        status_text = "ready-with-warnings" if ok and degraded else "ready" if ok else "starting"
        return JSONResponse(
            status_code=status_code,
            content={
                "ok": ok,
                "status": status_text,
                "service": "epi-gateway",
                "ready": snapshot["ready"],
                "auth_required": runtime_settings.auth_required,
                "auth_mode": runtime_settings.auth_mode,
                "local_user_auth_enabled": runtime_settings.local_user_auth_enabled,
                "local_user_count": snapshot["auth_user_count"],
                "retention_mode": runtime_settings.retention_mode,
                "replay": {
                    "applied_batches": snapshot["replayed_batches"],
                    "skipped_batches": snapshot["skipped_replay_batches"],
                    "corrupt_batch_count": snapshot["corrupt_batch_count"],
                    "corrupt_files": snapshot["corrupt_files"],
                    "moved_corrupt_files": snapshot["moved_corrupt_files"],
                    "last_error": snapshot["replay_last_error"],
                },
                "projection": {
                    "failure_count": snapshot["projection_failure_count"],
                    "last_error": snapshot["last_projection_error"],
                },
                "last_start_error": snapshot["last_start_error"],
            },
        )

    @app.get("/metrics")
    async def prometheus_metrics():
        """Prometheus text-format metrics endpoint.  No auth required (scrape-friendly)."""
        snapshot = runtime_worker.snapshot()
        lines = [
            "# HELP epi_capture_requests_total Total capture requests received (all capture paths)",
            "# TYPE epi_capture_requests_total counter",
            f"epi_capture_requests_total {_gateway_metrics.get('capture_requests')}",
            "",
            "# HELP epi_capture_errors_total Total capture requests that returned a 4xx/5xx response",
            "# TYPE epi_capture_errors_total counter",
            f"epi_capture_errors_total {_gateway_metrics.get('capture_errors')}",
            "",
            "# HELP epi_worker_queue_depth Current number of events waiting to be flushed",
            "# TYPE epi_worker_queue_depth gauge",
            f"epi_worker_queue_depth {snapshot['queue_size']}",
            "",
            "# HELP epi_worker_processed_total Total events flushed by the background worker",
            "# TYPE epi_worker_processed_total counter",
            f"epi_worker_processed_total {snapshot['processed_count']}",
            "",
            "# HELP epi_cases_total Total cases stored in the database",
            "# TYPE epi_cases_total gauge",
            f"epi_cases_total {snapshot['case_count']}",
            "",
            "# HELP epi_auth_users_total Total local users configured in the gateway",
            "# TYPE epi_auth_users_total gauge",
            f"epi_auth_users_total {snapshot['auth_user_count']}",
            "",
            "# HELP epi_projection_failures_total Total case-projection errors since startup",
            "# TYPE epi_projection_failures_total counter",
            f"epi_projection_failures_total {snapshot['projection_failure_count']}",
            "",
            "# HELP epi_replayed_batches_total Spool batches replayed from disk on startup",
            "# TYPE epi_replayed_batches_total counter",
            f"epi_replayed_batches_total {snapshot['replayed_batches']}",
        ]
        from starlette.responses import PlainTextResponse
        return PlainTextResponse(
            "\n".join(lines) + "\n",
            media_type="text/plain; version=0.0.4; charset=utf-8",
        )

    @app.post("/capture", status_code=202)
    async def capture_evidence(request: CaptureEventModel):
        try:
            runtime_worker.enqueue(request.model_dump(mode="json"))
            return {
                "status": "accepted",
                "message": "Evidence queued for persistence",
                "event_id": request.event_id,
                "decision_id": request.decision_id,
                "trace_id": request.trace_id,
            }
        except Exception as exc:
            logger.error("Failed to enqueue evidence: %s", exc)
            raise HTTPException(status_code=500, detail="Internal Gateway Error") from exc

    @app.post("/capture/batch", status_code=202)
    async def capture_evidence_batch(request: CaptureBatchRequest):
        try:
            for item in request.items:
                runtime_worker.enqueue(item.model_dump(mode="json"))
            return {
                "status": "accepted",
                "message": "Evidence batch queued for persistence",
                "accepted_count": len(request.items),
                "event_ids": [item.event_id for item in request.items],
            }
        except Exception as exc:
            logger.error("Failed to enqueue evidence batch: %s", exc)
            raise HTTPException(status_code=500, detail="Internal Gateway Error") from exc

    @app.post("/capture/llm", status_code=202)
    async def capture_llm_interaction(request: LLMCaptureRequest):
        try:
            events = _enqueue_llm_capture(runtime_worker, request, settings=runtime_settings, route_name="/capture/llm")
            provider = events[0].provider if events else request.provider
            profile = events[0].meta.get("provider_profile") if events else None
            return {
                "status": "accepted",
                "message": "LLM interaction queued for normalization and persistence",
                "accepted_count": len(events),
                "provider": provider,
                "provider_profile": profile,
                "event_ids": [item.event_id for item in events],
            }
        except Exception as exc:
            logger.error("Failed to normalize LLM interaction: %s", exc)
            raise HTTPException(status_code=500, detail="Internal Gateway Error") from exc

    @app.post("/v1/chat/completions")
    async def proxy_openai_chat_completions(request: Request):
        try:
            payload = await request.json()
        except Exception as exc:
            raise HTTPException(status_code=400, detail="Invalid JSON request body") from exc

        inbound_headers = dict(request.headers)
        failure_mode = _resolve_failure_mode(inbound_headers, runtime_settings)
        try:
            result, capture_request = relay_openai_chat_completions(payload, inbound_headers)
            try:
                _enqueue_llm_capture(
                    runtime_worker,
                    capture_request,
                    settings=runtime_settings,
                    route_name="/v1/chat/completions",
                )
            except Exception as capture_exc:
                logger.error("OpenAI-compatible capture failed in %s mode: %s", failure_mode, capture_exc, exc_info=True)
                if failure_mode == "fail-closed":
                    return _capture_failure_response(
                        "Upstream response received, but EPI could not persist the capture in fail-closed mode.",
                        settings=runtime_settings,
                    )
                return _build_proxy_response(result, capture_status="failed-open", settings=runtime_settings)
            return _build_proxy_response(result, capture_status="captured", settings=runtime_settings)
        except ProxyRelayError as exc:
            capture_request = build_openai_proxy_capture_request(
                payload,
                error_payload=exc.body,
                headers=inbound_headers,
            )
            try:
                _enqueue_llm_capture(
                    runtime_worker,
                    capture_request,
                    settings=runtime_settings,
                    route_name="/v1/chat/completions",
                )
            except Exception as capture_exc:
                logger.error("OpenAI-compatible error capture failed in %s mode: %s", failure_mode, capture_exc, exc_info=True)
                if failure_mode == "fail-closed":
                    return _capture_failure_response(
                        "The upstream request failed and EPI could not persist the error capture in fail-closed mode.",
                        settings=runtime_settings,
                    )
                return _build_proxy_response(exc, capture_status="failed-open", settings=runtime_settings)
            return _build_proxy_response(exc, capture_status="captured", settings=runtime_settings)
        except Exception as exc:
            logger.error("Failed OpenAI-compatible relay: %s", exc)
            raise HTTPException(status_code=500, detail="Internal Gateway Error") from exc

    @app.post("/v1/messages")
    async def proxy_anthropic_messages(request: Request):
        try:
            payload = await request.json()
        except Exception as exc:
            raise HTTPException(status_code=400, detail="Invalid JSON request body") from exc

        inbound_headers = dict(request.headers)
        failure_mode = _resolve_failure_mode(inbound_headers, runtime_settings)
        try:
            result, capture_request = relay_anthropic_messages(payload, inbound_headers)
            try:
                _enqueue_llm_capture(
                    runtime_worker,
                    capture_request,
                    settings=runtime_settings,
                    route_name="/v1/messages",
                )
            except Exception as capture_exc:
                logger.error("Anthropic-compatible capture failed in %s mode: %s", failure_mode, capture_exc, exc_info=True)
                if failure_mode == "fail-closed":
                    return _capture_failure_response(
                        "Upstream response received, but EPI could not persist the capture in fail-closed mode.",
                        settings=runtime_settings,
                    )
                return _build_proxy_response(result, capture_status="failed-open", settings=runtime_settings)
            return _build_proxy_response(result, capture_status="captured", settings=runtime_settings)
        except ProxyRelayError as exc:
            capture_request = build_anthropic_proxy_capture_request(
                payload,
                error_payload=exc.body,
                headers=inbound_headers,
            )
            try:
                _enqueue_llm_capture(
                    runtime_worker,
                    capture_request,
                    settings=runtime_settings,
                    route_name="/v1/messages",
                )
            except Exception as capture_exc:
                logger.error("Anthropic-compatible error capture failed in %s mode: %s", failure_mode, capture_exc, exc_info=True)
                if failure_mode == "fail-closed":
                    return _capture_failure_response(
                        "The upstream request failed and EPI could not persist the error capture in fail-closed mode.",
                        settings=runtime_settings,
                    )
                return _build_proxy_response(exc, capture_status="failed-open", settings=runtime_settings)
            return _build_proxy_response(exc, capture_status="captured", settings=runtime_settings)
        except Exception as exc:
            logger.error("Failed Anthropic relay: %s", exc)
            raise HTTPException(status_code=500, detail="Internal Gateway Error") from exc

    @app.post("/api/auth/login")
    async def auth_login(payload: AuthLoginRequest):
        if not runtime_settings.local_user_auth_enabled:
            raise HTTPException(status_code=404, detail="Local user login is not enabled for this gateway.")
        username_key = str(payload.username or "").strip().lower()
        if _login_throttle.is_locked_out(username_key):
            raise HTTPException(
                status_code=429,
                detail="Account temporarily locked due to too many failed login attempts. Try again in 15 minutes.",
            )
        user = runtime_worker.authenticate_user(payload.username, payload.password)
        if not user:
            _login_throttle.record_failure(username_key)
            raise HTTPException(status_code=401, detail="Invalid username or password")
        _login_throttle.record_success(username_key)
        token, session = runtime_worker.create_auth_session(user, ttl_hours=runtime_settings.session_ttl_hours)
        return {
            "ok": True,
            "access_token": token,
            "token_type": "bearer",
            "auth_mode": runtime_settings.auth_mode,
            "session": session.model_dump(mode="json"),
        }

    @app.get("/api/auth/session")
    async def auth_session(request: Request):
        principal = getattr(request.state, "auth", None)
        if not principal:
            raise HTTPException(status_code=401, detail="Unauthorized")
        return {
            "ok": True,
            "authenticated": True,
            "auth_mode": principal.get("auth_mode", runtime_settings.auth_mode),
            "session": principal,
        }

    @app.post("/api/auth/logout")
    async def auth_logout(request: Request):
        principal = getattr(request.state, "auth", None)
        if not principal:
            raise HTTPException(status_code=401, detail="Unauthorized")
        token = _extract_bearer_token(request.headers.get("authorization"))
        if principal.get("auth_mode") == "session" and token:
            runtime_worker.revoke_auth_session(token)
        return {"ok": True}

    @app.get("/api/cases")
    async def list_cases(
        request: Request,
        status: str | None = Query(default=None),
        trust: str | None = Query(default=None),
        review: str | None = Query(default=None),
        workflow: str | None = Query(default=None),
        search: str | None = Query(default=None),
        assignee: str | None = Query(default=None),
        overdue: bool | None = Query(default=None),
    ):
        _require_roles(request, "admin", "reviewer", "auditor")
        return {
            "ok": True,
            "cases": runtime_worker.list_cases(
                status=status,
                trust=trust,
                review=review,
                workflow=workflow,
                search=search,
                assignee=assignee,
                overdue=overdue,
            ),
        }

    @app.get("/api/cases/{case_id}")
    async def get_case(case_id: str, request: Request):
        _require_roles(request, "admin", "reviewer", "auditor")
        payload = runtime_worker.get_case(case_id)
        if not payload:
            raise HTTPException(status_code=404, detail="Case not found")
        return {"ok": True, "case": payload}

    @app.post("/api/cases/{case_id}/reviews")
    async def save_case_review(case_id: str, request: Request, review_payload: dict[str, Any]):
        principal = _require_roles(request, "admin", "reviewer")
        try:
            review_payload.setdefault("reviewed_by", principal.get("username"))
            payload = runtime_worker.save_review(case_id, review_payload)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Case not found") from exc
        bg = None
        if runtime_settings.webhook_url and payload.get("status") in ("unassigned", "needs_review"):
            _wh_url = runtime_settings.webhook_url
            _wh_payload = {
                "event": "case.needs_review",
                "case_id": payload.get("case_id") or case_id,
                "title": payload.get("title") or payload.get("workflow_name") or payload.get("workflow_id") or "",
                "created_at": utc_now_iso(),
                "gateway_url": str(request.base_url).rstrip("/"),
            }
            bg = BackgroundTask(lambda u=_wh_url, p=_wh_payload: _fire_webhook(u, p))
        return JSONResponse({"ok": True, "case": payload}, background=bg)

    @app.patch("/api/cases/{case_id}")
    async def patch_case(case_id: str, request: Request, payload: CaseWorkflowPatchRequest):
        principal = _require_roles(request, "admin", "reviewer")
        try:
            updates = payload.model_dump(mode="json", exclude_unset=True)
            updates.setdefault("updated_by", principal.get("username"))
            payload = runtime_worker.update_case_workflow(case_id, updates)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Case not found") from exc
        return {"ok": True, "case": payload}

    @app.get("/api/cases/{case_id}/comments")
    async def get_case_comments(case_id: str, request: Request):
        _require_roles(request, "admin", "reviewer", "auditor")
        payload = runtime_worker.get_case(case_id)
        if not payload:
            raise HTTPException(status_code=404, detail="Case not found")
        return {
            "ok": True,
            "comments": runtime_worker.list_comments(case_id),
        }

    @app.post("/api/cases/{case_id}/comments")
    async def post_case_comment(case_id: str, request: Request, comment: CaseCommentRequest):
        principal = _require_roles(request, "admin", "reviewer")
        try:
            payload = runtime_worker.add_comment(
                case_id,
                _clean(comment.author) or principal.get("username"),
                comment.body,
                created_at=comment.created_at,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Case not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "case": payload, "comments": payload.get("comments", [])}

    @app.post("/api/cases/{case_id}/export")
    async def export_case(case_id: str, request: Request):
        _require_roles(request, "admin", "reviewer", "auditor")
        temp_dir = EPIContainer._make_temp_dir("epi_gateway_export_response_")
        export_path = temp_dir / f"{_safe_filename(case_id)}.epi"
        signer = _build_gateway_signer(runtime_settings)
        try:
            result = runtime_worker.export_case(case_id, export_path, signer_function=signer)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Case not found") from exc

        return FileResponse(
            path=result.output_path,
            media_type="application/vnd.epi+zip",
            filename=result.filename,
            background=BackgroundTask(lambda: shutil.rmtree(temp_dir, ignore_errors=True)),
        )

    @app.post("/api/fetch-record")
    async def fetch_record(request: Request, payload: FetchRecordRequest):
        _require_roles(request, "admin", "reviewer")
        try:
            record = fetch_live_record(
                system=payload.system,
                connector_profile=payload.connector_profile,
                case_input=payload.case_input,
            )
            event = _build_preview_capture_event(
                payload.system,
                record,
                connector_profile=payload.connector_profile,
                case_input=payload.case_input,
            )
            touched_case_ids = runtime_worker.store_items([event.model_dump(mode="json")])
            case_id = touched_case_ids[0] if touched_case_ids else _first_nonempty(event.case_id, event.decision_id, event.trace_id)
            case_payload = runtime_worker.get_case(case_id) if case_id else None
        except (ValueError, FileNotFoundError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            logger.error("Failed to fetch record: %s", exc)
            raise HTTPException(status_code=500, detail="Internal Gateway Error") from exc

        return {"ok": True, "record": record, "case": case_payload}

    @app.get("/api/workspace/state")
    async def workspace_state(request: Request):
        _require_roles(request, "admin", "reviewer", "auditor")
        cases = runtime_worker.list_cases()
        snapshot = runtime_worker.snapshot()
        return {
            "ok": True,
            "cases": cases,
            "workspace_file": snapshot["database_path"],
        }

    @app.post("/api/workspace/cases")
    async def workspace_cases(request: Request, payload: WorkspaceCaseRequest):
        _require_roles(request, "admin", "reviewer")
        try:
            stored_case = runtime_worker.upsert_case_payload(payload.case)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        bg = None
        if runtime_settings.webhook_url and stored_case.get("status") in ("unassigned", "needs_review"):
            _wh_url = runtime_settings.webhook_url
            _wh_payload = {
                "event": "case.needs_review",
                "case_id": stored_case.get("case_id") or "",
                "title": stored_case.get("title") or stored_case.get("workflow_name") or stored_case.get("workflow_id") or "",
                "created_at": utc_now_iso(),
                "gateway_url": str(request.base_url).rstrip("/"),
            }
            bg = BackgroundTask(lambda u=_wh_url, p=_wh_payload: _fire_webhook(u, p))
        return JSONResponse({"ok": True, "case": stored_case}, background=bg)

    return app


app = create_app()
