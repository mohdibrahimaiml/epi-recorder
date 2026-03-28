import io
import json
from urllib import error as urlerror

from epi_gateway.proxy import (
    ProxyRelayError,
    build_anthropic_proxy_capture_request,
    build_anthropic_proxy_headers,
    build_openai_proxy_capture_request,
    build_openai_proxy_headers,
    extract_proxy_meta,
    relay_anthropic_messages,
    relay_json_request,
    relay_openai_chat_completions,
)


class _FakeResponse:
    def __init__(self, body: dict, *, status: int = 200, headers: dict[str, str] | None = None):
        self._body = json.dumps(body).encode("utf-8")
        self.status = status
        self.headers = headers or {"content-type": "application/json"}

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_extract_proxy_meta_reads_epi_headers():
    meta = extract_proxy_meta(
        {
            "x-trace-id": "trace-1",
            "x-epi-decision-id": "decision-1",
            "x-epi-case-id": "case-1",
            "x-epi-source-app": "refund-service",
            "x-epi-actor-id": "user-123",
        },
        provider_adapter="openai-proxy",
        provider_profile="openai-compatible",
        provider="openai-compatible",
    )

    assert meta["trace_id"] == "trace-1"
    assert meta["decision_id"] == "decision-1"
    assert meta["case_id"] == "case-1"
    assert meta["source_app"] == "refund-service"
    assert meta["actor_id"] == "user-123"
    assert meta["provider_adapter"] == "openai-proxy"


def test_build_openai_proxy_headers_prefers_inbound_auth(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "env-openai-key")

    headers = build_openai_proxy_headers(
        {
            "Authorization": "Bearer inbound-key",
            "OpenAI-Organization": "org_123",
            "OpenAI-Project": "proj_123",
        }
    )

    assert headers["Authorization"] == "Bearer inbound-key"
    assert headers["OpenAI-Organization"] == "org_123"
    assert headers["OpenAI-Project"] == "proj_123"


def test_build_anthropic_proxy_headers_uses_env_fallback(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-env-key")

    headers = build_anthropic_proxy_headers({})

    assert headers["x-api-key"] == "anthropic-env-key"
    assert headers["anthropic-version"] == "2023-06-01"


def test_relay_json_request_raises_structured_proxy_error():
    error = urlerror.HTTPError(
        "https://example.com",
        429,
        "Too Many Requests",
        hdrs={"content-type": "application/json"},
        fp=io.BytesIO(json.dumps({"error": "rate limited"}).encode("utf-8")),
    )

    def _raiser(_request, timeout=60.0):
        raise error

    try:
        relay_json_request(
            "https://example.com",
            {"hello": "world"},
            {"Authorization": "Bearer test"},
            opener=_raiser,
        )
        raised = False
    except ProxyRelayError as exc:
        raised = True
        proxy_error = exc

    assert raised is True
    assert proxy_error.status_code == 429
    assert proxy_error.body["error"] == "rate limited"


def test_relay_openai_chat_completions_builds_capture_request(monkeypatch):
    monkeypatch.setenv("EPI_GATEWAY_OPENAI_UPSTREAM_URL", "https://proxy.example/v1/chat/completions")

    def _fake_open(_request, timeout=60.0):
        return _FakeResponse(
            {
                "model": "gpt-4o-mini",
                "choices": [
                    {
                        "message": {"role": "assistant", "content": "Approved with review"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 6, "total_tokens": 16},
            }
        )

    result, capture_request = relay_openai_chat_completions(
        {
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": "Should we approve this refund?"}],
        },
        {"x-trace-id": "trace-9"},
        opener=_fake_open,
    )

    assert result.status_code == 200
    assert capture_request.provider == "openai-compatible"
    assert capture_request.meta["provider_adapter"] == "openai-proxy"
    assert capture_request.meta["trace_id"] == "trace-9"
    assert capture_request.response["usage"]["total_tokens"] == 16


def test_relay_anthropic_messages_builds_capture_request(monkeypatch):
    monkeypatch.setenv("EPI_GATEWAY_ANTHROPIC_UPSTREAM_URL", "https://proxy.example/v1/messages")

    def _fake_open(_request, timeout=60.0):
        return _FakeResponse(
            {
                "model": "claude-3-5-sonnet",
                "role": "assistant",
                "content": [{"type": "text", "text": "Escalate for approval"}],
                "usage": {"input_tokens": 8, "output_tokens": 5},
                "stop_reason": "end_turn",
            }
        )

    result, capture_request = relay_anthropic_messages(
        {
            "model": "claude-3-5-sonnet",
            "messages": [{"role": "user", "content": "Can this claim be auto-approved?"}],
            "max_tokens": 256,
        },
        {"x-epi-source-app": "claims-service"},
        opener=_fake_open,
    )

    assert result.status_code == 200
    assert capture_request.provider == "anthropic"
    assert capture_request.meta["provider_adapter"] == "anthropic-proxy"
    assert capture_request.meta["source_app"] == "claims-service"
    assert capture_request.response["stop_reason"] == "end_turn"


def test_build_proxy_capture_requests_preserve_error_payloads():
    openai_capture = build_openai_proxy_capture_request(
        {"model": "gpt-4"},
        error_payload={"error": "timeout"},
        headers={"x-epi-decision-id": "decision-3"},
    )
    anthropic_capture = build_anthropic_proxy_capture_request(
        {"model": "claude-3"},
        error_payload={"error": "upstream unavailable"},
        headers={"x-epi-decision-id": "decision-4"},
    )

    assert openai_capture.error["error"] == "timeout"
    assert openai_capture.meta["decision_id"] == "decision-3"
    assert anthropic_capture.error["error"] == "upstream unavailable"
    assert anthropic_capture.meta["decision_id"] == "decision-4"
