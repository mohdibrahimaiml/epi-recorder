"""
epi export-summary — produce a human-readable HTML or plain-text summary of a .epi artifact.

Designed for lawyers, auditors, and compliance teams who need a printable document
rather than a binary .epi file.
"""
from __future__ import annotations

import html as _html
import json
import zipfile
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from epi_cli.view import _resolve_epi_file
from epi_core.container import EPIContainer
from epi_core.trust import create_verification_report, verify_embedded_manifest_signature

app = typer.Typer(help="Export a human-readable summary of a .epi artifact.")
console = Console()


def _format_ts(ts: str | None) -> str:
    """Format an ISO timestamp into a readable UTC string."""
    if not ts:
        return "Unknown"
    try:
        from datetime import datetime
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M UTC")
    except Exception:
        return str(ts)


def _format_ts_short(ts: str | None) -> str:
    """Return HH:MM:SS from an ISO timestamp."""
    if not ts:
        return "??:??:??"
    try:
        from datetime import datetime
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.strftime("%H:%M:%S")
    except Exception:
        return str(ts)[:8]


def _read_steps(epi_path: Path) -> list[dict]:
    steps = []
    with zipfile.ZipFile(epi_path, "r") as zf:
        if "steps.jsonl" in zf.namelist():
            for line in zf.read("steps.jsonl").decode("utf-8").splitlines():
                line = line.strip()
                if line:
                    try:
                        steps.append(json.loads(line))
                    except Exception:
                        pass
    return steps


def _count_step_kinds(steps: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for step in steps:
        k = step.get("kind", "unknown")
        counts[k] = counts.get(k, 0) + 1
    return counts


def _describe_step(step: dict) -> str:
    kind = step.get("kind", "unknown")
    content = step.get("content") or step.get("payload") or {}
    if not isinstance(content, dict):
        content = {}

    if kind == "agent.start":
        name = content.get("agent_name") or content.get("name") or ""
        return f"Agent started: {name}"
    if kind == "tool.call":
        name = content.get("tool_name") or content.get("name") or ""
        arg = content.get("input", "")
        if isinstance(arg, dict):
            arg = ", ".join(f"{k}={v}" for k, v in list(arg.items())[:2])
        return f"Tool called: {name}" + (f" ({arg})" if arg else "")
    if kind == "tool.result":
        status = content.get("status") or ("error" if content.get("error") else "success")
        return f"Tool result: {status}"
    if kind in ("llm.request", "llm.call"):
        model = content.get("model") or ""
        tokens = content.get("tokens") or content.get("prompt_tokens") or ""
        return f"LLM request: {model}" + (f" ({tokens} tokens)" if tokens else "")
    if kind in ("llm.response", "llm.decision"):
        text = content.get("text") or content.get("output_text") or content.get("decision") or ""
        if isinstance(text, str) and len(text) > 60:
            text = text[:57] + "..."
        return f'LLM decision: "{text}"'
    if kind == "decision":
        decision = content.get("decision_id") or content.get("id") or ""
        conf = content.get("confidence") or ""
        return f"Decision recorded: {decision}" + (f" (confidence: {conf}%)" if conf else "")
    if kind == "agent.complete":
        outcome = content.get("outcome") or content.get("status") or "success"
        return f"Agent completed: {outcome}"
    return f"{kind}: {str(content)[:60]}"


def _build_text_summary(
    epi_path: Path,
    manifest,
    integrity_ok: bool,
    signature_valid: bool | None,
    signer_name: str | None,
    steps: list[dict],
    review_info: dict | None,
) -> str:
    workflow = str(manifest.workflow_id)
    created = _format_ts(manifest.created_at.isoformat() if manifest.created_at else None)

    kind_counts = _count_step_kinds(steps)
    step_parts = [f"{v} {k.replace('.', ' ')}" for k, v in sorted(kind_counts.items())]
    step_summary = ", ".join(step_parts) if step_parts else "none"

    if signature_valid is True:
        signed_line = f"Yes — Ed25519 (key: {signer_name or 'unknown'})"
    elif signature_valid is None:
        signed_line = "No signature"
    else:
        signed_line = "INVALID signature"

    integrity_line = "Verified — all files intact" if integrity_ok else "FAILED — files modified"

    lines = [
        "EPI EVIDENCE SUMMARY",
        "=" * 20,
        f"File:        {epi_path.name}",
        f"Workflow:    {workflow}",
        f"Created:     {created}",
        f"Steps:       {len(steps)} ({step_summary})",
        f"Signed:      {signed_line}",
        f"Integrity:   {integrity_line}",
        "",
        "DECISION TRAIL",
        "-" * 14,
    ]

    for step in steps:
        ts_str = _format_ts_short(step.get("timestamp") or step.get("ts"))
        lines.append(f"[{ts_str}] {_describe_step(step)}")

    if review_info:
        lines += [
            "",
            "REVIEW",
            "-" * 6,
            f"Reviewed by:  {review_info.get('reviewed_by', '')}",
            f"Decision:     {str(review_info.get('decision', '')).upper()}",
            f"Time:         {_format_ts(review_info.get('reviewed_at', ''))}",
        ]

    lines += [
        "",
        "VERIFICATION",
        "-" * 12,
        f"Run: epi verify {epi_path.name}",
        "This file is cryptographically tamper-evident.",
        "Anyone can verify it has not been modified.",
    ]

    return "\n".join(lines)


def _build_html_summary(epi_path: Path, text_content: str) -> str:
    escaped = _html.escape(text_content)
    title = _html.escape(epi_path.stem)
    stem = _html.escape(epi_path.name)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>EPI Evidence Summary — {title}</title>
<style>
  @media print {{ body {{ margin: 1cm; }} }}
  body {{
    font-family: 'Courier New', monospace;
    font-size: 13px;
    line-height: 1.6;
    max-width: 800px;
    margin: 40px auto;
    padding: 20px;
    background: #fff;
    color: #222;
  }}
  h1 {{ font-size: 16px; border-bottom: 2px solid #333; padding-bottom: 8px; }}
  pre {{
    white-space: pre-wrap;
    word-wrap: break-word;
    background: #f8f8f8;
    border: 1px solid #ddd;
    padding: 16px;
    border-radius: 4px;
  }}
  .footer {{
    margin-top: 32px;
    font-size: 11px;
    color: #999;
    border-top: 1px solid #eee;
    padding-top: 8px;
  }}
</style>
</head>
<body>
<h1>EPI Evidence Summary</h1>
<pre>{escaped}</pre>
<div class="footer">
  Generated by EPI (Evidence Packaged Infrastructure) — epi export-summary {stem}
</div>
</body>
</html>"""


@app.command()
def summary(
    epi_file: str = typer.Argument(..., help="Path or name of .epi file to summarise."),
    out: Optional[Path] = typer.Option(
        None,
        "--out",
        "-o",
        help="Output .html file (default: <name>_summary.html alongside the .epi file).",
    ),
    text: bool = typer.Option(False, "--text", help="Print plain text to stdout instead of writing HTML."),
):
    """
    Export a human-readable summary of a .epi artifact.

    By default writes a self-contained HTML file suitable for printing or
    attaching to an audit submission.  Use --text to get plain text instead.
    """
    try:
        epi_path = _resolve_epi_file(epi_file)
    except FileNotFoundError:
        console.print(f"[red][FAIL][/red] File not found: {epi_file}")
        raise typer.Exit(1)

    try:
        manifest = EPIContainer.read_manifest(epi_path)
    except Exception as exc:
        console.print(f"[red][FAIL][/red] Could not read manifest: {exc}")
        raise typer.Exit(1)

    integrity_ok, _ = EPIContainer.verify_integrity(epi_path)
    signature_valid, signer_name, _ = verify_embedded_manifest_signature(manifest)
    steps = _read_steps(epi_path)

    review_info: dict | None = None
    try:
        with zipfile.ZipFile(epi_path, "r") as zf:
            if "review.json" in zf.namelist():
                review_info = json.loads(zf.read("review.json").decode("utf-8"))
    except Exception:
        pass

    text_content = _build_text_summary(
        epi_path, manifest, integrity_ok, signature_valid, signer_name, steps, review_info
    )

    if text:
        console.print(text_content)
        return

    if out is None:
        out = epi_path.parent / f"{epi_path.stem}_summary.html"

    html_content = _build_html_summary(epi_path, text_content)
    out.write_text(html_content, encoding="utf-8")
    console.print(f"[green][OK][/green] Summary written: {out}")
