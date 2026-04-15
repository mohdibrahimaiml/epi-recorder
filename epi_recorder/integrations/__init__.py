"""
Framework integrations for EPI Recorder

Native integrations with popular agent frameworks.

Available integrations:
  - LangGraph:      EPICheckpointSaver, record_langgraph()
  - OpenAI Agents:  OpenAIAgentsRecorder, record_openai_agent_events()
  - LiteLLM:        EPICallback, enable_epi(), disable_epi()
  - LangChain:      EPICallbackHandler
  - OpenTelemetry:  EPISpanExporter, setup_epi_tracing()
  - Guardrails:     GuardrailsRecorder
"""

# Lazy imports — only fail when actually used, not on import
def __getattr__(name):
    if name in ("EPICheckpointSaver", "record_langgraph"):
        from .langgraph import EPICheckpointSaver, record_langgraph
        return {
            "EPICheckpointSaver": EPICheckpointSaver,
            "record_langgraph": record_langgraph,
        }[name]
    if name in (
        "AGTBundleModel",
        "AGTBundleMetadataModel",
        "AGTInputError",
        "DEFAULT_AGT_IMPORT_MANIFEST",
        "coerce_agt_bundle",
        "export_agt_to_epi",
        "load_agt_input",
    ):
        from .agt import (
            AGTInputError,
            AGTBundleMetadataModel,
            AGTBundleModel,
            DEFAULT_AGT_IMPORT_MANIFEST,
            coerce_agt_bundle,
            export_agt_to_epi,
            load_agt_input,
        )
        return {
            "AGTInputError": AGTInputError,
            "AGTBundleModel": AGTBundleModel,
            "AGTBundleMetadataModel": AGTBundleMetadataModel,
            "DEFAULT_AGT_IMPORT_MANIFEST": DEFAULT_AGT_IMPORT_MANIFEST,
            "coerce_agt_bundle": coerce_agt_bundle,
            "export_agt_to_epi": export_agt_to_epi,
            "load_agt_input": load_agt_input,
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
    if name == "GuardrailsRecorder":
        from .guardrails import GuardrailsRecorder
        return GuardrailsRecorder
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    'EPICheckpointSaver',
    'record_langgraph',
    'AGTInputError',
    'AGTBundleModel',
    'AGTBundleMetadataModel',
    'DEFAULT_AGT_IMPORT_MANIFEST',
    'coerce_agt_bundle',
    'export_agt_to_epi',
    'load_agt_input',
    'OpenAIAgentsRecorder',
    'record_openai_agent_events',
    'EPICallback',
    'enable_epi',
    'disable_epi',
    'EPICallbackHandler',
    'EPISpanExporter',
    'setup_epi_tracing',
    'GuardrailsRecorder',
]

