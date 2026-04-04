"""
EPI Global Install — System-wide automatic recording.

Provides commands to install and uninstall EPI auto-recording
at the Python environment level via sitecustomize.py.

When installed:
  - Every Python process automatically patches LLM libraries
  - All LLM calls are recorded when EPI_RECORD=1 is set
  - Recordings go to ~/.epi/recordings/ by default

Commands:
  epi install --global     Install EPI auto-recording
  epi uninstall --global   Remove EPI auto-recording

Safety:
  - Only modifies the current Python environment's sitecustomize.py
  - Adds a clearly marked block that can be cleanly removed
  - Respects EPI_AUTO_RECORD=0 to disable at runtime
  - epi uninstall --global cleanly reverses everything
"""

import os
import sys
import site
import textwrap
from pathlib import Path
from typing import Optional, Tuple

import typer
from rich.console import Console

console = Console()

# The block we inject into sitecustomize.py
EPI_BLOCK_START = "# === EPI RECORDER AUTO-PATCH START ==="
EPI_BLOCK_END = "# === EPI RECORDER AUTO-PATCH END ==="

EPI_SITECUSTOMIZE_CODE = textwrap.dedent(f"""\
{EPI_BLOCK_START}
# Auto-installed by: epi install --global
# Remove with:       epi uninstall --global
# Disable at runtime: set EPI_AUTO_RECORD=0
import os as _epi_os
if _epi_os.environ.get("EPI_AUTO_RECORD", "1") != "0":
    try:
        from epi_recorder.bootstrap import initialize_recording as _epi_init
        # Only activate if EPI_RECORD=1 is set
        # (bootstrap.py checks this internally)
        _epi_init()
    except ImportError:
        pass  # epi-recorder not installed in this env
    except Exception:
        pass  # Never break user's Python
{EPI_BLOCK_END}
""")


def _get_sitecustomize_path() -> Path:
    """Get the path to sitecustomize.py in the current environment."""
    # Prefer virtual environment if active
    if hasattr(sys, "real_prefix") or (hasattr(sys, "base_prefix") and sys.base_prefix != sys.prefix):
        # We're in a virtualenv
        site_packages = None
        for p in sys.path:
            if "site-packages" in p and os.path.isdir(p):
                site_packages = Path(p)
                break
        if site_packages:
            return site_packages / "sitecustomize.py"

    # Fallback: use site.ENABLE_USER_SITE path
    user_site = site.getusersitepackages()
    if user_site:
        return Path(user_site) / "sitecustomize.py"

    # Last resort: use first site-packages in sys.path
    for p in sys.path:
        if "site-packages" in p:
            return Path(p) / "sitecustomize.py"

    raise RuntimeError("Could not determine sitecustomize.py location")


def _has_epi_block(content: str) -> bool:
    """Check if EPI block is already in sitecustomize content."""
    return EPI_BLOCK_START in content


def _remove_epi_block(content: str) -> str:
    """Remove EPI block from sitecustomize content."""
    lines = content.split("\n")
    result = []
    inside_block = False

    for line in lines:
        if EPI_BLOCK_START in line:
            inside_block = True
            continue
        if EPI_BLOCK_END in line:
            inside_block = False
            continue
        if not inside_block:
            result.append(line)

    # Clean up extra blank lines at the end
    while result and result[-1].strip() == "":
        result.pop()

    return "\n".join(result) + "\n" if result else ""


def _ensure_recordings_dir() -> Path:
    """Ensure the default recordings directory exists."""
    recordings_dir = Path.home() / ".epi" / "recordings"
    recordings_dir.mkdir(parents=True, exist_ok=True)
    return recordings_dir


def install_global() -> Tuple[bool, str]:
    """
    Install EPI auto-recording into sitecustomize.py.

    Returns:
        Tuple of (success, message)
    """
    try:
        sc_path = _get_sitecustomize_path()
    except RuntimeError as e:
        return False, str(e)

    # Read existing content
    existing_content = ""
    if sc_path.exists():
        existing_content = sc_path.read_text(encoding="utf-8")

        if _has_epi_block(existing_content):
            return True, f"EPI auto-recording is already installed at {sc_path}"

    # Ensure parent directory exists
    sc_path.parent.mkdir(parents=True, exist_ok=True)

    # Append EPI block
    new_content = existing_content.rstrip() + "\n\n" + EPI_SITECUSTOMIZE_CODE
    sc_path.write_text(new_content, encoding="utf-8")

    # Ensure recordings directory exists
    rec_dir = _ensure_recordings_dir()

    return True, f"Installed at {sc_path}"


def uninstall_global() -> Tuple[bool, str]:
    """
    Remove EPI auto-recording from sitecustomize.py.

    Returns:
        Tuple of (success, message)
    """
    try:
        sc_path = _get_sitecustomize_path()
    except RuntimeError as e:
        return False, str(e)

    if not sc_path.exists():
        return True, "No sitecustomize.py found — nothing to remove"

    content = sc_path.read_text(encoding="utf-8")

    if not _has_epi_block(content):
        return True, "EPI auto-recording was not installed"

    # Remove EPI block
    cleaned = _remove_epi_block(content)

    if cleaned.strip():
        sc_path.write_text(cleaned, encoding="utf-8")
    else:
        # File would be empty — remove it
        sc_path.unlink()

    return True, f"Removed from {sc_path}"


# ---- CLI Commands ----

app = typer.Typer(
    name="install",
    help="Install/uninstall EPI auto-recording globally",
)


@app.command(name="install")
def cli_install(
    show_path: bool = typer.Option(False, "--show-path", help="Show sitecustomize.py path and exit"),
):
    """
    Install EPI auto-recording for all Python processes in this environment.

    After installation:
      - Set EPI_RECORD=1 to enable recording in any Python process
      - Set EPI_STEPS_DIR to specify where steps are written
      - Set EPI_AUTO_RECORD=0 to temporarily disable

    Undo with: epi uninstall --global
    """
    if show_path:
        try:
            path = _get_sitecustomize_path()
            console.print(f"[cyan]{path}[/cyan]")
        except RuntimeError as e:
            console.print(f"[red]Error: {e}[/red]")
            raise typer.Exit(1)
        return

    console.print("\n[bold cyan]EPI Global Install[/bold cyan]\n")
    console.print("[dim]Installing auto-recording into this Python environment...[/dim]\n")

    success, message = install_global()

    if success:
        console.print(f"[bold green]\\[OK] {message}[/bold green]\n")
        console.print("[bold]How to use:[/bold]")
        console.print("  1. Set [cyan]EPI_RECORD=1[/cyan] environment variable")
        console.print("  2. Set [cyan]EPI_STEPS_DIR=/path/to/steps[/cyan] for output")
        console.print("  3. Run any Python script — LLM calls are auto-recorded\n")
        console.print("[bold]To disable:[/bold]")
        console.print("  • Temporarily: set [cyan]EPI_AUTO_RECORD=0[/cyan]")
        console.print("  • Permanently: run [cyan]epi uninstall --global[/cyan]\n")
    else:
        console.print(f"[bold red]\\[ERROR] Installation failed: {message}[/bold red]")
        raise typer.Exit(1)


@app.command(name="uninstall")
def cli_uninstall():
    """
    Remove EPI auto-recording from this Python environment.

    Cleanly removes the EPI block from sitecustomize.py.
    Does not affect existing recordings or keys.
    """
    console.print("\n[bold cyan]EPI Global Uninstall[/bold cyan]\n")

    success, message = uninstall_global()

    if success:
        console.print(f"[bold green]\\[OK] {message}[/bold green]\n")
    else:
        console.print(f"[bold red]\\[ERROR] Uninstall failed: {message}[/bold red]")
        raise typer.Exit(1)
