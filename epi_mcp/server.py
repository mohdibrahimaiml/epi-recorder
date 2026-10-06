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
    "Usage notes for sealing a conversation or a run\n"
    "1. Scope: seal the conversation or task the user asked about. If the "
    "chat covers several topics and it is unclear which one is meant, ask "
    "one short question first.\n"
    "2. Content: send each user and assistant message as it appears in the "
    "conversation, with fidelity \"verbatim\". Use \"summary\" for text that was "
    "condensed and \"hash_only\" (with a sha256) for content the user wants "
    "kept private. The label should match what was sent. Send long user and "
    "assistant messages in full (the size limit is generous); summarize only "
    "bulky tool output such as search results or fetched pages.\n"
    "3. Times: if the host shows a time for an event, send it as an ISO-8601 "
    "`timestamp`. If not, leave it out; the server records its own receive "
    "time and flags it.\n"
    "4. Event shape: {\"kind\": ..., \"content\": {\"text\": ...}, "
    "\"timestamp\": optional, \"fidelity\": ...}. Kinds: user.message, "
    "assistant.message, artifact.attached / artifact.produced (filename and "
    "sha256 in content), tool.call (content {\"tool\": name, \"input\": {...}}), "
    "tool.response (content {\"result\": ...}), agent.decision (content "
    "{\"decision\": ..., \"rationale\": ...}), redaction.omitted.\n"
    "5. Privacy: replace secrets and other people's personal data with "
    "[REDACTED]. If something is left out on purpose, add a redaction.omitted "
    "event that names the kind of content and the reason (for example: raw "
    "file bytes kept private, another person's details, or text supplied by "
    "the host rather than the user), so the record shows what is absent.\n"
    "6. Errors: if sealing fails, tell the user nothing was sealed. Files "
    "come from epi_seal_record; a file assembled by hand will not verify.\n"
    "7. After sealing, give the user: the view link (view_url: opens the "
    "sealed record in the browser, nothing to install), the download link "
    "(download_url: it expires; the server removes its copy then, so download "
    "promptly), the SHA-256, any warnings returned, a note that the signer "
    "is not pinned until they trust the key, and that a seal shows the "
    "record was not altered, not that it is complete. They can confirm "
    "independently with `epi verify <file>.epi`. Also tell them who the "
    "file names as the signer, using sealer_identity from the result."
)

server = MCPServer(
    name="epi-evidence",
    icons=_server_icons(),
    instructions=(
        "When someone asks to seal, save, export, preserve or certify a "
        "conversation or run, call epi_seal_record. Do not write a Markdown or "
        "text file instead: only this server produces a signed .epi file.\n\n"
        "Seal caller-provided observable evidence into signed EPI artifacts. "
        + SCOPE_NOTE
        + "\n\n"
        + SEAL_GUIDE
    ),
)


@server.tool(
    description=(
        "Use this when the user asks to seal, save, export, preserve or certify "
        "this chat or a run, or wants a downloadable, verifiable record of it "
        "(for example \"seal this chat\", \"save this conversation as evidence\", "
        "\"make a tamper-evident copy\"). Do not write a Markdown or text file "
        "instead: only this tool produces a signed .epi file. "
        "Seals a conversation or an agent run into a signed .epi evidence file "
        "(Ed25519 + SHA-256). Send each message in full, word for word: text "
        "condensed into a summary is recorded as a summary and is weaker evidence. "
        "Pass the events that appeared in it, each as "
        "{kind, content: {text}, timestamp?, fidelity?}. Kinds: user.message, "
        "assistant.message, artifact.attached / artifact.produced (content: "
        "filename, sha256), tool.call (content: tool, input), tool.response "
        "(content: result), agent.decision (content: decision, rationale), "
        "redaction.omitted (content: text "
        "naming the kind of content left out and why). fidelity is verbatim, "
        "summary or hash_only. timestamp is ISO-8601 when the host shows one. "
        "Returns artifact_id, an expiring download_url, the SHA-256, a seal "
        "self-check, fidelity counts and warnings, and the file as base64 "
        "unless include_bytes=false or the file is large (then use download_url). "
        + SCOPE_NOTE
    ),
    # One copy only: the default also repeats the result as structured content,
    # doubling a response that already carries the file.
    structured_output=False,
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


# One-click starters. In the host's connector menu these appear as ready-made
# prompts, so a person never has to word a request.
@server.prompt(
    name="seal_this_conversation",
    title="Seal this conversation",
    description="Seal this whole conversation into a signed .epi file and give me the download link.",
)
def seal_this_conversation() -> str:
    return (
        "Seal this conversation with the EPI evidence connector. Call epi_seal_record "
        "with every message so far, then give me the download link, the SHA-256 and "
        "any warnings. Do not create a Markdown or text file."
    )


@server.prompt(
    name="seal_last_answer",
    title="Seal your last answer",
    description="Seal only my last question and your last answer. Quick and works in long chats.",
)
def seal_last_answer() -> str:
    return (
        "Seal only my previous message and your answer to it with the EPI evidence "
        "connector. Call epi_seal_record with just those two messages, then give me "
        "the download link and the SHA-256. Do not create a Markdown or text file."
    )


def main() -> None:
    asyncio.run(server.run_stdio_async())


if __name__ == "__main__":
    main()
