"""
Relay helpers for provider-compatible gateway endpoints.

These helpers keep proxy behavior testable without requiring FastAPI in the
test environment. The gateway routes can call them, and future SDKs or sidecars
can reuse the same normalization and upstream relay logic.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from typing import Any, Mapping
from urllib import error as urlerror
from urllib import request as urlrequest

from epi_core.llm_capture import LLMCaptureRequest

DEFAULT_OPENAI_UPSTREAM_URL = "https://api.openai.com/v1/chat/completions"
DEFAULT_ANTHROPIC_UPSTREAM_URL = "https://api.anthropic.com/v1/messages"
DEFAULT_ANTHROPIC_VERSION = "2023-06-01"

OPENAI_UPSTREAM_ENV = "EPI_GATEWAY_OPENAI_UPSTREAM_URL"
ANTHROPIC_UPSTREAM_ENV = "EPI_GATEWAY_ANTHROPIC_UPSTREAM_URL"
OPENAI_API_KEY_ENV = "OPENAI_API_KEY"
ANTHROPIC_API_KEY_ENV = "ANTHROPIC_API_KEY"


@dataclass
class ProxyRelayResult:
    status_code: int
    body: dict[str, Any]
    headers: dict[str, str]


class ProxyRelayError(RuntimeError):
    def __init__(self, status_code: int, body: dict[str, Any], headers: dict[str, str] | None = None):
        super().__init__(body.get("error") or body.get("detail") or "Upstream relay failed")
        self.status_code = status_code
        self.body = body
        self.headers = headers or {}


def _header_lookup(headers: Mapping[str, Any], key: str) -> str | None:
    for candidate, value in headers.items():
        if str(candidate).lower() == key.lower():
            text = str(value or "").strip()
            if text:
                return text
    return None


def extract_proxy_meta(
    headers: Mapping[str, Any] | None,
    *,
    provider_adapter: str,
    provider_profile: str,
    provider: str,
) -> dict[str, Any]:
    headers = headers or {}
    meta = {
        "trace_id": _header_lookup(headers, "x-trace-id") or _header_lookup(headers, "x-request-id"),
        "decision_id": _header_lookup(headers, "x-epi-decision-id"),
        "case_id": _header_lookup(headers, "x-epi-case-id"),
        "workflow_id": _header_lookup(headers, "x-epi-workflow-id"),
        "workflow_name": _header_lookup(headers, "x-epi-workflow-name"),
        "source_app": _header_lookup(headers, "x-epi-source-app") or _header_lookup(headers, "x-forwarded-host"),
        "actor_id": _header_lookup(headers, "x-epi-actor-id"),
        "provider_profile": provider_profile,
        "provider_adapter": provider_adapter,
        "provider": provider,
        "source": "epi_gateway",
        "capture_mode": "direct",
    }
    return {key: value for key, value in meta.items() if value is not None}


def build_openai_proxy_capture_request(
    request_payload: dict[str, Any],
    *,
    response_payload: dict[str, Any] | None = None,
    error_payload: dict[str, Any] | None = None,
    headers: Mapping[str, Any] | None = None,
    provider: str = "openai-compatible",
) -> LLMCaptureRequest:
    return LLMCaptureRequest(
        provider=provider,
        request=request_payload,
        response=response_payload,
        error=error_payload,
        meta=extract_proxy_meta(
            headers,
            provider_adapter="openai-proxy",
            provider_profile="openai-compatible",
            provider=provider,
        ),
    )


def build_anthropic_proxy_capture_request(
    request_payload: dict[str, Any],
    *,
    response_payload: dict[str, Any] | None = None,
    error_payload: dict[str, Any] | None = None,
    headers: Mapping[str, Any] | None = None,
) -> LLMCaptureRequest:
    return LLMCaptureRequest(
        provider="anthropic",
        request=request_payload,
        response=response_payload,
        error=error_payload,
        meta=extract_proxy_meta(
            headers,
            provider_adapter="anthropic-proxy",
            provider_profile="anthropic-messages",
            provider="anthropic",
        ),
    )


def resolve_upstream_url(kind: str) -> str:
    if kind == "openai":
        return os.getenv(OPENAI_UPSTREAM_ENV, DEFAULT_OPENAI_UPSTREAM_URL)
    if kind == "anthropic":
        return os.getenv(ANTHROPIC_UPSTREAM_ENV, DEFAULT_ANTHROPIC_UPSTREAM_URL)
    raise ValueError(f"Unsupported upstream kind: {kind}")


def build_openai_proxy_headers(headers: Mapping[str, Any] | None) -> dict[str, str]:
    headers = headers or {}
    outbound = {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    authorization = _header_lookup(headers, "authorization") or (
        f"Bearer {os.getenv(OPENAI_API_KEY_ENV)}" if os.getenv(OPENAI_API_KEY_ENV) else None
    )
    if authorization:
        outbound["Authorization"] = authorization

    organization = _header_lookup(headers, "openai-organization")
    if organization:
        outbound["OpenAI-Organization"] = organization

    project = _header_lookup(headers, "openai-project")
    if project:
        outbound["OpenAI-Project"] = project

    return outbound


def build_anthropic_proxy_headers(headers: Mapping[str, Any] | None) -> dict[str, str]:
    headers = headers or {}
    outbound = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "anthropic-version": _header_lookup(headers, "anthropic-version") or DEFAULT_ANTHROPIC_VERSION,
    }

    api_key = _header_lookup(headers, "x-api-key") or os.getenv(ANTHROPIC_API_KEY_ENV)
    if api_key:
        outbound["x-api-key"] = api_key

    beta_header = _header_lookup(headers, "anthropic-beta")
    if beta_header:
        outbound["anthropic-beta"] = beta_header

    return outbound


def relay_json_request(
    url: str,
    payload: dict[str, Any],
    headers: Mapping[str, Any],
    *,
    timeout: float = 60.0,
    opener: Any | None = None,
) -> ProxyRelayResult:
    encoded = json.dumps(payload).encode("utf-8")
    request = urlrequest.Request(url, data=encoded, headers=dict(headers), method="POST")
    open_fn = opener or urlrequest.urlopen

    try:
        with open_fn(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            body = json.loads(raw) if raw else {}
            response_headers = {str(k): str(v) for k, v in getattr(response, "headers", {}).items()}
            status_code = getattr(response, "status", 200)
            return ProxyRelayResult(status_code=status_code, body=body, headers=response_headers)
    except urlerror.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            body = {"error": raw or exc.reason}
        response_headers = {str(k): str(v) for k, v in getattr(exc, "headers", {}).items()}
        raise ProxyRelayError(exc.code, body, response_headers) from exc
    except urlerror.URLError as exc:
        raise ProxyRelayError(502, {"error": f"Could not reach upstream provider: {exc.reason}"}) from exc


def relay_openai_chat_completions(
    request_payload: dict[str, Any],
    inbound_headers: Mapping[str, Any] | None,
    *,
    opener: Any | None = None,
    timeout: float = 60.0,
) -> tuple[ProxyRelayResult, LLMCaptureRequest]:
    result = relay_json_request(
        resolve_upstream_url("openai"),
        request_payload,
        build_openai_proxy_headers(inbound_headers),
        timeout=timeout,
        opener=opener,
    )
    provider = str(result.body.get("provider") or result.body.get("system_fingerprint") or "openai-compatible")
    capture_request = build_openai_proxy_capture_request(
        request_payload,
        response_payload=result.body,
        headers=inbound_headers,
        provider=provider,
    )
    return result, capture_request


def relay_anthropic_messages(
    request_payload: dict[str, Any],
    inbound_headers: Mapping[str, Any] | None,
    *,
    opener: Any | None = None,
    timeout: float = 60.0,
) -> tuple[ProxyRelayResult, LLMCaptureRequest]:
    result = relay_json_request(
        resolve_upstream_url("anthropic"),
        request_payload,
        build_anthropic_proxy_headers(inbound_headers),
        timeout=timeout,
        opener=opener,
    )
    capture_request = build_anthropic_proxy_capture_request(
        request_payload,
        response_payload=result.body,
        headers=inbound_headers,
    )
    return result, capture_request
