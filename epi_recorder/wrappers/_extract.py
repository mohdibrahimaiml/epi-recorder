"""Turn provider SDK objects into plain data for the sealed record.

The wrappers used to hand-pick ``role`` and ``content`` off each response. That
silently dropped the one thing most agents actually do: call a tool. A decision
like ``deny_claim({"reason": "excluded peril"})`` lives in ``message.tool_calls``
on OpenAI and in a ``tool_use`` content block on Anthropic, so both were sealed
as ``content: null``.

Everything here is deliberately defensive: provider objects are pydantic models,
plain dicts, or SDK-specific wrappers depending on version. Unknown shapes are
serialized rather than dropped, because a missing field in an evidence file is
worse than an ugly one.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

__all__ = [
    "plain",
    "scalar",
    "openai_tool_calls",
    "openai_function_call",
    "openai_message",
    "openai_choice",
    "openai_response_meta",
    "openai_request_fields",
    "anthropic_blocks",
    "anthropic_response_meta",
    "anthropic_request_fields",
    "tool_call_summary",
    "parse_arguments",
]

_MAX_DEPTH = 12


def plain(value: Any, _depth: int = 0) -> Any:
    """Best-effort conversion to JSON-safe primitives.

    pydantic v2 (``model_dump``), pydantic v1 / dataclasses (``dict``), and
    plain objects with a ``__dict__`` are all handled. Anything else becomes
    its ``str`` form rather than disappearing.
    """
    if _depth > _MAX_DEPTH:
        return str(value)
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dict):
        return {str(k): plain(v, _depth + 1) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [plain(v, _depth + 1) for v in value]

    cls = type(value)
    dumper = getattr(cls, "model_dump", None)
    if callable(dumper):
        try:
            return plain(value.model_dump(mode="json"), _depth + 1)
        except TypeError:
            try:
                return plain(value.model_dump(), _depth + 1)
            except Exception:  # noqa: BLE001 - fall through to the next shape
                pass
        except Exception:  # noqa: BLE001
            pass

    dumper = getattr(cls, "dict", None)
    if callable(dumper):
        try:
            return plain(value.dict(), _depth + 1)
        except Exception:  # noqa: BLE001
            pass

    raw = getattr(value, "__dict__", None)
    if isinstance(raw, dict):
        return {
            k: plain(v, _depth + 1)
            for k, v in raw.items()
            if not k.startswith("_") and k not in ("__pydantic_extra__",)
        }

    return str(value)


def scalar(value: Any) -> Any:
    """Return ``value`` if it is a JSON scalar, else ``None``.

    Guards against SDK objects (and test doubles) that answer every attribute
    access with a live object.
    """
    return value if isinstance(value, (bool, int, float, str)) else None


def parse_arguments(arguments: Any) -> Optional[Any]:
    """Parse a JSON-string argument payload; ``None`` when it is not JSON."""
    if isinstance(arguments, (dict, list)):
        return arguments
    if not isinstance(arguments, str) or not arguments.strip():
        return None
    try:
        return json.loads(arguments)
    except (ValueError, TypeError):
        return None


def _arguments_text(arguments: Any) -> str:
    """Keep the exact string the model produced; stringify other shapes."""
    if isinstance(arguments, str):
        return arguments
    if arguments is None:
        return ""
    try:
        return json.dumps(plain(arguments), ensure_ascii=False, sort_keys=True)
    except Exception:  # noqa: BLE001
        return str(arguments)


def _get(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


# ---------------------------------------------------------------------------
# OpenAI
# ---------------------------------------------------------------------------

def openai_tool_calls(message: Any) -> List[Dict[str, Any]]:
    """Normalize ``message.tool_calls`` (list) into id / name / arguments.

    Returns an empty list when the model answered in text, which is the signal
    that no tool decision was made.
    """
    raw = _get(message, "tool_calls")
    if not isinstance(raw, (list, tuple)):
        return []
    calls: List[Dict[str, Any]] = []
    for call in raw:
        data = plain(call)
        if not isinstance(data, dict):
            continue
        function = data.get("function") if isinstance(data.get("function"), dict) else {}
        calls.append(
            {
                "id": scalar(data.get("id")) or "",
                "type": scalar(data.get("type")) or "function",
                "function": {
                    "name": scalar(function.get("name")) or "",
                    "arguments": _arguments_text(function.get("arguments")),
                },
            }
        )
    return calls


def openai_function_call(message: Any) -> Optional[Dict[str, Any]]:
    """Legacy pre-``tool_calls`` single function call, normalized the same way."""
    raw = _get(message, "function_call")
    if not isinstance(raw, (dict, list)):
        return None
    data = plain(raw)
    if not isinstance(data, dict) or not data.get("name"):
        return None
    return {
        "type": "function",
        "function": {
            "name": scalar(data.get("name")) or "",
            "arguments": _arguments_text(data.get("arguments")),
        },
    }


def openai_message(message: Any) -> Dict[str, Any]:
    """Serialize an assistant message, keeping tool calls and refusals."""
    out: Dict[str, Any] = {
        "role": scalar(_get(message, "role")) or "assistant",
        "content": plain(_get(message, "content", "")),
    }
    calls = openai_tool_calls(message)
    if calls:
        out["tool_calls"] = calls
    legacy = openai_function_call(message)
    if legacy:
        out["function_call"] = legacy
    refusal = scalar(_get(message, "refusal"))
    if refusal:
        out["refusal"] = refusal
    return out


def openai_choice(choice: Any) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "message": openai_message(_get(choice, "message")),
        "finish_reason": scalar(_get(choice, "finish_reason")),
    }
    index = scalar(_get(choice, "index"))
    if index is not None:
        out["index"] = index
    return out


def openai_response_meta(response: Any) -> Dict[str, Any]:
    """Server-side identity of the answer: which provider request, which model.

    ``model`` on the request is what the caller asked for. ``served_model`` is
    what actually answered, and can be a dated snapshot or a different alias.
    """
    meta: Dict[str, Any] = {}
    served = scalar(_get(response, "model"))
    if served:
        meta["served_model"] = served
    for field, key in (
        ("id", "response_id"),
        ("created", "created"),
        ("system_fingerprint", "system_fingerprint"),
    ):
        value = scalar(_get(response, field))
        if value not in (None, ""):
            meta[key] = value
    return meta


def _model_facing(value: Any) -> Any:
    """Settings echoed back into the record, without leaking SDK class objects."""
    data = plain(value)
    if isinstance(data, dict) and not data:
        return None
    if isinstance(data, list) and not data:
        return None
    if isinstance(data, str) and not data:
        return None
    # Anything that could only be rendered as ``str(obj)`` is a class or an
    # unserializable object; its repr names internal code, so leave it out.
    if isinstance(data, str) and not isinstance(value, str):
        return None
    if data is not None and not isinstance(data, (dict, list, str, int, float, bool)):
        return None
    return data


def _tool_specs(tools: Any) -> List[Dict[str, Any]]:
    """Names and descriptions of the tools the model was offered.

    The argument schema is the tool's own contract and stays with the code; the
    record captures what the model could choose between, which is what a
    reviewer asks about after the fact.
    """
    if not isinstance(tools, (list, tuple)):
        return []
    specs: List[Dict[str, Any]] = []
    for tool in tools:
        data = plain(tool)
        if not isinstance(data, dict):
            continue
        function = data.get("function") if isinstance(data.get("function"), dict) else data
        name = scalar(function.get("name"))
        if not name:
            continue
        spec: Dict[str, Any] = {"name": name}
        description = scalar(function.get("description"))
        if description:
            spec["description"] = description
        specs.append(spec)
    return specs


def openai_request_fields(kwargs: Dict[str, Any]) -> Dict[str, Any]:
    """Request settings that changed the answer, captured alongside the prompt."""
    out: Dict[str, Any] = {}
    for key in (
        "temperature",
        "top_p",
        "max_tokens",
        "max_completion_tokens",
        "seed",
        "response_format",
        "tool_choice",
        "presence_penalty",
        "frequency_penalty",
    ):
        if key in kwargs and kwargs[key] is not None:
            value = _model_facing(kwargs[key])
            if value is not None:
                out[key] = value
    tools = _tool_specs(kwargs.get("tools"))
    if tools:
        out["tools"] = tools
    if kwargs.get("parallel_tool_calls") is not None:
        out["parallel_tool_calls"] = bool(kwargs["parallel_tool_calls"])
    return out


# ---------------------------------------------------------------------------
# Anthropic
# ---------------------------------------------------------------------------

def anthropic_blocks(response: Any) -> List[Dict[str, Any]]:
    """Serialize content blocks, keeping ``tool_use`` decisions intact."""
    blocks = _get(response, "content")
    if not isinstance(blocks, (list, tuple)):
        return []
    out: List[Dict[str, Any]] = []
    for block in blocks:
        data = plain(block)
        if not isinstance(data, dict):
            out.append({"type": "unknown", "value": data})
            continue
        kind = scalar(data.get("type"))
        if kind == "text":
            out.append({"type": "text", "text": scalar(data.get("text")) or ""})
        elif kind == "tool_use":
            out.append(
                {
                    "type": "tool_use",
                    "id": scalar(data.get("id")) or "",
                    "name": scalar(data.get("name")) or "",
                    "input": data.get("input"),
                }
            )
        elif kind in ("thinking", "redacted_thinking"):
            out.append(data)
        else:
            # Never drop a block we do not recognize.
            out.append(data if kind else {"type": "unknown", "value": data})
    return out


def anthropic_response_meta(response: Any) -> Dict[str, Any]:
    meta: Dict[str, Any] = {}
    served = scalar(_get(response, "model"))
    if served:
        meta["served_model"] = served
    response_id = scalar(_get(response, "id"))
    if response_id:
        meta["response_id"] = response_id
    for field in ("stop_reason", "stop_sequence", "type"):
        value = scalar(_get(response, field))
        if value not in (None, ""):
            meta[field] = value
    return meta


def anthropic_request_fields(kwargs: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    # ``metadata`` is deliberately not captured: it commonly carries the
    # caller's end-user id, which has no business in a file handed to a
    # counterparty.
    for key in ("temperature", "top_p", "top_k", "max_tokens", "stop_sequences"):
        if key in kwargs and kwargs[key] is not None:
            value = _model_facing(kwargs[key])
            if value is not None:
                out[key] = value
    tools = _tool_specs(kwargs.get("tools"))
    if tools:
        out["tools"] = tools
    tool_choice = kwargs.get("tool_choice")
    if tool_choice is not None:
        value = _model_facing(tool_choice)
        if value is not None:
            out["tool_choice"] = value
    return out


# ---------------------------------------------------------------------------
# Shared
# ---------------------------------------------------------------------------

def tool_call_summary(tool_calls: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Flat, readable decisions for the top of an ``llm.response`` step.

    ``arguments`` is the exact string the model produced; ``arguments_parsed``
    is the same payload decoded, so a reader can see ``reason: excluded peril``
    without writing a JSON parser.
    """
    summary: List[Dict[str, Any]] = []
    for call in tool_calls:
        function = call.get("function") or {}
        arguments = function.get("arguments", "")
        entry: Dict[str, Any] = {
            "id": call.get("id", ""),
            "name": function.get("name", ""),
            "arguments": arguments,
        }
        parsed = parse_arguments(arguments)
        if parsed is not None:
            entry["arguments_parsed"] = parsed
        summary.append(entry)
    return summary
