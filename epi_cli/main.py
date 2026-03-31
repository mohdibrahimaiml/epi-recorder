"""
EPI CLI Main - Entry point for the EPI command-line interface.

Provides the main CLI application with frictionless first-run experience.
"""

import tempfile
import time

import typer
from pathlib import Path
from rich.console import Console

# Create callback that handles --version
def version_callback(value: bool):
    if value:
        from epi_core import __version__
        console.print(f"[bold]EPI[/bold] version [cyan]{__version__}[/cyan]")
        raise typer.Exit()

# Create Typer app
app = typer.Typer(
    name="epi",
    help="""EPI — Portable repro artifacts for AI agent runs.

Try it now (no API key needed):
  epi demo

No-install trial:
  Open the Colab notebook from the README

Review cases with your team:
  epi connect open

Add to your code:
  from epi_recorder import record, wrap_openai
  from openai import OpenAI
  client = wrap_openai(OpenAI())
  with record("my_agent.epi"):
      client.chat.completions.create(...)

Then open it:
  epi view my_agent.epi
  epi verify my_agent.epi
  epi share my_agent.epi

Commands:
  demo       Capture one sample run, open it in the browser, and verify it. Start here.
  init       First-time setup wizard (framework picker: OpenAI, LiteLLM, LangChain...).
  run        <script.py>   Record an already-instrumented Python script.
  view       <file.epi>    Open a case file in the browser review view.
  verify     <file.epi>    Cryptographic integrity check.
  share      <file.epi>    Upload a hosted share link for browser review.
  review     <file.epi>    Add human review notes to a case file.
  analyze    <file.epi>    Show fault analysis summary.
  policy     init          Create epi_policy.json with control rules.
  chat       <file.epi>    Chat with evidence using AI.
  debug      <file.epi>    Debug agent recordings for mistakes.
  connect    open          Review cases with your team in the local browser workspace.
  gateway    serve         Advanced: run the AI capture service.
  ls                       List local recordings.
  doctor                   Self-healing system health check.

Tips:
  - `epi demo` = `epi dev` (same command, friendlier name).
  - Windows double-click: use the packaged installer or `epi associate`.
  - Local LLMs: wrap_openai(OpenAI(base_url="http://localhost:11434/v1", api_key="ollama"))
""",
    add_completion=False,
    no_args_is_help=True,
    rich_markup_mode="rich",
    # Add version option
    callback=None  # Will set via decorator below
)

console = Console(legacy_windows=False)

_KEY_BOOTSTRAP_COMMANDS = {"run", "record", "review", "init", "doctor"}
_WINDOWS_ASSOCIATION_COMMANDS = {"run", "view", "init", "doctor"}
_WINDOWS_ASSOCIATION_PROBE_TTL_SECONDS = 6 * 60 * 60


def _analysis_has_fault(analysis: dict) -> bool:
    """Treat a real primary fault as authoritative even if fault_detected drifted."""
    if not isinstance(analysis, dict):
        return False
    return bool(analysis.get("primary_fault") or analysis.get("fault_detected"))


def _count_steps_in_artifact(epi_path: Path) -> int:
    import zipfile

    if not epi_path.exists() or not zipfile.is_zipfile(epi_path):
        return 0

    with zipfile.ZipFile(epi_path, "r") as zf:
        if "steps.jsonl" not in zf.namelist():
            return 0
        return len([line for line in zf.read("steps.jsonl").decode("utf-8").splitlines() if line.strip()])


def _step_kinds_in_artifact(epi_path: Path) -> set[str]:
    import zipfile
    import json

    if not epi_path.exists() or not zipfile.is_zipfile(epi_path):
        return set()

    with zipfile.ZipFile(epi_path, "r") as zf:
        if "steps.jsonl" not in zf.namelist():
            return set()
        kinds = set()
        for line in zf.read("steps.jsonl").decode("utf-8").splitlines():
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except Exception:
                continue
            kind = payload.get("kind")
            if isinstance(kind, str) and kind:
                kinds.add(kind)
        return kinds


def _analyze_reviewer_guidance(has_fault: bool, steps_recorded: int) -> tuple[str, str, str]:
    """Return plain-language reviewer guidance for analyze output."""
    if has_fault:
        return (
            "Needs review before trust",
            "A policy-linked issue was detected in this run.",
            "Run 'epi review <file.epi>' to confirm or dismiss this fault.",
        )
    if steps_recorded == 0:
        return (
            "No decision possible",
            "No execution steps were captured, so risk cannot be assessed.",
            "Re-run with EPI instrumentation (record()/log_step wrappers) and analyze again.",
        )
    return (
        "No fault detected",
        "No rule or heuristic anomalies were flagged in captured steps.",
        "Proceed with normal review process; keep the case file for audit traceability.",
    )


def _resolve_cli_state_dir() -> Path:
    """Resolve a writable state dir for lightweight CLI probe markers."""
    candidates = [
        Path.home() / ".epi" / "state",
        Path(tempfile.gettempdir()) / "epi" / "state",
        Path.cwd() / ".epi" / "state",
    ]
    for candidate in candidates:
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            return candidate
        except Exception:
            continue
    return Path.cwd()


def _windows_association_probe_marker() -> Path:
    return _resolve_cli_state_dir() / "windows_association_probe.marker"


def _windows_association_probe_due(now: float | None = None) -> bool:
    """Return True when the next Windows association probe should run."""
    marker = _windows_association_probe_marker()
    now = time.time() if now is None else now
    try:
        last_checked = marker.stat().st_mtime
    except FileNotFoundError:
        return True
    except Exception:
        return True
    return (now - last_checked) >= _WINDOWS_ASSOCIATION_PROBE_TTL_SECONDS


def _mark_windows_association_probe() -> None:
    marker = _windows_association_probe_marker()
    try:
        marker.write_text(str(int(time.time())), encoding="ascii")
    except Exception:
        pass


def _command_needs_default_keys(command_name: str | None) -> bool:
    """Only bootstrap keys for commands that can actually use them."""
    return command_name in _KEY_BOOTSTRAP_COMMANDS


def _auto_repair_windows_association(interactive: bool, command_name: str | None) -> None:
    """Best-effort Windows association repair for pip installs on first real use."""
    import sys as _sys

    if _sys.platform != "win32":
        return

    if command_name in {"associate", "unassociate", "help", "version"}:
        return

    if command_name not in _WINDOWS_ASSOCIATION_COMMANDS:
        return

    if command_name != "doctor" and not _windows_association_probe_due():
        return

    from epi_core.platform.associate import get_association_diagnostics, register_file_association

    diag = get_association_diagnostics()
    if diag.get("status") == "OK" and diag.get("extension_progid") == "EPIRecorder.File":
        _mark_windows_association_probe()
        if interactive and command_name in {"run", "view", "init", "doctor"}:
            console.print("[dim].epi double-click support checked on Windows.[/dim]")
        return

    register_file_association(silent=True)

    diag = get_association_diagnostics()
    _mark_windows_association_probe()
    if diag.get("status") == "OK" and diag.get("extension_progid") == "EPIRecorder.File":
        if interactive and command_name in {"run", "view", "init", "doctor"}:
            console.print("[dim].epi double-click support checked on Windows.[/dim]")
        return

    if interactive:
        console.print("[yellow][!][/yellow] Windows .epi double-click support is not fully registered yet.")
        console.print("[dim]Run [cyan]epi associate[/cyan] to repair the per-user association.[/dim]")
        console.print("[dim]For the most reliable Windows experience, use the packaged installer.[/dim]")


@app.callback()
def main_callback(
    ctx: typer.Context,
    version: bool = typer.Option(
        False,
        "--version",
        "-v",
        help="Show version and exit",
        callback=version_callback,
        is_eager=True
    )
):
    """
    Main callback - runs before any command.

    Implements frictionless first run by auto-generating a default key pair.
    For pip installs we also try to register `.epi` as a convenience, but the
    recommended Windows double-click path is the packaged installer.
    """
    import sys as _sys
    # Auto-generate default keypair if missing (frictionless first run)
    # Only print welcome message when running in an interactive terminal
    interactive = _sys.stdout.isatty()
    if _command_needs_default_keys(ctx.invoked_subcommand):
        from epi_cli.keys import generate_default_keypair_if_missing
        generate_default_keypair_if_missing(console_output=interactive)

    # Auto-register .epi file association (idempotent — skips if already done)
    _auto_repair_windows_association(interactive=interactive, command_name=ctx.invoked_subcommand)


@app.command()
def version():
    """Show EPI version information."""
    from epi_core import __version__
    console.print(f"[bold]EPI[/bold] version [cyan]{__version__}[/cyan]")
    console.print("[dim]Portable repro and trust review for AI workflows[/dim]")


@app.command(name="help")
def show_help():
    """Show extended quickstart help."""
    help_text = """[bold cyan]EPI — Portable repro artifacts for AI agent runs[/bold cyan]

[bold]Try it now (no API key needed):[/bold]
  [green]epi demo[/green]

[bold]No-install trial:[/bold]
  Open the Colab notebook from the README

[bold]Review cases with your team:[/bold]
  [green]epi connect open[/green]

[bold]Add to your code:[/bold]
  [green]from epi_recorder import record, wrap_openai[/green]
  [green]from openai import OpenAI[/green]
  [green]client = wrap_openai(OpenAI())[/green]
  [green]with record("my_agent.epi"):[/green]
  [green]    client.chat.completions.create(...)[/green]
  [green]epi view my_agent.epi[/green]
  [green]epi share my_agent.epi[/green]

[bold]pytest — one flag, evidence per test:[/bold]
  [green]pytest --epi[/green]

[bold]Commands:[/bold]
  [cyan]demo[/cyan]       Capture one sample run, open it, and verify it. [bold]Start here.[/bold]
  [cyan]init[/cyan]       First-time setup wizard.
  [cyan]run[/cyan]        <script.py>   Record an instrumented script.
  [cyan]view[/cyan]       <file.epi>    Open a case file in the browser review view.
  [cyan]verify[/cyan]     <file.epi>    Cryptographic integrity check.
  [cyan]share[/cyan]      <file.epi>    Upload a hosted share link for browser review.
  [cyan]review[/cyan]     <file.epi>    Add human review notes to a case file.
  [cyan]analyze[/cyan]    <file.epi>    Show fault analysis summary.
  [cyan]policy[/cyan]     init          Create epi_policy.json.
  [cyan]chat[/cyan]       <file.epi>    Chat with evidence using AI.
  [cyan]debug[/cyan]      <file.epi>    Debug agent recordings.
  [cyan]connect[/cyan]    open          Review cases with your team in the local browser workspace.
  [cyan]gateway[/cyan]    serve         Advanced capture service.
  [cyan]ls[/cyan]                       List local recordings.
  [cyan]doctor[/cyan]                   Self-healing health check.

[bold]Tips:[/bold]
  - [cyan]epi demo[/cyan] = [cyan]epi dev[/cyan] (same thing, friendlier name).
  - Local LLMs: [dim]wrap_openai(OpenAI(base_url="http://localhost:11434/v1", api_key="ollama"))[/dim]
  - Windows double-click: use the packaged installer or [cyan]epi associate[/cyan].
"""
    console.print(help_text)


# Import and register subcommands
# These will be added as they're implemented

# NEW: run command (zero-config) - lazy import to keep read-only CLI startup fast
@app.command(name="run", help="Record a Python workflow that already emits EPI steps.")
def run(
    script: Path = typer.Argument(None, help="Python script to record (Optional - Interactive if missing)"),
    no_verify: bool = typer.Option(False, "--no-verify", help="Skip verification"),
    no_open: bool = typer.Option(False, "--no-open", help="Don't open viewer automatically"),
    goal: str | None = typer.Option(None, "--goal", help="Goal or objective of this workflow"),
    notes: str | None = typer.Option(None, "--notes", help="Additional notes about this workflow"),
    metric: list[str] | None = typer.Option(None, "--metric", help="Key=value metrics (can be used multiple times)"),
    approved_by: str | None = typer.Option(None, "--approved-by", help="Person who approved this workflow"),
    tag: list[str] | None = typer.Option(None, "--tag", help="Tags for categorizing this workflow (can be used multiple times)"),
):
    from epi_cli.run import run as run_command

    return run_command(script, no_verify, no_open, goal, notes, metric, approved_by, tag)

# Phase 1: verify command
from epi_cli.verify import verify_command

@app.command(name="verify", help="Verify .epi file integrity and authenticity")
def verify(
    ctx: typer.Context,
    epi_file: str = typer.Argument(..., help="Path to .epi file to verify"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
    report_out: Path | None = typer.Option(
        None,
        "--report",
        help="Write a verification report to this file (e.g. verification_report.txt).",
    ),
):
    return verify_command(ctx, Path(epi_file), json_output, verbose, report_out)

# Phase 2: record command (legacy/advanced) - lazy import to avoid loading the
# recording engine for simple read-only commands like version/ls/verify.
@app.command(
    name="record",
    help="Advanced: record any command, exact output file.",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
def record(
    ctx: typer.Context,
    out: Path = typer.Option(..., "--out", help="Output .epi file path"),
    name: str | None = typer.Option(None, "--name", help="Optional run name"),
    tag: str | None = typer.Option(None, "--tag", help="Optional tag/label"),
    no_sign: bool = typer.Option(False, "--no-sign", help="Do not sign the manifest"),
    no_redact: bool = typer.Option(False, "--no-redact", help="Disable secret redaction"),
    include_all_env: bool = typer.Option(False, "--include-all-env", help="Capture all env vars (redacted)"),
    command: list[str] = typer.Argument(..., help="Command to execute after --"),
):
    from epi_cli.record import record as record_command

    return record_command(ctx, out, name, tag, no_sign, no_redact, include_all_env, command)

# Phase 3: view command
from epi_cli.view import view as view_command
@app.command(name="view", help="Open a case file in the browser review view or extract it.")
def view(
    ctx: typer.Context,
    epi_file: str = typer.Argument(..., help="Path or name of .epi file to view"),
    extract: str = typer.Option(None, "--extract", help="Destination directory to extract the viewer.html and assets instead of opening browser"),
):
    return view_command(ctx, epi_file, extract)

from epi_cli.share import share as share_command
app.command(name="share", help="Upload a hosted share link for a portable .epi case file.")(share_command)

# NEW: ls command
from epi_cli.ls import ls as ls_command
app.command(name="ls", help="List local recordings (./epi-recordings/)")(ls_command)

# NEW: chat command (v2.1.3 - AI-powered evidence querying)
from epi_cli.chat import chat as chat_command
app.command(name="chat", help="Chat with your evidence file using AI")(chat_command)

# NEW: debug command (v2.2.0 - AI-powered mistake detection)
from epi_cli.debug import app as debug_app
app.add_typer(debug_app, name="debug", help="Debug AI agent recordings for mistakes")

# NEW: install/uninstall commands (v2.6.0 - global auto-recording)
from epi_cli.install import app as install_app
app.add_typer(install_app, name="global", help="Install/uninstall EPI auto-recording globally")

# NEW: fault intelligence commands (v2.8.0)
from epi_cli.review import app as review_app
app.add_typer(
    review_app,
    name="review",
    help="Review fault analysis results for a saved case file",
    invoke_without_command=True,
    no_args_is_help=False,
)

from epi_cli.policy import app as policy_app
app.add_typer(policy_app, name="policy", help="Create, explain, and validate epi_policy.json rule files")

from epi_cli.connect import app as connect_app
app.add_typer(connect_app, name="connect", help="Launch or serve the local team review workspace and connector bridge")

from epi_cli.gateway import app as gateway_app
app.add_typer(gateway_app, name="gateway", help="Advanced: run the open-source AI capture service")

from epi_cli.dev import app as dev_app
app.add_typer(dev_app, name="dev", help="Zero-friction sample AI run -> browser repro -> verify flow")
# 'epi demo' is an alias for 'epi dev' for discoverability
app.add_typer(dev_app, name="demo", help="Try EPI in 60 seconds — capture, open, share, verify. Alias for 'epi dev'.")

from epi_cli.export_summary import app as export_summary_app
app.add_typer(export_summary_app, name="export-summary", help="Export a human-readable HTML or text summary of a .epi case file")


@app.command()
def analyze(
    epi_file: str = typer.Argument(..., help="Path or name of .epi file"),
):
    """Show fault analysis summary without opening the viewer."""
    import zipfile

    from epi_cli.view import _resolve_epi_file

    try:
        epi_path = _resolve_epi_file(epi_file)
    except FileNotFoundError:
        console.print(f"[red][X] File not found:[/red] {epi_file}")
        raise typer.Exit(1)

    if not zipfile.is_zipfile(epi_path):
        console.print(f"[red][X] Not a valid .epi file.[/red]")
        raise typer.Exit(1)

    with zipfile.ZipFile(epi_path, "r") as zf:
        if "analysis.json" not in zf.namelist():
            console.print(f"[yellow]No analysis.json in {epi_path.name}[/yellow]")
            console.print("[dim]This case file predates the Fault Intelligence layer.[/dim]")
            raise typer.Exit(0)
        import json
        analysis = json.loads(zf.read("analysis.json").decode("utf-8"))

    fault_detected = _analysis_has_fault(analysis)
    mode = analysis.get("mode", "unknown")
    coverage = analysis.get("coverage", {})
    primary_fault = analysis.get("primary_fault")
    secondary_flags = analysis.get("secondary_flags", []) or []
    display_fault = primary_fault or (secondary_flags[0] if secondary_flags else None)

    steps_recorded = coverage.get("steps_recorded")
    if steps_recorded is None:
        steps_recorded = 0

    if fault_detected:
        if display_fault is None:
            console.print(f"\n[bold red]FAULT DETECTED[/bold red] — [bold]{epi_path.name}[/bold]")
            verdict, impact, action = _analyze_reviewer_guidance(True, steps_recorded)
            console.print(f"  Verdict:    [bold red]{verdict}[/bold red]")
            console.print(f"  Impact:     {impact}")
            console.print(f"  Action:     {action}")
            console.print(f"  Mode:       {mode}")
            console.print("  Details:    The analyzer marked this run for review, but no primary fault summary was embedded.")
            console.print(f"\n  [dim]Run: [cyan]epi view {epi_path.name}[/cyan] to inspect the full case file[/dim]\n")
            raise typer.Exit(0)

        fault = display_fault
        sev = fault.get("severity", "").upper()
        sev_color = {"CRITICAL": "red", "HIGH": "yellow", "MEDIUM": "blue"}.get(sev, "white")
        console.print(f"\n[bold red]FAULT DETECTED[/bold red] — [bold]{epi_path.name}[/bold]")
        verdict, impact, action = _analyze_reviewer_guidance(True, steps_recorded)
        console.print(f"  Verdict:    [bold red]{verdict}[/bold red]")
        console.print(f"  Impact:     {impact}")
        console.print(f"  Action:     {action}")
        console.print(f"  Severity:   [{sev_color}]{sev}[/{sev_color}]")
        console.print(f"  Type:       {fault.get('fault_type')}")
        if fault.get("rule_id"):
            console.print(f"  Rule:       {fault['rule_id']} — {fault.get('rule_name', '')}")
        console.print(f"  Step:       {fault.get('step_number', fault.get('step_index', '?'))}")
        console.print(f"\n  {fault.get('plain_english', '')}")

        secondary_count = len(secondary_flags) - (1 if primary_fault is None and secondary_flags else 0)
        if secondary_count > 0:
            console.print(f"\n  [dim]{secondary_count} secondary flag(s) — run [cyan]epi view[/cyan] to inspect[/dim]")

        console.print(f"\n  [dim]Run: [cyan]epi review {epi_path.name}[/cyan] to confirm or dismiss[/dim]\n")
    else:
        if steps_recorded == 0:
            console.print(f"\n[yellow][!][/yellow] [bold]{epi_path.name}[/bold] — No data to analyze")
            verdict, impact, action = _analyze_reviewer_guidance(False, 0)
            console.print(f"  Verdict:    [bold yellow]{verdict}[/bold yellow]")
            console.print(f"  Impact:     {impact}")
            console.print(f"  Action:     {action}")
            console.print(f"  Mode:       {mode}")
            console.print("  Steps:      0 recorded")
            console.print("  Analysis:   Skipped meaningful fault review because no execution steps were captured")
            console.print("\n  [dim]Fix: instrument the workflow with record() or a supported integration, then rerun it.[/dim]\n")
        else:
            console.print(f"\n[green][OK][/green] [bold]{epi_path.name}[/bold] — No anomalies detected")
            verdict, impact, action = _analyze_reviewer_guidance(False, steps_recorded)
            console.print(f"  Verdict:    [bold green]{verdict}[/bold green]")
            console.print(f"  Impact:     {impact}")
            console.print(f"  Action:     {action}")
            console.print(f"  Mode:       {mode}")
            console.print(f"  Steps:      {steps_recorded} recorded, "
                          f"{coverage.get('coverage_percentage', '?')}% coverage\n")


# Windows file association commands
@app.command()
def associate(
    force: bool = typer.Option(False, "--force", help="Re-register even if already done"),
    system: bool = typer.Option(
        False, "--system",
        help="Write to HKLM (system-wide, all users). Triggers UAC admin prompt. "
             "Permanent — survives Windows updates and Python reinstalls."
    ),
    elevated: bool = typer.Option(False, "--elevated", hidden=True),  # internal flag
):
    """Register .epi file type with the OS so double-clicking opens the viewer.

    By default writes to HKCU (current user only). Use --system for a permanent,
    system-wide association identical to what Docker and VS Code install.
    """
    import sys
    from epi_core.platform.associate import (
        register_file_association, _needs_registration, get_association_diagnostics,
        register_windows_system, _elevate_and_register_system,
    )

    # ── System-wide (HKLM) path ────────────────────────────────────────────
    if system and sys.platform == "win32":
        import ctypes
        if elevated or ctypes.windll.shell32.IsUserAnAdmin():
            # Already elevated — write HKLM directly
            try:
                register_windows_system()
                console.print("[green][OK][/green] .epi registered system-wide (HKLM). Double-click will work for all users.")
                _print_association_diagnostics(console)
            except Exception as e:
                console.print(f"[red][FAIL][/red] {e}")
                raise typer.Exit(1)
        else:
            # Not admin — trigger UAC elevation and re-launch
            console.print("[yellow]→[/yellow] Requesting administrator privileges (UAC prompt)…")
            try:
                _elevate_and_register_system()
                console.print("[green][OK][/green] Elevated process launched. Check the new window for results.")
            except Exception as e:
                console.print(f"[red][FAIL][/red] {e}")
                raise typer.Exit(1)
        return

    # ── Per-user (HKCU) path ───────────────────────────────────────────────
    drift_repair = False
    if sys.platform == "win32" and not force:
        diag = get_association_diagnostics()
        issues = [str(i).lower() for i in diag.get("issues", [])]
        drift_repair = any("does not match the current installation" in issue for issue in issues)
        if drift_repair:
            console.print("[yellow][!][/yellow] Detected stale .epi open command; attempting per-user repair.")

    if not force and not drift_repair and not _needs_registration():
        console.print("[green][OK][/green] .epi file association already registered.")
        _print_association_diagnostics(console)
        return

    success = register_file_association(silent=False, force=(force or drift_repair))

    # Always show post-registration diagnostics so the user can see what was written
    _print_association_diagnostics(console)

    if sys.platform == "win32":
        console.print()
        console.print("[dim]Tip: for a permanent system-wide association (like Docker/VS Code):[/dim]")
        console.print("[dim]  epi associate --system[/dim]")
        console.print("[dim]  (triggers one UAC prompt, then works forever for all users)[/dim]")

    if not success:
        raise typer.Exit(1)


def _print_association_diagnostics(console):
    """Print a summary of the current file association state."""
    import sys
    from epi_core.platform.associate import get_association_diagnostics

    if sys.platform != "win32":
        return

    diag = get_association_diagnostics()
    console.print()

    ext_progid = diag.get("extension_progid")
    reg_cmd = diag.get("registered_command")
    user_choice = diag.get("user_choice")
    assoc_scope = diag.get("association_scope")

    if ext_progid == "EPIRecorder.File":
        console.print(f"  [green][OK][/green] .epi -> {ext_progid}")
    else:
        console.print(f"  [red][X][/red] .epi extension key: {ext_progid or 'MISSING'}")

    if reg_cmd:
        console.print(f"  [green][OK][/green] Open command: {reg_cmd}")
    else:
        console.print("  [red][X][/red] Open command: MISSING")

    if assoc_scope:
        console.print(f"  [green][OK][/green] Association scope: {assoc_scope}")

    if user_choice:
        if user_choice == "EPIRecorder.File":
            console.print(f"  [green][OK][/green] UserChoice: {user_choice}")
        else:
            console.print(f"  [yellow][!][/yellow] UserChoice override: [bold]{user_choice}[/bold]")
            console.print("     [dim]Windows is forcing this file type to open with another app.[/dim]")
            console.print("     [dim]Use 'Open with' -> 'Choose another app' to override.[/dim]")
    else:
        console.print("  [dim]  UserChoice: not set (Windows will use our registration)[/dim]")

    if diag.get("issues"):
        console.print()
        for issue in diag["issues"]:
            console.print(f"  [yellow]![/yellow] {issue}")


@app.command()
def unassociate():
    """Remove .epi file association from the OS."""
    from epi_core.platform.associate import unregister_file_association
    success = unregister_file_association(silent=False)
    if not success:
        raise typer.Exit(1)

# Phase 1: keys command (for manual key management)
@app.command()
def keys(
    action: str = typer.Argument(..., help="Action: generate, list, or export"),
    name: str = typer.Option("default", "--name", "-n", help="Key pair name"),
    overwrite: bool = typer.Option(False, "--overwrite", help="Overwrite existing keys")
):
    """Manage Ed25519 key pairs for signing."""
    from epi_cli.keys import KeyManager, print_keys_table
    
    key_manager = KeyManager()
    
    if action == "generate":
        try:
            private_path, public_path = key_manager.generate_keypair(name, overwrite=overwrite)
            console.print(f"\n[bold green][OK] Generated key pair:[/bold green] {name}")
            console.print(f"  [cyan]Private:[/cyan] {private_path}")
            console.print(f"  [cyan]Public:[/cyan]  {public_path}\n")
        except FileExistsError as e:
            console.print(f"[red][FAIL] Error:[/red] {e}")
            raise typer.Exit(1)
    
    elif action == "list":
        keys_list = key_manager.list_keys()
        print_keys_table(keys_list)
    
    elif action == "export":
        try:
            public_key_b64 = key_manager.export_public_key(name)
            console.print(f"\n[bold]Public key for '{name}':[/bold] [dim](base64-encoded Ed25519 raw public key, 32 bytes)[/dim]")
            console.print(f"[cyan]{public_key_b64}[/cyan]\n")
        except FileNotFoundError as e:
            console.print(f"[red][FAIL] Error:[/red] {e}")
            raise typer.Exit(1)
    
    else:
        console.print(f"[red][FAIL] Unknown action:[/red] {action}")
        console.print("[dim]Valid actions: generate, list, export[/dim]")
        raise typer.Exit(1)


@app.command()
def init(
    demo_filename: str = typer.Option("epi_demo.py", "--name", "-n", help="Name of the demo script"),
    no_open: bool = typer.Option(False, "--no-open", help="Don't open viewer automatically (for testing)"),
    framework: str = typer.Option(
        "",
        "--framework",
        "-f",
        help="Skip the interactive picker: openai | litellm | langchain | langgraph | generic",
    ),
):
    """
    [Wizard] First-time setup wizard. Creates keys, an instrumented demo script, and runs it.
    """
    console.print("\n[bold magenta]EPI Setup Wizard[/bold magenta]\n")

    # 1. Keys
    from epi_cli.keys import generate_default_keypair_if_missing
    console.print("1. [dim]Checking security keys...[/dim]", end=" ")
    if generate_default_keypair_if_missing(console_output=False):
         console.print("[green]Created![/green]")
    else:
         console.print("[green]Found! [OK][/green]")

    # 2. Demo Script — framework picker
    # Map friendly --framework names to numeric choices
    _FRAMEWORK_ALIASES = {
        "openai": "1", "anthropic": "1",
        "litellm": "2",
        "langchain": "3",
        "langgraph": "4",
        "generic": "5", "plain": "5", "other": "5",
    }
    import sys as _sys
    _interactive = _sys.stdin.isatty() if hasattr(_sys.stdin, "isatty") else False

    # Guard: Typer may pass OptionInfo instead of a plain string in direct calls
    _fw = str(framework).strip() if isinstance(framework, str) else ""

    if _fw:
        framework_choice = _FRAMEWORK_ALIASES.get(_fw.lower(), _fw)
    elif _interactive:
        console.print("\n2. [bold]What are you building with?[/bold]")
        console.print("   [green]1.[/green] OpenAI / Anthropic (direct client)")
        console.print("   [green]2.[/green] LiteLLM (100+ providers)")
        console.print("   [green]3.[/green] LangChain")
        console.print("   [green]4.[/green] LangGraph")
        console.print("   [green]5.[/green] Plain Python / other (generic demo)")

        from rich.prompt import Prompt
        framework_choice = Prompt.ask("   Pick a number", default="1")
    else:
        # Non-interactive (CI, tests, piped input) — default to generic demo
        framework_choice = "5"

    _FRAMEWORK_SCRIPTS = {
        "1": (
            "openai_demo.py",
            '''# EPI + OpenAI quick-start
# pip install epi-recorder openai

from epi_recorder import record, wrap_openai

# Uncomment and set your key, or set OPENAI_API_KEY env var
# import os; os.environ["OPENAI_API_KEY"] = "sk-..."

try:
    from openai import OpenAI
    client = wrap_openai(OpenAI())
except ImportError:
    print("openai not installed — pip install openai")
    import sys; sys.exit(1)

with record("epi-recordings/openai_demo.epi", goal="OpenAI quick-start demo") as epi:
    print("Calling OpenAI...")
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "Say hello in one sentence."}],
        )
        print("Response:", response.choices[0].message.content)
        epi.log_step("agent.decision", {"decision": "demo_complete", "confidence": 1.0})
    except Exception as e:
        epi.log_step("agent.run.error", {"error_message": str(e)})
        print(f"API error: {e}")
        print("Tip: set OPENAI_API_KEY and rerun.")

print("\\nDone! Open with: epi view epi-recordings/openai_demo.epi")
''',
        ),
        "2": (
            "litellm_demo.py",
            '''# EPI + LiteLLM quick-start (100+ providers)
# pip install epi-recorder litellm

try:
    import litellm
    from epi_recorder.integrations.litellm import enable_epi
except ImportError:
    print("litellm not installed — pip install litellm")
    import sys; sys.exit(1)

from epi_recorder import record

enable_epi()  # one line — all litellm calls are now captured

with record("epi-recordings/litellm_demo.epi", goal="LiteLLM quick-start demo") as epi:
    print("Calling via LiteLLM...")
    try:
        response = litellm.completion(
            model="gpt-4o-mini",  # swap to "claude-3-haiku-20240307" etc.
            messages=[{"role": "user", "content": "Say hello in one sentence."}],
        )
        print("Response:", response.choices[0].message.content)
        epi.log_step("agent.decision", {"decision": "demo_complete", "confidence": 1.0})
    except Exception as e:
        epi.log_step("agent.run.error", {"error_message": str(e)})
        print(f"API error: {e}")
        print("Tip: set the appropriate API key env var and rerun.")

print("\\nDone! Open with: epi view epi-recordings/litellm_demo.epi")
''',
        ),
        "3": (
            "langchain_demo.py",
            '''# EPI + LangChain quick-start
# pip install epi-recorder langchain langchain-openai

from epi_recorder import record
from epi_recorder.integrations.langchain import EPICallbackHandler

try:
    from langchain_openai import ChatOpenAI
except ImportError:
    print("langchain-openai not installed — pip install langchain langchain-openai")
    import sys; sys.exit(1)

with record("epi-recordings/langchain_demo.epi", goal="LangChain quick-start demo") as epi:
    llm = ChatOpenAI(model="gpt-4o-mini", callbacks=[EPICallbackHandler()])
    print("Calling LangChain...")
    try:
        result = llm.invoke("Say hello in one sentence.")
        print("Response:", result.content)
        epi.log_step("agent.decision", {"decision": "demo_complete", "confidence": 1.0})
    except Exception as e:
        epi.log_step("agent.run.error", {"error_message": str(e)})
        print(f"Error: {e}")
        print("Tip: set OPENAI_API_KEY and rerun.")

print("\\nDone! Open with: epi view epi-recordings/langchain_demo.epi")
''',
        ),
        "4": (
            "langgraph_demo.py",
            '''# EPI + LangGraph quick-start
# pip install epi-recorder langgraph langchain-openai

from epi_recorder import record
from epi_recorder.integrations.langgraph import EPICheckpointSaver

try:
    from langgraph.graph import StateGraph, END
    from langchain_openai import ChatOpenAI
    from langchain_core.messages import HumanMessage
    from typing import TypedDict, List
except ImportError:
    print("Install: pip install langgraph langchain langchain-openai")
    import sys; sys.exit(1)

class AgentState(TypedDict):
    messages: List

def call_model(state):
    llm = ChatOpenAI(model="gpt-4o-mini")
    response = llm.invoke(state["messages"])
    return {"messages": state["messages"] + [response]}

with record("epi-recordings/langgraph_demo.epi", goal="LangGraph quick-start demo") as epi:
    checkpointer = EPICheckpointSaver(epi)
    graph = StateGraph(AgentState)
    graph.add_node("agent", call_model)
    graph.set_entry_point("agent")
    graph.add_edge("agent", END)
    app = graph.compile(checkpointer=checkpointer)

    print("Running LangGraph agent...")
    try:
        result = app.invoke(
            {"messages": [HumanMessage(content="Say hello in one sentence.")]},
            {"configurable": {"thread_id": "demo-thread"}},
        )
        print("Response:", result["messages"][-1].content)
    except Exception as e:
        epi.log_step("agent.run.error", {"error_message": str(e)})
        print(f"Error: {e}")

print("\\nDone! Open with: epi view epi-recordings/langgraph_demo.epi")
''',
        ),
        "5": (
            "epi_demo.py",
            '''# EPI generic quick-start — no external LLM required
# pip install epi-recorder

from pathlib import Path
from epi_recorder import record

output_file = Path("epi-recordings") / "epi_demo.epi"
output_file.parent.mkdir(parents=True, exist_ok=True)

print("=" * 40)
print("   Hello from your first EPI recording!")
print("=" * 40)
print("EPI will capture these console prints as stdout evidence.")
print("Inside the record() block below, it will also capture structured workflow steps.")

with record(str(output_file), workflow_name="EPI Setup Demo", goal="Create a first artifact") as epi:
    print("\\n1. Doing some math...")
    result = 123 * 456
    # Structured steps are richer than plain console output.
    epi.log_step("CALCULATION", {"expression": "123 * 456", "result": result})
    print(f"   123 * 456 = {result}")

    print("\\n2. Creating a file...")
    hello_path = Path("epi_hello.txt")
    hello_path.write_text(f"Calculation result: {result}\\n", encoding="utf-8")
    epi.log_step("FILE_WRITE", {"path": str(hello_path), "bytes_written": hello_path.stat().st_size})
    print("   Saved epi_hello.txt")

    epi.log_step("SUMMARY", {"status": "complete"})

print(f"\\n[OK] Done! Open with: epi view {output_file}")
''',
        ),
    }

    chosen_filename, script_content = _FRAMEWORK_SCRIPTS.get(
        framework_choice.strip(), _FRAMEWORK_SCRIPTS["5"]
    )
    # Respect explicit --name override; otherwise use framework-specific name
    if demo_filename == "epi_demo.py":
        demo_filename = chosen_filename

    console.print(f"\n   [dim]Creating '{demo_filename}'...[/dim]", end=" ")
    import os
    if not os.path.exists(demo_filename):
         with open(demo_filename, "w", encoding="utf-8") as f:
             f.write(script_content)
         console.print("[green]Created![/green]")
    else:
         console.print("[yellow]Exists (Skipped) >>[/yellow]")

    # 3. Running
    console.print("\n3. [bold cyan]Running the demo now...[/bold cyan]\n")

    # Run the instrumented demo directly so the user gets a meaningful artifact.
    import subprocess
    import sys
    result = subprocess.run([sys.executable, demo_filename], check=False)

    # Derive artifact path from demo filename (stem → epi-recordings/<stem>.epi)
    demo_stem = Path(demo_filename).stem
    artifact_path = Path("epi-recordings") / f"{demo_stem}.epi"
    # If the script writes its own artifact in epi-recordings/, pick the newest one
    if not artifact_path.exists():
        candidates = sorted(
            Path("epi-recordings").glob("*.epi") if Path("epi-recordings").exists() else [],
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if candidates:
            artifact_path = candidates[0]

    step_count = _count_steps_in_artifact(artifact_path)
    step_kinds = _step_kinds_in_artifact(artifact_path)
    if result.returncode != 0 or not artifact_path.exists() or step_count == 0:
        console.print("\n[bold red][FAIL] Setup is incomplete.[/bold red]")
        if result.returncode != 0:
            console.print(f"[dim]The demo exited with code {result.returncode}.[/dim]")
        if not artifact_path.exists():
            console.print(f"[dim]The demo did not produce {artifact_path.name}.[/dim]")
        elif step_count == 0:
            console.print("[dim]The demo case file was created but contains no meaningful execution steps.[/dim]")
        console.print("[dim]Most likely cause: EPI could not create a writable recording workspace.[/dim]")
        console.print("[dim]Fix: point TMP/TEMP to a writable folder and rerun [cyan]epi init[/cyan].[/dim]")
        raise typer.Exit(1)

    console.print("\n[bold green]You are all set![/bold green]")
    console.print("[dim]Your first case file now shows both kinds of evidence:[/dim]")
    if "stdout.print" in step_kinds:
        console.print("[dim]  • Console evidence: printed output captured as [cyan]stdout.print[/cyan] steps[/dim]")
    if step_kinds - {"stdout.print"}:
        console.print("[dim]  • Structured workflow evidence: explicit EPI steps[/dim]")
    console.print("[dim]Policy review and fault analysis work best with structured EPI steps, not just console output.[/dim]")
    console.print(f"[dim]Recorded steps:[/dim] {step_count}")
    console.print(f"[dim]Run it again with:[/dim] python {demo_filename}")
    console.print(f"[dim]Open the case file with:[/dim] epi view {artifact_path}")
    if not no_open:
        try:
            from epi_cli.run import _open_viewer

            if _open_viewer(artifact_path):
                console.print("[dim]Opened your first case file in the browser.[/dim]")
            else:
                console.print("[yellow][!][/yellow] Could not open the browser automatically.")
                console.print(f"[dim]Use: epi view {artifact_path}[/dim]")
        except Exception:
            console.print("[yellow][!][/yellow] Could not open the browser automatically.")
            console.print(f"[dim]Use: epi view {artifact_path}[/dim]")


@app.command()
def doctor(
    gateway_url: str = typer.Option(
        "",
        "--gateway",
        help="Check a running gateway at this URL (e.g. http://localhost:8787).",
    ),
):
    """
    Self-healing system health check. Run this before going to production.

    Checks keys, disk, write permissions, dependencies, and gateway connectivity.
    Fixes what it can automatically. Tells you exactly what to do for the rest.
    """
    import json
    import os
    import shutil
    import platform
    import tempfile
    import socket

    console.print()
    console.print("[bold]EPI Doctor — System Health Check[/bold]")
    console.print("[dim]Running all checks...[/dim]")
    console.print()

    issues = 0
    fixed = 0

    def _ok(label: str, detail: str = ""):
        msg = f"  [green][OK][/green]  {label}"
        if detail:
            msg += f"  [dim]{detail}[/dim]"
        console.print(msg)

    def _warn(label: str, fix: str = ""):
        nonlocal issues
        issues += 1
        console.print(f"  [yellow][!][/yellow]  {label}")
        if fix:
            console.print(f"        [dim]Fix: {fix}[/dim]")

    def _fail(label: str, fix: str = ""):
        nonlocal issues
        issues += 1
        console.print(f"  [red][X][/red]  {label}")
        if fix:
            console.print(f"        [dim]Fix: {fix}[/dim]")

    def _fixed(label: str):
        nonlocal fixed
        fixed += 1
        console.print(f"  [cyan][+][/cyan]  {label} [dim](auto-fixed)[/dim]")

    # ── 1. Signing keys ───────────────────────────────────────────────────
    console.print("[bold]Signing & Cryptography[/bold]")
    try:
        from epi_cli.keys import generate_default_keypair_if_missing, KeyManager
        was_missing = generate_default_keypair_if_missing(console_output=False)
        km = KeyManager()
        if was_missing:
            _fixed("Ed25519 signing key generated")
        elif km.has_key("default"):
            _ok("Ed25519 signing key", "default key present")
        else:
            _fail("No signing key found", "Run: epi keys generate")
    except Exception as e:
        _fail(f"Key system error: {e}", "Run: epi keys generate")

    # ── 2. Disk space ─────────────────────────────────────────────────────
    console.print()
    console.print("[bold]Storage & Disk[/bold]")
    try:
        usage = shutil.disk_usage(Path.cwd())
        free_gb = usage.free / (1024 ** 3)
        if free_gb < 0.5:
            _fail(
                f"Low disk space: {free_gb:.1f} GB free",
                "Free up disk space. EPI needs at least 500 MB for recordings.",
            )
        elif free_gb < 2.0:
            _warn(
                f"Disk space low: {free_gb:.1f} GB free",
                "Consider freeing disk space before long recording sessions.",
            )
        else:
            _ok("Disk space", f"{free_gb:.1f} GB free")
    except Exception as e:
        _warn(f"Could not check disk space: {e}")

    # ── 3. Write permissions ──────────────────────────────────────────────
    try:
        test_dir = Path(tempfile.mkdtemp(prefix="epi_doctor_"))
        test_file = test_dir / "write_test.tmp"
        test_file.write_bytes(b"epi_ok")
        test_file.unlink()
        test_dir.rmdir()
        _ok("Write permissions", f"can write to {Path.cwd()}")
    except Exception as e:
        _fail(
            f"Cannot write to current directory: {e}",
            "Run EPI from a directory you have write access to.",
        )

    # ── 4. Recordings directory ───────────────────────────────────────────
    recordings_dir = Path(os.getenv("EPI_RECORDINGS_DIR", "epi-recordings"))
    try:
        recordings_dir.mkdir(parents=True, exist_ok=True)
        probe = recordings_dir / ".epi_doctor_probe"
        probe.write_bytes(b"ok")
        probe.unlink()
        _ok("Recordings directory", str(recordings_dir.resolve()))
    except Exception as e:
        _fail(
            f"Cannot write to recordings directory ({recordings_dir}): {e}",
            f"Fix permissions or set EPI_RECORDINGS_DIR to a writable path.",
        )

    # ── 5. Gateway storage (evidence_vault) ───────────────────────────────
    vault_dir = Path(os.getenv("EPI_GATEWAY_STORAGE_DIR", "./evidence_vault"))
    if vault_dir.exists():
        try:
            probe = vault_dir / ".epi_doctor_probe"
            probe.write_bytes(b"ok")
            probe.unlink()
            db_path = vault_dir / "cases.sqlite3"
            db_size = f"{db_path.stat().st_size // 1024} KB" if db_path.exists() else "not yet created"
            _ok("Gateway storage", f"{vault_dir.resolve()} — cases.sqlite3: {db_size}")
        except Exception as e:
            _fail(f"Gateway storage not writable: {e}", f"Fix permissions on {vault_dir}")
    else:
        _ok("Gateway storage", f"{vault_dir} — not yet created (normal if gateway never started)")

    # ── 6. Required packages ──────────────────────────────────────────────
    console.print()
    console.print("[bold]Dependencies[/bold]")
    required = {
        "epi_core": "core EPI library",
        "cryptography": "Ed25519 signing",
        "cbor2": "canonical hashing",
        "pydantic": "data models",
        "typer": "CLI",
        "rich": "terminal output",
    }
    optional = {
        "uvicorn": "gateway server (needed for epi gateway serve)",
        "fastapi": "gateway server (needed for epi gateway serve)",
        "openai": "OpenAI SDK wrapper",
        "anthropic": "Anthropic SDK wrapper",
        "litellm": "LiteLLM integration",
        "langchain": "LangChain integration",
    }
    import importlib
    for pkg, desc in required.items():
        try:
            importlib.import_module(pkg)
            _ok(pkg, desc)
        except ImportError:
            _fail(f"{pkg} missing ({desc})", f"pip install {pkg}")

    console.print()
    console.print("[bold]Optional packages[/bold]")
    for pkg, desc in optional.items():
        try:
            importlib.import_module(pkg)
            _ok(pkg, desc)
        except ImportError:
            console.print(f"  [dim][-]  {pkg} not installed ({desc})[/dim]")

    # ── 7. epi command on PATH ────────────────────────────────────────────
    console.print()
    console.print("[bold]CLI[/bold]")
    if shutil.which("epi"):
        _ok("'epi' command on PATH")
    else:
        _warn(
            "'epi' command not found on PATH",
            "Use 'python -m epi_cli' as fallback, or re-install: pip install --force-reinstall epi-recorder",
        )
        if platform.system() == "Windows":
            try:
                import importlib.util
                if importlib.util.find_spec("epi_postinstall") is not None:
                    import epi_postinstall
                    scripts_dir = epi_postinstall.get_scripts_dir()
                    if scripts_dir and scripts_dir.exists():
                        if epi_postinstall.add_to_user_path_windows(scripts_dir):
                            _fixed("PATH updated — restart terminal to apply")
            except Exception:
                pass

    # ── 8. Gateway connectivity ───────────────────────────────────────────
    if gateway_url:
        console.print()
        console.print("[bold]Gateway[/bold]")
        try:
            import urllib.request
            req = urllib.request.urlopen(f"{gateway_url.rstrip('/')}/health", timeout=5)
            data = json.loads(req.read())
            status = data.get("status", "unknown")
            cases = data.get("case_count", "?")
            ready = data.get("ready", False)
            if status == "healthy" and ready:
                _ok(f"Gateway reachable at {gateway_url}", f"{cases} cases, worker ready")
            elif not ready:
                _warn(f"Gateway at {gateway_url} is starting up (worker not ready yet)")
            else:
                _warn(f"Gateway at {gateway_url} returned status: {status}")
        except Exception as e:
            _fail(
                f"Cannot reach gateway at {gateway_url}: {e}",
                "Run: epi gateway serve — or check the gateway URL.",
            )

    # ── Summary ───────────────────────────────────────────────────────────
    console.print()
    console.rule()
    if issues == 0:
        console.print()
        console.print("  [bold green]System healthy. EPI is ready for production.[/bold green]")
    else:
        unfixed = issues - fixed
        if fixed:
            console.print()
            console.print(f"  [cyan]Auto-fixed {fixed} issue(s).[/cyan]")
        if unfixed:
            console.print(f"  [yellow]{unfixed} issue(s) need manual attention (see above).[/yellow]")
    console.print()
    console.print(f"  [dim]Tip: run with --gateway http://localhost:8787 to also check your gateway.[/dim]")
    console.print()


# Entry point for CLI
def cli_main():
    """CLI entry point (called by `epi` command)."""
    # Fix Windows console encoding (cp1252 → utf-8) BEFORE any output.
    # Three layers needed:
    #   1. SetConsoleCP(65001)  — switches Win32 code page for the console API
    #   2. sys.stdout/stderr    — covers plain print() and Rich non-legacy path
    #   3. console._file patch  — Rich Console captures sys.stdout at import
    #      time, so we must update its internal reference after patching stdout
    import sys as _sys
    import io as _io
    if _sys.platform == "win32":
        try:
            import ctypes as _ct
            _ct.windll.kernel32.SetConsoleOutputCP(65001)
            _ct.windll.kernel32.SetConsoleCP(65001)
        except Exception:
            pass
        try:
            _sys.stdout = _io.TextIOWrapper(
                _sys.stdout.buffer, encoding="utf-8", errors="replace"
            )
            _sys.stderr = _io.TextIOWrapper(
                _sys.stderr.buffer, encoding="utf-8", errors="replace"
            )
        except Exception:
            pass  # Already wrapped or no buffer — safe to ignore
        try:
            # Patch the module-level Rich Console so it writes to the new
            # UTF-8 stdout rather than the cp1252 one it captured at import.
            console._file = _sys.stdout  # type: ignore[union-attr]
        except Exception:
            pass

    app()


if __name__ == "__main__":
    cli_main()



 
