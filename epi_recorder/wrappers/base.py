"""
Base classes for EPI traced clients.
"""

from abc import ABC
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
    
    def _get_session(self):
        """Get the current active EPI recording session."""
        from epi_recorder.api import get_current_session
        return get_current_session()
    
    def _log_request(self, provider: str, model: str, messages: list, **kwargs) -> None:
        """Log an LLM request to the active session."""
        session = self._get_session()
        if session:
            session.log_step("llm.request", {
                "provider": provider,
                "model": model,
                "messages": messages,
                "timestamp": utc_now_iso(),
                **kwargs
            })
    
    def _log_response(
        self, 
        provider: str, 
        model: str, 
        content: str,
        usage: Optional[dict] = None,
        latency_seconds: Optional[float] = None,
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
            session.log_step("llm.response", response_data)
    
    def _log_error(self, provider: str, error: Exception, **kwargs) -> None:
        """Log an LLM error to the active session."""
        session = self._get_session()
        if session:
            session.log_step("llm.error", {
                "provider": provider,
                "error": str(error),
                "error_type": type(error).__name__,
                "timestamp": utc_now_iso(),
                **kwargs
            })
