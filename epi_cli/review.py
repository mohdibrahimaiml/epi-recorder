"""
epi review <file.epi> — Interactive fault review terminal UI.

Shows each fault from analysis.json one at a time. The reviewer types
confirm / dismiss / skip for each. Their signed decision is appended to
the artifact as review.json without touching the original sealed files.
"""

import json
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.rule import Rule
from rich.syntax import Syntax

from epi_core.container import EPIContainer
from epi_core.trust import create_verification_report, verify_embedded_manifest_signature
from epi_cli.view import _resolve_epi_file

app = typer.Typer(
    help="Review fault analysis results for a .epi artifact.",
    invoke_without_command=True,
    no_args_is_help=False,
    # ignore_unknown_options/allow_extra_args let a subcommand receive its own
    # options (`epi review <file> approve --approval-id ...`): otherwise the
    # group parser rejects options it does not itself define.
    context_settings={
        "allow_interspersed_args": True,
        "ignore_unknown_options": True,
        "allow_extra_args": True,
    },
)
console = Console()


def _analysis_has_fault(analysis: dict | None) -> bool:
    if not isinstance(analysis, dict):
        return False
    return bool(analysis.get("primary_fault") or analysis.get("fault_detected"))


def _read_analysis(epi_path: Path) -> Optional[dict]:
    """Extract analysis.json from a .epi archive."""
    try:
        payload = EPIContainer.read_member_json(epi_path, "analysis.json")
        return payload if isinstance(payload, dict) else None
    except Exception:
        return None


def _read_step(epi_path: Path, step_index: int) -> Optional[dict]:
    """Read a specific step from steps.jsonl by its index field."""
    return EPIContainer.read_step(epi_path, step_index)


def _show_fault(fault: dict, epi_path: Path) -> None:
    """Render a single fault in the terminal."""
    step_num = fault.get("step_number", "?")
    rule_id = fault.get("rule_id", "")
    rule_name = fault.get("rule_name", "")
    severity = fault.get("severity", "").upper()
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

    try:
        EPIContainer.detect_container_format(epi_path)
    except Exception:
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

    # Build the review record. Signing happens after artifact binding so the
    # signature covers the exact sealed evidence hash and review chain pointer.
    record = ReviewRecord(reviewed_by=reviewer, reviews=review_entries)

    priv = None
    try:
        from epi_cli.keys import KeyManager
        km = KeyManager()
        priv = km.load_private_key(key_name)
    except Exception as e:
        console.print(f"[yellow]Could not sign review (key '{key_name}' not found): {e}[/yellow]")
        console.print("[dim]Review will be saved unsigned.[/dim]")

    # Append to artifact
    try:
        add_review_to_artifact(epi_path, record, private_key=priv)
        console.print(f"[green][OK][/green] Review saved to [bold]{epi_path.name}[/bold]")
        confirmed = sum(1 for e in review_entries if e["outcome"] == "confirmed_fault")
        dismissed = sum(1 for e in review_entries if e["outcome"] == "dismissed")
        console.print(f"  [dim]{confirmed} confirmed · {dismissed} dismissed · {len(review_entries) - confirmed - dismissed} skipped[/dim]")
        console.print(
            "[dim]A fault review is not a signed human approval. For an approval a "
            "verifier can confirm: epi review <file.epi> approve --as <name>[/dim]"
        )
    except Exception as e:
        console.print(f"[red][FAIL] Could not write review to artifact: {e}[/red]")
        raise typer.Exit(1)


@app.command("show")
def show_review(ctx: typer.Context):
    """Show the review record from a .epi artifact, if present."""
    from epi_core.review import read_review, verify_review_trust

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
    review_trust = verify_review_trust(epi_path, strict=False)
    console.print(f"  Trust:       {review_trust['status']}")
    if review_trust.get("latest_review_id"):
        console.print(f"  Review ID:   [dim]{review_trust['latest_review_id']}[/dim]")
    if review_trust.get("warnings"):
        console.print(f"  Warnings:    [yellow]{len(review_trust['warnings'])}[/yellow]")
    if review_trust.get("failures"):
        console.print(f"  Failures:    [red]{len(review_trust['failures'])}[/red]")
    console.print()

    approvals = (review_trust.get("human_approval") or {}).get("approvals") or []
    if approvals:
        console.print("[bold]Approvals[/bold] (who signed, and how it was classified)")
        for item in approvals:
            _cls = str(item.get("classification") or "unknown")
            _color = "green" if _cls == "human_signed" else ("red" if _cls == "invalid" else "yellow")
            console.print(
                f"  [{_color}]{_cls}[/{_color}]  {item.get('approver_name') or '—'}"
                f"  [dim](fp {item.get('key_fingerprint') or '—'})[/dim]"
                f"  {item.get('approval_id') or '(case-level)'}"
            )
        console.print(
            "[dim]Only 'human_signed' means a pinned approver, not the agent, signed it.[/dim]"
        )
        console.print()

    for entry in record.reviews:
        if entry.get("entry_type"):
            continue
        outcome = entry.get("outcome", "?")
        color = {"confirmed_fault": "red", "dismissed": "green", "skipped": "dim"}.get(outcome, "white")
        console.print(
            f"  Step {entry.get('fault_step', '?')}  [{color}]{outcome}[/{color}]"
            + (f"  [dim]{entry.get('notes', '')}[/dim]" if entry.get("notes") else "")
        )

    console.print(
        "[dim]A person signs a real approval with: "
        "epi review <file.epi> approve --approval-id <id> --as <name>[/dim]"
    )


@app.command("bind")
def bind_review(
    ctx: typer.Context,
    reviewer: Optional[str] = typer.Option(
        None,
        "--reviewer",
        "-r",
        help="Reviewer identity for the new artifact-bound review entry.",
    ),
    key_name: str = typer.Option(
        "default",
        "--key",
        "-k",
        help="Key name to sign the artifact-bound review with.",
    ),
):
    """Promote the latest unbound review into a new artifact-bound signed review."""
    from epi_cli.keys import KeyManager
    from epi_core.review import ReviewRecord, add_review_to_artifact, read_review, verify_review_trust

    epi_path = ctx.obj["epi_path"]
    latest = read_review(epi_path)
    if latest is None:
        console.print(f"[red][X][/red] No review found in {epi_path.name}.")
        raise typer.Exit(1)

    reviewer = (reviewer or latest.reviewed_by or "").strip()
    if not reviewer:
        console.print("[red][X][/red] Reviewer identity is required.")
        raise typer.Exit(1)

    try:
        private_key = KeyManager().load_private_key(key_name)
    except Exception as exc:
        console.print(f"[red][X][/red] Could not load signing key '{key_name}': {exc}")
        raise typer.Exit(1) from exc

    # Only fault-review entries can be re-signed by the agent's key. An approval
    # belongs to the person who signed it: copying it into a record signed by a
    # different key would make the approval's fingerprint claim false, and
    # verification would (correctly) call the file invalid.
    promotable = [
        entry for entry in latest.reviews
        if not (isinstance(entry, dict) and entry.get("entry_type") == "approval")
    ]
    if not promotable:
        console.print(
            "[yellow]Nothing to bind:[/yellow] the latest record is a signed human "
            "approval, not a fault review. It stays as it is."
        )
        raise typer.Exit(0)

    record = ReviewRecord(
        reviewed_by=reviewer,
        reviews=promotable,
    )

    try:
        add_review_to_artifact(epi_path, record, private_key=private_key)
    except Exception as exc:
        console.print(f"[red][X][/red] Could not bind review to artifact: {exc}")
        raise typer.Exit(1) from exc

    trust = verify_review_trust(epi_path, strict=True)
    console.print(f"[green][OK][/green] Added artifact-bound review to [bold]{epi_path.name}[/bold].")
    console.print(f"[dim]Review trust: {trust['status']} - latest review: {trust.get('latest_review_id') or 'unknown'}[/dim]")


@app.command("approve")
def approve(
    ctx: typer.Context,
    approval_id: Optional[str] = typer.Option(
        None,
        "--approval-id",
        help="The approval_id of a sealed agent.approval.request step.",
    ),
    decision: str = typer.Option("approve", "--decision", help="approve or deny"),
    as_: str = typer.Option(
        ...,
        "--as",
        help="Approver name; also the key name in the approver keys dir.",
    ),
    reason: Optional[str] = typer.Option(None, "--reason", help="Why (shown to the verifier)."),
    case_level: bool = typer.Option(
        False, "--case-level", help="Approve the whole run when there is no request step."
    ),
    yes: bool = typer.Option(
        False,
        "--yes",
        help="Skip the typed confirmation (scripted tests only; prints a warning).",
    ),
):
    """Sign a human approval with an approver's own key.

    Signs only with a key from the approver keys dir, never the agent key. The
    key must differ from the sealing key, and a per-request approval needs an
    approval_id that exists as an agent.approval.request in the sealed steps.
    """
    from cryptography.hazmat.primitives import serialization

    from epi_cli.keys import KeyManager
    from epi_core.approvers import _resolve_default_approver_keys_dir
    from epi_core.keys import key_fingerprint
    from epi_core.review import ReviewRecord, add_review_to_artifact, make_approval_entry
    from epi_core.trust import verify_embedded_manifest_signature

    epi_path = ctx.obj["epi_path"]

    try:
        EPIContainer.detect_container_format(epi_path)
    except Exception:
        console.print(f"[red][X] Not a valid .epi file:[/red] {epi_path.name}")
        raise typer.Exit(1)

    if decision not in ("approve", "deny"):
        console.print("[red][X] --decision must be approve or deny.[/red]")
        raise typer.Exit(1)

    # Rule: verify first, refuse otherwise.
    integrity_ok, mismatches = EPIContainer.verify_integrity(epi_path)
    manifest = EPIContainer.read_manifest(epi_path)
    signature_valid, _signer, _message = verify_embedded_manifest_signature(manifest)
    if not integrity_ok or signature_valid is not True:
        console.print("[red][X] Refusing to approve: this file does not verify.[/red]")
        console.print(
            f"  Integrity: {'ok' if integrity_ok else 'FAILED'}"
            f" · Signature: {'valid' if signature_valid is True else 'INVALID or unsigned'}"
        )
        raise typer.Exit(1)

    action = ""
    if case_level:
        if approval_id:
            console.print("[red][X] --case-level cannot be combined with --approval-id.[/red]")
            raise typer.Exit(1)
    else:
        if not approval_id:
            console.print("[red][X] --approval-id is required (or use --case-level).[/red]")
            raise typer.Exit(1)
        request_content = None
        for step in EPIContainer.read_steps(epi_path):
            content = step.get("content") if isinstance(step.get("content"), dict) else {}
            if (
                step.get("kind") == "agent.approval.request"
                and str(content.get("approval_id")) == str(approval_id)
            ):
                request_content = content
                break
        if request_content is None:
            console.print(
                f"[red][X] No agent.approval.request with approval_id "
                f"'{approval_id}' in the sealed steps.[/red]"
            )
            raise typer.Exit(1)
        action = str(request_content.get("action") or "")

    keys_dir = _resolve_default_approver_keys_dir()
    try:
        private_key = KeyManager(keys_dir=keys_dir).load_private_key(as_)
    except Exception as exc:
        console.print(f"[red][X] No approver key '{as_}' in {keys_dir}:[/red] {exc}")
        console.print("[dim]Create one: epi approvers keygen --name <approver>[/dim]")
        raise typer.Exit(1)

    approver_hex = private_key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    ).hex()
    sealing_key = str(manifest.public_key or "").strip().lower()
    if approver_hex == sealing_key:
        console.print(
            "[red][X] Refusing: separation of duties.[/red] That key sealed this run, "
            "so it cannot be the approver."
        )
        raise typer.Exit(1)

    console.print("\n[bold]You are about to sign:[/bold]")
    console.print(f"  Goal:      {manifest.goal or '—'}")
    console.print(f"  Decision:  [bold]{decision}[/bold]")
    console.print(f"  Action:    {action or '(case-level approval of the whole run)'}")
    if approval_id:
        console.print(f"  Approval:  {approval_id}")
    console.print(f"  Manifest:  {_build_review_trust_report(epi_path)['workflow_id']}")
    console.print(f"  Sealer fp: {' '.join(sealing_key[i:i + 4] for i in range(0, 16, 4))}")
    console.print(f"  Your fp:   {key_fingerprint(approver_hex)}")

    if not yes:
        typed = Prompt.ask(f'Type "{decision}" to sign')
        if typed.strip().lower() != decision:
            console.print("[yellow]Cancelled — nothing was written.[/yellow]")
            raise typer.Exit(1)
    else:
        console.print(
            "[yellow]Warning: --yes skipped the confirmation prompt (scripted use only).[/yellow]"
        )

    entry = make_approval_entry(
        approval_id=approval_id,
        decision=decision,
        action=action,
        reason=reason,
        approver_name=as_,
        key_fingerprint_hex=key_fingerprint(approver_hex, grouped=False),
        case_level=case_level,
    )
    record = ReviewRecord(
        reviewed_by=as_,
        reviews=[entry],
        reviewer_identity={
            "type": "email" if "@" in as_ else "name",
            "value": as_,
            "role": "Approver",
            "org": "Unknown",
            # In the file this is the writer's claim. It stays False: only the
            # verifier decides, against its own approver registry.
            "verified": False,
        },
    )

    try:
        add_review_to_artifact(epi_path, record, private_key=private_key)
    except Exception as exc:
        console.print(f"[red][FAIL] Could not write the approval:[/red] {exc}")
        raise typer.Exit(1)

    console.print(f"[green][OK][/green] Signed approval written to [bold]{epi_path.name}[/bold]")
    console.print(f"  [cyan]Fingerprint:[/cyan] {key_fingerprint(approver_hex)}")
