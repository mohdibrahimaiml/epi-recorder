"""
epi policy — Create, validate, and inspect epi_policy.json files.

Commands:
    epi policy init      Interactive wizard to generate a starter policy file.
    epi policy validate  Validate an existing epi_policy.json.
    epi policy show      Print the current policy summary.
"""

import json
from datetime import date
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table

app = typer.Typer(help="Manage epi_policy.json for fault analysis rules.")
console = Console()

POLICY_FILENAME = "epi_policy.json"


@app.command("init")
def init(
    output: str = typer.Option(POLICY_FILENAME, "--output", "-o",
                                help="Output path for the policy file"),
    profile: Optional[str] = typer.Option(
        None,
        "--profile",
        help="Built-in policy profile, e.g. finance.loan-underwriting or healthcare.triage",
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Accept all defaults without prompting"),
):
    """
    Interactive wizard to generate a starter epi_policy.json.

    Walks through the most common rule types and produces a valid policy
    file that the FaultAnalyzer will pick up on the next `epi run`.
    """
    output_path = Path(output)

    if output_path.exists() and not yes:
        if not Confirm.ask(f"[yellow]{output_path}[/yellow] already exists. Overwrite?", default=False):
            raise typer.Exit(0)

    from epi_core.policy import POLICY_PROFILES, build_policy_from_profile, list_policy_profiles

    console.print("\n[bold]EPI Policy Wizard[/bold]\n")
    console.print("This creates an [cyan]epi_policy.json[/cyan] that defines rules your AI agent must follow.")
    console.print("The Fault Analyzer will check every recording against these rules.\n")

    # System info
    system_name = Prompt.ask("System name", default="my-ai-agent") if not yes else "my-ai-agent"
    system_version = Prompt.ask("System version", default="1.0") if not yes else "1.0"
    policy_version = str(date.today())

    if not profile and not yes:
        use_profile = Confirm.ask(
            "Use a built-in policy profile for healthcare or finance?",
            default=True,
        )
        if use_profile:
            profile = Prompt.ask(
                "Profile",
                default="finance.loan-underwriting",
            )

    if profile:
        if profile not in POLICY_PROFILES:
            available = ", ".join(list_policy_profiles())
            console.print(f"[red][FAIL][/red] Unknown profile: [bold]{profile}[/bold]")
            console.print(f"[dim]Available profiles: {available}[/dim]")
            raise typer.Exit(1)

        policy = build_policy_from_profile(
            profile,
            system_name=system_name,
            system_version=system_version,
            policy_version=policy_version,
        )
        output_path.write_text(json.dumps(policy, indent=2), encoding="utf-8")

        console.print(f"\n[green][OK][/green] Policy written to [bold]{output_path}[/bold]")
        console.print(f"  Profile:  [cyan]{profile}[/cyan]")
        console.print(f"  Rules:    {len(policy['rules'])}")
        console.print(f"  Focus:    {POLICY_PROFILES[profile]['description']}")
        console.print(f"\n[dim]Run [cyan]epi policy validate[/cyan] to inspect the generated policy.[/dim]")
        console.print(f"[dim]Run [cyan]epi run your_script.py[/cyan] to record with policy-grounded fault analysis.[/dim]\n")
        return

    rules = []
    rule_counter = 1

    # ── Constraint guard ──────────────────────────────────────────────────
    console.print("\n[bold]Constraint Guards[/bold] — numerical limits the agent must respect")
    if yes or Confirm.ask("Add a constraint guard rule?", default=True):
        watch_terms = Prompt.ask(
            "  Fields that carry the limit (comma-separated)",
            default="balance,limit,quota"
        ) if not yes else "balance,limit,quota"

        rules.append({
            "id": f"R{rule_counter:03d}",
            "name": "Constraint Guard",
            "severity": "critical",
            "description": "Agent must not exceed the established limit.",
            "type": "constraint_guard",
            "watch_for": [t.strip() for t in watch_terms.split(",") if t.strip()],
            "violation_if": "committed_value > constraint_value",
        })
        rule_counter += 1

    # ── Sequence guard ────────────────────────────────────────────────────
    console.print("\n[bold]Sequence Guards[/bold] — actions that must be preceded by another")
    if yes or Confirm.ask("Add a sequence guard rule?", default=True):
        action_b = Prompt.ask("  Action that REQUIRES a predecessor (e.g. refund)", default="refund") if not yes else "refund"
        action_a = Prompt.ask("  Action that MUST happen first (e.g. verify_identity)", default="verify_identity") if not yes else "verify_identity"

        rules.append({
            "id": f"R{rule_counter:03d}",
            "name": f"Sequence: {action_a} before {action_b}",
            "severity": "high",
            "description": f"Agent must call {action_a} before executing {action_b}.",
            "type": "sequence_guard",
            "required_before": action_b,
            "must_call": action_a,
        })
        rule_counter += 1

    # ── Threshold guard ───────────────────────────────────────────────────
    console.print("\n[bold]Threshold Guards[/bold] — large values that require human approval")
    if yes or Confirm.ask("Add a threshold guard rule?", default=False):
        threshold_val = float(Prompt.ask("  Threshold value", default="10000") if not yes else "10000")
        threshold_field = Prompt.ask("  Field name", default="amount") if not yes else "amount"
        required_action = Prompt.ask("  Required action above threshold", default="human_approval") if not yes else "human_approval"

        rules.append({
            "id": f"R{rule_counter:03d}",
            "name": f"Threshold: {threshold_field} > {threshold_val:,.0f}",
            "severity": "high",
            "description": f"Values above {threshold_val:,.0f} require {required_action}.",
            "type": "threshold_guard",
            "threshold_value": threshold_val,
            "threshold_field": threshold_field,
            "required_action": required_action,
        })
        rule_counter += 1

    # ── Prohibition guard ─────────────────────────────────────────────────
    console.print("\n[bold]Prohibition Guards[/bold] — patterns that must never appear in output")
    if yes or Confirm.ask("Add a prohibition guard rule?", default=False):
        pattern = Prompt.ask("  Regex pattern to prohibit", default=r"sk-[A-Za-z0-9]+") if not yes else r"sk-[A-Za-z0-9]+"

        rules.append({
            "id": f"R{rule_counter:03d}",
            "name": "Prohibition Guard",
            "severity": "critical",
            "description": "Prohibited pattern must never appear in agent output.",
            "type": "prohibition_guard",
            "prohibited_pattern": pattern,
        })
        rule_counter += 1

    policy = {
        "system_name": system_name,
        "system_version": system_version,
        "policy_version": policy_version,
        "rules": rules,
    }

    output_path.write_text(json.dumps(policy, indent=2), encoding="utf-8")
    console.print(f"\n[green][OK][/green] Policy written to [bold]{output_path}[/bold]")
    console.print(f"  {len(rules)} rule(s) defined")
    console.print(f"\n[dim]Run [cyan]epi run your_script.py[/cyan] to record with fault analysis.[/dim]")
    console.print(f"[dim]Run [cyan]epi policy validate[/cyan] to check the file.[/dim]\n")


@app.command("profiles")
def profiles():
    """List built-in healthcare and finance policy profiles."""
    from epi_core.policy import POLICY_PROFILES, list_policy_profiles

    table = Table(show_header=True, header_style="bold", box=None, padding=(0, 2))
    table.add_column("Profile", style="cyan", no_wrap=True)
    table.add_column("Description")

    for name in list_policy_profiles():
        table.add_row(name, POLICY_PROFILES[name]["description"])

    console.print()
    console.print(Panel("Built-in policy packs for high-risk healthcare and finance workflows.", title="EPI Policy Profiles"))
    console.print(table)
    console.print()


@app.command("validate")
def validate(
    policy_file: str = typer.Argument(POLICY_FILENAME, help="Path to policy file"),
):
    """Validate an epi_policy.json file and show a summary."""
    from epi_core.policy import load_policy

    path = Path(policy_file)
    if not path.exists():
        console.print(f"[red][X] File not found:[/red] {path}")
        raise typer.Exit(1)

    policy = load_policy(search_dir=path.parent if path.name == POLICY_FILENAME else Path.cwd())

    # Try direct load if load_policy returns None (different filename)
    if policy is None:
        try:
            from epi_core.policy import EPIPolicy
            data = json.loads(path.read_text(encoding="utf-8"))
            policy = EPIPolicy(**data)
        except Exception as e:
            console.print(f"[red][FAIL] Invalid policy:[/red] {e}")
            raise typer.Exit(1)

    console.print(f"\n[green][OK][/green] Valid policy: [bold]{path}[/bold]")
    console.print(f"  System:   [cyan]{policy.system_name}[/cyan] v{policy.system_version}")
    console.print(f"  Version:  {policy.policy_version}")
    console.print(f"  Rules:    {len(policy.rules)}\n")

    table = Table(show_header=True, header_style="bold", box=None, padding=(0, 2))
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("Name")
    table.add_column("Type", style="dim")
    table.add_column("Severity", no_wrap=True)

    severity_colors = {"critical": "red", "high": "yellow", "medium": "blue", "low": "dim"}
    for rule in policy.rules:
        color = severity_colors.get(rule.severity, "white")
        table.add_row(
            rule.id,
            rule.name,
            rule.type,
            f"[{color}]{rule.severity}[/{color}]",
        )

    console.print(table)
    console.print()


@app.command("show")
def show(
    policy_file: str = typer.Argument(POLICY_FILENAME, help="Path to policy file"),
):
    """Print the raw content of the policy file."""
    path = Path(policy_file)
    if not path.exists():
        console.print(f"[red][X] Not found:[/red] {path}")
        raise typer.Exit(1)

    from rich.syntax import Syntax
    console.print(Syntax(path.read_text(encoding="utf-8"), "json", theme="monokai"))
