"""
EPI Recorder - Runtime interception and workflow capture.

Python API for recording AI workflows with cryptographic verification.
"""

__version__ = "2.4.0"

# Export Python API
from epi_recorder.api import (
    EpiRecorderSession,
    record,
    get_current_session
)

# Export wrapper clients (new in v2.3.0)
from epi_recorder.wrappers import (
    wrap_openai,
    TracedOpenAI,
)

# Export analytics (new in v2.3.0)
from epi_recorder.analytics import AgentAnalytics

# Note: Framework integrations are imported on-demand
# from epi_recorder.integrations import EPICheckpointSaver

__all__ = [
    "EpiRecorderSession",
    "record",
    "get_current_session",
    "wrap_openai",
    "TracedOpenAI",
    "AgentAnalytics",
    "__version__"
]



 