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
        if session is None and os.getenv("EPI_QUIET", "0") != "1":
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
            session.log_step("llm.request", {
                "provider": self._provider,
                "model": model,
                "messages": messages,
                "timestamp": utc_now_iso(),
            })
        
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
        
        # Log request if session is active
        if session:
            session.log_step("llm.request", {
                "provider": self._provider,
                "model": model,
                "messages": messages,
                "stream": True,
                "timestamp": utc_now_iso(),
            })
        
        # Force stream=True
        kwargs["stream"] = True
        
        start_time = time.time()
        accumulated_content = []
        finish_reason = None
        usage = None
        
        try:
            stream = self._completions.create(*args, **kwargs)
            
            for chunk in stream:
                # Accumulate content from delta
                if hasattr(chunk, "choices") and chunk.choices:
                    delta = chunk.choices[0].delta
                    if hasattr(delta, "content") and delta.content:
                        accumulated_content.append(delta.content)
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
                response_data = {
                    "provider": self._provider,
                    "model": model,
                    "choices": [{
                        "message": {
                            "role": "assistant",
                            "content": "".join(accumulated_content),
                        },
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
