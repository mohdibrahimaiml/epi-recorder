"""
EPI Recorder - Runtime interception and workflow capture.

Python API for recording AI workflows with cryptographic verification.
"""

__version__ = "1.1.1"

# Export Python API
from epi_recorder.api import (
    EpiRecorderSession,
    record,
    get_current_session
)

__all__ = [
    "EpiRecorderSession",
    "record",
    "get_current_session",
    "__version__"
]
