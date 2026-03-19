"""
EPI Core - Core data structures, serialization, and container management.
"""

from epi_core._version import get_version

__version__ = get_version()

from epi_core.schemas import ManifestModel, StepModel
from epi_core.serialize import get_canonical_hash

__all__ = [
    "ManifestModel",
    "StepModel",
    "get_canonical_hash",
]



 
