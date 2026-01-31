"""
EPI Core - Core data structures, serialization, and container management.
"""

__version__ = "2.2.0"

from epi_core.schemas import ManifestModel, StepModel
from epi_core.serialize import get_canonical_hash

__all__ = [
    "ManifestModel",
    "StepModel",
    "get_canonical_hash",
]


