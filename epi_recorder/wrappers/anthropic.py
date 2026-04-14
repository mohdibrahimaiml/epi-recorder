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
            request_data = {
                "provider": self._provider,
                "model": model,
                "messages": messages,
                "max_tokens": max_tokens,
                "timestamp": utc_now_iso(),
            }
            
            # Add optional parameters if present
            if temperature is not None:
                request_data["temperature"] = temperature
            if top_p is not None:
                request_data["top_p"] = top_p
            if system is not None:
                request_data["system"] = system
            
            session.log_step("llm.request", request_data)
        
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
        
        # Log request if session is active
        if session:
            session.log_step("llm.request", {
                "provider": self._provider,
                "model": model,
                "messages": messages,
                "stream": True,
                "timestamp": utc_now_iso(),
            })
        
        start_time = time.time()
        accumulated_text = []
        
        try:
            # Stream the response
            stream = self._messages.create(*args, **kwargs, stream=True)
            
            for chunk in stream:
                # Accumulate text for logging
                if hasattr(chunk, "delta") and hasattr(chunk.delta, "text"):
                    accumulated_text.append(chunk.delta.text)
                
                yield chunk
            
            latency = time.time() - start_time
            
            # Log complete response after streaming
            if session:
                session.log_step("llm.response", {
                    "provider": self._provider,
                    "model": model,
                    "role": "assistant",
                    "content": [{
                        "type": "text",
                        "text": "".join(accumulated_text)
                    }],
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
