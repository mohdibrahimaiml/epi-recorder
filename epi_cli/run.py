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
import time
import zipfile
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import typer
from rich.console import Console
from rich.panel import Panel

from epi_core.container import EPIContainer
from epi_core.schemas import ManifestModel
from epi_core.trust import verify_embedded_manifest_signature
from epi_core.workspace import RecordingWorkspaceError, create_recording_workspace

from epi_cli.keys import KeyManager
from epi_cli._shared import ensure_python_command, build_env_for_child
from epi_cli.view import (
    _build_viewer_context,
    _inject_viewer_context,
    _make_temp_dir,
    _refresh_viewer_html,
)
from epi_recorder.environment import save_environment_snapshot

console = Console()

app = typer.Typer(name="run", help="Record a Python workflow that already emits EPI steps.")

DEFAULT_DIR = Path("epi-recordings")


def _print_workspace_failure(exc: Exception) -> None:
    console.print("\n[bold red][X] EPI could not start recording.[/bold red]")
    console.print(f"[dim]{exc}[/dim]")
    console.print("[dim]Fix: set TMP/TEMP to a writable folder and rerun.[/dim]\n")


def _gen_auto_name(script_path: Path) -> Path:
    """
    Generate automatic output filename in ./epi-recordings/ directory.
    
    Args:
        script_path: Path to the script being recorded
        
    Returns:
        Path to the .epi file
    """
    base = script_path.stem if script_path.name != "-" else "recording"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
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
        
        signature_valid, _signer_name, msg = verify_embedded_manifest_signature(manifest)
        if signature_valid is True:
            return True, "OK (signed & verified)"
        if signature_valid is None:
            return True, "OK (unsigned)"
        return False, msg
            
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


def _summarize_recording_steps(workspace: Path) -> tuple[int, set[str]]:
    """Return total step count and the set of recorded kinds."""
    timeline_path = workspace / "steps.jsonl"
    if not timeline_path.exists():
        return 0, set()

    try:
        lines = timeline_path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return 0, set()

    kinds: set[str] = set()
    count = 0
    for line in lines:
        if not line.strip():
            continue
        count += 1
        try:
            payload = json.loads(line)
            kind = payload.get("kind")
            if isinstance(kind, str) and kind:
                kinds.add(kind)
        except Exception:
            continue
    return count, kinds


def _summarize_artifact_steps(epi_file: Path) -> tuple[int, set[str]]:
    """Return total step count and recorded kinds from a packed artifact."""
    if not epi_file.exists():
        return 0, set()

    try:
        with zipfile.ZipFile(epi_file, "r") as zf:
            if "steps.jsonl" not in zf.namelist():
                return 0, set()
            lines = zf.read("steps.jsonl").decode("utf-8").splitlines()
    except Exception:
        return 0, set()

    kinds: set[str] = set()
    count = 0
    for line in lines:
        if not line.strip():
            continue
        count += 1
        try:
            payload = json.loads(line)
            kind = payload.get("kind")
            if isinstance(kind, str) and kind:
                kinds.add(kind)
        except Exception:
            continue
    return count, kinds


def _artifact_dirs_for_script(script_path: Path) -> list[Path]:
    """Candidate directories where a child script may create .epi artifacts."""
    candidates = [
        Path.cwd() / DEFAULT_DIR,
        script_path.parent / DEFAULT_DIR,
        Path.cwd(),
        script_path.parent,
    ]

    resolved: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        try:
            key = str(candidate.resolve())
        except Exception:
            key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        resolved.append(candidate)
    return resolved


def _snapshot_artifacts(script_path: Path) -> dict[Path, tuple[float, int]]:
    """Capture .epi files and lightweight stats from likely user artifact dirs."""
    snapshot: dict[Path, tuple[float, int]] = {}
    for directory in _artifact_dirs_for_script(script_path):
        if not directory.exists() or not directory.is_dir():
            continue
        for artifact in directory.glob("*.epi"):
            try:
                stat = artifact.stat()
            except Exception:
                continue
            snapshot[artifact.resolve()] = (stat.st_mtime, stat.st_size)
    return snapshot


def _detect_new_artifacts(
    before: dict[Path, tuple[float, int]],
    after: dict[Path, tuple[float, int]],
    *,
    exclude: Optional[Set[Path]] = None,
) -> list[Path]:
    """Return new or modified artifacts created during script execution."""
    exclude = exclude or set()
    created: list[Path] = []
    for path, fingerprint in after.items():
        if path in exclude:
            continue
        previous = before.get(path)
        if previous is None or previous != fingerprint:
            created.append(path)
    created.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return created


def _should_prefer_child_artifact(
    bootstrap_count: int,
    bootstrap_kinds: set[str],
    child_count: int,
    child_kinds: set[str],
) -> bool:
    """Decide whether a child-created artifact is a better user-facing result."""
    if child_count <= 0:
        return False

    bootstrap_stdout_only = bootstrap_count > 0 and bootstrap_kinds.issubset({"stdout.print"})
    child_stdout_only = child_count > 0 and child_kinds.issubset({"stdout.print"})

    if bootstrap_count == 0:
        return True
    if bootstrap_stdout_only and not child_stdout_only:
        return True
    if child_count > bootstrap_count:
        return True
    return False


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
        temp_dir = _make_temp_dir()
        if temp_dir is None:
            return False
        with zipfile.ZipFile(epi_file, "r") as zf:
            zf.extractall(temp_dir)
        viewer_path = _refresh_viewer_html(temp_dir, epi_file)
        _inject_viewer_context(viewer_path, _build_viewer_context(epi_file))

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
    try:
        temp_workspace = create_recording_workspace("epi_record_")
        steps_dir = temp_workspace
        env_json = temp_workspace / "environment.json"

        # Capture environment snapshot
        save_environment_snapshot(env_json, include_all_env_vars=False, redact_env_vars=True)

        # Build child environment and run
        child_env = build_env_for_child(steps_dir, enable_redaction=True)
    except (RecordingWorkspaceError, OSError, PermissionError) as exc:
        _print_workspace_failure(exc)
        raise typer.Exit(1)
    
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

    before_artifacts = _snapshot_artifacts(script)
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

    step_count, step_kinds = _summarize_recording_steps(temp_workspace)
    effective_out = out
    script_artifact_detected = None

    after_artifacts = _snapshot_artifacts(script)
    child_artifacts = _detect_new_artifacts(
        before_artifacts,
        after_artifacts,
        exclude={out.resolve()},
    )
    if child_artifacts:
        child_summaries = []
        for artifact in child_artifacts:
            child_count, child_kinds = _summarize_artifact_steps(artifact)
            child_summaries.append((artifact, child_count, child_kinds))

        # Prefer the richest child-created artifact so scripts that already use
        # record(...) don't end up with a misleading competing bootstrap file.
        child_summaries.sort(
            key=lambda item: (
                0 if (item[1] > 0 and not item[2].issubset({"stdout.print"})) else 1,
                -item[1],
                -item[0].stat().st_mtime,
            )
        )
        preferred_child, child_count, child_kinds = child_summaries[0]
        if _should_prefer_child_artifact(step_count, step_kinds, child_count, child_kinds):
            effective_out = preferred_child
            step_count, step_kinds = child_count, child_kinds
            script_artifact_detected = preferred_child
            if out.exists() and out.resolve() != preferred_child.resolve():
                out.unlink(missing_ok=True)

    empty_recording = step_count == 0
    stdout_only_recording = step_count > 0 and step_kinds.issubset({"stdout.print"})
    if script_artifact_detected is not None:
        console.print("\n[bold cyan][i] This script created its own EPI artifact via record(...).[/bold cyan]")
        console.print(f"[dim]Using that artifact instead of the bootstrap capture: {script_artifact_detected}[/dim]\n")

    if empty_recording:
        console.print("\n[bold red][X] No steps recorded.[/bold red]")
        console.print("[dim]EPI was not attached to this script, so the artifact is only useful for debugging.[/dim]")
        console.print("[dim]Fix: use [cyan]record(...) [/cyan], a supported integration, or [cyan]get_current_session().log_step(...)[/cyan] inside epi run mode.[/dim]\n")
    elif stdout_only_recording:
        console.print("\n[bold yellow][!] EPI captured console output, but not structured workflow steps.[/bold yellow]")
        console.print("[dim]This is enough to inspect what the script printed, but richer fault analysis needs explicit EPI steps.[/dim]")
        console.print("[dim]Next step: use [cyan]record(...)[/cyan], wrappers/integrations, or [cyan]get_current_session().log_step(...)[/cyan] for meaningful policy analysis.[/dim]\n")
    elif step_count <= 2:
        console.print("\n[bold yellow][!] Warning: Very little execution data was recorded.[/bold yellow]")
        console.print("[dim]Make sure your workflow emits meaningful EPI steps, not just setup/teardown.[/dim]\n")

    # Verify
    verified = False
    verify_msg = "Skipped"
    if not no_verify:
        verified, verify_msg = _verify_recording(effective_out)

    # Open viewer
    viewer_opened = False
    if not no_open and rc == 0 and verified and not empty_recording:
        viewer_opened = _open_viewer(effective_out)

    # Build summary panel
    size_bytes = effective_out.stat().st_size
    size_str = f"{size_bytes / (1024*1024):.2f} MB" if size_bytes >= 100_000 else f"{size_bytes / 1024:.1f} KB"

    lines = []
    lines.append(f"[bold]Saved:[/bold]    {effective_out.resolve()}")
    step_style = "red" if empty_recording else "yellow" if step_count <= 2 else "dim"
    lines.append(f"[bold]Size:[/bold]     {size_str}   [{step_style}]({step_count} steps  •  {duration}s)[/{step_style}]")
    if script_artifact_detected is not None:
        lines.append("[bold cyan]Source:[/bold cyan]   Used the artifact generated by the script itself")
    if empty_recording:
        lines.append("[bold red]Status:[/bold red]   Recording incomplete - no execution data was captured")
        lines.append("[dim]Use this artifact only for debugging the failed recording path.[/dim]")
    elif stdout_only_recording:
        lines.append("[bold yellow]Status:[/bold yellow]   Captured console output only - useful evidence, but limited analysis depth")
        lines.append("[dim]Add explicit EPI steps for policy-aware review and better fault detection.[/dim]")

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

    lines.append(f"\n[dim]  epi view {effective_out.stem}    epi verify {effective_out.stem}    epi ls[/dim]")
    if empty_recording:
        lines.append("[dim]  Next step: instrument with record(), wrappers/integrations, or get_current_session().log_step(...), then run again.[/dim]")
    elif stdout_only_recording:
        lines.append("[dim]  Next step: console output was captured automatically; add record(), wrappers, or get_current_session().log_step(...) for structured workflow evidence.[/dim]")

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



 
