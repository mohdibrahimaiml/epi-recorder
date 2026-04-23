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
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.panel import Panel

from epi_core.container import EPIContainer
from epi_core.review import verify_review_trust
from epi_core.trust import (
    create_verification_report, 
    verify_embedded_manifest_signature,
    VerificationPolicy,
    apply_policy,
    TrustRegistry
)
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
    sys.stdout.flush()


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
        "facts": {
            "integrity_ok": False,
            "signature_valid": signature_valid,
            "has_signature": has_signature,
            "mismatches": mismatch_map,
        },
        "identity": {
            "status": "UNKNOWN",
            "name": signer_name,
            "detail": message,
        },
        "summary": {
            "integrity": "FAILED",
            "trust": "NONE",
        },
        "decision": {
            "status": "FAIL",
            "policy": "none",
            "reason": message
        },
        # Legacy flat fields for backward compatibility
        "integrity_ok": False,
        "signature_valid": signature_valid,
        "trust_level": "NONE",
        "has_signature": has_signature,
        "mismatches_count": len(mismatch_map),
        "signer": signer_name,
        "files_checked": 0,
        "workflow_id": None,
        "created_at": None,
        "spec_version": None,
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
    policy: Annotated[VerificationPolicy, typer.Option(
        "--policy", 
        help="Governance policy to apply (permissive, standard, strict)"
    )] = VerificationPolicy.STANDARD,
) -> None:
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
    registry = TrustRegistry()
    
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
            
            # Version compatibility check
            SUPPORTED_VERSIONS = ["1.0.0", "1.1.0"]
            if manifest.spec_version not in SUPPORTED_VERSIONS:
                 if verbose:
                      console.print(f"  [yellow]![/yellow] Unsupported spec_version '{manifest.spec_version}' (supported: {SUPPORTED_VERSIONS})")
                 # We still continue but this can be checked by policy later
        except Exception as e:
            _handle_verification_error(
                message=f"Structural validation failed: {e}",
                json_output=json_output,
                console_message=f"[red][FAIL] Structural validation failed:[/red] {e}",
                error_type="structural_validation_failed",
            )
        
        # ========== STEP 2: INTEGRITY CHECKS (Facts) ==========
        if verbose:
            console.print("\n[bold]Step 2: Integrity Checks (Facts)[/bold]")
        
        integrity_ok, mismatches = EPIContainer.verify_integrity(epi_file)
        
        # ========== STEP 3: FORENSIC AUDIT (Facts) ==========
        # Moved forward as these are objective 'facts'
        sequence_ok = True
        completeness_ok = True
        steps_hash_ok = True
        
        try:
            import zipfile
            import hashlib as _hashlib
            import json

            with zipfile.ZipFile(epi_file, "r") as zf:
                members = zf.namelist()
                steps_member = next((m for m in members if m.endswith("steps.jsonl")), None)
                if steps_member:
                    raw_steps = zf.read(steps_member).decode("utf-8").splitlines()
                    steps = [json.loads(line) for line in raw_steps]
                    
                    # 1. Index Sequence Audit (Monotonicity)
                    indices = [s.get("index", 0) for s in steps]
                    sequence_ok = all(indices[i] == indices[i-1] + 1 for i in range(1, len(indices))) if indices else True
                    
                    # 2. Timestamp Monotonicity Audit
                    # Check both OTel-style ns and standard ISO timestamps
                    times = []
                    for s in steps:
                        t_ns = s.get("content", {}).get("timestamp_ns")
                        if t_ns is not None:
                            times.append(t_ns)
                        else:
                            # Fallback to ISO timestamp string comparison (safe for monotonicity)
                            times.append(s.get("timestamp", ""))
                    
                    is_time_monotonic = all(times[i] >= times[i-1] for i in range(1, len(times))) if times else True
                    sequence_ok = sequence_ok and is_time_monotonic

                    # 3. Semantic Completeness Audit
                    iteration_steps = [s for s in steps if s.get("content", {}).get("subtype") == "guardrails"]
                    completeness_ok = len(iteration_steps) > 0 and all(len(s.get("content", {}).get("validators", [])) > 0 for s in iteration_steps)

                    # 4. Steps Hash Verification
                    execution_data = {}
                    try:
                        execution_data = EPIContainer.read_member_json(epi_file, "execution.json")
                    except: pass
                    
                    claimed_hash = execution_data.get("steps_hash") or (manifest.trust or {}).get("steps_hash")
                    if claimed_hash:
                        actual_hash = _hashlib.sha256(zf.read(steps_member)).hexdigest()
                        steps_hash_ok = (actual_hash == claimed_hash)
        except Exception as _e:
            if verbose:
                console.print(f"  [yellow]![/yellow] Forensic audit warning: {_e}")

        integrity_ok = integrity_ok and steps_hash_ok

        # ========== STEP 4: AUTHENTICITY CHECKS (Trust) ==========
        if verbose:
            console.print("\n[bold]Step 4: Authenticity Checks (Trust)[/bold]")
        
        signature_valid, signer_name, sig_message = verify_embedded_manifest_signature(manifest)
        
        # ========== STEP 5: CREATE REPORT & APPLY POLICY ==========
        report = create_verification_report(
            integrity_ok=integrity_ok,
            signature_valid=signature_valid,
            signer_name=signer_name,
            mismatches=mismatches,
            manifest=manifest,
            trusted_registry=registry,
            sequence_ok=sequence_ok,
            completeness_ok=completeness_ok
        )
        
        # Apply the selected governance policy
        active_policy = VerificationPolicy.STRICT if strict else policy
        apply_policy(report, active_policy)

        # ========== STEP 5: REVIEW TRUST CHECKS ==========
        if review:
            if verbose:
                console.print("\n[bold]Step 5: Review Trust Checks[/bold]")
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

        # Exit code based on policy decision
        if report["decision"]["status"] == "FAIL" or (review_report is not None and review_report.get("status") == "failed"):
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
    """Print the human-readable verification results with Facts/Identity/Decision separation.

    Supports both the new nested report format (facts/identity/decision) and
    the legacy flat format for backward compatibility.
    """
    # Normalise: detect new nested vs old flat format
    if "facts" in report:
        facts = report["facts"]
        identity = report.get("identity", {})
        decision = report.get("decision", {})
        integrity_ok = facts["integrity_ok"]
        signature_valid = facts["signature_valid"]
        sequence_ok = facts.get("sequence_ok", True)
        completeness_ok = facts.get("completeness_ok", True)
        identity_status = identity.get("status", "UNKNOWN")
        identity_name = identity.get("name")
        identity_detail = identity.get("detail", "")
        public_key_id = identity.get("public_key_id")
        decision_status = decision.get("status", "FAIL")
        decision_policy = decision.get("policy", "none")
        decision_reason = decision.get("reason", "")
    else:
        # Legacy flat format
        integrity_ok = report.get("integrity_ok", False)
        signature_valid = report.get("signature_valid", None)
        sequence_ok = True
        completeness_ok = True
        identity_status = "KNOWN" if report.get("identity_trusted") else "UNKNOWN"
        identity_name = report.get("signer")
        identity_detail = report.get("trust_message", "")
        public_key_id = None
        decision_status = "PASS" if (integrity_ok and signature_valid is not False) else "FAIL"
        decision_policy = "none"
        decision_reason = report.get("trust_message", "")

    # Header and Result
    status_symbol = "[bold green]✔[/bold green]" if decision_status == "PASS" else "[bold red]✘[/bold red]"
    panel_style = "green" if decision_status == "PASS" else "red"

    content_lines = []

    # Decision Layer
    content_lines.append(f"[bold]DECISION: {decision_status}[/bold]")
    content_lines.append(f"Policy: {decision_policy}")
    content_lines.append(f"Reason: {decision_reason}")
    content_lines.append("")

    # Fact Layer
    content_lines.append("[bold underline]FACTS (Objective Proofs)[/bold underline]")
    i_color = "green" if integrity_ok else "red"
    content_lines.append(f"  [{i_color}]- Integrity:    {'Verified' if integrity_ok else 'FAILED'}[/{i_color}]")

    s_color = "green" if signature_valid else ("yellow" if signature_valid is None else "red")
    s_text = "Valid" if signature_valid else ("Unsigned" if signature_valid is None else "INVALID")
    content_lines.append(f"  [{s_color}]- Signature:    {s_text}[/{s_color}]")

    f_color = "green" if (sequence_ok and completeness_ok) else "red"
    f_text = "PASS" if (sequence_ok and completeness_ok) else "FAIL"
    content_lines.append(f"  [{f_color}]- Forensic:     {f_text}[/{f_color}]")
    content_lines.append("")

    # Identity Layer
    content_lines.append("[bold underline]IDENTITY (Trust Context)[/bold underline]")
    id_color = "green" if identity_status == "KNOWN" else ("red" if identity_status == "REVOKED" else "yellow")
    content_lines.append(f"  [{id_color}]- Status:       {identity_status}[/{id_color}]")
    content_lines.append(f"  - Name:         {identity_name or 'Unknown'}")
    if public_key_id:
        content_lines.append(f"  - Key ID:       {public_key_id}...")
    content_lines.append(f"  - Source:       {identity_detail}")

    if "warnings" in report and report["warnings"]:
        content_lines.append("")
        content_lines.append("[bold yellow]Warnings:[/bold yellow]")
        for w in report["warnings"]:
            content_lines.append(f"  [yellow]![/yellow] {w}")

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



 
