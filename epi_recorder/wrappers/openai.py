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
            })
            # Pre-execution commitment: log intent before the API call fires.
            session.log_step("llm.pre_commit", {
                "provider": self._provider,
                "model": model,
                "messages_hash": pre_hash_hex,
                "message_count": len(messages),
                "timestamp": utc_now_iso(),
            })
            try:
                from epi_core.notarize import notarize_hash
                self._last_pre_commit_ts = notarize_hash(pre_hash_hex, label="llm.pre_commit")
                # Bind TSA receipt into the pre_commit step content if available
                if isinstance(self._last_pre_commit_ts, dict) and self._last_pre_commit_ts.get("tsa_token"):
                    session.log_step("llm.pre_commit_notarized", {
                        "provider": self._provider,
                        "hash": pre_hash_hex,
                        "receipt": self._last_pre_commit_ts,
                        "timestamp": utc_now_iso(),
                    })
            except Exception:
                self._last_pre_commit_ts = {"notarization_attempted": True, "notarization_status": "error"}
        
        # Call original method
        start_time = time.time()
        try:
            response = self._completions.create(*args, **kwargs)
            latency = time.time() - start_time
            
            # Log response if session is active
            if session:
                # Extract response content
                choices = []
                for choice in response.choices:
                    msg = choice.message
                    choices.append({
                        "message": {
                            "role": getattr(msg, "role", "assistant"),
                            "content": getattr(msg, "content", ""),
                        },
                        "finish_reason": getattr(choice, "finish_reason", None),
                    })
                
                # Extract usage
                usage = None
                if hasattr(response, "usage") and response.usage:
                    usage = {
                        "prompt_tokens": getattr(response.usage, "prompt_tokens", 0),
                        "completion_tokens": getattr(response.usage, "completion_tokens", 0),
                        "total_tokens": getattr(response.usage, "total_tokens", 0),
                    }
                
                session.log_step("llm.response", {
                    "provider": self._provider,
                    "model": model,
                    "choices": choices,
                    "usage": usage,
                    "latency_seconds": round(latency, 3),
                    "timestamp": utc_now_iso(),
                })
            
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
            })
            session.log_step("llm.pre_commit", {
                "provider": self._provider,
                "model": model,
                "messages_hash": pre_hash_hex2,
                "message_count": len(messages),
                "stream": True,
                "timestamp": utc_now_iso(),
            })
            try:
                from epi_core.notarize import notarize_hash as _notarize2
                self._last_pre_commit_ts = _notarize2(pre_hash_hex2, label="llm.pre_commit")
            except Exception:
                self._last_pre_commit_ts = {"notarization_attempted": True, "notarization_status": "error"}
        
        # Force stream=True
        kwargs["stream"] = True
        
        start_time = time.time()
        accumulated_content = []
        accumulated_tool_calls: dict[int, dict] = {}
        accumulated_reasoning: list[str] = []
        finish_reason = None
        usage = None
        
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
                
                # Check for usage in final chunk (OpenAI sends it with stream_options)
                if hasattr(chunk, "usage") and chunk.usage:
                    usage = {
                        "prompt_tokens": getattr(chunk.usage, "prompt_tokens", 0),
                        "completion_tokens": getattr(chunk.usage, "completion_tokens", 0),
                        "total_tokens": getattr(chunk.usage, "total_tokens", 0),
                    }
                
                yield chunk
            
            latency = time.time() - start_time
            
            # Log assembled response after streaming completes
            if session:
                msg: dict = {
                    "role": "assistant",
                    "content": "".join(accumulated_content),
                }
                if accumulated_tool_calls:
                    msg["tool_calls"] = [accumulated_tool_calls[k] for k in sorted(accumulated_tool_calls)]
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
