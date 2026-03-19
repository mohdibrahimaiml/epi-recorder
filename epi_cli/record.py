"""
EPI CLI Record - Capture AI workflow into a portable .epi file.

Usage:
  epi record --out run.epi -- python script.py [args...]

This command:
- Prepares a recording workspace
- Patches LLM libraries in the child process
- Captures environment snapshot (environment.json)
- Runs the user command with secret redaction enabled by default
- Packages everything into a .epi
- Auto-signs the manifest with the default Ed25519 key
"""

import shlex
import time
from pathlib import Path
from typing import List, Optional

import typer
from rich.console import Console
from rich.panel import Panel

from epi_core.container import EPIContainer
from epi_core.schemas import ManifestModel
from epi_core.trust import sign_manifest
from epi_core.workspace import RecordingWorkspaceError, create_recording_workspace
from epi_cli.keys import KeyManager
from epi_cli._shared import ensure_python_command, build_env_for_child
from epi_recorder.environment import save_environment_snapshot

console = Console()


app = typer.Typer(name="record", help="Record a workflow into a .epi file")


def _print_workspace_failure(exc: Exception) -> None:
    console.print("[red][FAIL] EPI could not start recording.[/red]")
    console.print(f"[dim]{exc}[/dim]")
    console.print("[dim]Fix: point TMP/TEMP to a writable folder and rerun.[/dim]")


@app.callback(invoke_without_command=True)
def record(
    ctx: typer.Context,
    out: Path = typer.Option(..., "--out", help="Output .epi file path"),
    name: Optional[str] = typer.Option(None, "--name", help="Optional run name"),
    tag: Optional[str] = typer.Option(None, "--tag", help="Optional tag/label"),
    no_sign: bool = typer.Option(False, "--no-sign", help="Do not sign the manifest"),
    no_redact: bool = typer.Option(False, "--no-redact", help="Disable secret redaction"),
    include_all_env: bool = typer.Option(False, "--include-all-env", help="Capture all env vars (redacted)"),
    command: List[str] = typer.Argument(..., help="Command to execute after --"),
):
    """
    Record a command and package the run into a .epi file.
    
    [NOTICE] For scripts that already emit EPI steps, try: epi run script.py
    This command (epi record --out) is for advanced/CI use cases.
    """
    if not command:
        console.print("[red][FAIL] No command provided[/red]")
        raise typer.Exit(1)
    
    # Show deprecation notice
    console.print("[dim][NOTICE] For scripts that already emit EPI steps, try: epi run script.py[/dim]")
    console.print("[dim]This advanced command is for CI/exact-control use cases.[/dim]\n")

    # Normalize command
    cmd = ensure_python_command(command)

    # Prepare workspace
    try:
        temp_workspace = create_recording_workspace("epi_record_")
        steps_dir = temp_workspace  # steps.jsonl lives here
        env_json = temp_workspace / "environment.json"

        # Capture environment snapshot
        save_environment_snapshot(env_json, include_all_env_vars=include_all_env, redact_env_vars=True)

        # Build child environment and run
        child_env = build_env_for_child(steps_dir, enable_redaction=(not no_redact))
    except (RecordingWorkspaceError, OSError, PermissionError) as exc:
        _print_workspace_failure(exc)
        raise typer.Exit(1)

    # Create stdout/stderr logs
    stdout_log = temp_workspace / "stdout.log"
    stderr_log = temp_workspace / "stderr.log"

    console.print(f"[dim]Recording:[/dim] {' '.join(shlex.quote(c) for c in cmd)}")

    import subprocess

    start = time.time()
    with open(stdout_log, "wb") as out_f, open(stderr_log, "wb") as err_f:
        proc = subprocess.Popen(cmd, env=child_env, stdout=out_f, stderr=err_f)
        rc = proc.wait()
    duration = round(time.time() - start, 3)

    # Build manifest
    manifest = ManifestModel(
        cli_command=" ".join(shlex.quote(c) for c in cmd),
    )

    # Package into .epi
    out = out if str(out).endswith(".epi") else out.with_suffix(".epi")
    
    signed = False
    signer = None
    if not no_sign:
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
            console.print(f"[yellow][WARN]  Signing setup failed:[/yellow] {e}")

    EPIContainer.pack(temp_workspace, manifest, out, signer_function=signer)

    # Final output panel
    size_mb = out.stat().st_size / (1024 * 1024)
    title = "[OK] Recording complete" if rc == 0 else "[WARN] Recording finished with errors"
    panel = Panel(
        f"[bold]File:[/bold] {out}\n"
        f"[bold]Size:[/bold] {size_mb:.1f} MB\n"
        f"[bold]Duration:[/bold] {duration}s\n"
        f"[bold]Exit code:[/bold] {rc}\n"
        f"[bold]Signed:[/bold] {'Yes' if signed else 'No'}\n"
        f"[dim]Verify:[/dim] epi verify {shlex.quote(str(out))}",
        title=title,
        border_style="green" if rc == 0 else "yellow",
    )
    console.print(panel)

    # Exit with child return code
    raise typer.Exit(rc)



 
