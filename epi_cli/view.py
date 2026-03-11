"""
EPI CLI View - Open .epi file in browser viewer.

Extracts the embedded viewer.html and opens it in the default browser.
No code execution, all data is pre-rendered JSON.

Features (v2.7.0):
  - Unicode-safe path handling via pathlib
  - Stem resolution picks most recent match
  - Temp directory auto-cleanup after browser loads
  - Clear error messages for corrupt/missing files
"""

import shutil
import tempfile
import threading
import time
import webbrowser
import zipfile
from pathlib import Path

import typer
from rich.console import Console

console = Console()

DEFAULT_DIR = Path("epi-recordings")


def _resolve_epi_file(name_or_path: str) -> Path:
    """
    Resolve a name or path to an .epi file.

    Resolution order:
    1. Exact path if it exists
    2. Add .epi extension if missing
    3. Look in ./epi-recordings/ directory by exact name
    4. Glob ./epi-recordings/ for stem matches → pick most recent by mtime

    Args:
        name_or_path: User input (name, stem, or full path)

    Returns:
        Resolved Path object

    Raises:
        FileNotFoundError if file cannot be found
    """
    path = Path(name_or_path)

    # 1. Exact path
    if path.exists() and path.is_file():
        return path

    # 2. Try adding .epi extension
    if not str(path).endswith(".epi"):
        with_ext = path.with_suffix(".epi")
        if with_ext.exists():
            return with_ext

    # 3. Try exact name in default directory
    in_default = DEFAULT_DIR / path.name
    if in_default.exists():
        return in_default

    in_default_with_ext = DEFAULT_DIR / f"{path.stem}.epi"
    if in_default_with_ext.exists():
        return in_default_with_ext

    # 4. Glob for stem matches → pick most recent by mtime
    if DEFAULT_DIR.exists():
        stem = path.stem if path.suffix == ".epi" else path.name
        candidates = sorted(
            DEFAULT_DIR.glob(f"{stem}*.epi"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if candidates:
            return candidates[0]

    # Not found
    raise FileNotFoundError(f"Recording not found: {name_or_path}")


def _make_temp_dir() -> Path | None:
    """Try multiple locations for temp dir creation."""
    candidates = [
        lambda: Path(tempfile.mkdtemp(prefix="epi_view_")),
        lambda: Path(tempfile.gettempdir()) / f"epi_view_{id(object())}",
        lambda: Path.cwd() / f".epi_temp_{id(object())}",
    ]
    for make in candidates:
        try:
            p = make()
            p.mkdir(parents=True, exist_ok=True)
            return p
        except Exception:
            continue
    return None

def _open_in_browser(viewer_path: Path):
    """Cross-platform browser open with fallbacks."""
    import sys
    uri = viewer_path.as_uri()
    opened = False

    if sys.platform == "win32":
        try:
            import os
            os.startfile(str(viewer_path))
            opened = True
        except Exception:
            pass

    if not opened:
        try:
            webbrowser.open(uri)
            opened = True
        except Exception:
            pass

    if not opened:
        print(f"\n📂 Could not open browser automatically.")
        print(f"   Open this file manually in your browser:")
        print(f"   {viewer_path}")

def _cleanup_after_delay(temp_dir: Path, delay_seconds: float = 8.0) -> None:
    """
    Remove a temp directory after a delay (gives browser time to load).
    
    Runs in a daemon thread so it doesn't block CLI exit.
    """
    def _do_cleanup():
        time.sleep(delay_seconds)
        shutil.rmtree(temp_dir, ignore_errors=True)

    cleanup_thread = threading.Thread(target=_do_cleanup, daemon=True)
    cleanup_thread.start()


def view(
    ctx: typer.Context,
    epi_file: str = typer.Argument(..., help="Path or name of .epi file to view"),
    extract: str = typer.Option(None, "--extract", help="Destination directory to extract the viewer.html and assets instead of opening browser"),
):
    """
    Open .epi file in browser viewer.

    Accepts file path, name, or base name. Automatically resolves:
    - foo -> ./epi-recordings/foo.epi (or most recent foo*.epi)
    - foo.epi -> ./epi-recordings/foo.epi
    - /path/to/file.epi -> /path/to/file.epi

    Example:
        epi view my_script_20251121_231501
        epi view my_recording.epi
    """
    # Resolve the file path
    try:
        resolved_path = _resolve_epi_file(epi_file)
    except FileNotFoundError as e:
        console.print(f"[red][X] File not found:[/red] {epi_file}")
        console.print("[dim]   Searched in: ./epi-recordings/[/dim]")
        console.print("[dim]   Try: epi ls   to see available recordings[/dim]")
        raise typer.Exit(1)

    # Validate it's a valid ZIP
    if not zipfile.is_zipfile(resolved_path):
        console.print(f"[red][X] Not a valid .epi file (failed ZIP check):[/red] {resolved_path.name}")
        console.print("[dim]   The file may be corrupt or incomplete.[/dim]")
        raise typer.Exit(1)

    if extract:
        dest = Path(extract)
        dest.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(resolved_path, "r") as zf:
            zf.extractall(dest)
        console.print(f"[green][OK][/green] Extracted to: {dest}")
        console.print(f"   Open in browser: {dest / 'viewer.html'}")
        raise typer.Exit(0)

    # Create temp dir
    temp_dir = _make_temp_dir()
    if temp_dir is None:
        console.print("[red][X] Could not create temp directory.[/red]")
        console.print("[dim]   Try: epi view --extract ./output/ <file>[/dim]")
        raise typer.Exit(1)

    try:
        with zipfile.ZipFile(resolved_path, "r") as zf:
            if "viewer.html" not in zf.namelist():
                console.print(f"[red][X] This .epi file has no viewer.html.[/red]")
                console.print(f"[dim]   It may be an older format. Try: epi verify {resolved_path}[/dim]")
                # Fallback: just print the manifest
                if "manifest.json" in zf.namelist():
                    console.print("\n[i] [bold]Manifest contents:[/bold]")
                    console.print(zf.read("manifest.json").decode("utf-8", errors="replace"))
                raise typer.Exit(1)
            
            zf.extract("viewer.html", temp_dir)

        viewer = temp_dir / "viewer.html"
        _open_in_browser(viewer)
        console.print(f"[green][OK][/green] Opened: {resolved_path.name}")

        # Schedule cleanup after browser loads
        _cleanup_after_delay(temp_dir, 8)

    except zipfile.BadZipFile:
        console.print(f"[red][X] Corrupt .epi file:[/red] {resolved_path.name}")
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise typer.Exit(1)
    except PermissionError as e:
        console.print(f"[red][X] Permission denied:[/red] {e}")
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red][X] Unexpected error:[/red] {e}")
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise typer.Exit(1)

    except typer.Exit:
        raise  # Re-raise typer exits

    except KeyboardInterrupt:
        console.print("\n[yellow]Cancelled[/yellow]")
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise typer.Exit(130)

    except Exception as e:
        console.print(f"[red][FAIL] Error opening file:[/red] {e}")
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise typer.Exit(1)