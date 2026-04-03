"""
LiteLLM Integration for EPI Recorder

Provides a custom callback that automatically logs all LLM calls
made through LiteLLM to the active EPI recording session.

Covers 100+ LLM providers in a single integration:
  OpenAI, Anthropic, Azure, Google, Groq, Mistral, Cohere,
  Ollama, Hugging Face, Bedrock, and many more.

Usage:
    import litellm
    from epi_recorder.integrations.litellm import EPICallback

    # Option 1: Set as global callback
    litellm.success_callback = [EPICallback()]
    litellm.failure_callback = [EPICallback()]

    # Option 2: One-liner setup
    from epi_recorder.integrations.litellm import enable_epi
    enable_epi()  # Sets callbacks automatically

    # Then record as usual
    from epi_recorder import record

    with record("my_agent.epi"):
        response = litellm.completion(
            model="gpt-4",
            messages=[{"role": "user", "content": "Hello"}]
        )
"""

import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


class EPICallback:
    """
    LiteLLM custom callback for EPI recording.

    Implements LiteLLM's callback interface to automatically log
    all LLM calls (success, failure, streaming) to the active
    EPI recording session.

    Supports:
    - Synchronous and async completions
    - Streaming responses
    - All 100+ LiteLLM providers
    - Token usage and cost tracking
    - Error logging with full context
    """

    def __init__(self, provider_label: str = "litellm"):
        """
        Initialize EPI callback.

        Args:
            provider_label: Provider name prefix in logged steps.
                            The actual provider (openai, anthropic, etc.)
                            is appended automatically.
        """
        self._provider_label = provider_label

    def _get_session(self):
        """Get the current active EPI recording session."""
        try:
            from epi_recorder.api import get_current_session
            return get_current_session()
        except ImportError:
            return None

    def _extract_provider(self, kwargs: Dict[str, Any]) -> str:
        """Extract the actual provider from LiteLLM kwargs."""
        model = kwargs.get("model", "unknown")
        # LiteLLM uses format: provider/model (e.g., "anthropic/claude-3")
        if "/" in model:
            return model.split("/")[0]
        # Fallback: check for custom_llm_provider
        return kwargs.get("litellm_params", {}).get(
            "custom_llm_provider", self._provider_label
        )

    def _extract_messages(self, kwargs: Dict[str, Any]) -> List[Dict]:
        """Extract messages from LiteLLM kwargs."""
        messages = kwargs.get("messages", [])
        # Ensure messages are serializable dicts
        result = []
        for msg in messages:
            if isinstance(msg, dict):
                result.append(msg)
            elif hasattr(msg, "model_dump"):
                result.append(msg.model_dump())
            else:
                result.append({"role": "unknown", "content": str(msg)})
        return result

    def _extract_usage(self, response: Any) -> Optional[Dict[str, int]]:
        """Extract token usage from LiteLLM response."""
        usage = None
        if hasattr(response, "usage") and response.usage:
            u = response.usage
            usage = {
                "prompt_tokens": getattr(u, "prompt_tokens", 0) or 0,
                "completion_tokens": getattr(u, "completion_tokens", 0) or 0,
                "total_tokens": getattr(u, "total_tokens", 0) or 0,
            }
        return usage

    def _extract_cost(self, kwargs: Dict[str, Any], response: Any) -> Optional[float]:
        """Extract cost from LiteLLM response metadata."""
        try:
            # LiteLLM tracks cost in response._hidden_params
            if hasattr(response, "_hidden_params"):
                cost = response._hidden_params.get("response_cost")
                if cost is not None:
                    return round(float(cost), 6)
        except Exception:
            pass
        return None

    def _extract_response_content(self, response: Any) -> List[Dict]:
        """Extract response choices from LiteLLM response."""
        choices = []
        try:
            for choice in response.choices:
                msg = choice.message
                choices.append({
                    "message": {
                        "role": getattr(msg, "role", "assistant"),
                        "content": getattr(msg, "content", "") or "",
                    },
                    "finish_reason": getattr(choice, "finish_reason", None),
                })
        except (AttributeError, TypeError):
            pass
        return choices

    # ---- LiteLLM Callback Interface ----

    def log_pre_api_call(self, model: str, messages: Any, kwargs: Dict) -> None:
        """Called before making the API call."""
        session = self._get_session()
        if not session:
            return

        provider = self._extract_provider(kwargs)
        msg_list = self._extract_messages(kwargs)

        session.log_step("llm.request", {
            "provider": provider,
            "model": model,
            "messages": msg_list,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    def log_success_event(self, kwargs: Dict, response_obj: Any, start_time: float, end_time: float) -> None:
        """Called after a successful API call."""
        session = self._get_session()
        if not session:
            return

        model = kwargs.get("model", "unknown")
        provider = self._extract_provider(kwargs)
        latency = end_time - start_time if isinstance(start_time, (int, float)) else None

        # Handle datetime start/end times
        if hasattr(start_time, "timestamp") and hasattr(end_time, "timestamp"):
            latency = (end_time - start_time).total_seconds()

        usage = self._extract_usage(response_obj)
        cost = self._extract_cost(kwargs, response_obj)
        choices = self._extract_response_content(response_obj)

        response_data = {
            "provider": provider,
            "model": model,
            "choices": choices,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        if usage:
            response_data["usage"] = usage
        if latency is not None:
            response_data["latency_seconds"] = round(latency, 3)
        if cost is not None:
            response_data["cost_usd"] = cost

        session.log_step("llm.response", response_data)

    def log_failure_event(self, kwargs: Dict, response_obj: Any, start_time: float, end_time: float) -> None:
        """Called after a failed API call."""
        session = self._get_session()
        if not session:
            return

        model = kwargs.get("model", "unknown")
        provider = self._extract_provider(kwargs)
        latency = end_time - start_time if isinstance(start_time, (int, float)) else None

        if hasattr(start_time, "timestamp") and hasattr(end_time, "timestamp"):
            latency = (end_time - start_time).total_seconds()

        error_data = {
            "provider": provider,
            "model": model,
            "error": str(response_obj),
            "error_type": type(response_obj).__name__,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        if latency is not None:
            error_data["latency_seconds"] = round(latency, 3)

        session.log_step("llm.error", error_data)

    # Async variants (LiteLLM calls these for async completions)

    async def async_log_pre_api_call(self, model: str, messages: Any, kwargs: Dict) -> None:
        """Async version of log_pre_api_call."""
        self.log_pre_api_call(model, messages, kwargs)

    async def async_log_success_event(self, kwargs: Dict, response_obj: Any, start_time: float, end_time: float) -> None:
        """Async version of log_success_event."""
        self.log_success_event(kwargs, response_obj, start_time, end_time)

    async def async_log_failure_event(self, kwargs: Dict, response_obj: Any, start_time: float, end_time: float) -> None:
        """Async version of log_failure_event."""
        self.log_failure_event(kwargs, response_obj, start_time, end_time)

    # Streaming support

    def log_stream_event(self, kwargs: Dict, response_obj: Any, start_time: float, end_time: float) -> None:
        """Called after streaming response is complete."""
        # Reuse success handler — LiteLLM assembles the full response
        self.log_success_event(kwargs, response_obj, start_time, end_time)

    async def async_log_stream_event(self, kwargs: Dict, response_obj: Any, start_time: float, end_time: float) -> None:
        """Async version of log_stream_event."""
        self.log_stream_event(kwargs, response_obj, start_time, end_time)


# ---- Convenience Functions ----

_epi_callback_instance: Optional[EPICallback] = None


def enable_epi(provider_label: str = "litellm") -> EPICallback:
    """
    Enable EPI recording for all LiteLLM calls.

    One-liner setup that registers EPI as a LiteLLM callback.

    Usage:
        from epi_recorder.integrations.litellm import enable_epi
        enable_epi()

        # All LiteLLM calls now auto-record when inside record()
        with record("my_agent.epi"):
            litellm.completion(model="gpt-4", messages=[...])

    Args:
        provider_label: Provider name prefix in logged steps

    Returns:
        EPICallback instance (for manual control if needed)
    """
    global _epi_callback_instance

    try:
        import litellm
    except ImportError:
        raise ImportError(
            "LiteLLM is not installed. Install with: pip install litellm"
        )

    _epi_callback_instance = EPICallback(provider_label=provider_label)

    # Register as both success and failure callback
    if not isinstance(litellm.success_callback, list):
        litellm.success_callback = []
    if not isinstance(litellm.failure_callback, list):
        litellm.failure_callback = []

    # Avoid duplicates
    if not any(isinstance(cb, EPICallback) for cb in litellm.success_callback):
        litellm.success_callback.append(_epi_callback_instance)
    if not any(isinstance(cb, EPICallback) for cb in litellm.failure_callback):
        litellm.failure_callback.append(_epi_callback_instance)

    return _epi_callback_instance


def disable_epi() -> None:
    """
    Disable EPI recording for LiteLLM calls.

    Removes the EPI callback from LiteLLM's callback lists.
    """
    try:
        import litellm
    except ImportError:
        return

    if isinstance(litellm.success_callback, list):
        litellm.success_callback = [
            cb for cb in litellm.success_callback
            if not isinstance(cb, EPICallback)
        ]
    if isinstance(litellm.failure_callback, list):
        litellm.failure_callback = [
            cb for cb in litellm.failure_callback
            if not isinstance(cb, EPICallback)
        ]
