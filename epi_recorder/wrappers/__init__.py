"""
EPI Wrapper Clients - Proxy wrappers for LLM clients.

Provides transparent tracing without monkey patching.
"""

from epi_recorder.wrappers.openai import wrap_openai, TracedOpenAI, TracedCompletions, TracedChat
from epi_recorder.wrappers.anthropic import wrap_anthropic, TracedAnthropic, TracedMessages
from epi_recorder.wrappers.base import TracedClientBase
from typing import Any


def wrap_client(client: Any) -> Any:
    """
    Auto-detect an LLM client type and wrap it for EPI tracing.

    Supports OpenAI and Anthropic clients. Use this when you don't want to
    import provider-specific wrappers.

    Args:
        client: An OpenAI or Anthropic client instance.

    Returns:
        A traced wrapper for the client.

    Raises:
        TypeError: If the client type is not recognised.

    Example::

        from epi_recorder import record
        from epi_recorder.wrappers import wrap_client

        client = wrap_client(OpenAI())       # or Anthropic()
        with record("run.epi"):
            client.chat.completions.create(...)
    """
    module = type(client).__module__ or ""
    qualname = f"{module}.{type(client).__qualname__}"

    if "openai" in module:
        return wrap_openai(client)
    if "anthropic" in module:
        return wrap_anthropic(client)

    raise TypeError(
        f"wrap_client() does not recognise client type '{qualname}'. "
        "Use wrap_openai() or wrap_anthropic() directly."
    )


__all__ = [
    "wrap_client",
    "wrap_openai",
    "TracedOpenAI",
    "TracedCompletions",
    "TracedChat",
    "wrap_anthropic",
    "TracedAnthropic",
    "TracedMessages",
    "TracedClientBase",
]
