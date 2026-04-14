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

from epi_core.container import EPIContainer
from epi_core.review import verify_review_trust
from epi_core.trust import create_verification_report, verify_embedded_manifest_signature
from epi_cli.view import _resolve_epi_file

console = Console()


def _print_share_hint() -> None:
    """Show the lowest-friction next steps after a successful verification."""
    console.print("")
    console.print("[bold]Share / review this case file:[/bold]")
    console.print("  [cyan]epi share <file.epi>[/cyan]       hosted link that opens in any browser")
    console.print("  [cyan]https://epilabs.org/verify[/cyan]  browser trust check, no install required")
    console.print("  [cyan]epi connect open[/cyan]           local team review workspace")


def _emit_json_report(report: dict) -> None:
    """Write a machine-readable verification report directly to stdout."""
    sys.stdout.write(json.dumps(report, indent=2) + "\n")


def _build_failure_report(
    message: str,
    *,
    error_type: str,
    signature_valid: bool | None = None,
    signer_name: str | None = None,
    has_signature: bool = False,
    mismatches: dict[str, str] | None = None,
) -> dict:
    """Return a consistent JSON failure payload for pre-manifest verification errors."""
    mismatch_map = mismatches or {}
    return {
        "integrity_ok": False,
        "signature_valid": signature_valid,
        "signer": signer_name,
        "has_signature": has_signature,
        "spec_version": None,
        "workflow_id": None,
        "created_at": None,
        "files_checked": 0,
        "mismatches_count": len(mismatch_map),
        "mismatches": mismatch_map,
        "trust_level": "NONE",
        "trust_message": message,
        "error": message,
        "error_type": error_type,
    }


def _handle_verification_error(
    *,
    message: str,
    json_output: bool,
    console_message: str | None = None,
    error_type: str = "verification_failed",
    signature_valid: bool | None = None,
    signer_name: str | None = None,
    has_signature: bool = False,
    mismatches: dict[str, str] | None = None,
) -> None:
    """Emit a user-facing or JSON verification failure and exit 1."""
    if json_output:
        _emit_json_report(
            _build_failure_report(
                message,
                error_type=error_type,
                signature_valid=signature_valid,
                signer_name=signer_name,
                has_signature=has_signature,
                mismatches=mismatches,
            )
        )
    else:
        console.print(console_message or message)
    raise typer.Exit(1)

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
    review: bool = False,
    strict: bool = False,
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
        _handle_verification_error(
            message=f"File not found: {epi_file}",
            json_output=json_output,
            console_message=f"[red][FAIL] Error:[/red] File not found: {epi_file}",
            error_type="file_not_found",
        )
    
    # Initialize verification state
    manifest = None
    integrity_ok = False
    signature_valid = None
    signer_name = None
    mismatches = {}
    review_report = None
    
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
            _handle_verification_error(
                message=f"Structural validation failed: {e}",
                json_output=json_output,
                console_message=f"[red][FAIL] Structural validation failed:[/red] {e}",
                error_type="structural_validation_failed",
            )
        
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

        # ========== STEP 4: REVIEW TRUST CHECKS ==========
        if review:
            if verbose:
                console.print("\n[bold]Step 4: Review Trust Checks[/bold]")
            review_report = verify_review_trust(epi_file, strict=strict)
            report["review_trust"] = review_report
            if verbose:
                if review_report["status"] == "verified":
                    console.print("  [green][OK][/green] Review ledger, binding, and signatures verified")
                elif review_report["status"] == "warnings":
                    console.print("  [yellow][WARN][/yellow] Review trust warnings present")
                else:
                    console.print("  [red][FAIL][/red] Review trust verification failed")
        
        # ========== OUTPUT REPORT ==========
        if json_output:
            # JSON output (write directly to stdout to avoid Rich line-wrapping
            # inserted newlines that would corrupt machine-readable JSON).
            _emit_json_report(report)
        else:
            # Rich formatted output
            print_trust_report(report, epi_file, verbose)
            if review_report is not None:
                print_review_trust_report(review_report)

        # ========== WRITE REPORT FILE ==========
        if report_out is not None:
            dest = report_out
            _write_verification_report(report, epi_file, dest)
            if not json_output:
                console.print(f"[green][OK][/green] Verification report written: {dest}")

        if not json_output and integrity_ok and signature_valid is not False:
            _print_share_hint()
            try:
                from epi_cli.telemetry_hint import maybe_print_telemetry_hint

                maybe_print_telemetry_hint(console, "verify")
            except Exception:
                pass

        try:
            from epi_core.telemetry import track_event

            review_failed = bool(review_report and review_report.get("status") == "failed")
            track_event(
                "epi.verify.completed",
                {
                    "command": "verify",
                    "success": bool(integrity_ok and signature_valid is not False and not review_failed),
                    "artifact_bytes": epi_file.stat().st_size,
                    "artifact_count": 1,
                },
            )
        except Exception:
            pass

        # Exit code based on verification result
        if not integrity_ok or signature_valid is False or (
            review_report is not None and review_report.get("status") == "failed"
        ):
            raise typer.Exit(1)
    
    except typer.Exit:
        raise
    except KeyboardInterrupt:
        if json_output:
            _emit_json_report(
                _build_failure_report(
                    "Verification interrupted",
                    error_type="interrupted",
                )
            )
        else:
            console.print("\n[yellow]Verification interrupted[/yellow]")
        raise typer.Exit(130)
    except Exception as e:
        if json_output:
            _emit_json_report(
                _build_failure_report(
                    f"Verification failed: {e}",
                    error_type="verification_failed",
                    signature_valid=signature_valid,
                    signer_name=signer_name,
                    has_signature=bool(getattr(manifest, "signature", None)),
                    mismatches=mismatches,
                )
            )
        elif verbose:
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


def print_review_trust_report(review_report: dict):
    """Print the optional review trust verification result."""
    status = review_report.get("status")
    if status == "verified":
        style = "green"
        title = "[OK] Review Trust"
    elif status == "warnings":
        style = "yellow"
        title = "[WARN] Review Trust"
    else:
        style = "red"
        title = "[FAIL] Review Trust"

    lines = [
        f"[bold]Status:[/bold] {status}",
        f"[bold]Reviews:[/bold] {review_report.get('review_count', 0)}",
        f"[bold]Latest review:[/bold] {review_report.get('latest_review_id') or 'none'}",
        f"[bold]Binding:[/bold] {review_report.get('binding_valid')}",
        f"[bold]Signature:[/bold] {review_report.get('signature_valid')}",
        f"[bold]Chain:[/bold] {review_report.get('chain_valid')}",
    ]

    failures = list(review_report.get("failures") or [])
    warnings = list(review_report.get("warnings") or [])
    if failures:
        lines.append("")
        lines.append("[bold red]Failures:[/bold red]")
        lines.extend(f"  [red]-[/red] {item}" for item in failures[:5])
    if warnings:
        lines.append("")
        lines.append("[bold yellow]Warnings:[/bold yellow]")
        lines.extend(f"  [yellow]-[/yellow] {item}" for item in warnings[:5])

    console.print(Panel("\n".join(lines), title=title, border_style=style, expand=False))
    console.print("")



 
