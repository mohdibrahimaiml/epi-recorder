"""`epi witness` — customer witness outbox management.

Every seal (with EPI_WITNESS_URL or witness_url= set) appends a hash-only
payload to the outbox and delivers it from a daemon thread. `flush` retries
whatever is undelivered; `status` lists pending, delivered and failed entries.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(help="Customer witness outbox: retry and inspect seal reports.")
console = Console()


def _secret() -> str | None:
    return os.environ.get("EPI_WITNESS_SECRET")


@app.command(name="flush")
def flush(
    secret: str | None = typer.Option(
        None, "--secret", help="HMAC secret for delivery (default: EPI_WITNESS_SECRET)."
    ),
    timeout: int = typer.Option(10, "--timeout", help="Per-request timeout in seconds."),
) -> None:
    """Retry every undelivered witness entry."""
    from epi_core.webhook import flush_outbox, outbox_path

    result = flush_outbox(
        secret=secret if secret is not None else _secret(),
        timeout_seconds=timeout,
        path=outbox_path(),
    )
    if not result["entries"]:
        console.print("[dim]Witness outbox is empty — nothing to deliver.[/dim]")
        return
    for url in result["delivered"]:
        console.print(f"[green]Delivered:[/green] {url}")
    for url, error in result["failed"].items():
        console.print(f"[red]Failed:[/red] {url} ({error})")
        if "401" in str(error) or "403" in str(error):
            console.print("[dim]  Set EPI_WITNESS_SECRET or pass --secret.[/dim]")
    if not result["delivered"] and not result["failed"]:
        console.print("[dim]Nothing pending.[/dim]")
    if result["failed"]:
        # Scripts and CI must see that reports are still undelivered.
        raise typer.Exit(1)


@app.command(name="status")
def status() -> None:
    """List pending, delivered and failed witness entries."""
    from epi_core.webhook import outbox_path, read_outbox

    entries = read_outbox(outbox_path())
    if not entries:
        console.print("[dim]Witness outbox is empty.[/dim]")
        return
    table = Table(title=f"Witness outbox ({outbox_path()})")
    table.add_column("id")
    table.add_column("created")
    table.add_column("workflow")
    table.add_column("pending")
    table.add_column("delivered")
    table.add_column("last error")
    for entry in entries:
        payload = entry.get("payload") or {}
        table.add_row(
            str(entry.get("id", ""))[:8],
            str(entry.get("created_at", ""))[:19],
            str(payload.get("workflow_id", ""))[:8],
            str(len(entry.get("pending") or [])),
            str(len(entry.get("delivered") or {})),
            str(entry.get("last_error") or "")[:160],
        )
    console.print(table)
    pending = sum(len(e.get("pending") or []) for e in entries)
    console.print(f"[dim]{len(entries)} entries, {pending} URLs pending.[/dim]")
