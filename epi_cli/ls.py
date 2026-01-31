"""
EPI CLI Ls - List recordings in ./epi-recordings/ directory.

Usage:
  epi ls
"""

import json
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Dict, Any

import typer
from rich.console import Console
from rich.table import Table

from epi_core.container import EPIContainer

console = Console()

app = typer.Typer(name="ls", help="List local recordings (./epi-recordings/)")

DEFAULT_DIR = Path("epi-recordings")


def _format_metrics(metrics: Dict[str, Any]) -> str:
    """Format metrics dictionary as a compact string."""
    if not metrics:
        return ""
    
    formatted = []
    for key, value in metrics.items():
        if isinstance(value, float):
            # Format floats to 2 decimal places
            formatted.append(f"{key}={value:.2f}")
        else:
            formatted.append(f"{key}={value}")
    
    return ", ".join(formatted)


def _get_recording_info(epi_file: Path) -> dict:
    """
    Extract basic info from a recording.
    
    Returns:
        Dictionary with recording metadata
    """
    try:
        # Read manifest
        manifest = EPIContainer.read_manifest(epi_file)
        
        # Get file stats
        stats = epi_file.stat()
        size_mb = stats.st_size / (1024 * 1024)
        modified = datetime.fromtimestamp(stats.st_mtime)
        
        # Extract CLI command if available
        cli_command = getattr(manifest, 'cli_command', None)
        
        # Extract originating script from cli_command
        script = "Unknown"
        if cli_command:
            parts = cli_command.split()
            for i, part in enumerate(parts):
                if part.endswith('.py'):
                    script = Path(part).name
                    break
        
        # Check signature
        signed = "Yes" if manifest.signature else "No"
        
        # Quick integrity check
        integrity_ok, _ = EPIContainer.verify_integrity(epi_file)
        status = "[OK]" if integrity_ok else "[FAIL]"
        
        # Extract new metadata fields
        goal = getattr(manifest, 'goal', None)
        metrics = getattr(manifest, 'metrics', None)
        tags = getattr(manifest, 'tags', None)
        
        return {
            "name": epi_file.name,
            "script": script,
            "size_mb": f"{size_mb:.2f}",
            "modified": modified.strftime("%Y-%m-%d %H:%M:%S"),
            "signed": signed,
            "status": status,
            "goal": goal or "",
            "metrics_summary": _format_metrics(metrics) if metrics else "",
            "tags_summary": ", ".join(tags) if tags else ""
        }
    except Exception as e:
        return {
            "name": epi_file.name,
            "script": "Error",
            "size_mb": "?",
            "modified": "?",
            "signed": "?",
            "status": f"[ERR] {str(e)[:20]}",
            "goal": "",
            "metrics_summary": "",
            "tags_summary": ""
        }


@app.callback(invoke_without_command=True)
def ls(
    all_dirs: bool = typer.Option(False, "--all", "-a", help="Search current directory too"),
):
    """
    List local recordings in ./epi-recordings/ directory.
    
    Shows created/verified status and originating script if available.
    """
    # Find recordings
    recordings = []
    
    # Check default directory
    if DEFAULT_DIR.exists():
        recordings.extend(DEFAULT_DIR.glob("*.epi"))
    
    # Optionally check current directory
    if all_dirs:
        recordings.extend(Path(".").glob("*.epi"))
    
    # Remove duplicates
    recordings = list(set(recordings))
    recordings.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    
    if not recordings:
        console.print("[yellow]No recordings found[/yellow]")
        if not DEFAULT_DIR.exists():
            console.print(f"[dim]Directory {DEFAULT_DIR} does not exist yet[/dim]")
        console.print("[dim]Tip: Run 'epi run script.py' to create your first recording[/dim]")
        return
    
    # Build table
    table = Table(title=f"EPI Recordings ({len(recordings)} found)")
    table.add_column("Name", style="cyan", no_wrap=True)
    table.add_column("Modified", style="dim")
    table.add_column("Goal", style="blue", no_wrap=False)
    table.add_column("Metrics", style="purple", no_wrap=False)
    table.add_column("Tags", style="green", no_wrap=False)
    
    for recording in recordings:
        info = _get_recording_info(recording)
        table.add_row(
            info["name"],
            info["modified"],
            info["goal"][:50] + "..." if len(info["goal"]) > 50 else info["goal"],
            info["metrics_summary"],
            info["tags_summary"]
        )
    
    console.print()
    console.print(table)
    console.print()
    console.print(f"[dim]Tip: View a recording with 'epi view <name>'[/dim]")


