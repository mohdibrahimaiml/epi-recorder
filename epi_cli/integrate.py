"""Generate safe EPI integration scaffolds for common stacks."""

from __future__ import annotations

import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.prompt import Confirm

from epi_cli.onboarding import (
    GITHUB_WORKFLOW_PATH,
    detect_pytest_project,
    integration_example,
    write_github_action_workflow,
    write_integration_example,
)

app = typer.Typer(
    name="integrate",
    help="Generate EPI integration examples and CI workflows.",
    invoke_without_command=True,
    no_args_is_help=False,
)
console = Console()
TARGETS = {"pytest", "langchain", "litellm", "opentelemetry", "agt"}


def _is_interactive() -> bool:
    return bool(getattr(sys.stdin, "isatty", lambda: False)())


def _print_plan(target: str, *, write_examples: bool, apply: bool, force: bool) -> None:
    filename, _ = integration_example(target)
    console.print(f"[bold]EPI integrate: {target}[/bold]")
    console.print(f"  Example: [cyan].epi/examples/{filename}[/cyan]")
    if target == "pytest":
        console.print(f"  CI workflow: [cyan]{GITHUB_WORKFLOW_PATH}[/cyan]")
        console.print(f"  Pytest detected: {'yes' if detect_pytest_project() else 'no'}")
    console.print(f"  Write examples: {'yes' if write_examples or apply else 'no'}")
    console.print(f"  Apply workflow/config: {'yes' if apply else 'no'}")
    console.print(f"  Overwrite existing generated files: {'yes' if force else 'no'}")
    console.print()
    console.print("[dim]V1 does not rewrite arbitrary user agent source files. It writes examples and safe workflow/config files only after confirmation or --apply.[/dim]")


@app.callback(invoke_without_command=True)
def integrate(
    ctx: typer.Context,
    target: str = typer.Argument(..., help="Target: pytest | langchain | litellm | opentelemetry | agt"),
    write_examples: bool = typer.Option(False, "--write-examples", help="Write .epi/examples scaffolding."),
    apply: bool = typer.Option(False, "--apply", help="Apply safe workflow/config changes."),
    force: bool = typer.Option(False, "--force", help="Overwrite generated files when they already exist."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show the integration plan without writing files."),
) -> None:
    integrate_command(
        target=target,
        write_examples=write_examples,
        apply=apply,
        force=force,
        dry_run=dry_run,
    )


def integrate_command(
    target: str = typer.Argument(..., help="Target: pytest | langchain | litellm | opentelemetry | agt"),
    write_examples: bool = typer.Option(False, "--write-examples", help="Write .epi/examples scaffolding."),
    apply: bool = typer.Option(False, "--apply", help="Apply safe workflow/config changes."),
    force: bool = typer.Option(False, "--force", help="Overwrite generated files when they already exist."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show the integration plan without writing files."),
) -> None:
    """Generate safe integration scaffolding for one target."""

    normalized = target.strip().lower()
    if normalized not in TARGETS:
        console.print(f"[red][FAIL][/red] Unsupported target: {target}")
        console.print(f"[dim]Supported targets: {', '.join(sorted(TARGETS))}[/dim]")
        raise typer.Exit(1)

    _print_plan(normalized, write_examples=write_examples, apply=apply, force=force)
    if dry_run or (not write_examples and not apply and not _is_interactive()):
        console.print("[yellow][DRY-RUN][/yellow] No files written.")
        console.print("[dim]Use --write-examples to write examples or --apply to write safe workflow/config files.[/dim]")
        return

    if not write_examples and not apply and _is_interactive():
        write_examples = Confirm.ask("Write EPI example files", default=True)
        if normalized == "pytest":
            apply = Confirm.ask("Write GitHub Actions EPI workflow", default=True)

    wrote_any = False
    if write_examples or apply:
        result = write_integration_example(normalized, root=Path.cwd(), force=force)
        wrote_any = wrote_any or result.created
        if result.created:
            console.print(f"[green][OK][/green] Wrote {result.path}")
        elif result.skipped:
            console.print(f"[yellow][SKIP][/yellow] {result.path} already exists")

    if apply and normalized == "pytest":
        workflow = write_github_action_workflow(root=Path.cwd(), force=force)
        wrote_any = wrote_any or workflow.created
        if workflow.created:
            console.print(f"[green][OK][/green] Wrote {workflow.path}")
        elif workflow.skipped:
            console.print(f"[yellow][SKIP][/yellow] {workflow.path} already exists")

    if not wrote_any:
        console.print("[dim]No files changed.[/dim]")
    console.print("[dim]Next: review generated files, run your agent/tests, then `epi verify <artifact-or-dir>`.[/dim]")
    try:
        from epi_core.telemetry import track_event

        track_event(
            "epi.integrate.completed",
            {
                "command": "integrate",
                "target": normalized,
                "success": True,
                "workflow_created": bool(apply and normalized == "pytest"),
            },
        )
    except Exception:
        pass
    try:
        from epi_cli.telemetry_hint import maybe_print_telemetry_hint

        maybe_print_telemetry_hint(console, "integrate")
    except Exception:
        pass
