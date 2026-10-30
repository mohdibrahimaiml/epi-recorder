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
from epi_recorder.wrappers._extract import (
    anthropic_blocks,
    anthropic_request_fields,
    anthropic_response_meta,
    parse_arguments,
    scalar,
)


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
            # Everything else that shaped the answer: top_k, stop_sequences,
            # and the tools the model was offered.
            for key, value in anthropic_request_fields(kwargs).items():
                request_data.setdefault(key, value)

            session.log_step("llm.request", request_data)
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
            response = self._messages.create(*args, **kwargs)
            latency = time.time() - start_time
            
            # Log response if session is active
            if session:
                # Every block, not just text: a tool_use block is the decision.
                content = anthropic_blocks(response)

                # Extract usage
                usage = None
                usage_obj = getattr(response, "usage", None)
                if usage_obj is not None:
                    usage = {
                        "input_tokens": scalar(getattr(usage_obj, "input_tokens", None)),
                        "output_tokens": scalar(getattr(usage_obj, "output_tokens", None)),
                    }
                    if all(v is None for v in usage.values()):
                        usage = None

                response_data = {
                    "provider": self._provider,
                    "model": model,
                    "role": scalar(getattr(response, "role", None)) or "assistant",
                    "content": content,
                    "usage": usage,
                    "latency_seconds": round(latency, 3),
                    "timestamp": utc_now_iso(),
                }
                # Which provider request answered, and which model version.
                response_data.update(anthropic_response_meta(response))
                tool_uses = [b for b in content if b.get("type") == "tool_use"]
                if tool_uses:
                    response_data["tool_uses"] = [
                        {"id": b.get("id", ""), "name": b.get("name", ""), "input": b.get("input")}
                        for b in tool_uses
                    ]

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
    
    def stream(self, *args, **kwargs):
        """
        Stream messages with automatic EPI tracing.
        
        Note: Streaming responses are logged after completion.
        """
        session = self._get_session()
        
        # Extract request info
        model = kwargs.get("model", "unknown")
        messages = kwargs.get("messages", [])
        stream_request_fields = anthropic_request_fields(kwargs)

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
                **stream_request_fields,
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
        
        start_time = time.time()
        accumulated_text = []
        accumulated_tool_blocks: list[dict] = []
        usage_accum: dict | None = None
        served_model: str | None = None
        response_id: str | None = None
        stop_reason: str | None = None
        
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
                # message_start carries the provider request id and served model;
                # message_delta carries stop_reason.
                message = getattr(chunk, "message", None)
                if message is not None:
                    served_model = served_model or scalar(getattr(message, "model", None))
                    response_id = response_id or scalar(getattr(message, "id", None))
                delta = getattr(chunk, "delta", None)
                if delta is not None:
                    stop_reason = stop_reason or scalar(getattr(delta, "stop_reason", None))
                
                yield chunk
            
            latency = time.time() - start_time
            
            # Log complete response after streaming
            if session:
                content_blocks: list[dict] = []
                if accumulated_text:
                    content_blocks.append({"type": "text", "text": "".join(accumulated_text)})
                for block in accumulated_tool_blocks:
                    # input_json arrives as a raw string in deltas; decode it so
                    # the decision's arguments are readable, keep the raw text.
                    parsed_block = dict(block)
                    raw_json = parsed_block.get("input_json")
                    if raw_json:
                        parsed = parse_arguments(raw_json)
                        if parsed is not None:
                            parsed_block["input"] = parsed
                    content_blocks.append(parsed_block)

                response_data = {
                    "provider": self._provider,
                    "model": model,
                    "role": "assistant",
                    "content": content_blocks,
                    "usage": usage_accum,
                    "stream": True,
                    "latency_seconds": round(latency, 3),
                    "timestamp": utc_now_iso(),
                }
                if served_model:
                    response_data["served_model"] = served_model
                if response_id:
                    response_data["response_id"] = response_id
                if stop_reason:
                    response_data["stop_reason"] = stop_reason
                if accumulated_tool_blocks:
                    response_data["tool_uses"] = [
                        {"id": b.get("id", ""), "name": b.get("name", ""), "input": b.get("input")}
                        for b in content_blocks
                        if b.get("type") == "tool_use"
                    ]
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
