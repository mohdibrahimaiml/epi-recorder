"""
EPI CLI Shared Utilities - Common helpers used by record.py and run.py.

Centralised here to avoid duplication and ensure bug fixes apply everywhere.
"""

import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import List

import typer
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from epi_core.workspace import create_recording_workspace


console = Console()


def require_extra(
    extra_name: str,
    module_name: str | None = None,
    command: str | None = None,
) -> None:
    """
    Verify that an optional dependency extra is installed.

    If the import fails, print a friendly message explaining how to install the
    required extra and exit the CLI cleanly.
    """
    module = module_name or extra_name
    try:
        __import__(module)
    except ImportError as exc:
        cmd = command or "This command"
        message = Text.assemble(
            (cmd, "bold red"),
            " requires the ",
            (extra_name, "cyan"),
            " extra.\n\nInstall it with:\n",
            ("pip install epi-recorder[", "bold"),
            (extra_name, "bold cyan"),
            ("]", "bold"),
        )
        console.print(
            Panel.fit(
                message,
                title="Missing optional dependency",
                border_style="red",
            )
        )
        raise typer.Exit(1) from exc


def require_service(url: str, timeout: float = 5.0, label: str | None = None) -> None:
    """
    Check that a remote service is reachable.

    Prints a clear error and exits if the service cannot be reached. HTTP error
    responses (4xx/5xx) are treated as reachable; only network-level failures
    trigger an exit, because the CLI command will handle the HTTP error itself.
    """
    display = label or url
    try:
        req = urllib.request.Request(url, method="HEAD")
        urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError:
        # Service is reachable; let the command handle the HTTP status.
        return
    except urllib.error.URLError as exc:
        console.print(f"[red][FAIL][/red] Cannot reach {display} ({url})")
        console.print(
            "[dim]If you are offline or running a self-hosted service, "
            "set the appropriate EPI_*_URL environment variable.[/dim]"
        )
        raise typer.Exit(1) from exc


def ensure_python_command(cmd: List[str]) -> List[str]:
    """
    Prepend the current Python executable if the first arg is a .py file.
    If the user already typed 'python script.py', leave it as-is.
    """
    if not cmd:
        return cmd
    if cmd[0].lower().endswith(".py"):
        return [sys.executable] + cmd
    return cmd


def build_env_for_child(steps_dir: Path, enable_redaction: bool) -> dict:
    """
    Build the environment for the child recording process.

    Injects EPI_RECORD, EPI_STEPS_DIR, and EPI_REDACT, then prepends a
    temporary bootstrap directory containing sitecustomize.py so that
    epi_recorder patches LLM libraries before the user script runs.
    """
    env = os.environ.copy()

    env["EPI_RECORD"] = "1"
    env["EPI_STEPS_DIR"] = str(steps_dir)
    env["EPI_REDACT"] = "1" if enable_redaction else "0"
    env["EPI_CAPTURE_PRINTS"] = "1"

    # Force UTF-8 I/O in the child process.
    # On Windows the default is cp1252 which corrupts any non-ASCII output
    # (e.g. LLM responses containing Unicode) written to stdout/stderr logs.
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"  # PEP 540 — also covers open() calls in child

    # Temporary sitecustomize.py bootstrap
    bootstrap_dir = create_recording_workspace("epi_bootstrap_")
    (bootstrap_dir / "sitecustomize.py").write_text(
        "from epi_recorder.bootstrap import initialize_recording\n",
        encoding="utf-8",
    )

    project_root = Path(__file__).resolve().parent.parent
    existing = env.get("PYTHONPATH", "")
    sep = os.pathsep
    env["PYTHONPATH"] = (
        f"{bootstrap_dir}{sep}{project_root}{sep + existing if existing else ''}"
    )

    return env
