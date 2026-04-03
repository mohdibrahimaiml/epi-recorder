"""
EPI Platform Utilities — Cross-platform OS integration.

Provides file association registration so double-clicking .epi files
opens the EPI viewer automatically.
"""

from epi_core.platform.associate import (
    register_file_association,
    unregister_file_association,
)

__all__ = [
    "register_file_association",
    "unregister_file_association",
]
