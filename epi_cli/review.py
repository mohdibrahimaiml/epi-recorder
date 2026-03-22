"""
epi review <file.epi> — Interactive fault review terminal UI.

Shows each fault from analysis.json one at a time. The reviewer types
confirm / dismiss / skip for each. Their signed decision is appended to
the artifact as review.json without touching the original sealed files.
"""

import json
import zipfile
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.rule import Rule
from rich.syntax import Syntax
from rich.text import Text

from epi_core.container import EPIContainer
from epi_core.trust import create_verification_report, verify_embedded_manifest_signature
from epi_cli.view import _resolve_epi_file

app = typer.Typer(
    help="Review fault analysis results for a .epi artifact.",
    invoke_without_command=True,
    no_args_is_help=False,
    context_settings={"allow_interspersed_args": True},
)
console = Console()


def _analysis_has_fault(analysis: dict | None) -> bool:
    if not isinstance(analysis, dict):
        return False
    return bool(analysis.get("primary_fault") or analysis.get("fault_detected"))


def _read_analysis(epi_path: Path) -> Optional[dict]:
    """Extract analysis.json from a .epi archive."""
    with zipfile.ZipFile(epi_path, "r") as zf:
        if "analysis.json" not in zf.namelist():
            return None
        try:
            return json.loads(zf.read("analysis.json").decode("utf-8"))
        except Exception:
            return None


def _read_step(epi_path: Path, step_index: int) -> Optional[dict]:
    """Read a specific step from steps.jsonl by its index field."""
    with zipfile.ZipFile(epi_path, "r") as zf:
        if "steps.jsonl" not in zf.namelist():
            return None
        for line in zf.read("steps.jsonl").decode("utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                step = json.loads(line)
                if step.get("index") == step_index:
                    return step
            except Exception:
                pass
    return None


def _show_fault(fault: dict, epi_path: Path) -> None:
    """Render a single fault in the terminal."""
    step_num = fault.get("step_number", "?")
    rule_id = fault.get("rule_id", "")
    rule_name = fault.get("rule_name", "")
    severity = fault.get("severity", "").upper()
    fault_type = fault.get("fault_type", "")
    plain = fault.get("plain_english", "")
    chain = fault.get("fault_chain", [])

    severity_color = {
        "CRITICAL": "bold red", "HIGH": "red", "MEDIUM": "yellow", "LOW": "dim"
    }.get(severity, "white")

    console.print(Rule(style="dim"))
    title_parts = [f"[bold]FAULT — Step {step_num}[/bold]"]
    if rule_id:
        title_parts.append(f"[cyan]{rule_id}[/cyan]")
    if rule_name:
        title_parts.append(f"[dim]{rule_name}[/dim]")
    if severity:
        title_parts.append(f"[{severity_color}][{severity}][/{severity_color}]")
    console.print("  " + "  ·  ".join(title_parts))
    console.print()

    console.print(Panel(plain, title="[bold]What happened[/bold]", border_style="yellow", padding=(0, 1)))

    # Show fault chain steps
    for chain_entry in chain:
        chain_step_num = chain_entry.get("step_number", "?")
        chain_step_idx = chain_entry.get("step_index", 0)
        role = chain_entry.get("role", "")
        detail = chain_entry.get("detail", "")
        role_color = "blue" if "source" in role else "red"
        console.print(f"  [dim]Step {chain_step_num}[/dim] [{role_color}]{role}[/{role_color}]  {detail}")

        step_data = _read_step(epi_path, chain_step_idx)
        if step_data:
            content_json = json.dumps(step_data.get("content", {}), indent=2)
            console.print(
                Syntax(content_json, "json", theme="monokai", line_numbers=False, word_wrap=True),
                style="dim",
            )
        console.print()


def _review_guidance(fault: dict) -> tuple[str, str]:
    """Return short reviewer-facing impact/action guidance."""
    severity = str(fault.get("severity", "")).upper()
    if severity == "CRITICAL":
        return (
            "This fault can invalidate trust in the decision outcome.",
            "Confirm unless you can prove the behavior is expected and policy-safe.",
        )
    return (
        "This fault may affect reliability or policy compliance.",
        "Confirm or dismiss with notes so downstream reviewers can trace your decision.",
    )


def _build_review_trust_report(epi_path: Path) -> dict:
    manifest = EPIContainer.read_manifest(epi_path)
    integrity_ok, mismatches = EPIContainer.verify_integrity(epi_path)
    signature_valid, signer_name, _message = verify_embedded_manifest_signature(manifest)
    return create_verification_report(
        integrity_ok=integrity_ok,
        signature_valid=signature_valid,
        signer_name=signer_name,
        mismatches=mismatches,
        manifest=manifest,
    )


def _print_review_trust_summary(report: dict) -> None:
    if report["trust_level"] == "HIGH":
        status = "[green]Signed[/green]"
        guidance = "This artifact is cryptographically verified and safe to review."
    elif report["trust_level"] == "MEDIUM":
        status = "[yellow]Unsigned[/yellow]"
        guidance = "Integrity is intact, but there is no signature. Review the content, but do not treat origin as cryptographically proven."
    else:
        status = "[red]Tampered or invalid[/red]"
        guidance = "Do not review this artifact as evidence. Recover the original sealed file first."

    console.print(
        Panel(
            f"[bold]Evidence status:[/bold] {status}\n"
            f"[bold]What this means:[/bold] {report['trust_message']}\n"
            f"[bold]Reviewer guidance:[/bold] {guidance}",
            title="Trust Check",
            border_style="green" if report["trust_level"] == "HIGH" else ("yellow" if report["trust_level"] == "MEDIUM" else "red"),
        )
    )


@app.callback(invoke_without_command=True)
def review(
    ctx: typer.Context,
    epi_file: str = typer.Argument(..., help="Path to .epi file to review"),
    reviewer: Optional[str] = typer.Option(None, "--reviewer", "-r",
                                            help="Reviewer identity (email or name)"),
    key_name: str = typer.Option("default", "--key", "-k",
                                  help="Key name to sign the review with"),
):
    """
    Interactively review fault analysis results for a .epi artifact.

    Shows each detected fault and asks: confirm / dismiss / skip.
    Signs the review and appends it to the artifact as review.json.
    """
    try:
        resolved_path = _resolve_epi_file(epi_file)
    except FileNotFoundError:
        console.print(f"[red][X] File not found:[/red] {epi_file}")
        raise typer.Exit(1)

    ctx.obj = {"epi_path": resolved_path}

    if ctx.invoked_subcommand:
        return

    from epi_core.review import ReviewRecord, add_review_to_artifact, make_review_entry

    epi_path = resolved_path

    if not zipfile.is_zipfile(epi_path):
        console.print(f"[red][X] Not a valid .epi file:[/red] {epi_file}")
        raise typer.Exit(1)

    trust_report = _build_review_trust_report(epi_path)
    console.print()
    _print_review_trust_summary(trust_report)
    console.print()
    if trust_report["trust_level"] == "NONE":
        console.print("[red][X] Review stopped because the artifact is not trustworthy evidence.[/red]")
        raise typer.Exit(1)

    analysis = _read_analysis(epi_path)
    if analysis is None:
        console.print(f"[yellow]No analysis.json found in {epi_path.name}[/yellow]")
        console.print("[dim]This artifact was created before the Fault Intelligence layer.[/dim]")
        raise typer.Exit(0)

    if not _analysis_has_fault(analysis):
        console.print(f"[green][OK][/green] No faults detected in [bold]{epi_path.name}[/bold]. Nothing to review.")
        raise typer.Exit(0)

    # Collect all faults to review
    faults = []
    if analysis.get("primary_fault"):
        faults.append(analysis["primary_fault"])
    faults.extend(f for f in (analysis.get("secondary_flags") or [])
                  if f.get("fault_type") == "POLICY_VIOLATION")

    if not faults:
        console.print("[dim]Only heuristic observations found — no policy violations require review.[/dim]")
        raise typer.Exit(0)

    console.print(f"\n[bold]Fault Review[/bold] — [cyan]{epi_path.name}[/cyan]")
    console.print(f"[dim]{len(faults)} fault(s) to review[/dim]\n")

    # Get reviewer identity
    if not reviewer:
        reviewer = Prompt.ask("Your name or email (for attribution)")
    if not reviewer.strip():
        console.print("[red]Reviewer identity is required.[/red]")
        raise typer.Exit(1)

    review_entries = []
    for fault in faults:
        _show_fault(fault, epi_path)
        impact, action = _review_guidance(fault)
        console.print(f"[bold]Impact:[/bold] {impact}")
        console.print(f"[bold]Action:[/bold] {action}\n")

        console.print("[bold]Your decision:[/bold]")
        console.print("  [green][c][/green] Confirm as genuine fault")
        console.print("  [yellow][d][/yellow] Dismiss as expected behavior")
        console.print("  [dim][s][/dim] Skip (decide later)")
        console.print()

        decision = ""
        while decision not in ("c", "d", "s"):
            decision = Prompt.ask("Decision", choices=["c", "d", "s"], default="s").strip().lower()

        notes = ""
        if decision in ("c", "d"):
            notes = Prompt.ask("Notes (optional, press Enter to skip)", default="")

        outcome_map = {"c": "confirmed_fault", "d": "dismissed", "s": "skipped"}
        review_entries.append(make_review_entry(
            fault=fault,
            outcome=outcome_map[decision],
            notes=notes,
            reviewer=reviewer,
        ))
        console.print()

    if not any(e["outcome"] != "skipped" for e in review_entries):
        console.print("[dim]All faults skipped. No review record written.[/dim]")
        raise typer.Exit(0)

    # Build and sign the review record
    record = ReviewRecord(reviewed_by=reviewer, reviews=review_entries)

    try:
        from epi_cli.keys import KeyManager
        km = KeyManager()
        priv = km.load_private_key(key_name)
        record.sign(priv)
    except Exception as e:
        console.print(f"[yellow]Could not sign review (key '{key_name}' not found): {e}[/yellow]")
        console.print("[dim]Review will be saved unsigned.[/dim]")

    # Append to artifact
    try:
        add_review_to_artifact(epi_path, record)
        console.print(f"[green][OK][/green] Review saved to [bold]{epi_path.name}[/bold]")
        confirmed = sum(1 for e in review_entries if e["outcome"] == "confirmed_fault")
        dismissed = sum(1 for e in review_entries if e["outcome"] == "dismissed")
        console.print(f"  [dim]{confirmed} confirmed · {dismissed} dismissed · {len(review_entries) - confirmed - dismissed} skipped[/dim]")
    except Exception as e:
        console.print(f"[red][FAIL] Could not write review to artifact: {e}[/red]")
        raise typer.Exit(1)


@app.command("show")
def show_review(ctx: typer.Context):
    """Show the review record from a .epi artifact, if present."""
    from epi_core.review import read_review

    epi_path = ctx.obj["epi_path"]
    console.print()
    _print_review_trust_summary(_build_review_trust_report(epi_path))
    console.print()
    record = read_review(epi_path)

    if record is None:
        console.print(f"[dim]No review found in {epi_path.name}[/dim]")
        return

    console.print(f"\n[bold]Review Record[/bold] — {epi_path.name}")
    console.print(f"  Reviewed by: [cyan]{record.reviewed_by}[/cyan]")
    console.print(f"  Reviewed at: [dim]{record.reviewed_at}[/dim]")
    console.print(f"  Signature:   {'[green]present[/green]' if record.review_signature else '[yellow]unsigned[/yellow]'}")
    console.print()

    for entry in record.reviews:
        outcome = entry.get("outcome", "?")
        color = {"confirmed_fault": "red", "dismissed": "green", "skipped": "dim"}.get(outcome, "white")
        console.print(
            f"  Step {entry.get('fault_step', '?')}  [{color}]{outcome}[/{color}]"
            + (f"  [dim]{entry.get('notes', '')}[/dim]" if entry.get("notes") else "")
        )
