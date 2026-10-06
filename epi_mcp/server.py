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

try:
    from mcp.types import Icon as _MCPIcon
except Exception:  # pragma: no cover - older SDK without Icon
    _MCPIcon = None


def _server_icons():
    import os as _os

    base = (_os.environ.get("EPI_MCP_PUBLIC_URL") or "https://epilabs.org").rstrip("/")
    if _MCPIcon is None:
        return None
    return [
        _MCPIcon(
            src=f"{base}/assets/epi-logo.png",
            mimeType="image/png",
            sizes=["1024x1024"],
        )
    ]

from epi_mcp.records import SCOPE_NOTE
from epi_mcp.tools import (
    compare_runs,
    epi_export_summary_tool,
    epi_seal_record_tool,
    epi_verify_tool,
)

SEAL_GUIDE = (
    "HOW TO SEAL A CHAT OR RUN (read before calling epi_seal_record)\n"
    "1. Seal what the user actually asked about. If several topics or tasks "
    "are in the conversation and it is unclear which one, ask one short "
    "question first. Never seal a different thread than the one requested.\n"
    "2. Send the real record, not your account of it. For each user and "
    "assistant message pass the exact text with fidelity=\"verbatim\". Use "
    "fidelity=\"summary\" only for text you condensed, and "
    "fidelity=\"hash_only\" with a sha256 when content must stay private. "
    "Never describe a message in your own words and label it verbatim.\n"
    "3. Pass each event's real time as an ISO-8601 `timestamp` when the host "
    "shows one. If you do not know it, omit it; the server stamps its own "
    "receive time and says so. Never invent times.\n"
    "4. Event shape: {\"kind\": ..., \"content\": {\"text\": ...}, "
    "\"timestamp\": optional, \"fidelity\": ...}. Kinds: user.message, "
    "assistant.message, artifact.attached / artifact.produced (filename + "
    "sha256 in content), tool.call, tool.response, agent.decision, "
    "redaction.omitted.\n"
    "5. Redact secrets and personal data of third parties by replacing them "
    "with [REDACTED]. If you leave something out, add a redaction.omitted "
    "event saying WHAT category was omitted and WHY, so omissions are "
    "declared inside the record instead of invisible.\n"
    "6. If the tool errors, say the run is NOT sealed and stop. Never build "
    ".epi bytes yourself; a hand-made file fails verification.\n"
    "7. After sealing, tell the user plainly: the download link (it works in "
    "a browser and expires), the SHA-256, the warnings the tool returned, "
    "that identity is unpinned unless they trust the key, and that the seal "
    "proves the record was not altered, not that it is complete. Tell them "
    "to confirm independently with `epi verify <file>.epi`."
)

server = MCPServer(
    name="epi-evidence",
    icons=_server_icons(),
    instructions=(
        "Seal caller-provided observable evidence into signed EPI artifacts. "
        + SCOPE_NOTE
        + "\n\n"
        + SEAL_GUIDE
    ),
)


@server.tool(
    description=(
        "Seal caller-provided events (a chat transcript or an agent run) into "
        "a signed .epi evidence file (Ed25519 + SHA-256). The server cannot "
        "observe your run, hidden reasoning, or inaccessible state; it seals "
        "exactly what you pass and reports how faithful it was (fidelity "
        "counts, caller vs server timestamps, warnings). Returns artifact_id, "
        "download_url (expiring, opens in a browser), filename, SHA-256, a "
        "seal self-check, fidelity, warnings and, unless include_bytes=false, "
        "the file as base64. "
        + SEAL_GUIDE
        + "\n"
        + SCOPE_NOTE
    )
)
def epi_seal_record(
    events: list[dict[str, Any]],
    goal: str = "MCP caller-provided record",
    output_path: str | None = None,
    include_bytes: bool = True,
) -> dict[str, Any]:
    from epi_mcp.tools import _current_subject as _subject_var

    _subject_var.set("operator")  # stdio runs are the server operator
    try:
        return epi_seal_record_tool(
            events, goal=goal, output_path=output_path, include_bytes=include_bytes
        )
    finally:
        _subject_var.set(None)


@server.tool(
    description=(
        "Verify a sealed .epi file by the artifact_id returned from "
        "epi_seal_record (or a server path). Returns integrity, signature validity, "
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


@server.tool(
    description=(
        "Compare two sealed .epi timelines: step deltas, kind coverage, "
        "decisions and first divergence. Compares sealed records only, "
        "never the runs behind them."
    )
)
def epi_compare_runs(epi_path_a: str, epi_path_b: str) -> dict[str, Any]:
    return compare_runs(epi_path_a, epi_path_b)


def main() -> None:
    asyncio.run(server.run_stdio_async())


if __name__ == "__main__":
    main()
