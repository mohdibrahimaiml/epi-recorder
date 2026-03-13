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
  run        <script.py>       Record, auto-verify and open viewer. (Zero-config)
  record     --out <file.epi> -- <cmd...>
                               Advanced: record any command, exact output file.
  verify     <file.epi>        Verify a recording's integrity.
  view       <file.epi|name>   Open recording in browser or extract.
  ls                           List local recordings (./epi-recordings/).
  keys                         Manage keys (list/generate/export) - advanced.
  chat       <file.epi>        Chat with evidence file using AI.
  debug      <file.epi>        Debug AI agent recordings for mistakes.
  global                       Install/uninstall global auto-recording.
  associate                    Register .epi file type with the OS.
  init                         First-time setup wizard.
  doctor                       Self-healing system health check.
  help                         Show this quickstart.

Quickstart (first 30s):
  1) Install: pip install epi-recorder
  2) Record (simplest): epi run my_script.py
     -> Saved: ./epi-recordings/my_script_20251121_231501.epi
     -> Verified: OK
     -> Viewer: opened in browser
  3) See recordings: epi ls
  4) Open a recording: epi view my_script_20251121_231501

Tips:
  - Want explicit name? Use the advanced command: epi record --out experiment.epi -- python my_script.py
  - For scripts using the API, use @record decorator or with record(): no filenames needed.
""",
    add_completion=False,
    no_args_is_help=True,
    rich_markup_mode="rich",
    # Add version option
    callback=None  # Will set via decorator below
)

console = Console()


@app.callback()
def main_callback(
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

    Implements frictionless first run by auto-generating default key pair
    and registering .epi file association with the OS.
    """
    import sys as _sys
    # Auto-generate default keypair if missing (frictionless first run)
    # Only print welcome message when running in an interactive terminal
    generate_default_keypair_if_missing(console_output=_sys.stdout.isatty())

    # Auto-register .epi file association (idempotent — skips if already done)
    from epi_core.platform.associate import register_file_association
    register_file_association(silent=True)


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
  [cyan]run[/cyan]        <script.py>       Record, auto-verify and open viewer. (Zero-config)
  [cyan]record[/cyan]     --out <file.epi> -- <cmd...>
                             Advanced: record any command, exact output file.
  [cyan]verify[/cyan]     <file.epi>        Verify a recording's integrity.
  [cyan]view[/cyan]       <file.epi|name>   Open recording in browser or extract.
  [cyan]ls[/cyan]                           List local recordings (./epi-recordings/).
  [cyan]keys[/cyan]                         Manage keys (list/generate/export) - advanced.
  [cyan]chat[/cyan]       <file.epi>        Chat with evidence file using AI.
  [cyan]debug[/cyan]      <file.epi>        Debug AI agent recordings for mistakes.
  [cyan]global[/cyan]                       Install/uninstall global auto-recording.
  [cyan]associate[/cyan]                    Register .epi file type with the OS.
  [cyan]init[/cyan]                         First-time setup wizard.
  [cyan]doctor[/cyan]                       Self-healing system health check.
  [cyan]help[/cyan]                         Show this quickstart.

[bold]Quickstart (first 30s):[/bold]
  1) Install: pip install epi-recorder
  2) Record (simplest): [green]epi run my_script.py[/green]
     -> Saved: ./epi-recordings/my_script_20251121_231501.epi
     -> Verified: OK
     -> Viewer: opened in browser
  3) See recordings: [green]epi ls[/green]
  4) Open a recording: [green]epi view my_script_20251121_231501[/green]

[bold]Tips:[/bold]
  - Want explicit name? Use the advanced command: epi record --out experiment.epi -- python my_script.py
  - For scripts using the API, use @record decorator or with record(): no filenames needed.
"""
    console.print(help_text)


# Import and register subcommands
# These will be added as they're implemented

# NEW: run command (zero-config) - direct import
from epi_cli.run import run as run_command
app.command(name="run", help="Record, auto-verify and open viewer. (Zero-config)")(run_command)

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


# NEW: file association commands (v2.7.2)
@app.command()
def associate(
    force: bool = typer.Option(False, "--force", help="Re-register even if already done"),
):
    """Register .epi file type with the OS so double-clicking opens the viewer."""
    from epi_core.platform.associate import register_file_association, _needs_registration
    if not force and not _needs_registration():
        console.print("[green][OK][/green] .epi file association already registered.")
        return
    success = register_file_association(silent=False, force=force)
    if not success:
        raise typer.Exit(1)


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
    [Wizard] First-time setup wizard! Creates keys, demo script, and runs it.
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

import time

print("="*40)
print("   Hello from your first EPI recording!")
print("="*40)

print("\\n1. Doing some math...")
result = 123 * 456
print(f"   123 * 456 = {result}")

print("\\n2. Creating a file...")
with open("epi_hello.txt", "w", encoding="utf-8") as f:
    f.write(f"Calculation result: {result}")
print("   Saved 'epi_hello.txt'")

print("\\n3. Finishing up...")
time.sleep(0.5)
print("[OK] Done! Now check the browser!")
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
    
    # Call run command programmatically
    # We use subprocess to keep it clean separate process
    import subprocess
    import sys
    cmd = [sys.executable, "-m", "epi_cli.main", "run", demo_filename]
    if no_open:
        cmd.append("--no-open")
    subprocess.run(cmd)

    console.print("\n[bold green]You are all set![/bold green]")
    console.print(f"[dim]Next time just run:[/dim] epi run {demo_filename}")


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



 