"""
EPI Recorder - Runtime interception and workflow capture.

Python API for recording AI workflows with cryptographic verification.
"""

from epi_core._version import get_version

__version__ = get_version()

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
    wrap_anthropic,
    TracedAnthropic,
)

# AgentAnalytics requires pandas — imported lazily so a missing pandas
# does not crash `import epi_recorder` for users who don't use analytics.
def __getattr__(name: str):
    if name == "AgentAnalytics":
        from epi_recorder.analytics import AgentAnalytics
        return AgentAnalytics
    raise AttributeError(f"module 'epi_recorder' has no attribute {name!r}")

# Note: Framework integrations are imported on-demand
# from epi_recorder.integrations import EPICheckpointSaver

__all__ = [
    "EpiRecorderSession",
    "record",
    "get_current_session",
    "wrap_openai",
    "TracedOpenAI",
    "wrap_anthropic",
    "TracedAnthropic",
    "AgentAnalytics",
    "__version__",
]

# Auto-register .epi file association on Windows the first time this package
# is imported — covers users who write Python scripts before running the CLI.
# Silent and idempotent: skips instantly if already registered.
import sys as _sys
if _sys.platform == "win32":
    try:
        from epi_core.platform.associate import register_file_association
        register_file_association(silent=True)
    except Exception:
        pass



 
