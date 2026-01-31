"""
EPI CLI Record - Capture AI workflow into a portable .epi file.

Usage:
  epi record --out run.epi -- python script.py [args...]

This command:
- Prepares a recording workspace
- Patches LLM libraries in the child process
- Captures environment snapshot (env.json)
- Runs the user command with secret redaction enabled by default
- Packages everything into a .epi
- Auto-signs the manifest with the default Ed25519 key
"""

import os
import shlex
import sys
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
from epi_core.trust import sign_manifest, sign_manifest_inplace
from epi_cli.keys import KeyManager
from epi_recorder.environment import save_environment_snapshot

console = Console()


def _ensure_python_command(cmd: List[str]) -> List[str]:
    """
    Ensure the command is run with Python if it looks like a Python script.
    If the user provided `python ...`, leave as-is.
    If the command is a .py file, prepend current Python executable.
    """
    if not cmd:
        return cmd
    first = cmd[0]
    if first.lower().endswith('.py'):
        return [sys.executable] + cmd
    return cmd


def _build_env_for_child(steps_dir: Path, enable_redaction: bool) -> dict:
    """
    Build environment variables for child process to enable recording via sitecustomize.
    """
    env = os.environ.copy()

    # Indicate recording mode and where to write steps
    env["EPI_RECORD"] = "1"
    env["EPI_STEPS_DIR"] = str(steps_dir)
    env["EPI_REDACT"] = "1" if enable_redaction else "0"

    # Create a temporary bootstrap dir with sitecustomize.py
    bootstrap_dir = Path(tempfile.mkdtemp(prefix="epi_bootstrap_"))
    sitecustomize = bootstrap_dir / "sitecustomize.py"
    sitecustomize.write_text(
        "from epi_recorder.bootstrap import initialize_recording\n",
        encoding="utf-8",
    )

    # Prepend bootstrap dir and project root to PYTHONPATH
    project_root = Path(__file__).resolve().parent.parent
    existing = env.get("PYTHONPATH", "")
    sep = os.pathsep
    env["PYTHONPATH"] = f"{bootstrap_dir}{sep}{project_root}{(sep + existing) if existing else ''}"

    return env


app = typer.Typer(name="record", help="Record a workflow into a .epi file")


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
    
    [NOTICE] For simpler usage, try: epi run script.py
    This command (epi record --out) is for advanced/CI use cases.
    """
    if not command:
        console.print("[red][FAIL] No command provided[/red]")
        raise typer.Exit(1)
    
    # Show deprecation notice
    console.print("[dim][NOTICE] For simpler usage, try: epi run script.py[/dim]")
    console.print("[dim]This advanced command is for CI/exact-control use cases.[/dim]\n")

    # Normalize command
    cmd = _ensure_python_command(command)

    # Prepare workspace
    temp_workspace = Path(tempfile.mkdtemp(prefix="epi_record_"))
    steps_dir = temp_workspace  # steps.jsonl lives here
    env_json = temp_workspace / "env.json"

    # Capture environment snapshot
    save_environment_snapshot(env_json, include_all_env_vars=include_all_env, redact_env_vars=True)

    # Build child environment and run
    child_env = _build_env_for_child(steps_dir, enable_redaction=(not no_redact))

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
    EPIContainer.pack(temp_workspace, manifest, out)

    # Auto-sign manifest inside .epi (without re-packing)
    signed = False
    if not no_sign:
        try:
            km = KeyManager()
            priv = km.load_private_key("default")
            
            # Read manifest from ZIP
            import json as _json
            with zipfile.ZipFile(out, "r") as zf:
                raw = zf.read("manifest.json").decode("utf-8")
                data = _json.loads(raw)
            
            # Sign manifest
            from epi_core.schemas import ManifestModel as _MM
            from epi_core.trust import sign_manifest as _sign
            m = _MM(**data)
            sm = _sign(m, priv, "default")
            signed_json = sm.model_dump_json(indent=2)
            
            # Replace manifest in ZIP (avoid duplicate)
            temp_zip = out.with_suffix(".epi.tmp")
            with zipfile.ZipFile(out, "r") as zf_in:
                with zipfile.ZipFile(temp_zip, "w", zipfile.ZIP_DEFLATED) as zf_out:
                    # Copy all files except manifest.json
                    for item in zf_in.namelist():
                        if item != "manifest.json":
                            zf_out.writestr(item, zf_in.read(item))
                    # Write signed manifest
                    zf_out.writestr("manifest.json", signed_json)
            
            # Replace original with updated ZIP
            temp_zip.replace(out)
            signed = True
        except Exception as e:
            console.print(f"[yellow][WARN]  Signing failed:[/yellow] {e}")

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


