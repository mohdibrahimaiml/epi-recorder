"""
EPI CLI Run - Record an already-instrumented Python workflow.

Usage:
  epi run script.py

This command:
- Auto-generates output filename in ./epi-recordings/
- Executes the script with EPI recording environment variables
- Verifies the recording
- Opens the viewer automatically when meaningful evidence was captured
"""

import shlex
import tempfile
import time
import zipfile
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import typer
from rich.console import Console
from rich.panel import Panel

from epi_core.container import EPIContainer
from epi_core.schemas import ManifestModel
from epi_core.trust import verify_signature, get_signer_name, create_verification_report

from epi_cli.keys import KeyManager
from epi_cli._shared import ensure_python_command, build_env_for_child
from epi_recorder.environment import save_environment_snapshot

console = Console()

app = typer.Typer(name="run", help="Record a Python workflow that already emits EPI steps.")

DEFAULT_DIR = Path("epi-recordings")


def _gen_auto_name(script_path: Path) -> Path:
    """
    Generate automatic output filename in ./epi-recordings/ directory.
    
    Args:
        script_path: Path to the script being recorded
        
    Returns:
        Path to the .epi file
    """
    base = script_path.stem if script_path.name != "-" else "recording"
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    DEFAULT_DIR.mkdir(parents=True, exist_ok=True)
    return DEFAULT_DIR / f"{base}_{timestamp}.epi"




def _verify_recording(epi_file: Path) -> tuple[bool, str]:
    """
    Verify the recording and return status.
    
    Returns:
        (success, message) tuple
    """
    try:
        manifest = EPIContainer.read_manifest(epi_file)
        integrity_ok, mismatches = EPIContainer.verify_integrity(epi_file)
        
        if not integrity_ok:
            return False, f"Integrity check failed ({len(mismatches)} mismatches)"
        
        # Check signature
        if manifest.signature:
            if not manifest.public_key:
                return False, "Signature error: No public key embedded in manifest"
            try:
                public_key_bytes = bytes.fromhex(manifest.public_key)
                signature_valid, msg = verify_signature(manifest, public_key_bytes)
                if signature_valid:
                    return True, "OK (signed & verified)"
                else:
                    return False, f"Signature invalid: {msg}"
            except Exception as e:
                return False, f"Verification error: {e}"
        else:
            return True, "OK (unsigned)"
            
    except Exception as e:
        return False, f"Verification failed: {e}"


def _count_recorded_steps(workspace: Path) -> int:
    """Count execution steps from the live recording workspace."""
    timeline_path = workspace / "steps.jsonl"
    if not timeline_path.exists():
        return 0

    try:
        content = timeline_path.read_text(encoding="utf-8").strip()
    except Exception:
        return 0

    if not content:
        return 0
    return len([line for line in content.splitlines() if line.strip()])


def _open_viewer(epi_file: Path) -> bool:
    """
    Open the viewer for the recording.

    Returns:
        True if opened successfully
    """
    try:
        import shutil
        import threading
        import webbrowser

        # Extract viewer to temp location
        temp_dir = Path(tempfile.mkdtemp(prefix="epi_view_"))
        viewer_path = temp_dir / "viewer.html"

        with zipfile.ZipFile(epi_file, "r") as zf:
            if "viewer.html" not in zf.namelist():
                shutil.rmtree(temp_dir, ignore_errors=True)
                return False
            zf.extract("viewer.html", temp_dir)

        file_url = viewer_path.as_uri()
        opened = webbrowser.open(file_url)

        # Clean up temp dir after browser has had time to load the file.
        # Non-daemon so the process stays alive long enough for the browser.
        def _cleanup():
            import time
            time.sleep(30)
            shutil.rmtree(temp_dir, ignore_errors=True)

        t = threading.Thread(target=_cleanup, daemon=False)
        t.start()

        return opened

    except Exception:
        return False


@app.command()
def run(
    script: Optional[Path] = typer.Argument(None, help="Python script to record (Optional - Interactive if missing)"),
    no_verify: bool = typer.Option(False, "--no-verify", help="Skip verification"),
    no_open: bool = typer.Option(False, "--no-open", help="Don't open viewer automatically"),
    # New metadata options
    goal: Optional[str] = typer.Option(None, "--goal", help="Goal or objective of this workflow"),
    notes: Optional[str] = typer.Option(None, "--notes", help="Additional notes about this workflow"),
    metric: Optional[List[str]] = typer.Option(None, "--metric", help="Key=value metrics (can be used multiple times)"),
    approved_by: Optional[str] = typer.Option(None, "--approved-by", help="Person who approved this workflow"),
    tag: Optional[List[str]] = typer.Option(None, "--tag", help="Tags for categorizing this workflow (can be used multiple times)"),
):
    """
    Record + verify + view for a script that already emits EPI steps.
    
    Interactive:
        epi run  (Selects script from list)
        
    Direct:
        epi run my_script.py
    """
    
    # --- SMART UX 1: INTERACTIVE MODE ---
    if script is None:
        # Find Python files in current directory, sorted by most recently modified
        py_files = sorted(
            [f for f in Path.cwd().glob("*.py") if f.name not in ("setup.py", "epi_setup.py")],
            key=lambda f: f.stat().st_mtime,
            reverse=True,
        )

        if not py_files:
            console.print("[yellow]No Python scripts found in this directory.[/yellow]")
            console.print("Create one or specify path: epi run [path/to/script.py]")
            raise typer.Exit(1)

        console.print("\n[bold cyan]Select a script to record:[/bold cyan]")
        for idx, f in enumerate(py_files, 1):
            mtime = datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
            size_kb = f.stat().st_size / 1024
            size_str = f"{size_kb:.1f} KB"
            console.print(f"  [green]{idx}.[/green] {f.name:<30} [dim]{mtime}  {size_str}[/dim]")

        from rich.prompt import Prompt
        choice = Prompt.ask("\nNumber", default="1")

        try:
            choice_idx = int(choice) - 1
            if 0 <= choice_idx < len(py_files):
                script = py_files[choice_idx]
            else:
                console.print("[red]Invalid selection.[/red]")
                raise typer.Exit(1)
        except ValueError:
            console.print("[red]Invalid input.[/red]")
            raise typer.Exit(1)

        console.print(f"[dim]Selected:[/dim] {script.name}\n")

    # --- SMART UX 2: TYPO FIXER ---
    # Validate script exists
    if not script.exists():
        # Check for typos (simple close match)
        import difflib
        candidates = list(Path.cwd().glob("*.py"))
        candidate_names = [c.name for c in candidates]
        matches = difflib.get_close_matches(script.name, candidate_names, n=1, cutoff=0.6)
        
        if matches:
            from rich.prompt import Confirm
            suggestion = matches[0]
            if Confirm.ask(f"[yellow]Script '{script}' not found. Did you mean '{suggestion}'?[/yellow]"):
                script = Path(suggestion)
            else:
                console.print(f"[red][FAIL] Error:[/red] Script not found: {script}")
                raise typer.Exit(1)
        else:
            console.print(f"[red][FAIL] Error:[/red] Script not found: {script}")
            raise typer.Exit(1)
    
    # Parse metrics if provided
    metrics_dict = None
    if metric:
        metrics_dict = {}
        for m in metric:
            if "=" in m:
                key, value = m.split("=", 1)
                # Try to convert to float if possible, otherwise keep as string
                try:
                    metrics_dict[key] = float(value)
                except ValueError:
                    metrics_dict[key] = value
            else:
                console.print(f"[yellow]Warning:[/yellow] Invalid metric format: {m} (expected key=value)")
    
    # Auto-generate output filename
    out = _gen_auto_name(script)
    
    # Normalize command
    cmd = ensure_python_command([str(script)])
    
    # Prepare workspace
    temp_workspace = Path(tempfile.mkdtemp(prefix="epi_record_"))
    steps_dir = temp_workspace
    env_json = temp_workspace / "env.json"
    
    # Capture environment snapshot
    save_environment_snapshot(env_json, include_all_env_vars=False, redact_env_vars=True)
    
    # Build child environment and run
    child_env = build_env_for_child(steps_dir, enable_redaction=True)
    
    # Create stdout/stderr logs
    stdout_log = temp_workspace / "stdout.log"
    stderr_log = temp_workspace / "stderr.log"
    
    console.print(f"[dim]Recording:[/dim] {script.name}")
    
    # --- AUTO-FIX 1: KEYS ---
    # Ensure default keys exist so it's never "Unsigned"
    from epi_cli.keys import generate_default_keypair_if_missing
    generated = generate_default_keypair_if_missing(console_output=False)
    if generated:
         console.print("[green]Created your secure cryptographic identity (keys/default)[/green]")
    # -----------------------
    
    import shutil as _shutil
    import subprocess

    start = time.time()
    try:
        with open(stdout_log, "wb") as out_f, open(stderr_log, "wb") as err_f:
            proc = subprocess.Popen(cmd, env=child_env, stdout=out_f, stderr=err_f)
            rc = proc.wait()
    except Exception as e:
        _shutil.rmtree(temp_workspace, ignore_errors=True)
        console.print(f"\n[bold red][FAIL] Could not execute command:[/bold red] {cmd[0]}")
        console.print(f"[dim]Error detail: {e}[/dim]")
        raise typer.Exit(1)
    duration = round(time.time() - start, 3)
    
    # Build manifest with metadata
    manifest = ManifestModel(
        cli_command=" ".join(shlex.quote(c) for c in cmd),
        goal=goal,
        notes=notes,
        metrics=metrics_dict,
        approved_by=approved_by,
        tags=tag
    )
    
    # Auto-sign
    signed = False
    signer = None
    try:
        km = KeyManager()
        priv = km.load_private_key("default")
        from epi_core.trust import sign_manifest
        def signer_func(m):
            nonlocal signed
            signed_manifest = sign_manifest(m, priv, "default")
            signed = True
            return signed_manifest
        signer = signer_func
    except Exception as e:
        pass  # Non-fatal

    # Package into .epi
    EPIContainer.pack(temp_workspace, manifest, out, signer_function=signer)
    
    step_count = _count_recorded_steps(temp_workspace)
    empty_recording = step_count == 0
    if empty_recording:
        console.print("\n[bold red][X] No steps recorded.[/bold red]")
        console.print("[dim]EPI was not attached to this script, so the artifact is only useful for debugging.[/dim]")
        console.print("[dim]Fix: use [cyan]from epi_recorder import record[/cyan] or a supported integration.[/dim]\n")
    elif step_count <= 2:
        console.print("\n[bold yellow][!] Warning: Very little execution data was recorded.[/bold yellow]")
        console.print("[dim]Make sure your workflow emits meaningful EPI steps, not just setup/teardown.[/dim]\n")

    # Verify
    verified = False
    verify_msg = "Skipped"
    if not no_verify:
        verified, verify_msg = _verify_recording(out)

    # Open viewer
    viewer_opened = False
    if not no_open and rc == 0 and verified and not empty_recording:
        viewer_opened = _open_viewer(out)

    # Build summary panel
    size_bytes = out.stat().st_size
    size_str = f"{size_bytes / (1024*1024):.2f} MB" if size_bytes >= 100_000 else f"{size_bytes / 1024:.1f} KB"

    lines = []
    lines.append(f"[bold]Saved:[/bold]    {out.resolve()}")
    step_style = "red" if empty_recording else "yellow" if step_count <= 2 else "dim"
    lines.append(f"[bold]Size:[/bold]     {size_str}   [{step_style}]({step_count} steps  •  {duration}s)[/{step_style}]")
    if empty_recording:
        lines.append("[bold red]Status:[/bold red]   Recording incomplete - no execution data was captured")
        lines.append("[dim]Use this artifact only for debugging the failed recording path.[/dim]")

    if not no_verify:
        if verified:
            verify_color = "yellow" if empty_recording else "green"
            lines.append(f"[bold]Verified:[/bold] [{verify_color}]{verify_msg}[/{verify_color}]")
        else:
            lines.append(f"[bold]Verified:[/bold] [red]{verify_msg}[/red]")

    if viewer_opened:
        lines.append(f"[bold]Viewer:[/bold]   [green]Opened in browser[/green]")
    elif not no_open:
        if empty_recording:
            lines.append("[bold]Viewer:[/bold]   [yellow]Skipped - no meaningful execution data was captured[/yellow]")
        else:
            lines.append(f"[bold]Viewer:[/bold]   [yellow]Could not open automatically[/yellow]")

    lines.append(f"\n[dim]  epi view {out.stem}    epi verify {out.stem}    epi ls[/dim]")
    if empty_recording:
        lines.append("[dim]  Next step: instrument your script with record() and run it again.[/dim]")

    if empty_recording:
        title = "[bold red]Recording captured no execution data[/bold red]"
        border_style = "red"
    elif rc == 0:
        title = "[bold green]Recording complete[/bold green]"
        border_style = "green"
    else:
        title = "[bold yellow]Recording finished with errors[/bold yellow]"
        border_style = "yellow"
    panel = Panel(
        "\n".join(lines),
        title=title,
        border_style=border_style,
    )
    console.print(panel)
    
    # Exit with appropriate code
    if rc != 0:
        raise typer.Exit(rc)
    if empty_recording:
        raise typer.Exit(1)
    if not verified and not no_verify:
        raise typer.Exit(1)
    raise typer.Exit(0)



 
