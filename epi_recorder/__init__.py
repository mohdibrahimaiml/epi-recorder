"""
EPI Recorder - Runtime interception and workflow capture.

Python API for recording AI workflows with cryptographic verification.
"""

from epi_core._version import get_version

__version__ = get_version()

# Export Python API
from epi_recorder.api import (
    AgentRun,
    EpiRecorderSession,
    get_current_session,
    record,
)

# Export wrapper clients (new in v2.3.0)
from epi_recorder.wrappers import (
    TracedAnthropic,
    TracedOpenAI,
    wrap_anthropic,
    wrap_client,
    wrap_openai,
)


# AgentAnalytics requires pandas - imported lazily so a missing pandas
# does not crash `import epi_recorder` for users who don't use analytics.
def __getattr__(name: str):
    if name == "AgentAnalytics":
        from epi_recorder.analytics import AgentAnalytics

        return AgentAnalytics
    raise AttributeError(f"module 'epi_recorder' has no attribute {name!r}")


# Note: Framework integrations are imported on-demand
# from epi_recorder.integrations import EPICheckpointSaver

from epi_recorder import auto  # noqa: E402 - available as epi_recorder.auto

__all__ = [
    "EpiRecorderSession",
    "AgentRun",
    "record",
    "get_current_session",
    "wrap_client",
    "wrap_openai",
    "TracedOpenAI",
    "wrap_anthropic",
    "TracedAnthropic",
    "AgentAnalytics",
    "auto",
    "__version__",
]

# Keep package import side-effect free.
# Windows `.epi` association is handled explicitly by:
#   - the packaged installer
#   - `epi associate`
#   - optional post-install helpers
#
# Importing `epi_recorder` must not mutate the registry or trigger UAC prompts.
