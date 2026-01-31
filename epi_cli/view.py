"""
EPI CLI View - Open .epi file in browser viewer.

Extracts the embedded viewer.html and opens it in the default browser.
No code execution, all data is pre-rendered JSON.
"""

import tempfile
import webbrowser
import zipfile
from pathlib import Path

import typer
from rich.console import Console

console = Console()

app = typer.Typer(name="view", help="View .epi file in browser")

DEFAULT_DIR = Path("epi-recordings")


def _resolve_epi_file(name_or_path: str) -> Path:
    """
    Resolve a name or path to an .epi file.
    
    Tries in order:
    1. Exact path if it exists
    2. Add .epi extension if missing
    3. Look in ./epi-recordings/ directory
    
    Args:
        name_or_path: User input (name or path)
        
    Returns:
        Resolved Path object
        
    Raises:
        FileNotFoundError if file cannot be found
    """
    path = Path(name_or_path)
    
    # Try exact path
    if path.exists() and path.is_file():
        return path
    
    # Try adding .epi extension
    if not str(path).endswith(".epi"):
        with_ext = path.with_suffix(".epi")
        if with_ext.exists():
            return with_ext
    
    # Try in default directory
    in_default = DEFAULT_DIR / path.name
    if in_default.exists():
        return in_default
    
    # Try in default directory with .epi extension
    in_default_with_ext = DEFAULT_DIR / f"{path.stem}.epi"
    if in_default_with_ext.exists():
        return in_default_with_ext
    
    # Not found
    raise FileNotFoundError(f"Recording not found: {name_or_path}")


@app.callback(invoke_without_command=True)
def view(
    ctx: typer.Context,
    epi_file: str = typer.Argument(..., help="Path or name of .epi file to view"),
):
    """
    Open .epi file in browser viewer.
    
    Accepts file path, name, or base name. Automatically resolves:
    - foo -> ./epi-recordings/foo.epi
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
        console.print(f"[red][FAIL] Error:[/red] {e}")
        console.print(f"[dim]Tip: Run 'epi ls' to see available recordings[/dim]")
        raise typer.Exit(1)
    
    # Validate it's a ZIP file
    if not zipfile.is_zipfile(resolved_path):
        console.print(f"[red][FAIL] Error:[/red] Not a valid .epi file: {resolved_path}")
        raise typer.Exit(1)
    
    try:
        # Create temp directory for viewer
        temp_dir = Path(tempfile.mkdtemp(prefix="epi_view_"))
        viewer_path = temp_dir / "viewer.html"
        
        # Extract viewer.html
        with zipfile.ZipFile(resolved_path, "r") as zf:
            if "viewer.html" not in zf.namelist():
                console.print("[red][FAIL] Error:[/red] No viewer found in .epi file")
                console.print("[dim]This file may have been created with an older version of EPI[/dim]")
                raise typer.Exit(1)
            
            # Extract viewer
            zf.extract("viewer.html", temp_dir)
        
        # Open in browser
        file_url = viewer_path.as_uri()
        console.print(f"[dim]Opening viewer:[/dim] {file_url}")
        
        success = webbrowser.open(file_url)
        
        if success:
            console.print("[green][OK][/green] Viewer opened in browser")
        else:
            console.print("[yellow][WARN]  Could not open browser automatically[/yellow]")
            console.print(f"[dim]Open manually:[/dim] {file_url}")
        
    except KeyboardInterrupt:
        console.print("\n[yellow]Cancelled[/yellow]")
        raise typer.Exit(130)
    except Exception as e:
        console.print(f"[red][FAIL] Error:[/red] {e}")
        raise typer.Exit(1)


