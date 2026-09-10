"""
Anthropic wrapper for EPI tracing.

Provides a proxy wrapper that automatically logs all Claude API calls
without monkey patching.
"""

import os
import time
import warnings
from typing import Any

from epi_core.time_utils import utc_now_iso
from epi_recorder.wrappers.base import TracedClientBase


class TracedMessages:
    """Proxy wrapper for anthropic.messages."""
    
    def __init__(self, messages: Any):
        self._messages = messages
        self._provider = "anthropic"
    
    def _get_session(self):
        """Get the current active EPI recording session."""
        from epi_recorder.api import get_current_session
        return get_current_session()
    
    def create(self, *args, **kwargs) -> Any:
        """
        Create a message with automatic EPI tracing.
        
        All arguments are passed through to the underlying client.
        """
        session = self._get_session()
        
        # Extract request info
        model = kwargs.get("model", "unknown")
        messages = kwargs.get("messages", [])
        max_tokens = kwargs.get("max_tokens", None)
        temperature = kwargs.get("temperature", None)
        top_p = kwargs.get("top_p", None)
        system = kwargs.get("system", None)
        
        if session is None and os.getenv("EPI_QUIET", "0") != "1":
            warnings.warn(
                "wrap_anthropic() call detected outside a record() context — no evidence will be captured. "
                "Did you forget `with record('my_agent.epi'):`? "
                "Set EPI_QUIET=1 to suppress this warning.",
                stacklevel=2,
            )

        # Log request if session is active
        if session:
            import hashlib as _hashlib
            import json as _json
            try:
                _canonical_msg = _json.dumps(messages, sort_keys=True, ensure_ascii=False, default=str)
            except Exception:
                _canonical_msg = str(messages)
            pre_hash_hex = _hashlib.sha256((_canonical_msg + str(model)).encode("utf-8")).hexdigest()
            request_data = {
                "provider": self._provider,
                "model": model,
                "messages": messages,
                "max_tokens": max_tokens,
                "timestamp": utc_now_iso(),
                "pre_commit_hash": pre_hash_hex,
            }
            
            # Add optional parameters if present
            if temperature is not None:
                request_data["temperature"] = temperature
            if top_p is not None:
                request_data["top_p"] = top_p
            if system is not None:
                request_data["system"] = system
            
            session.log_step("llm.request", request_data)
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
            except Exception:
                self._last_pre_commit_ts = {"notarization_attempted": True, "notarization_status": "error"}
        
        # Call original method
        start_time = time.time()
        try:
            response = self._messages.create(*args, **kwargs)
            latency = time.time() - start_time
            
            # Log response if session is active
            if session:
                # Extract response content
                content = []
                for block in response.content:
                    if hasattr(block, "text"):
                        content.append({
                            "type": "text",
                            "text": block.text
                        })
                
                # Extract usage
                usage = None
                if hasattr(response, "usage") and response.usage:
                    usage = {
                        "input_tokens": getattr(response.usage, "input_tokens", 0),
                        "output_tokens": getattr(response.usage, "output_tokens", 0),
                    }
                
                session.log_step("llm.response", {
                    "provider": self._provider,
                    "model": model,
                    "role": getattr(response, "role", "assistant"),
                    "content": content,
                    "usage": usage,
                    "stop_reason": getattr(response, "stop_reason", None),
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
    
    def stream(self, *args, **kwargs):
        """
        Stream messages with automatic EPI tracing.
        
        Note: Streaming responses are logged after completion.
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
        
        start_time = time.time()
        accumulated_text = []
        accumulated_tool_blocks: list[dict] = []
        usage_accum: dict | None = None
        
        try:
            # Stream the response
            stream = self._messages.create(*args, **kwargs, stream=True)
            
            for chunk in stream:
                # Accumulate text for logging
                if hasattr(chunk, "delta") and hasattr(chunk.delta, "text") and chunk.delta.text:
                    accumulated_text.append(chunk.delta.text)
                # Tool use blocks (Anthropic streams tool_use deltas as content_block_delta with type tool_use)
                if hasattr(chunk, "content_block") and getattr(chunk.content_block, "type", None) == "tool_use":
                    accumulated_tool_blocks.append({"type": "tool_use", "id": getattr(chunk.content_block, "id", ""), "name": getattr(chunk.content_block, "name", "")})
                if hasattr(chunk, "delta") and hasattr(chunk.delta, "partial_json") and chunk.delta.partial_json:
                    if accumulated_tool_blocks:
                        accumulated_tool_blocks[-1].setdefault("input_json", "")
                        accumulated_tool_blocks[-1]["input_json"] += str(chunk.delta.partial_json)
                # Usage from message_delta
                if hasattr(chunk, "usage") and chunk.usage:
                    usage_accum = {
                        "input_tokens": getattr(chunk.usage, "input_tokens", 0),
                        "output_tokens": getattr(chunk.usage, "output_tokens", 0),
                    }
                if hasattr(chunk, "message") and getattr(chunk.message, "usage", None):
                    usage_accum = {
                        "input_tokens": getattr(chunk.message.usage, "input_tokens", 0),
                        "output_tokens": getattr(chunk.message.usage, "output_tokens", 0),
                    }
                
                yield chunk
            
            latency = time.time() - start_time
            
            # Log complete response after streaming
            if session:
                content_blocks: list[dict] = []
                if accumulated_text:
                    content_blocks.append({"type": "text", "text": "".join(accumulated_text)})
                content_blocks.extend(accumulated_tool_blocks)
                session.log_step("llm.response", {
                    "provider": self._provider,
                    "model": model,
                    "role": "assistant",
                    "content": content_blocks,
                    "usage": usage_accum,
                    "stream": True,
                    "latency_seconds": round(latency, 3),
                    "timestamp": utc_now_iso(),
                })
                
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


class TracedAnthropic(TracedClientBase):
    """
    Traced Anthropic client wrapper.
    
    Wraps an Anthropic client and automatically logs all Claude API calls
    to the active EPI recording session.
    
    Usage:
        from anthropic import Anthropic
        from epi_recorder.wrappers import wrap_anthropic
        
        client = wrap_anthropic(Anthropic())
        
        with record("my_agent.epi"):
            response = client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=1024,
                messages=[{"role": "user", "content": "Hello, Claude!"}]
            )
    """
    
    def __init__(self, client: Any):
        """
        Initialize traced Anthropic client.
        
        Args:
            client: Anthropic client instance
        """
        super().__init__(client)
        self.messages = TracedMessages(client.messages)
    
    def __getattr__(self, name: str) -> Any:
        """
        Forward attribute access to underlying client.
        
        This allows access to non-message APIs without explicit wrapping.
        """
        return getattr(self._client, name)


def wrap_anthropic(client: Any) -> TracedAnthropic:
    """
    Wrap an Anthropic client for EPI tracing.
    
    Args:
        client: Anthropic client instance
        
    Returns:
        TracedAnthropic wrapper
        
    Usage:
        from anthropic import Anthropic
        from epi_recorder.wrappers import wrap_anthropic
        
        # Wrap the client once
        client = wrap_anthropic(Anthropic(api_key="your-key"))
        
        # Use normally - calls are automatically traced when inside record()
        with record("claude_conversation.epi"):
            response = client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=1024,
                messages=[{"role": "user", "content": "Explain quantum computing"}]
            )
    """
    return TracedAnthropic(client)
