"""
EPI CLI View - Open .epi file in browser viewer.

Extracts the artifact contents, regenerates viewer.html, and opens it in the
default browser. No code execution, all data is pre-rendered JSON.

Features (v2.8.0):
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
import json
import re
import base64
from pathlib import Path

import typer
from rich.console import Console

from epi_core.container import EPIContainer, _html_safe_json_dumps
from epi_core.workspace import RecordingWorkspaceError, create_recording_workspace
from epi_core.trust import create_verification_report, verify_embedded_manifest_signature
from epi_core.viewer_assets import load_viewer_assets

console = Console()

DEFAULT_DIR = Path("epi-recordings")
_MAX_INLINE_ARCHIVE_BYTES = 4 * 1024 * 1024


def _print_share_hint() -> None:
    """Show follow-up paths after opening or extracting a case file."""
    console.print("")
    console.print("[bold]Share / review this case file:[/bold]")
    console.print("  [cyan]epi share <file.epi>[/cyan]       hosted link that opens in any browser")
    console.print("  [cyan]https://epilabs.org/verify[/cyan]  browser trust check, no install required")
    console.print("  [cyan]epi connect open[/cyan]           local team review workspace")


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
    try:
        return create_recording_workspace("epi_view_")
    except RecordingWorkspaceError:
        candidates = [
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

def _cleanup_after_delay(temp_dir: Path, delay_seconds: float = 30.0) -> None:
    """
    Remove a temp directory after a delay (gives browser time to load).

    Uses a non-daemon thread so the process stays alive long enough for the
    browser to fully load the HTML file before cleanup, even when launched
    from Windows Explorer via double-click (where the process would otherwise
    exit immediately after opening the browser).
    """
    def _do_cleanup():
        time.sleep(delay_seconds)
        shutil.rmtree(temp_dir, ignore_errors=True)

    cleanup_thread = threading.Thread(target=_do_cleanup, daemon=False)
    cleanup_thread.start()


def _build_viewer_context(epi_path: Path) -> dict:
    """Build verification context for the extracted viewer."""
    manifest = EPIContainer.read_manifest(epi_path)
    integrity_ok, mismatches = EPIContainer.verify_integrity(epi_path)

    signature_valid, signer_name, _sig_message = verify_embedded_manifest_signature(manifest)

    report = create_verification_report(
        integrity_ok=integrity_ok,
        signature_valid=signature_valid,
        signer_name=signer_name,
        mismatches=mismatches,
        manifest=manifest,
    )
    return report


def _inject_viewer_context(viewer_path: Path, context: dict) -> None:
    """Inject verification context into extracted viewer.html."""
    html = viewer_path.read_text(encoding="utf-8")
    context_json = _html_safe_json_dumps(context, indent=2)
    script_tag = f'<script id="epi-view-context" type="application/json">{context_json}</script>'

    existing_pattern = r'<script id="epi-view-context" type="application/json">.*?</script>'
    if re.search(existing_pattern, html, flags=re.DOTALL):
        html = re.sub(existing_pattern, script_tag, html, flags=re.DOTALL)
    elif "</head>" in html:
        html = html.replace("</head>", f"{script_tag}\n</head>")
    else:
        html = f"{script_tag}\n{html}"
    viewer_path.write_text(html, encoding="utf-8")


def _read_json_if_exists(path: Path) -> dict | list | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _read_text_if_exists(path: Path) -> str | None:
    if not path.exists():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return None


def _read_steps_if_exists(path: Path) -> list[dict]:
    if not path.exists():
        return []
    steps: list[dict] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                steps.append(json.loads(line))
            except Exception:
                continue
    except Exception:
        return []
    return steps


def _build_preloaded_case_payload(extracted_dir: Path, resolved_path: Path) -> dict:
    manifest = EPIContainer.read_manifest(resolved_path)
    integrity_ok, mismatches = EPIContainer.verify_integrity(resolved_path)
    signature_valid, signer_name, signature_message = verify_embedded_manifest_signature(manifest)

    archive_base64 = None
    try:
        if resolved_path.stat().st_size <= _MAX_INLINE_ARCHIVE_BYTES:
            archive_base64 = base64.b64encode(resolved_path.read_bytes()).decode("ascii")
    except Exception:
        archive_base64 = None

    return {
        "source_name": resolved_path.name,
        "file_size": resolved_path.stat().st_size if resolved_path.exists() else 0,
        "archive_base64": archive_base64,
        "manifest": manifest.model_dump(mode="json"),
        "steps": _read_steps_if_exists(extracted_dir / "steps.jsonl"),
        "analysis": _read_json_if_exists(extracted_dir / "analysis.json"),
        "policy": _read_json_if_exists(extracted_dir / "policy.json"),
        "policy_evaluation": _read_json_if_exists(extracted_dir / "policy_evaluation.json"),
        "review": _read_json_if_exists(extracted_dir / "review.json"),
        "environment": _read_json_if_exists(extracted_dir / "environment.json")
        or _read_json_if_exists(extracted_dir / "env.json"),
        "stdout": _read_text_if_exists(extracted_dir / "stdout.log"),
        "stderr": _read_text_if_exists(extracted_dir / "stderr.log"),
        "integrity": {
            "ok": integrity_ok,
            "checked": len(manifest.file_manifest),
            "mismatches": sorted(mismatches.keys()),
        },
        "signature": {
            "valid": signature_valid is True,
            "reason": signature_message,
            "signer": signer_name,
        },
    }


def _create_decision_ops_viewer(extracted_dir: Path, resolved_path: Path) -> str:
    assets = load_viewer_assets()
    template_html = assets["template_html"]
    app_js = assets["app_js"]
    css_styles = assets["css_styles"]
    crypto_js = assets["crypto_js"]

    if not template_html or app_js is None or css_styles is None or crypto_js is None:
        raise FileNotFoundError("Decision viewer assets are not available in this install.")

    payload = {"cases": [_build_preloaded_case_payload(extracted_dir, resolved_path)]}
    payload_json = _html_safe_json_dumps(payload, indent=2)
    preload_tag = f'<script id="epi-preloaded-cases" type="application/json">{payload_json}</script>'

    html = template_html.replace(
        '<link rel="stylesheet" href="styles.css">',
        f"<style>{css_styles}</style>",
    )
    html = html.replace(
        '<script src="https://cdn.jsdelivr.net/npm/jszip@3.10.1/dist/jszip.min.js"></script>\n<script src="../epi_viewer_static/crypto.js"></script>\n<script src="app.js"></script>',
        f'{preload_tag}\n<script src="https://cdn.jsdelivr.net/npm/jszip@3.10.1/dist/jszip.min.js"></script>\n<script>{crypto_js}</script>\n<script>{app_js}</script>',
    )
    return html


def _refresh_viewer_html(extracted_dir: Path, resolved_path: Path) -> Path:
    """
    Regenerate viewer.html from the extracted artifact contents.

    This keeps the viewer aligned with append-only files like review.json that
    may have been added after the original viewer was baked into the artifact.
    """
    viewer_path = extracted_dir / "viewer.html"
    try:
        viewer_html = _create_decision_ops_viewer(extracted_dir, resolved_path)
        viewer_path.write_text(viewer_html, encoding="utf-8")
        return viewer_path
    except FileNotFoundError:
        if viewer_path.exists():
            return viewer_path
        raise


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
        viewer = _refresh_viewer_html(dest, resolved_path)
        if viewer.exists():
            _inject_viewer_context(viewer, _build_viewer_context(resolved_path))
        console.print(f"[green][OK][/green] Extracted to: {dest}")
        console.print(f"   Open in browser: {dest / 'viewer.html'}")
        _print_share_hint()
        raise typer.Exit(0)

    # Create temp dir
    temp_dir = _make_temp_dir()
    if temp_dir is None:
        console.print("[red][X] Could not create temp directory.[/red]")
        console.print("[dim]   Try: epi view --extract ./output/ <file>[/dim]")
        raise typer.Exit(1)

    try:
        viewer_context = _build_viewer_context(resolved_path)

        with zipfile.ZipFile(resolved_path, "r") as zf:
            zf.extractall(temp_dir)

        viewer = _refresh_viewer_html(temp_dir, resolved_path)
        _inject_viewer_context(viewer, viewer_context)
        _open_in_browser(viewer)
        console.print(f"[green][OK][/green] Opened: {resolved_path.name}")
        _print_share_hint()

        # Schedule cleanup after browser loads
        _cleanup_after_delay(temp_dir, 8)

    except typer.Exit:
        raise  # Re-raise typer exits cleanly
    except KeyboardInterrupt:
        console.print("\n[yellow]Cancelled[/yellow]")
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise typer.Exit(130)
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
