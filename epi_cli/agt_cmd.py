"""AGT adapter CLI commands for evidence receipt generation."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel

from epi_recorder.integrations.agt_adapter import (
    export_evidence_receipt,
    verify_evidence_receipt,
    build_agt_log_data,
)

app = typer.Typer(help="AGT adapter commands — evidence receipts and raw imports.")
console = Console()


@app.command("receipt")
def agt_receipt(
    epi_file: Path = typer.Argument(..., help="Path to .epi file to generate receipt from."),
    out: Path | None = typer.Option(None, "--out", "-o", help="Write receipt bytes to this file."),
    verify: bool = typer.Option(False, "--verify", help="Verify an existing receipt against the artifact."),
    receipt_file: Path | None = typer.Option(None, "--receipt", help="Receipt file to verify (with --verify)."),
):
    """Generate or verify a signed EPI evidence receipt for AGT.

    The receipt is a COSE Sign1 object that AGT can store opaquely
    via AuditLog.log(data={"epi_evidence": receipt.hex()}).
    """
    if not epi_file.exists():
        console.print(f"[red][X] File not found:[/red] {epi_file}")
        raise typer.Exit(1)

    if verify:
        if not receipt_file or not receipt_file.exists():
            console.print("[red][X] --receipt required for --verify[/red]")
            raise typer.Exit(1)
        receipt_bytes = receipt_file.read_bytes()
        is_valid = verify_evidence_receipt(receipt_bytes, epi_file)
        status = "[green]VALID[/green]" if is_valid else "[red]INVALID[/red]"
        console.print(f"Receipt verification: {status}")
        raise typer.Exit(0 if is_valid else 1)

    # Generate receipt
    try:
        receipt = export_evidence_receipt(epi_file)
    except Exception as exc:
        console.print(f"[red][X] Receipt generation failed:[/red] {exc}")
        raise typer.Exit(1)

    log_data = build_agt_log_data(receipt, epi_file)

    if out:
        out.write_bytes(receipt)
        console.print(f"[green]Receipt written:[/green] {out}")

    console.print("")
    panel = Panel(
        f"[bold]Artifact:[/bold] {epi_file}\n"
        f"[bold]Receipt Size:[/bold] {len(receipt)} bytes\n"
        f"[bold]Artifact Hash:[/bold] {log_data['epi_artifact_hash'][:16]}...\n"
        f"[bold]Workflow ID:[/bold] {log_data['epi_workflow_id']}\n"
        f"[bold]Signature Valid:[/bold] {'Yes' if log_data['epi_signature_valid'] else 'No'}\n"
        f"\n[dim]AGT AuditLog usage:[/dim]\n"
        f"  data={{'epi_evidence_hex': '{receipt.hex()[:32]}...'}}",
        title="[OK] EPI Evidence Receipt",
        border_style="green",
    )
    console.print(panel)
