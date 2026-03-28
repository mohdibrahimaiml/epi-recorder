"""
Provider-normalized LLM capture helpers.

The goal is not to force every provider into one transport protocol.
The goal is to normalize many provider-specific payloads into one EPI
capture model so the rest of the system can treat them consistently.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from epi_core.capture import CaptureEventModel

OPENAI_COMPATIBLE_PROVIDERS = {
    "openai",
    "openai-compatible",
    "azure-openai",
    "azure",
    "ollama",
    "vllm",
    "lmstudio",
    "groq",
    "fireworks",
    "together",
    "perplexity",
    "xai",
    "deepseek",
    "mistral-openai",
}

PROVIDER_ALIASES = {
    "google": "gemini",
    "google-generativeai": "gemini",
    "claude": "anthropic",
}


class LLMCaptureRequest(BaseModel):
    """
    Provider-agnostic HTTP/SDK envelope for one LLM interaction.

    Callers can post their native provider request/response payloads here and
    let EPI turn them into stable `llm.request`, `llm.response`, and
    `llm.error` events.
    """

    provider: str = Field(default="auto")
    request: dict[str, Any] = Field(default_factory=dict)
    response: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    meta: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="allow")


def normalize_provider_name(raw_provider: str | None) -> str:
    provider = str(raw_provider or "").strip().lower()
    if not provider or provider == "auto":
        return "auto"
    return PROVIDER_ALIASES.get(provider, provider)


def _copy_meta(meta: dict[str, Any], **extra: Any) -> dict[str, Any]:
    payload = dict(meta or {})
    for key, value in extra.items():
        if value is not None:
            payload[key] = value
    return payload


def _normalize_text_parts(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text") or item.get("content")
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts)
    if isinstance(value, dict):
        text = value.get("text") or value.get("content")
        if isinstance(text, str):
            return text
    return ""


def _looks_openai_compatible(request_payload: dict[str, Any], response_payload: dict[str, Any] | None) -> bool:
    if "messages" in request_payload or "input" in request_payload:
        return True
    if response_payload and "choices" in response_payload:
        return True
    return False


def _looks_anthropic(request_payload: dict[str, Any], response_payload: dict[str, Any] | None) -> bool:
    if "anthropic_version" in request_payload:
        return True
    if response_payload and isinstance(response_payload.get("content"), list) and "choices" not in response_payload:
        return True
    return False


def _looks_gemini(request_payload: dict[str, Any], response_payload: dict[str, Any] | None) -> bool:
    if "contents" in request_payload or "system_instruction" in request_payload:
        return True
    if response_payload and ("candidates" in response_payload or "usageMetadata" in response_payload):
        return True
    return False


def _provider_from_litellm(request_payload: dict[str, Any], meta: dict[str, Any]) -> str | None:
    litellm_params = request_payload.get("litellm_params") or {}
    custom_provider = litellm_params.get("custom_llm_provider") or meta.get("custom_llm_provider")
    if custom_provider:
        return normalize_provider_name(str(custom_provider))

    model = str(request_payload.get("model") or meta.get("model") or "")
    if "/" in model:
        return normalize_provider_name(model.split("/", 1)[0])
    return None


def _resolve_provider_profile(payload: LLMCaptureRequest) -> tuple[str, str, str | None]:
    request_payload = payload.request or {}
    response_payload = payload.response or {}
    provider = normalize_provider_name(payload.provider)
    adapter: str | None = None

    if provider == "litellm":
        adapter = "litellm"
        provider = _provider_from_litellm(request_payload, payload.meta) or "litellm"
        if _looks_openai_compatible(request_payload, response_payload):
            return provider, "openai-compatible", adapter

    if provider in OPENAI_COMPATIBLE_PROVIDERS:
        return provider, "openai-compatible", adapter
    if provider == "anthropic":
        return provider, "anthropic-messages", adapter
    if provider == "gemini":
        return provider, "gemini-generate-content", adapter

    if provider == "auto":
        if _looks_anthropic(request_payload, response_payload):
            return "anthropic", "anthropic-messages", adapter
        if _looks_gemini(request_payload, response_payload):
            return "gemini", "gemini-generate-content", adapter
        if _looks_openai_compatible(request_payload, response_payload):
            return "openai-compatible", "openai-compatible", adapter
        return "generic", "generic", adapter

    if _looks_openai_compatible(request_payload, response_payload):
        return provider, "openai-compatible", adapter
    return provider, "generic", adapter


def _extract_openai_request(request_payload: dict[str, Any]) -> tuple[str | None, dict[str, Any]]:
    content = {
        "messages": request_payload.get("messages") or request_payload.get("input") or [],
        "temperature": request_payload.get("temperature"),
        "top_p": request_payload.get("top_p"),
        "max_tokens": request_payload.get("max_tokens"),
        "tools": request_payload.get("tools"),
        "tool_choice": request_payload.get("tool_choice"),
        "response_format": request_payload.get("response_format"),
        "stream": bool(request_payload.get("stream")),
    }
    return request_payload.get("model"), {k: v for k, v in content.items() if v not in (None, [], {})}


def _extract_openai_response(response_payload: dict[str, Any]) -> tuple[str | None, dict[str, Any]]:
    choices = response_payload.get("choices") or []
    normalized_choices: list[dict[str, Any]] = []
    output_text = ""
    finish_reason = None
    for choice in choices:
        message = (choice or {}).get("message") or {}
        content = message.get("content")
        normalized_choices.append(
            {
                "message": {
                    "role": message.get("role", "assistant"),
                    "content": content,
                    "tool_calls": message.get("tool_calls"),
                },
                "finish_reason": choice.get("finish_reason"),
            }
        )
        if not output_text:
            output_text = _normalize_text_parts(content)
        if finish_reason is None:
            finish_reason = choice.get("finish_reason")
    usage = response_payload.get("usage")
    content = {
        "choices": normalized_choices,
        "output_text": output_text,
        "usage": usage,
        "finish_reason": finish_reason,
    }
    return response_payload.get("model"), {k: v for k, v in content.items() if v not in (None, [], {})}


def _extract_anthropic_request(request_payload: dict[str, Any]) -> tuple[str | None, dict[str, Any]]:
    content = {
        "messages": request_payload.get("messages") or [],
        "system": request_payload.get("system"),
        "max_tokens": request_payload.get("max_tokens"),
        "temperature": request_payload.get("temperature"),
        "top_p": request_payload.get("top_p"),
        "tools": request_payload.get("tools"),
        "stream": bool(request_payload.get("stream")),
    }
    return request_payload.get("model"), {k: v for k, v in content.items() if v not in (None, [], {})}


def _extract_anthropic_response(response_payload: dict[str, Any]) -> tuple[str | None, dict[str, Any]]:
    blocks = response_payload.get("content") or []
    output_parts = []
    normalized_blocks = []
    for block in blocks:
        normalized_blocks.append(block)
        if isinstance(block, dict) and block.get("type") == "text":
            text = block.get("text")
            if isinstance(text, str):
                output_parts.append(text)
    usage = response_payload.get("usage")
    content = {
        "content": normalized_blocks,
        "output_text": "".join(output_parts),
        "usage": usage,
        "stop_reason": response_payload.get("stop_reason"),
        "role": response_payload.get("role", "assistant"),
    }
    return response_payload.get("model"), {k: v for k, v in content.items() if v not in (None, [], {})}


def _extract_gemini_request(request_payload: dict[str, Any]) -> tuple[str | None, dict[str, Any]]:
    content = {
        "contents": request_payload.get("contents") or request_payload.get("messages") or [],
        "system_instruction": request_payload.get("system_instruction"),
        "generation_config": request_payload.get("generation_config"),
        "tools": request_payload.get("tools"),
    }
    model = request_payload.get("model") or request_payload.get("model_name") or "gemini"
    return model, {k: v for k, v in content.items() if v not in (None, [], {})}


def _extract_gemini_response(response_payload: dict[str, Any]) -> tuple[str | None, dict[str, Any]]:
    candidates = response_payload.get("candidates") or []
    output_parts: list[str] = []
    normalized_candidates: list[dict[str, Any]] = []
    for candidate in candidates:
        normalized_candidates.append(candidate)
        content = (candidate or {}).get("content") or {}
        for part in content.get("parts") or []:
            text = part.get("text")
            if isinstance(text, str):
                output_parts.append(text)
    if not output_parts and isinstance(response_payload.get("text"), str):
        output_parts.append(response_payload["text"])
    content = {
        "candidates": normalized_candidates,
        "output_text": "".join(output_parts),
        "usage": response_payload.get("usageMetadata"),
        "finish_reason": response_payload.get("finishReason"),
    }
    model = response_payload.get("model") or response_payload.get("modelVersion") or "gemini"
    return model, {k: v for k, v in content.items() if v not in (None, [], {})}


def _extract_generic_request(request_payload: dict[str, Any]) -> tuple[str | None, dict[str, Any]]:
    model = request_payload.get("model") or request_payload.get("model_name")
    return model, dict(request_payload)


def _extract_generic_response(response_payload: dict[str, Any]) -> tuple[str | None, dict[str, Any]]:
    model = response_payload.get("model") or response_payload.get("model_name")
    return model, dict(response_payload)


def _build_request_event(
    provider: str,
    profile: str,
    adapter: str | None,
    payload: LLMCaptureRequest,
) -> CaptureEventModel | None:
    if not payload.request:
        return None

    extractors = {
        "openai-compatible": _extract_openai_request,
        "anthropic-messages": _extract_anthropic_request,
        "gemini-generate-content": _extract_gemini_request,
        "generic": _extract_generic_request,
    }
    model, content = extractors[profile](payload.request)
    content = dict(content)
    content["provider"] = provider
    content["provider_profile"] = profile
    if adapter:
        content["provider_adapter"] = adapter
    meta = _copy_meta(payload.meta, provider_profile=profile, provider_adapter=adapter)
    return CaptureEventModel(
        kind="llm.request",
        content=content,
        meta=meta,
        provider=provider,
        model=model,
    )


def _build_response_event(
    provider: str,
    profile: str,
    adapter: str | None,
    payload: LLMCaptureRequest,
) -> CaptureEventModel | None:
    if not payload.response:
        return None

    extractors = {
        "openai-compatible": _extract_openai_response,
        "anthropic-messages": _extract_anthropic_response,
        "gemini-generate-content": _extract_gemini_response,
        "generic": _extract_generic_response,
    }
    model, content = extractors[profile](payload.response)
    content = dict(content)
    content["provider"] = provider
    content["provider_profile"] = profile
    latency_seconds = payload.meta.get("latency_seconds")
    if latency_seconds is not None:
        content["latency_seconds"] = latency_seconds
    if adapter:
        content["provider_adapter"] = adapter
    meta = _copy_meta(payload.meta, provider_profile=profile, provider_adapter=adapter)
    return CaptureEventModel(
        kind="llm.response",
        content=content,
        meta=meta,
        provider=provider,
        model=model,
    )


def _build_error_event(
    provider: str,
    profile: str,
    adapter: str | None,
    payload: LLMCaptureRequest,
) -> CaptureEventModel | None:
    if not payload.error:
        return None

    response_model = None
    if payload.response:
        response_model = payload.response.get("model") or payload.response.get("modelVersion")
    model = payload.request.get("model") or response_model or payload.meta.get("model")
    content = dict(payload.error)
    content["provider"] = provider
    content["provider_profile"] = profile
    if adapter:
        content["provider_adapter"] = adapter
    latency_seconds = payload.meta.get("latency_seconds")
    if latency_seconds is not None:
        content["latency_seconds"] = latency_seconds
    meta = _copy_meta(payload.meta, provider_profile=profile, provider_adapter=adapter)
    return CaptureEventModel(
        kind="llm.error",
        content=content,
        meta=meta,
        provider=provider,
        model=model,
    )


def build_llm_capture_events(payload: LLMCaptureRequest | dict[str, Any]) -> list[CaptureEventModel]:
    """Normalize one provider-native LLM interaction into EPI capture events."""
    if not isinstance(payload, LLMCaptureRequest):
        payload = LLMCaptureRequest.model_validate(payload)

    provider, profile, adapter = _resolve_provider_profile(payload)
    events: list[CaptureEventModel] = []

    request_event = _build_request_event(provider, profile, adapter, payload)
    if request_event is not None:
        events.append(request_event)

    response_event = _build_response_event(provider, profile, adapter, payload)
    if response_event is not None:
        events.append(response_event)

    error_event = _build_error_event(provider, profile, adapter, payload)
    if error_event is not None:
        events.append(error_event)

    return events
