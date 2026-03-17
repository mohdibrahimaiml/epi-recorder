"""
EPI CLI Main - Entry point for the EPI command-line interface.

Provides the main CLI application with frictionless first-run experience.
"""

import typer
from rich.console import Console

from epi_cli.keys import generate_default_keypair_if_missing

# Create callback that handles --version
def version_callback(value: bool):
    if value:
        from epi_core import __version__
        console.print(f"[bold]EPI[/bold] version [cyan]{__version__}[/cyan]")
        raise typer.Exit()

# Create Typer app
app = typer.Typer(
    name="epi",
    help="""EPI - The PDF for AI Evidence.

Cryptographic proof of what Autonomous AI Systems actually did.

Commands:
  run        <script.py>       Record a Python workflow that already emits EPI steps.
  record     --out <file.epi> -- <cmd...>
                               Advanced: record any command, exact output file.
  verify     <file.epi>        Verify a recording's integrity.
  view       <file.epi|name>   Open recording in browser or extract.
  ls                           List local recordings (./epi-recordings/).
  keys                         Manage keys (list/generate/export) - advanced.
  chat       <file.epi>        Chat with evidence file using AI.
  debug      <file.epi>        Debug AI agent recordings for mistakes.
  global                       Install/uninstall global auto-recording.
  associate                    Register .epi file type with the OS. (Repair/fallback)
  init                         First-time setup wizard.
  doctor                       Self-healing system health check.
  help                         Show this quickstart.

Quickstart (first 30s):
  1) Install: pip install epi-recorder
  2) Add EPI to your script:
     -> from epi_recorder import record
     -> with record("my_script.epi"): ...
  3) Run your script normally: python my_script.py
  4) Open the artifact: epi view my_script.epi

Tips:
  - Windows double-click support is best via the packaged installer.
  - `epi associate` is the manual repair/fallback path for pip installs.
  - `epi run my_script.py` is best for scripts that already emit EPI steps.
  - Want explicit name? Use the advanced command: epi record --out experiment.epi -- python my_script.py
  - For guaranteed evidence capture, use @record or `with record(...)`.
""",
    add_completion=False,
    no_args_is_help=True,
    rich_markup_mode="rich",
    # Add version option
    callback=None  # Will set via decorator below
)

console = Console()


def _analysis_has_fault(analysis: dict) -> bool:
    """Treat a real primary fault as authoritative even if fault_detected drifted."""
    if not isinstance(analysis, dict):
        return False
    return bool(analysis.get("primary_fault") or analysis.get("fault_detected"))


def _auto_repair_windows_association(interactive: bool, command_name: str | None) -> None:
    """Best-effort Windows association repair for pip installs on first real use."""
    import sys as _sys

    if _sys.platform != "win32":
        return

    if command_name in {"associate", "unassociate", "help", "version"}:
        return

    from epi_core.platform.associate import get_association_diagnostics, register_file_association

    register_file_association(silent=True)

    diag = get_association_diagnostics()
    if diag.get("status") == "OK" and diag.get("extension_progid") == "EPIRecorder.File":
        if interactive and command_name in {"run", "view", "ls", "init", "doctor"}:
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
    generate_default_keypair_if_missing(console_output=interactive)

    # Auto-register .epi file association (idempotent — skips if already done)
    _auto_repair_windows_association(interactive=interactive, command_name=ctx.invoked_subcommand)


@app.command()
def version():
    """Show EPI version information."""
    from epi_core import __version__
    console.print(f"[bold]EPI[/bold] version [cyan]{__version__}[/cyan]")
    console.print("[dim]The PDF for AI workflows[/dim]")


@app.command(name="help")
def show_help():
    """Show extended quickstart help."""
    help_text = """[bold cyan]EPI Recorder - Quickstart Guide[/bold cyan]

[bold]Usage:[/bold] epi <command> [options]

[bold]Commands:[/bold]
  [cyan]run[/cyan]        <script.py>       Record a Python workflow that already emits EPI steps.
  [cyan]record[/cyan]     --out <file.epi> -- <cmd...>
                             Advanced: record any command, exact output file.
  [cyan]verify[/cyan]     <file.epi>        Verify a recording's integrity.
  [cyan]view[/cyan]       <file.epi|name>   Open recording in browser or extract.
  [cyan]ls[/cyan]                           List local recordings (./epi-recordings/).
  [cyan]keys[/cyan]                         Manage keys (list/generate/export) - advanced.
  [cyan]chat[/cyan]       <file.epi>        Chat with evidence file using AI.
  [cyan]debug[/cyan]      <file.epi>        Debug AI agent recordings for mistakes.
  [cyan]global[/cyan]                       Install/uninstall global auto-recording.
  [cyan]associate[/cyan]                    Register .epi file type with the OS. (Repair/fallback)
  [cyan]init[/cyan]                         First-time setup wizard.
  [cyan]doctor[/cyan]                       Self-healing system health check.
  [cyan]help[/cyan]                         Show this quickstart.

[bold]Quickstart (first 30s):[/bold]
  1) Install: pip install epi-recorder
  2) Instrument your script: [green]from epi_recorder import record[/green]
  3) Run it normally: [green]python my_script.py[/green]
  4) Open the artifact: [green]epi view my_script.epi[/green]

[bold]Tips:[/bold]
  - Windows double-click support is best via the packaged installer.
  - [cyan]epi associate[/cyan] is the manual repair/fallback path for pip installs.
  - [cyan]epi run my_script.py[/cyan] is best for scripts that already emit EPI steps.
  - Want explicit name? Use the advanced command: epi record --out experiment.epi -- python my_script.py
  - For guaranteed evidence capture, use @record or with record(...).
"""
    console.print(help_text)


# Import and register subcommands
# These will be added as they're implemented

# NEW: run command (zero-config) - direct import
from epi_cli.run import run as run_command
app.command(name="run", help="Record a Python workflow that already emits EPI steps.")(run_command)

# Phase 1: verify command
from epi_cli.verify import verify_command
from pathlib import Path

@app.command(name="verify", help="Verify .epi file integrity and authenticity")
def verify(
    ctx: typer.Context,
    epi_file: str = typer.Argument(..., help="Path to .epi file to verify"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output")
):
    return verify_command(ctx, Path(epi_file), json_output, verbose)

# Phase 2: record command (legacy/advanced)
from epi_cli.record import app as record_app
app.add_typer(record_app, name="record", help="Advanced: record any command, exact output file.")

# Phase 3: view command
from epi_cli.view import view as view_command
@app.command(name="view", help="Open recording in browser or extract.")
def view(
    ctx: typer.Context,
    epi_file: str = typer.Argument(..., help="Path or name of .epi file to view"),
    extract: str = typer.Option(None, "--extract", help="Destination directory to extract the viewer.html and assets instead of opening browser"),
):
    return view_command(ctx, epi_file, extract)

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
app.add_typer(review_app, name="review", help="Review fault analysis results for a .epi artifact")

from epi_cli.policy import app as policy_app
app.add_typer(policy_app, name="policy", help="Create and validate epi_policy.json rule files")


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
            console.print("[dim]This artifact predates the Fault Intelligence layer.[/dim]")
            raise typer.Exit(0)
        import json
        analysis = json.loads(zf.read("analysis.json").decode("utf-8"))

    fault_detected = _analysis_has_fault(analysis)
    mode = analysis.get("mode", "unknown")
    coverage = analysis.get("coverage", {})

    steps_recorded = coverage.get("steps_recorded")
    if steps_recorded is None:
        steps_recorded = 0

    if fault_detected:
        fault = analysis["primary_fault"]
        sev = fault.get("severity", "").upper()
        sev_color = {"CRITICAL": "red", "HIGH": "yellow", "MEDIUM": "blue"}.get(sev, "white")
        console.print(f"\n[bold red]FAULT DETECTED[/bold red] — [bold]{epi_path.name}[/bold]")
        console.print(f"  Severity:   [{sev_color}]{sev}[/{sev_color}]")
        console.print(f"  Type:       {fault.get('fault_type')}")
        if fault.get("rule_id"):
            console.print(f"  Rule:       {fault['rule_id']} — {fault.get('rule_name', '')}")
        console.print(f"  Step:       {fault.get('step_number')}")
        console.print(f"\n  {fault.get('plain_english', '')}")

        secondary = analysis.get("secondary_flags", [])
        if secondary:
            console.print(f"\n  [dim]{len(secondary)} secondary flag(s) — run [cyan]epi view[/cyan] to inspect[/dim]")

        console.print(f"\n  [dim]Run: [cyan]epi review {epi_path.name}[/cyan] to confirm or dismiss[/dim]\n")
    else:
        if steps_recorded == 0:
            console.print(f"\n[yellow][!][/yellow] [bold]{epi_path.name}[/bold] — No data to analyze")
            console.print(f"  Mode:       {mode}")
            console.print("  Steps:      0 recorded")
            console.print("  Analysis:   Skipped meaningful fault review because no execution steps were captured")
            console.print("\n  [dim]Fix: instrument the workflow with record() or a supported integration, then rerun it.[/dim]\n")
        else:
            console.print(f"\n[green][OK][/green] [bold]{epi_path.name}[/bold] — No anomalies detected")
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
    if not force and not _needs_registration():
        console.print("[green][OK][/green] .epi file association already registered.")
        _print_association_diagnostics(console)
        return

    success = register_file_association(silent=False, force=force)

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
        console.print(f"  [green]✓[/green] .epi → {ext_progid}")
    else:
        console.print(f"  [red]✗[/red] .epi extension key: {ext_progid or 'MISSING'}")

    if reg_cmd:
        console.print(f"  [green]✓[/green] Open command: {reg_cmd}")
    else:
        console.print("  [red]✗[/red] Open command: MISSING")

    if assoc_scope:
        console.print(f"  [green]âœ“[/green] Association scope: {assoc_scope}")

    if user_choice:
        if user_choice == "EPIRecorder.File":
            console.print(f"  [green]✓[/green] UserChoice: {user_choice}")
        else:
            console.print(f"  [yellow]⚠[/yellow]  UserChoice override: [bold]{user_choice}[/bold]")
            console.print("     [dim]Windows is forcing this file type to open with another app.[/dim]")
            console.print("     [dim]Use 'Open with' → 'Choose another app' to override.[/dim]")
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
    no_open: bool = typer.Option(False, "--no-open", help="Don't open viewer automatically (for testing)")
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

    # 2. Demo Script
    console.print(f"2. [dim]Creating demo script '{demo_filename}'...[/dim]", end=" ")
    script_content = '''# Welcome to EPI!

from pathlib import Path

from epi_recorder import record


output_file = Path("epi_demo.epi")

print("=" * 40)
print("   Hello from your first EPI recording!")
print("=" * 40)

with record(str(output_file), workflow_name="EPI Setup Demo", goal="Create a meaningful first EPI artifact") as epi:
    print("\\n1. Doing some math...")
    result = 123 * 456
    epi.log_step("CALCULATION", {"expression": "123 * 456", "result": result})
    print(f"   123 * 456 = {result}")

    print("\\n2. Creating a file...")
    hello_path = Path("epi_hello.txt")
    hello_path.write_text(f"Calculation result: {result}\\n", encoding="utf-8")
    epi.log_step("FILE_WRITE", {"path": str(hello_path), "bytes_written": hello_path.stat().st_size})
    print("   Saved 'epi_hello.txt'")

    print("\\n3. Summarizing the work...")
    epi.log_step("SUMMARY", {"status": "complete", "artifacts": [str(hello_path)]})

print(f"\\n[OK] Done! Created {output_file}")
'''
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
    subprocess.run([sys.executable, demo_filename], check=False)

    console.print("\n[bold green]You are all set![/bold green]")
    console.print(f"[dim]Run it again with:[/dim] python {demo_filename}")
    console.print("[dim]Open the artifact with:[/dim] epi view epi_demo.epi")


@app.command()
def doctor():
    """
    [Doctor] Self-healing doctor. Fixes common issues silently.
    """
    console.print("\n[bold blue]EPI Doctor - System Health Check[/bold blue]\n")
    
    issues = 0
    fixed = 0
    
    # Check 1: Keys
    console.print("1. Security Keys: ", end="")
    from epi_cli.keys import generate_default_keypair_if_missing
    if generate_default_keypair_if_missing(console_output=False):
        console.print("[green][OK] FIXED (Generated)[/green]")
        fixed += 1
    else:
        console.print("[green][OK][/green]")
        
    # Check 2: Command on PATH
    console.print("2. 'epi' command: ", end="")
    import shutil
    if shutil.which("epi"):
        console.print("[green][OK][/green]")
    else:
        console.print("[red][X] NOT IN PATH[/red]")
        issues += 1
        
        # Try to auto-fix on Windows
        import platform
        if platform.system() == "Windows":
            console.print("   [cyan]→ Attempting automatic PATH fix...[/cyan]")
            try:
                import importlib.util
                from pathlib import Path

                if importlib.util.find_spec("epi_postinstall") is not None:
                    import epi_postinstall

                    scripts_dir = epi_postinstall.get_scripts_dir()
                    if scripts_dir and scripts_dir.exists():
                        console.print(f"   [dim]Scripts directory: {scripts_dir}[/dim]")

                        if epi_postinstall.add_to_user_path_windows(scripts_dir):
                            console.print("   [green][OK] PATH updated successfully![/green]")
                            console.print("   [yellow][!] Please restart your terminal for changes to take effect[/yellow]")
                            fixed += 1
                        else:
                            console.print("   [yellow][!] Could not update PATH automatically[/yellow]")
                            console.print("   [dim]Manual fix: Use 'python -m epi_cli' instead[/dim]")
                    else:
                        console.print("   [red][X] Could not locate Scripts directory[/red]")
                else:
                    console.print("   [yellow][!] Auto-fix not available in this environment[/yellow]")
                    console.print("   [dim]Workaround: Use 'python -m epi_cli' instead[/dim]")
            except Exception as e:
                console.print(f"   [red][X] Auto-fix failed: {e}[/red]")
                console.print("   [dim]Workaround: Use 'python -m epi_cli' instead[/dim]")
        else:
            console.print("   [dim]Workaround: Use 'python -m epi_cli' instead[/dim]")

    # Check 3: Browser
    console.print("3. Browser Check: ", end="")
    try:
        import webbrowser
        webbrowser.get()
        console.print("[green][OK][/green]")
    except Exception:
        console.print("[yellow][!] WARNING (Headless?)[/yellow]")
        
    # Check 4: File Association (Deep check)
    console.print("4. File Association: ", end="")
    from epi_core.platform.associate import get_association_diagnostics
    diag = get_association_diagnostics()
    
    if diag["status"] == "OK":
        if not diag.get("extension_progid"):
             console.print("[yellow][!] NOT REGISTERED[/yellow]")
             issues += 1
        else:
             console.print("[green][OK][/green]")
    elif diag["status"] == "OVERRIDDEN":
        console.print("[bold red][OVERRIDDEN][/bold red]")
        console.print(f"   [yellow]→ {diag['issues'][0]}[/yellow]")
        console.print("   [dim]Fix: Right-click any .epi file -> Open with -> Choose another app[/dim]")
        console.print("   [dim]     Select 'EPI Viewer' and check 'Always use this app'[/dim]")
        issues += 1
    else:
        console.print("[red][X] ISSUES FOUND[/red]")
        for issue in diag["issues"]:
            console.print(f"   [red]• {issue}[/red]")
        issues += 1
        
    # Summary
    print()
    console.print("[bold]" + "="*70 + "[/bold]")
    if issues == 0:
        console.print("[bold green][OK] System Healthy![/bold green]")
    else:
        if fixed > 0:
            console.print(f"[bold yellow][!] Fixed {fixed}/{issues} issues[/bold yellow]")
            if fixed < issues:
                console.print("[dim]Some issues require manual attention (see above)[/dim]")
        else:
            console.print(f"[bold yellow][!] Found {issues} issues[/bold yellow]")
            console.print("[dim]See suggestions above[/dim]")
    console.print("[bold]" + "="*70 + "[/bold]\n")


# Entry point for CLI
def cli_main():
    """CLI entry point (called by `epi` command)."""
    # Fix Windows console encoding (cp1252 → utf-8) BEFORE any output
    import sys as _sys
    import io as _io
    if _sys.platform == "win32":
        try:
            _sys.stdout = _io.TextIOWrapper(
                _sys.stdout.buffer, encoding="utf-8", errors="replace"
            )
            _sys.stderr = _io.TextIOWrapper(
                _sys.stderr.buffer, encoding="utf-8", errors="replace"
            )
        except Exception:
            pass  # Already wrapped or no buffer — safe to ignore

    app()


if __name__ == "__main__":
    cli_main()



 
