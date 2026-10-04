"""EPI evidence MCP server (stdio).

Exposes three tools:

- ``epi_seal_record`` — seal caller-provided observable events into a
  signed .epi file (returns file bytes + verdicts).
- ``epi_verify`` — verify a .epi file (integrity, signature, identity, trust).
- ``epi_export_summary`` — read back a sealed timeline.

Run: ``epi-mcp`` (stdio) or ``python -m epi_mcp.server``.
Remote hosts (ChatGPT): ``epi-mcp-http`` (Streamable HTTP at /mcp).
"""

from __future__ import annotations

import asyncio
from typing import Any

try:
    from mcp.server.mcpserver import MCPServer
except ModuleNotFoundError as exc:
    raise SystemExit(
        "The EPI MCP server needs the 'mcp' package: "
        "pip install epi-recorder[mcp]"
    ) from exc

from epi_mcp.records import SCOPE_NOTE
from epi_mcp.tools import (
    epi_export_summary_tool,
    epi_seal_record_tool,
    epi_verify_tool,
)

server = MCPServer(
    name="epi-evidence",
    instructions=(
        "Seal caller-provided observable evidence into signed EPI artifacts. "
        + SCOPE_NOTE
    ),
)


@server.tool(
    description=(
        "Seal caller-provided observable events into a signed .epi evidence "
        "file (Ed25519 + SHA-256). Returns the file bytes (base64), filename, "
        "SHA-256, and an immediate seal self-check. The events must be "
        "provided by the caller — the server cannot observe the caller's "
        "run, hidden reasoning, or inaccessible system state. "
        + SCOPE_NOTE
    )
)
def epi_seal_record(
    events: list[dict[str, Any]],
    goal: str = "MCP caller-provided record",
    output_path: str | None = None,
) -> dict[str, Any]:
    return epi_seal_record_tool(events, goal=goal, output_path=output_path)


@server.tool(
    description=(
        "Verify a .epi evidence file. Returns integrity, signature validity, "
        "signer identity status, and trust level. Authoritative check; "
        "same verdicts as `epi verify`."
    )
)
def epi_verify(epi_path: str) -> dict[str, Any]:
    return epi_verify_tool(epi_path)


@server.tool(
    description=(
        "Read back the sealed timeline of a .epi file "
        "(step index, kind, content)."
    )
)
def epi_export_summary(epi_path: str, max_steps: int = 50) -> dict[str, Any]:
    return epi_export_summary_tool(epi_path, max_steps=max_steps)


def main() -> None:
    asyncio.run(server.run_stdio_async())


if __name__ == "__main__":
    main()
