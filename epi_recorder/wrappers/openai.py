"""
OpenAI wrapper for EPI tracing.

Provides a proxy wrapper that automatically logs all LLM calls
without monkey patching.
"""

import os
import time
import warnings
from typing import Any

from epi_core.time_utils import utc_now_iso
from epi_recorder.wrappers.base import TracedClientBase
from epi_recorder.wrappers._extract import (
    openai_choice,
    openai_request_fields,
    openai_response_meta,
    scalar,
    tool_call_summary,
)


def _openai_usage(usage_obj: Any) -> dict | None:
    """Token counts, or ``None`` when the provider did not report any."""
    if usage_obj is None:
        return None
    usage = {
        "prompt_tokens": scalar(getattr(usage_obj, "prompt_tokens", None)),
        "completion_tokens": scalar(getattr(usage_obj, "completion_tokens", None)),
        "total_tokens": scalar(getattr(usage_obj, "total_tokens", None)),
    }
    return usage if any(v is not None for v in usage.values()) else None


class TracedCompletions:
    """Proxy wrapper for openai.chat.completions."""
    
    def __init__(self, completions: Any, provider: str = "openai"):
        self._completions = completions
        self._provider = provider
    
    def _get_session(self):
        """Get the current active EPI recording session."""
        from epi_recorder.api import get_current_session
        return get_current_session()
    
    def create(self, *args, **kwargs) -> Any:
        """
        Create a chat completion with automatic EPI tracing.

        All arguments are passed through to the underlying client.
        Automatically routes to streaming handler when stream=True.
        """
        session = self._get_session()

        # Warn on every call path (non-streaming and streaming) so the
        # developer sees the message regardless of how they use the client.
        if session is None:
            if os.getenv("EPI_ENFORCE") == "1":
                raise RuntimeError("EPI_ENFORCE=1: wrap_openai() call rejected - no record() context")
            elif os.getenv("EPI_QUIET", "0") != "1":
                warnings.warn(
                "wrap_openai() call detected outside a record() context — no evidence will be captured. "
                "Did you forget `with record('my_agent.epi'):`? "
                "Set EPI_QUIET=1 to suppress this warning.",
                stacklevel=2,
            )

        # Route streaming calls to dedicated handler
        if kwargs.get("stream", False):
            return self._create_streaming(*args, **kwargs)

        # Extract request info
        model = kwargs.get("model", "unknown")
        messages = kwargs.get("messages", [])
        # Settings that changed the answer, and the tools the model could pick
        # from. Without these a reader cannot tell what the model was allowed
        # to decide.
        request_fields = openai_request_fields(kwargs)

        # Log request if session is active
        if session:
            import hashlib as _hashlib
            import json as _json
            try:
                _canonical_msg = _json.dumps(messages, sort_keys=True, ensure_ascii=False, default=str)
            except Exception:
                _canonical_msg = str(messages)
            pre_hash_hex = _hashlib.sha256((_canonical_msg + str(model)).encode("utf-8")).hexdigest()
            session.log_step("llm.request", {
                "provider": self._provider,
                "model": model,
                "messages": messages,
                "timestamp": utc_now_iso(),
                "pre_commit_hash": pre_hash_hex,
                **request_fields,
            })
            # Pre-execution commitment: log intent before the API call fires.
            session.log_step("llm.pre_commit", {
                "provider": self._provider,
                "model": model,
                "messages_hash": pre_hash_hex,
                "message_count": len(messages),
                "timestamp": utc_now_iso(),
            })
            # NOTE: per-call TSA anchoring was attempted here (notarize the
            # pre-commit hash on every LLM call) and deliberately removed.
            # A network round-trip to an external authority in the path of
            # every model call makes recorder reliability hostage to TSA
            # uptime. Heartbeat checkpoints (epi_core/checkpoints.py) provide
            # the same forward-security property at a fraction of the
            # coupling. See docs/THREAT_MODEL.md Assumptions.
        
        # Call original method
        start_time = time.time()
        try:
            response = self._completions.create(*args, **kwargs)
            latency = time.time() - start_time
            
            # Log response if session is active
            if session:
                # Extract response content, including tool calls: for most
                # agents the tool call *is* the decision.
                raw_choices = getattr(response, "choices", None)
                if not isinstance(raw_choices, (list, tuple)):
                    raw_choices = []
                choices = [openai_choice(choice) for choice in raw_choices]

                decisions = [
                    call
                    for choice in choices
                    for call in choice["message"].get("tool_calls", [])
                ]

                # Extract usage
                usage = _openai_usage(getattr(response, "usage", None))

                response_data = {
                    "provider": self._provider,
                    "model": model,
                    "choices": choices,
                    "usage": usage,
                    "latency_seconds": round(latency, 3),
                    "timestamp": utc_now_iso(),
                }
                # Which provider request answered, and which model version.
                response_data.update(openai_response_meta(response))
                if decisions:
                    response_data["tool_calls"] = tool_call_summary(decisions)

                session.log_step("llm.response", response_data)
            
            return response
            
        except Exception as e:
            latency = time.time() - start_time
            
            # Log error if session is active
            if session:
                session.log_step("llm.error", {
                    "provider": self._provider,
                    "model": model,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "latency_seconds": round(latency, 3),
                    "timestamp": utc_now_iso(),
                })
            
            raise

    def _create_streaming(self, *args, **kwargs) -> Any:
        """
        Create a streaming chat completion with automatic EPI tracing.
        
        Yields chunks while accumulating the full response for logging.
        After streaming completes, logs the assembled response.
        """
        session = self._get_session()
        
        # Extract request info
        model = kwargs.get("model", "unknown")
        messages = kwargs.get("messages", [])
        request_fields = openai_request_fields(kwargs)

        # Log request + pre_commit for streaming (was missing)
        if session:
            import hashlib as _hashlib2
            import json as _json2
            try:
                _canonical_msg2 = _json2.dumps(messages, sort_keys=True, ensure_ascii=False, default=str)
            except Exception:
                _canonical_msg2 = str(messages)
            pre_hash_hex2 = _hashlib2.sha256((_canonical_msg2 + str(model)).encode("utf-8")).hexdigest()
            session.log_step("llm.request", {
                "provider": self._provider,
                "model": model,
                "messages": messages,
                "stream": True,
                "timestamp": utc_now_iso(),
                "pre_commit_hash": pre_hash_hex2,
                **request_fields,
            })
            session.log_step("llm.pre_commit", {
                "provider": self._provider,
                "model": model,
                "messages_hash": pre_hash_hex2,
                "message_count": len(messages),
                "stream": True,
                "timestamp": utc_now_iso(),
            })
            # NOTE: per-call TSA anchoring was attempted here and deliberately
            # removed — see note above. Heartbeat checkpoints supersede it.
        
        # Force stream=True
        kwargs["stream"] = True
        
        start_time = time.time()
        accumulated_content = []
        accumulated_tool_calls: dict[int, dict] = {}
        accumulated_reasoning: list[str] = []
        finish_reason = None
        usage = None
        served_model = None
        response_id = None
        system_fingerprint = None
        created = None
        
        try:
            stream = self._completions.create(*args, **kwargs)
            
            for chunk in stream:
                # Accumulate content + tool_calls + reasoning from delta
                if hasattr(chunk, "choices") and chunk.choices:
                    delta = chunk.choices[0].delta
                    if hasattr(delta, "content") and delta.content:
                        accumulated_content.append(delta.content)
                    # Tool calls in streaming delta
                    if hasattr(delta, "tool_calls") and delta.tool_calls:
                        for tc in delta.tool_calls:
                            idx = getattr(tc, "index", 0) or 0
                            entry = accumulated_tool_calls.setdefault(idx, {"id": "", "type": "function", "function": {"name": "", "arguments": ""}})
                            if getattr(tc, "id", None):
                                entry["id"] = tc.id
                            if getattr(tc, "type", None):
                                entry["type"] = tc.type
                            if getattr(tc, "function", None):
                                fn = tc.function
                                if getattr(fn, "name", None):
                                    entry["function"]["name"] = fn.name
                                if getattr(fn, "arguments", None):
                                    entry["function"]["arguments"] += fn.arguments
                    # Legacy function_call
                    if hasattr(delta, "function_call") and delta.function_call:
                        fc = delta.function_call
                        accumulated_tool_calls.setdefault(0, {"id": "", "type": "function", "function": {"name": "", "arguments": ""}})
                        if getattr(fc, "name", None):
                            accumulated_tool_calls[0]["function"]["name"] = fc.name
                        if getattr(fc, "arguments", None):
                            accumulated_tool_calls[0]["function"]["arguments"] += fc.arguments
                    # Reasoning / refusal
                    if hasattr(delta, "reasoning") and getattr(delta, "reasoning", None):
                        accumulated_reasoning.append(str(delta.reasoning))
                    if hasattr(delta, "refusal") and getattr(delta, "refusal", None):
                        accumulated_reasoning.append(str(delta.refusal))
                    if hasattr(chunk.choices[0], "finish_reason") and chunk.choices[0].finish_reason:
                        finish_reason = chunk.choices[0].finish_reason
                
                # Server-side identity arrives on every chunk; keep the first
                # non-empty value seen.
                served_model = served_model or scalar(getattr(chunk, "model", None))
                response_id = response_id or scalar(getattr(chunk, "id", None))
                system_fingerprint = system_fingerprint or scalar(
                    getattr(chunk, "system_fingerprint", None)
                )
                created = created if created is not None else scalar(
                    getattr(chunk, "created", None)
                )

                # Check for usage in final chunk (OpenAI sends it with stream_options)
                reported_usage = _openai_usage(getattr(chunk, "usage", None))
                if reported_usage:
                    usage = reported_usage
                
                yield chunk
            
            latency = time.time() - start_time
            
            # Log assembled response after streaming completes
            if session:
                msg: dict = {
                    "role": "assistant",
                    "content": "".join(accumulated_content),
                }
                tool_calls = [accumulated_tool_calls[k] for k in sorted(accumulated_tool_calls)]
                if tool_calls:
                    msg["tool_calls"] = tool_calls
                if accumulated_reasoning:
                    msg["reasoning"] = "".join(accumulated_reasoning)
                response_data = {
                    "provider": self._provider,
                    "model": model,
                    "choices": [{
                        "message": msg,
                        "finish_reason": finish_reason,
                    }],
                    "stream": True,
                    "latency_seconds": round(latency, 3),
                    "timestamp": utc_now_iso(),
                }
                if served_model:
                    response_data["served_model"] = served_model
                if response_id:
                    response_data["response_id"] = response_id
                if system_fingerprint:
                    response_data["system_fingerprint"] = system_fingerprint
                if created is not None:
                    response_data["created"] = created
                if tool_calls:
                    response_data["tool_calls"] = tool_call_summary(tool_calls)
                if usage:
                    response_data["usage"] = usage
                
                session.log_step("llm.response", response_data)
        
        except Exception as e:
            latency = time.time() - start_time
            
            if session:
                session.log_step("llm.error", {
                    "provider": self._provider,
                    "model": model,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "stream": True,
                    "latency_seconds": round(latency, 3),
                    "timestamp": utc_now_iso(),
                })
            
            
            raise


class TracedChat:
    """Proxy wrapper for openai.chat."""
    
    def __init__(self, chat: Any, provider: str = "openai"):
        self._chat = chat
        self._provider = provider
        self.completions = TracedCompletions(chat.completions, provider)


class TracedOpenAI(TracedClientBase):
    """
    Traced OpenAI client wrapper.
    
    Wraps an OpenAI client and automatically logs all LLM calls
    to the active EPI recording session.
    
    Usage:
        from openai import OpenAI
        from epi_recorder.wrappers import wrap_openai
        
        client = wrap_openai(OpenAI())
        
        with record("my_agent.epi"):
            response = client.chat.completions.create(
                model="gpt-4",
                messages=[{"role": "user", "content": "Hello"}]
            )
    """
    
    def __init__(self, client: Any, provider: str = "openai"):
        """
        Initialize traced OpenAI client.
        
        Args:
            client: OpenAI client instance
            provider: Provider name for logging (default: "openai")
        """
        super().__init__(client)
        self._provider = provider
        self.chat = TracedChat(client.chat, provider)
    
    def __getattr__(self, name: str) -> Any:
        """
        Forward attribute access to underlying client.
        
        This allows access to non-chat APIs (embeddings, files, etc.)
        without explicit wrapping.
        """
        return getattr(self._client, name)


def wrap_openai(client: Any, provider: str = "openai") -> TracedOpenAI:
    """
    Wrap an OpenAI client for EPI tracing.
    
    Args:
        client: OpenAI client instance
        provider: Provider name for logging (default: "openai")
        
    Returns:
        TracedOpenAI wrapper
        
    Usage:
        from openai import OpenAI
        from epi_recorder.wrappers import wrap_openai
        
        # Wrap the client once
        client = wrap_openai(OpenAI())
        
        # Use normally - calls are automatically traced when inside record()
        with record("my_agent.epi"):
            response = client.chat.completions.create(...)
    """
    return TracedOpenAI(client, provider)
