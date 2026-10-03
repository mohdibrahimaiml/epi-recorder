"""EPI evidence MCP server.

Exposes three tools over stdio:

- ``epi_seal_record`` — seal caller-provided events into a signed .epi file.
- ``epi_verify`` — verify a .epi file (integrity, signature, identity, trust).
- ``epi_export_summary`` — read back a sealed timeline.

Run: ``epi-mcp`` (stdio) or ``python -m epi_mcp.server``.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from mcp.server.mcpserver import MCPServer

from epi_mcp.records import SCOPE_NOTE, export_summary, seal_record, verify_artifact

server = MCPServer(
    name="epi-evidence",
    instructions=(
        "Seal caller-provided execution records into signed EPI evidence "
        "artifacts. " + SCOPE_NOTE
    ),
)


@server.tool(
    description=(
        "Seal a list of execution events into a signed .epi evidence file "
        "(Ed25519 + SHA-256). The events must be provided by the caller — "
        "the server cannot observe the caller's run. " + SCOPE_NOTE
    )
)
def epi_seal_record(
    events: list[dict[str, Any]],
    goal: str = "MCP caller-provided record",
    output_path: str | None = None,
) -> dict[str, Any]:
    result = seal_record(events, goal=goal, output_path=output_path)
    check = verify_artifact(result["epi_path"])
    result["seal_check"] = {
        "integrity_ok": check["integrity_ok"],
        "signature_valid": check["signature_valid"],
        "trust_level": check["trust_level"],
    }
    return result


@server.tool(
    description=(
        "Verify a .epi evidence file. Returns integrity, signature validity, "
        "signer identity status, and trust level. Authoritative check; "
        "same verdicts as `epi verify`."
    )
)
def epi_verify(epi_path: str) -> dict[str, Any]:
    return verify_artifact(epi_path)


@server.tool(
    description=(
        "Read back the sealed timeline of a .epi file "
        "(step index, kind, content)."
    )
)
def epi_export_summary(epi_path: str, max_steps: int = 50) -> dict[str, Any]:
    return export_summary(epi_path, max_steps=max_steps)


def main() -> None:
    asyncio.run(server.run_stdio_async())


if __name__ == "__main__":
    main()
