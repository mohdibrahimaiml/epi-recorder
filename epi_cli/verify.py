"""
EPI CLI Verify - Verify .epi file integrity and authenticity.

Performs comprehensive verification including:
- Structural validation (ZIP format, mimetype, manifest schema)
- Integrity checks (file hashes match manifest)
- Authenticity checks (Ed25519 signature verification)
"""

import json
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from epi_core.container import EPIContainer
from epi_core.trust import create_verification_report, verify_embedded_manifest_signature
from epi_cli.view import _resolve_epi_file

console = Console()

def _write_verification_report(report: dict, epi_file: Path, report_out: Path) -> None:
    """Serialise a verification report dict to a plain-text file."""
    from datetime import datetime, timezone

    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    result_line = "VERIFIED ✓" if report["trust_level"] == "HIGH" else (
        "VERIFIED (unsigned) ✓" if report["trust_level"] == "MEDIUM" else "FAILED ✗"
    )
    integrity_line = (
        f"PASSED — {report['files_checked']} files verified (SHA-256)"
        if report["integrity_ok"]
        else f"FAILED — {report['mismatches_count']} file(s) modified"
    )
    if report["signature_valid"]:
        sig_line = f"VALID — Ed25519, signed by key '{report['signer']}'"
    elif report["signature_valid"] is None:
        sig_line = "NOT SIGNED — no signature present"
    else:
        sig_line = "INVALID — signature does not match"

    if report["trust_level"] == "HIGH":
        suitable = (
            "\nThis artifact has not been modified since it was signed.\n"
            "It is suitable for submission as evidence to regulators,\n"
            "auditors, or legal proceedings."
        )
    elif report["trust_level"] == "MEDIUM":
        suitable = "\nIntegrity intact but artifact is unsigned.\nConsider signing with: epi keys generate"
    else:
        suitable = "\nThis artifact FAILED verification and should not be trusted."

    lines = [
        "EPI VERIFICATION REPORT",
        f"Generated: {generated}",
        f"File: {epi_file.name}",
        "",
        f"RESULT: {result_line}",
        f"Trust Level: {report['trust_level']}",
        "",
        f"Integrity Check:  {integrity_line}",
        f"Signature Check:  {sig_line}",
        "",
        "ARTIFACT DETAILS",
        f"Workflow:     {report['workflow_id']}",
        f"Created:      {report['created_at']}",
        f"Spec Version: {report['spec_version']}",
        suitable,
        "",
        "---",
        "Verified by EPI (Evidence Packaged Infrastructure)",
        f"epi verify {epi_file.name}",
    ]
    report_out.write_text("\n".join(lines), encoding="utf-8")


def verify_command(
    ctx: typer.Context,
    epi_file: Path,
    json_output: bool = False,
    verbose: bool = False,
    report_out: Optional[Path] = None,
):
    """
    Verify .epi file integrity and authenticity.
    
    Performs three levels of verification:
    1. Structural: ZIP format, mimetype, manifest schema
    2. Integrity: File hashes match manifest
    3. Authenticity: Ed25519 signature validation
    """
    try:
        epi_file = _resolve_epi_file(str(epi_file))
    except FileNotFoundError:
        console.print(f"[red][FAIL] Error:[/red] File not found: {epi_file}")
        raise typer.Exit(1)
    
    # Initialize verification state
    manifest = None
    integrity_ok = False
    signature_valid = None
    signer_name = None
    mismatches = {}
    
    try:
        # ========== STEP 1: STRUCTURAL VALIDATION ==========
        if verbose:
            console.print("\n[bold]Step 1: Structural Validation[/bold]")
        
        # Read manifest (validates ZIP format and mimetype)
        try:
            manifest = EPIContainer.read_manifest(epi_file)
            if verbose:
                console.print("  [green][OK][/green] Valid ZIP format")
                console.print("  [green][OK][/green] Valid mimetype")
                console.print("  [green][OK][/green] Valid manifest schema")
        except Exception as e:
            console.print(f"[red][FAIL] Structural validation failed:[/red] {e}")
            raise typer.Exit(1)
        
        # ========== STEP 2: INTEGRITY CHECKS ==========
        if verbose:
            console.print("\n[bold]Step 2: Integrity Checks[/bold]")
        
        integrity_ok, mismatches = EPIContainer.verify_integrity(epi_file)
        
        if verbose:
            if integrity_ok:
                console.print(f"  [green][OK][/green] All {len(manifest.file_manifest)} files verified")
            else:
                console.print(f"  [red][FAIL][/red] {len(mismatches)} file(s) failed verification")
                for filename, reason in mismatches.items():
                    console.print(f"    [red]-[/red] {filename}: {reason}")
        
        # ========== STEP 3: AUTHENTICITY CHECKS ==========
        if verbose:
            console.print("\n[bold]Step 3: Authenticity Checks[/bold]")
        
        signature_valid, signer_name, sig_message = verify_embedded_manifest_signature(manifest)
        if verbose:
            if signature_valid is True:
                console.print(f"  [green][OK][/green] {sig_message}")
            elif signature_valid is None:
                console.print("  [yellow][WARN][/yellow]  No signature present (unsigned)")
            else:
                console.print(f"  [red][FAIL][/red] {sig_message}")
        
        # ========== CREATE REPORT ==========
        report = create_verification_report(
            integrity_ok=integrity_ok,
            signature_valid=signature_valid,
            signer_name=signer_name,
            mismatches=mismatches,
            manifest=manifest
        )
        
        # ========== OUTPUT REPORT ==========
        if json_output:
            # JSON output (write directly to stdout to avoid Rich line-wrapping
            # inserted newlines that would corrupt machine-readable JSON).
            sys.stdout.write(json.dumps(report, indent=2) + "\n")
        else:
            # Rich formatted output
            print_trust_report(report, epi_file, verbose)

        # ========== WRITE REPORT FILE ==========
        if report_out is not None:
            dest = report_out
            _write_verification_report(report, epi_file, dest)
            if not json_output:
                console.print(f"[green][OK][/green] Verification report written: {dest}")

        # Exit code based on verification result
        if not integrity_ok or signature_valid is False:
            raise typer.Exit(1)
    
    except typer.Exit:
        raise
    except KeyboardInterrupt:
        console.print("\n[yellow]Verification interrupted[/yellow]")
        raise typer.Exit(130)
    except Exception as e:
        if verbose:
            console.print_exception()
        else:
            console.print(f"[red][FAIL] Verification failed:[/red] {e}")
        raise typer.Exit(1)


def print_trust_report(report: dict, epi_file: Path, verbose: bool = False):
    """
    Print a formatted trust report using Rich.
    
    Args:
        report: Verification report dict
        epi_file: Path to .epi file
        verbose: Whether to show detailed information
    """
    # Determine overall status symbol and color
    if report["trust_level"] == "HIGH":
        status_symbol = "[OK]"
        status_color = "green"
        panel_style = "green"
    elif report["trust_level"] == "MEDIUM":
        status_symbol = "[WARN]"
        status_color = "yellow"
        panel_style = "yellow"
    else:
        status_symbol = "[FAIL]"
        status_color = "red"
        panel_style = "red"
    
    # Build panel content
    content_lines = []
    content_lines.append(f"[bold]File:[/bold] {epi_file}")
    content_lines.append(f"[bold]Trust Level:[/bold] [{status_color}]{report['trust_level']}[/{status_color}]")
    content_lines.append(f"[bold]Message:[/bold] {report['trust_message']}")
    content_lines.append("")
    
    # Integrity status
    if report["integrity_ok"]:
        content_lines.append(f"[green][OK] Integrity:[/green] Verified ({report['files_checked']} files)")
    else:
        content_lines.append(f"[red][FAIL] Integrity:[/red] Failed ({report['mismatches_count']} mismatches)")
    
    # Signature status
    if report["signature_valid"]:
        content_lines.append(f"[green][OK] Signature:[/green] Valid (key: {report['signer']})")
    elif report["signature_valid"] is None:
        content_lines.append("[yellow][WARN]  Signature:[/yellow] Not signed")
    else:
        content_lines.append(f"[red][FAIL] Signature:[/red] Invalid")
    
    # Show metadata if verbose
    if verbose:
        content_lines.append("")
        content_lines.append(f"[dim]Workflow ID:[/dim] {report['workflow_id']}")
        content_lines.append(f"[dim]Created:[/dim] {report['created_at']}")
        content_lines.append(f"[dim]Spec Version:[/dim] {report['spec_version']}")
    
    # Show mismatches if any
    if report["mismatches_count"] > 0 and verbose:
        content_lines.append("")
        content_lines.append("[bold red]File Mismatches:[/bold red]")
        for filename, reason in report["mismatches"].items():
            content_lines.append(f"  [red]-[/red] {filename}: {reason}")
    
    content = "\n".join(content_lines)
    
    # Print panel
    panel = Panel(
        content,
        title=f"{status_symbol} EPI Verification Report",
        border_style=panel_style,
        expand=False
    )
    console.print("\n")
    console.print(panel)
    console.print("")



 
