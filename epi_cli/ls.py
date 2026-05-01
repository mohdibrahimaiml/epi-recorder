"""
EPI CLI Ls - List recordings in ./epi-recordings/ directory.

Usage:
  epi ls
  epi ls --sort size
  epi ls --tag ml
  epi ls --signed
  epi ls --failed
"""

from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

import typer
from rich.console import Console
from rich.table import Table

from epi_core.container import EPIContainer
from epi_core.trust import create_verification_report, verify_embedded_manifest_signature

console = Console()

app = typer.Typer(name="ls", help="List local recordings in ./epi-recordings/ (use --all to include the current directory).")

DEFAULT_DIR = Path("epi-recordings")


def _format_metrics(metrics: Dict[str, Any]) -> str:
    """Format metrics dictionary as a compact string."""
    if not metrics:
        return ""

    formatted = []
    for key, value in metrics.items():
        if isinstance(value, float):
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
        manifest = EPIContainer.read_manifest(epi_file)

        stats = epi_file.stat()
        size_bytes = stats.st_size
        size_mb = size_bytes / (1024 * 1024)
        modified = datetime.fromtimestamp(stats.st_mtime)

        cli_command = getattr(manifest, "cli_command", None)

        script = "Unknown"
        if cli_command:
            parts = cli_command.split()
            for part in parts:
                if part.endswith(".py"):
                    script = Path(part).name
                    break

        integrity_ok, _ = EPIContainer.verify_integrity(epi_file)
        signature_valid, signer_name, _sig_message = verify_embedded_manifest_signature(manifest)
        report = create_verification_report(
            integrity_ok=integrity_ok,
            signature_valid=signature_valid,
            signer_name=signer_name,
            mismatches={},
            manifest=manifest,
        )
        signed = signature_valid is True

        goal = getattr(manifest, "goal", None)
        metrics = getattr(manifest, "metrics", None)
        tags = getattr(manifest, "tags", None)

        return {
            "name": epi_file.name,
            "stem": epi_file.stem,
            "script": script,
            "size_bytes": size_bytes,
            "size_mb": size_mb,
            "size_str": f"{size_mb:.2f} MB" if size_mb >= 0.1 else f"{size_bytes / 1024:.1f} KB",
            "modified": modified,
            "modified_str": modified.strftime("%Y-%m-%d %H:%M"),
            "signed": signed,
            "has_signature": report["has_signature"],
            "signature_valid": signature_valid,
            "integrity_ok": integrity_ok,
            "status": "[green]OK[/green]" if integrity_ok and signature_valid is not False else "[red]FAIL[/red]",
            "goal": goal or "",
            "metrics_summary": _format_metrics(metrics) if metrics else "",
            "tags": tags or [],
            "tags_summary": ", ".join(tags) if tags else "",
        }
    except Exception:
        return {
            "name": epi_file.name,
            "stem": epi_file.stem,
            "script": "Error",
            "size_bytes": 0,
            "size_mb": 0,
            "size_str": "?",
            "modified": datetime.min,
            "modified_str": "?",
            "signed": False,
            "integrity_ok": False,
            "status": f"[red]ERR[/red]",
            "goal": "",
            "metrics_summary": "",
            "tags": [],
            "tags_summary": "",
        }


@app.callback(invoke_without_command=True)
def ls(
    all_dirs: bool = typer.Option(False, "--all", "-a", help="Search current directory too"),
    sort: str = typer.Option("date", "--sort", "-s", help="Sort by: date, name, size"),
    tag: Optional[str] = typer.Option(None, "--tag", "-t", help="Filter by tag"),
    signed: bool = typer.Option(False, "--signed", help="Show only signed recordings"),
    failed: bool = typer.Option(False, "--failed", help="Show only recordings that failed integrity check"),
):
    """
    List local recordings in ./epi-recordings/ by default.

    Filter and sort:
      epi ls --sort size
      epi ls --tag ml
      epi ls --signed
      epi ls --failed
    """
    recordings = []

    if DEFAULT_DIR.exists():
        recordings.extend(DEFAULT_DIR.glob("*.epi"))

    if all_dirs:
        for f in Path(".").glob("*.epi"):
            if f not in recordings:
                recordings.append(f)

    if not recordings:
        console.print("[yellow]No recordings found[/yellow]")
        if not DEFAULT_DIR.exists():
            console.print(f"[dim]Directory {DEFAULT_DIR} does not exist yet[/dim]")
        console.print("[dim]Scope: epi ls shows ./epi-recordings/ by default. Use --all to include the current directory.[/dim]")
        console.print("[dim]Tip: Run an instrumented script with python, or use 'epi record --out demo.epi -- python my_script.py'.[/dim]")
        return

    # Collect info for all recordings
    infos = [_get_recording_info(r) for r in recordings]

    # Apply filters
    if tag:
        infos = [i for i in infos if tag in i["tags"]]
    if signed:
        infos = [i for i in infos if i["signed"]]
    if failed:
        infos = [i for i in infos if not i["integrity_ok"]]

    if not infos:
        console.print("[yellow]No recordings match the given filters.[/yellow]")
        return

    # Sort
    sort = sort.lower()
    if sort == "name":
        infos.sort(key=lambda i: i["name"].lower())
    elif sort == "size":
        infos.sort(key=lambda i: i["size_bytes"], reverse=True)
    else:  # date (default)
        infos.sort(key=lambda i: i["modified"], reverse=True)

    # Build table
    scope = "./epi-recordings/ + current directory" if all_dirs else "./epi-recordings/ only"
    table = Table(title=f"EPI Recordings ({len(infos)} found • {scope})")
    table.add_column("Name", style="cyan", no_wrap=True)
    table.add_column("Modified", style="dim", no_wrap=True)
    table.add_column("Size", style="dim", no_wrap=True, justify="right")
    table.add_column("Status", no_wrap=True)
    table.add_column("Signed", no_wrap=True)
    table.add_column("Goal", style="blue", no_wrap=False, max_width=30)
    table.add_column("Tags", style="green", no_wrap=False)
    table.add_column("Metrics", style="purple", no_wrap=False)

    for info in infos:
        signed_str = "[green]Yes[/green]" if info["signed"] else "[dim]No[/dim]"
        goal_str = info["goal"][:28] + "…" if len(info["goal"]) > 29 else info["goal"]
        table.add_row(
            info["name"],
            info["modified_str"],
            info["size_str"],
            info["status"],
            signed_str,
            goal_str,
            info["tags_summary"],
            info["metrics_summary"],
        )

    console.print()
    console.print(table)
    console.print()
    console.print("[dim]Tip: epi view <name>  •  epi verify <name>  •  epi ls --all[/dim]")
