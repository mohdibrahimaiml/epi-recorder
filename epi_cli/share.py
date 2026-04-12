"""
EPI CLI Share - Upload a portable .epi file and return a hosted share link.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path

import typer
from rich.console import Console

from epi_core.artifact_inspector import ArtifactInspectionError, ensure_shareable_artifact
from epi_core.container import EPIContainer
from epi_cli.view import _resolve_epi_file

console = Console()

DEFAULT_SHARE_API_URL = "https://api.epilabs.org"
MAX_LOCAL_SHARE_BYTES = 5 * 1024 * 1024


def _resolve_share_api_base_url(explicit: str | None) -> str:
    return str(explicit or os.getenv("EPI_SHARE_API_URL") or DEFAULT_SHARE_API_URL).rstrip("/")


def _local_preflight(epi_file: Path):
    if not epi_file.exists():
        raise FileNotFoundError(f"File not found: {epi_file}")
    if epi_file.stat().st_size > MAX_LOCAL_SHARE_BYTES:
        raise ValueError(f"File exceeds the {MAX_LOCAL_SHARE_BYTES} byte share limit.")
    return ensure_shareable_artifact(epi_file)


def _parse_error_body(exc: urllib.error.HTTPError) -> str:
    try:
        payload = json.loads(exc.read().decode("utf-8"))
    except Exception:
        return exc.reason or f"HTTP {exc.code}"
    return payload.get("detail") or payload.get("error") or exc.reason or f"HTTP {exc.code}"


def share(
    file: Path = typer.Argument(..., exists=False, dir_okay=False, help="Path to the .epi file to share."),
    expires: int = typer.Option(30, "--expires", min=1, help="Days until the share link expires (max 30)."),
    json_output: bool = typer.Option(False, "--json", help="Print the share response as JSON."),
    no_open: bool = typer.Option(False, "--no-open", help="Do not open the hosted share link in your browser."),
    api_base_url: str | None = typer.Option(
        None,
        "--api-base-url",
        help="Override the share API base URL (default: EPI_SHARE_API_URL or https://api.epilabs.org).",
    ),
):
    """
    Upload a .epi file and return a browser-openable share link.
    """
    try:
        resolved_file = _resolve_epi_file(str(file))
        inspection = _local_preflight(resolved_file)
    except FileNotFoundError as exc:
        console.print(f"[red][FAIL][/red] File not found: {file}")
        raise typer.Exit(1) from exc
    except (ValueError, ArtifactInspectionError) as exc:
        console.print(f"[red][FAIL][/red] {exc}")
        raise typer.Exit(1) from exc

    api_root = _resolve_share_api_base_url(api_base_url)
    request_url = f"{api_root}/api/share?{urllib.parse.urlencode({'expires_days': expires})}"
    payload_bytes = resolved_file.read_bytes()
    request = urllib.request.Request(
        request_url,
        data=payload_bytes,
        method="POST",
        headers={
            "Content-Type": EPIContainer.container_mimetype(resolved_file),
            "X-EPI-Filename": resolved_file.name,
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            response_payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = _parse_error_body(exc)
        console.print(f"[red][FAIL][/red] Share upload failed: {detail}")
        raise typer.Exit(1) from exc
    except urllib.error.URLError as exc:
        api_root_shown = _resolve_share_api_base_url(api_base_url)
        console.print(f"[red][FAIL][/red] Could not reach the share service at {api_root_shown}")
        console.print("[dim]To fix this, either:[/dim]")
        console.print("[dim]  • Deploy the EPI gateway and set EPI_SHARE_API_URL=http://your-host:8765[/dim]")
        console.print("[dim]  • Use --api-base-url http://your-gateway-host:8765[/dim]")
        console.print("[dim]  • Deploy api.epilabs.org (see docs/internal/HOSTED-PILOT-RUNBOOK.md)[/dim]")
        raise typer.Exit(1) from exc

    if json_output:
        sys.stdout.write(json.dumps(response_payload, indent=2) + "\n")
        raise typer.Exit(0)

    console.print("Uploading... [green]done[/green]")
    console.print("")
    console.print(f"[cyan]{response_payload['url']}[/cyan]")
    console.print("")
    console.print("Opens in any browser. No EPI install needed.")
    console.print(f"Link expires in {expires} days.")
    if inspection.signature_valid is None:
        console.print("[dim]This artifact is unsigned but its integrity was checked locally before upload.[/dim]")
    if not no_open:
        try:
            webbrowser.open(response_payload["url"])
        except Exception as exc:
            console.print(f"[yellow][WARN][/yellow] Could not open your browser automatically: {exc}")
    raise typer.Exit(0)
