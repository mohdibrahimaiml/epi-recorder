"""EPI evidence MCP package.

Exposes epi-recorder sealing and verification to MCP hosts (e.g. ChatGPT)
as real tools — not instructions. Honest scope: the server seals the
record the caller provides. It cannot observe the caller's run, capture
model-internal state, or prove the provided record is complete.
"""

from epi_mcp.records import seal_record, verify_artifact, export_summary

__all__ = ["seal_record", "verify_artifact", "export_summary"]
