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

from mcp.types import ToolAnnotations

from epi_mcp.records import SCOPE_NOTE
from epi_mcp.tools import (
    compare_runs,
    epi_export_summary_tool,
    epi_seal_record_tool,
    epi_verify_tool,
)

SEAL_GUIDE = (
    "Notes for sealing a conversation or a run\n"
    "1. The record covers the conversation or task the user asked about; if it "
    "is unclear which one, one short question settles it.\n"
    "2. Messages go in as they appeared, with fidelity matching what was "
    "sent: verbatim, summary, or hash_only (with a sha256).\n"
    "3. A timestamp is included only when the chat shows one; otherwise the "
    "server records its own receive time and flags it.\n"
    "4. Passwords, keys and other people's personal data are best shown as "
    "[REDACTED]. Anything left out on purpose can be noted with a "
    "redaction.omitted event saying what kind of content and why.\n"
    "5. If sealing fails, nothing was sealed. Signed files come only from "
    "epi_seal_record; a file assembled by hand will not verify.\n"
    "6. The user gets the view link (view_url: opens the sealed record in the "
    "browser, nothing to install), the download link (download_url: expires, "
    "and the server removes its copy then), the SHA-256 and any warnings. "
    "share_text holds the links and hash exactly as they work. A "
    "seal shows the record was not altered, not that it is complete."
)

server = MCPServer(
    name="epi-evidence",
    icons=_server_icons(),
    instructions=(
        "Use epi_seal_record when someone asks to seal, save, export or certify "
        "a conversation or run. A Markdown or text file is not a signed record; "
        "only this server produces a signed .epi file.\n\n"
        + SCOPE_NOTE
        + "\n\n"
        + SEAL_GUIDE
    ),
)


def _oauth_meta(scope: str) -> dict[str, Any]:
    """Per-tool auth declaration for hosts that read it (the Apps SDK convention).

    Every tool here needs the signed-in caller. This only describes that: the HTTP layer already
    refuses unauthenticated calls with a 401 challenge, which is what actually starts sign-in.
    """
    return {"securitySchemes": [{"type": "oauth2", "scopes": [scope]}]}


def _one_ref(epi_path: str | None, artifact_id: str | None) -> str:
    """The sealed file to act on, named by artifact_id (preferred) or epi_path."""
    ref = (artifact_id or epi_path or "").strip()
    if not ref:
        raise ValueError("Pass the artifact_id returned by epi_seal_record.")
    return ref


@server.tool(
    description=(
        "Create a signed, tamper-evident audit record (.epi file) of a "
        "conversation or workflow so it can be kept and verified later. Use it "
        "when the user asks to seal, save, export or certify a chat. A Markdown "
        "or text file is not a signed record; this tool produces one. events is a list of "
        "{kind, content: {text}, timestamp?, fidelity?}. kind is user.message, "
        "assistant.message, tool.call (content: tool, input), tool.response "
        "(content: result), artifact.attached or artifact.produced (content: "
        "filename, sha256), or redaction.omitted (content: text naming what was "
        "left out and why). fidelity is verbatim, summary or hash_only. "
        "timestamp is ISO-8601 when the chat shows one. Returns view_url, "
        "download_url, the SHA-256, a seal self-check, and warnings. "
        + SCOPE_NOTE
    ),
    title="Seal a conversation or run",
    # Writes one new file on our own server and deletes nothing. The only outside call is a hash
    # sent to a public time-stamp service; no content leaves the server.
    annotations=ToolAnnotations(
        title="Seal a conversation or run",
        read_only_hint=False,
        destructive_hint=False,
        idempotent_hint=False,
        open_world_hint=False,
    ),
    meta=_oauth_meta("seal"),
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

    # Over HTTP the server has already identified the caller; keep that identity. Only a local
    # stdio run, where nobody has been identified, is the server operator.
    token = _subject_var.set("operator") if _subject_var.get() is None else None
    try:
        return epi_seal_record_tool(
            events, goal=goal, output_path=output_path, include_bytes=include_bytes
        )
    finally:
        if token is not None:
            _subject_var.reset(token)


@server.tool(
    description=(
        "Verify a sealed .epi file by the artifact_id returned from "
        "epi_seal_record. Returns integrity, signature validity, "
        "signer identity status, and trust level. Authoritative check; "
        "same verdicts as `epi verify`."
    ),
    title="Verify a sealed file",
    annotations=ToolAnnotations(
        title="Verify a sealed file", read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False
    ),
    meta=_oauth_meta("verify"),
)
def epi_verify(epi_path: str | None = None, artifact_id: str | None = None) -> dict[str, Any]:
    return epi_verify_tool(_one_ref(epi_path, artifact_id))


@server.tool(
    description=(
        "Read back the sealed timeline of a sealed file, by the artifact_id "
        "returned from epi_seal_record (step index, kind, content)."
    ),
    title="Read back a sealed timeline",
    annotations=ToolAnnotations(
        title="Read back a sealed timeline", read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False
    ),
    meta=_oauth_meta("export"),
)
def epi_export_summary(
    epi_path: str | None = None, max_steps: int = 50, artifact_id: str | None = None
) -> dict[str, Any]:
    return epi_export_summary_tool(_one_ref(epi_path, artifact_id), max_steps=max_steps)


@server.tool(
    description=(
        "Compare two sealed timelines by artifact_id_a and artifact_id_b: step deltas, kind coverage, "
        "decisions and first divergence. Compares sealed records only, "
        "it does not examine the runs behind them."
    ),
    title="Compare two sealed timelines",
    annotations=ToolAnnotations(
        title="Compare two sealed timelines", read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False
    ),
    meta=_oauth_meta("export"),
)
def epi_compare_runs(epi_path_a: str | None = None, epi_path_b: str | None = None,
                     artifact_id_a: str | None = None, artifact_id_b: str | None = None) -> dict[str, Any]:
    epi_path_a = _one_ref(epi_path_a, artifact_id_a)
    epi_path_b = _one_ref(epi_path_b, artifact_id_b)
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
        "Seal this conversation with the EPI Evidence Sealer and give me the "
        "view link, the download link and the SHA-256."
    )


@server.prompt(
    name="seal_last_answer",
    title="Seal your last answer",
    description="Seal only my last question and your last answer. Quick and works in long chats.",
)
def seal_last_answer() -> str:
    return (
        "Seal only my previous message and your answer to it with the EPI "
        "Evidence Sealer, and give me the view link and the SHA-256."
    )


def main() -> None:
    asyncio.run(server.run_stdio_async())


if __name__ == "__main__":
    main()
