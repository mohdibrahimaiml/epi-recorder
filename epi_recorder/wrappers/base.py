"""
Base classes for EPI traced clients.

Deprecated for new integrations: these helpers cannot mint or pair
``epi-operation/v1`` identity on their own (they hold no per-operation state),
so steps logged through them are audited as name-based only. Use
``epi_recorder.wrappers.openai`` / ``anthropic`` or ``AgentRun.operation``
instead. ``correlation=`` is accepted here so a subclass that does own the
identity can pass it through.
"""

from abc import ABC
import os
from typing import Any, Optional

from epi_core.time_utils import utc_now_iso


class TracedClientBase(ABC):
    """
    Base class for traced LLM client wrappers.
    
    Provides common functionality for logging LLM calls
    to the active EPI recording session.
    """
    
    def __init__(self, client: Any):
        """
        Initialize traced client wrapper.
        
        Args:
            client: The original LLM client to wrap
        """
        self._client = client
    
    def _get_session(self, enforce=False):
        from epi_recorder.api import get_current_session
        session = get_current_session()
        if session is None and (enforce or os.getenv("EPI_ENFORCE") == "1"):
            raise RuntimeError("EPI_ENFORCE=1: LLM call outside record() context rejected")
        return session
    
    def _log_request(
        self,
        provider: str,
        model: str,
        messages: list,
        *,
        correlation: dict | None = None,
        **kwargs,
    ) -> None:
        """Log an LLM request to the active session."""
        session = self._get_session()
        if session:
            content = {
                "provider": provider,
                "model": model,
                "messages": messages,
                "timestamp": utc_now_iso(),
                **kwargs,
            }
            if correlation is not None:
                content["correlation"] = correlation
            session.log_step("llm.request", content)
    
    def _log_response(
        self, 
        provider: str, 
        model: str, 
        content: str,
        usage: Optional[dict] = None,
        latency_seconds: Optional[float] = None,
        *,
        correlation: dict | None = None,
        **kwargs
    ) -> None:
        """Log an LLM response to the active session."""
        session = self._get_session()
        if session:
            response_data = {
                "provider": provider,
                "model": model,
                "choices": [{"message": {"role": "assistant", "content": content}}],
                "timestamp": utc_now_iso(),
            }
            if usage:
                response_data["usage"] = usage
            if latency_seconds is not None:
                response_data["latency_seconds"] = round(latency_seconds, 3)
            response_data.update(kwargs)
            if correlation is not None:
                response_data["correlation"] = correlation
            session.log_step("llm.response", response_data)
    
    def _log_error(
        self,
        provider: str,
        error: Exception,
        *,
        correlation: dict | None = None,
        **kwargs,
    ) -> None:
        """Log an LLM error to the active session."""
        session = self._get_session()
        if session:
            content = {
                "provider": provider,
                "error": str(error),
                "error_type": type(error).__name__,
                "timestamp": utc_now_iso(),
                **kwargs,
            }
            if correlation is not None:
                content["correlation"] = correlation
            session.log_step("llm.error", content)
