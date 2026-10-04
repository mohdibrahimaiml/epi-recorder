"""EPI evidence MCP package.

Exposes epi-recorder sealing and verification to MCP hosts (e.g. ChatGPT)
as real tools — not instructions. Honest scope: the server seals
caller-provided observable evidence. It cannot observe the caller's run,
capture hidden reasoning or inaccessible system state, or prove the
provided record is complete.
"""

from epi_mcp.records import seal_record, verify_artifact, export_summary
from epi_mcp.tools import epi_seal_record_tool, epi_verify_tool, epi_export_summary_tool

__all__ = [
    "seal_record",
    "verify_artifact",
    "export_summary",
    "epi_seal_record_tool",
    "epi_verify_tool",
    "epi_export_summary_tool",
]
