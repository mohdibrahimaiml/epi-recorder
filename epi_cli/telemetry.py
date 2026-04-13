"""CLI commands for opt-in EPI telemetry and pilot signup."""

from __future__ import annotations

import sys

import typer
from rich.console import Console
from rich.prompt import Confirm, Prompt

from epi_core import telemetry as telemetry_core

app = typer.Typer(help="Manage privacy-first opt-in telemetry and pilot signup.")
console = Console()


def _is_interactive() -> bool:
    return bool(getattr(sys.stdin, "isatty", lambda: False)())


@app.command("status")
def status() -> None:
    """Show local telemetry status."""

    info = telemetry_core.status()
    console.print("[bold]EPI telemetry[/bold]")
    console.print(f"  Enabled: {'yes' if info['enabled'] else 'no'}")
    console.print(f"  Enabled by env: {'yes' if info['enabled_by_env'] else 'no'}")
    console.print(f"  Install ID present: {'yes' if info['has_install_id'] else 'no'}")
    console.print(f"  Config: {info['config_path']}")
    console.print(f"  Endpoint: {info['telemetry_url']}")
    console.print(f"  Queued events: {info['queued_events']}")
    console.print(f"  Queue: {info['queue_path']}")
    console.print(f"  Pilot signup saved: {'yes' if info['pilot_signup_saved'] else 'no'}")
    console.print()
    console.print("[dim]Telemetry is opt-in. EPI never sends prompts, outputs, file paths, repo names, usernames, hostnames, API keys, or artifact content.[/dim]")


@app.command("enable")
def enable(
    join_pilot: bool = typer.Option(False, "--join-pilot", help="Also submit the EPI Pilot signup form."),
    no_pilot_prompt: bool = typer.Option(False, "--no-pilot-prompt", help="Do not ask about pilot signup interactively."),
    email: str = typer.Option("", "--email", help="Pilot signup email."),
    org: str = typer.Option("", "--org", help="Pilot signup organization."),
    role: str = typer.Option("", "--role", help="Pilot signup role."),
    use_case: str = typer.Option(
        "other",
        "--use-case",
        help="Pilot use case: debugging | governance | compliance | agt integration | ci/cd | other.",
    ),
    link_telemetry: bool = typer.Option(
        False,
        "--link-telemetry",
        help="Allow EPI to link this pilot profile with your anonymous telemetry install ID.",
    ),
    consent_to_contact: bool = typer.Option(
        False,
        "--consent-to-contact",
        help="Explicitly allow EPI to contact you about the pilot.",
    ),
) -> None:
    """Enable opt-in telemetry and optionally join the EPI Pilot."""

    config = telemetry_core.enable()
    console.print("[green][OK][/green] Telemetry enabled")
    console.print(f"[dim]Install ID: {config.get('install_id')}[/dim]")
    console.print("[dim]EPI sends exact non-content metrics only and never sends prompts, outputs, paths, repos, hostnames, usernames, keys, or artifact content.[/dim]")

    should_join = join_pilot
    if not should_join and _is_interactive() and not no_pilot_prompt:
        console.print()
        console.print("[bold]Join the EPI Pilot?[/bold]")
        console.print("Get early access to artifact dashboard, compliance report exports, priority support, and the .epi integration roadmap.")
        should_join = Confirm.ask("Join the pilot", default=False)

    if not should_join:
        console.print("[dim]Pilot signup skipped. You can run this later with: epi telemetry enable --join-pilot[/dim]")
        return

    if not email and _is_interactive():
        email = Prompt.ask("Email")
    if not org and _is_interactive():
        org = Prompt.ask("Org", default="")
    if not role and _is_interactive():
        role = Prompt.ask("Role", default="")
    if (not use_case or use_case == "other") and _is_interactive():
        use_case = Prompt.ask(
            "Use case",
            choices=["debugging", "governance", "compliance", "agt integration", "ci/cd", "other"],
            default=use_case or "other",
        )
    if not link_telemetry and _is_interactive():
        link_telemetry = Confirm.ask(
            "Allow EPI to link this pilot profile to anonymous usage telemetry",
            default=False,
        )
    if not consent_to_contact and _is_interactive():
        consent_to_contact = Confirm.ask(
            "Allow EPI to contact you about the pilot",
            default=False,
        )

    try:
        signup = telemetry_core.build_pilot_signup(
            email=email,
            org=org,
            role=role,
            use_case=use_case,
            consent_to_contact=consent_to_contact,
            link_telemetry=link_telemetry,
        )
    except telemetry_core.TelemetryError as exc:
        console.print(f"[red][FAIL][/red] Pilot signup not saved: {exc}")
        raise typer.Exit(1) from exc

    delivered = telemetry_core.submit_pilot_signup(signup)
    if delivered:
        console.print("[green][OK][/green] Pilot signup submitted")
    else:
        console.print("[yellow][!][/yellow] Pilot signup saved locally; backend submission will need a later retry.")
    console.print(f"[dim]Local signup: {telemetry_core.pilot_signup_path()}[/dim]")


@app.command("disable")
def disable() -> None:
    """Disable telemetry locally."""

    telemetry_core.disable()
    console.print("[green][OK][/green] Telemetry disabled")
    console.print("[dim]No telemetry events will be sent unless EPI_TELEMETRY_OPT_IN=true is set.[/dim]")


@app.command("test")
def test() -> None:
    """Send a harmless test event if telemetry is enabled."""

    flush = telemetry_core.flush_queued_events()
    sent = telemetry_core.track_event(
        "telemetry.test",
        {"command": "telemetry test", "success": True, "source": "cli"},
    )
    if sent:
        console.print("[green][OK][/green] Test telemetry event sent")
    else:
        console.print("[yellow][!][/yellow] Test event was not sent. Telemetry may be disabled or the endpoint may be unreachable.")
    if flush["sent"] or flush["remaining"] or flush["dropped"]:
        console.print(
            f"[dim]Queued event retry: sent={flush['sent']} remaining={flush['remaining']} dropped={flush['dropped']}[/dim]"
        )
