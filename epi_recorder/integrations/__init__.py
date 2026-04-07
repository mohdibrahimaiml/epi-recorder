"""
Framework integrations for EPI Recorder

Native integrations with popular agent frameworks.

Available integrations:
  - LangGraph:      EPICheckpointSaver
  - OpenAI Agents:  OpenAIAgentsRecorder, record_openai_agent_events()
  - LiteLLM:        EPICallback, enable_epi(), disable_epi()
  - LangChain:      EPICallbackHandler
  - OpenTelemetry:  EPISpanExporter, setup_epi_tracing()
"""

from .langgraph import EPICheckpointSaver

# Lazy imports — only fail when actually used, not on import
def __getattr__(name):
    if name in ("AGTBundleModel", "AGTBundleMetadataModel", "coerce_agt_bundle", "export_agt_to_epi"):
        from .agt import (
            AGTBundleMetadataModel,
            AGTBundleModel,
            coerce_agt_bundle,
            export_agt_to_epi,
        )
        return {
            "AGTBundleModel": AGTBundleModel,
            "AGTBundleMetadataModel": AGTBundleMetadataModel,
            "coerce_agt_bundle": coerce_agt_bundle,
            "export_agt_to_epi": export_agt_to_epi,
        }[name]
    if name in ("OpenAIAgentsRecorder", "record_openai_agent_events"):
        from .openai_agents import OpenAIAgentsRecorder, record_openai_agent_events
        return {
            "OpenAIAgentsRecorder": OpenAIAgentsRecorder,
            "record_openai_agent_events": record_openai_agent_events,
        }[name]
    if name in ("EPICallback", "enable_epi", "disable_epi"):
        from .litellm import EPICallback, enable_epi, disable_epi
        return {"EPICallback": EPICallback, "enable_epi": enable_epi, "disable_epi": disable_epi}[name]
    if name == "EPICallbackHandler":
        from .langchain import EPICallbackHandler
        return EPICallbackHandler
    if name in ("EPISpanExporter", "setup_epi_tracing"):
        from .opentelemetry import EPISpanExporter, setup_epi_tracing
        return {"EPISpanExporter": EPISpanExporter, "setup_epi_tracing": setup_epi_tracing}[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    'EPICheckpointSaver',
    'AGTBundleModel',
    'AGTBundleMetadataModel',
    'coerce_agt_bundle',
    'export_agt_to_epi',
    'OpenAIAgentsRecorder',
    'record_openai_agent_events',
    'EPICallback',
    'enable_epi',
    'disable_epi',
    'EPICallbackHandler',
    'EPISpanExporter',
    'setup_epi_tracing',
]

