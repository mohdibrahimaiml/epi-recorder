"""
EPI CLI View - Open .epi file in browser viewer.

Extracts the artifact contents, regenerates viewer.html, and opens it in the
default browser. No code execution, all data is pre-rendered JSON.

Features (v2.8.0):
  - Unicode-safe path handling via pathlib
  - Stem resolution picks most recent match
  - Persistent viewer cache (Docker-volume approach) — no temp-file race condition
  - Clear error messages for corrupt/missing files
"""

import hashlib
import shutil
import tempfile
import threading
import time
import webbrowser
import json
import re
import base64
import subprocess
import sys
import importlib.util
from pathlib import Path

import typer
from rich.console import Console

from epi_core.container import EPIContainer, _html_safe_json_dumps
from epi_core.workspace import RecordingWorkspaceError, create_recording_workspace
from epi_core.trust import create_verification_report, verify_embedded_manifest_signature
from epi_core.viewer_assets import inline_viewer_assets, load_viewer_assets

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


def _get_persistent_viewer_dir(epi_path: Path) -> Path:
    """Return a stable cache directory for this .epi file's viewer.

    Inspired by Docker volumes: content persists until explicitly cleared,
    so the browser always has a valid file:// URL regardless of how long
    it takes to render. The directory is keyed by absolute path + mtime,
    so modifying the .epi file automatically regenerates the viewer on
    next open without any manual cleanup.
    """
    try:
        mtime = int(epi_path.stat().st_mtime)
    except Exception:
        mtime = 0
    cache_key = hashlib.md5(f"{epi_path.absolute()}|{mtime}".encode()).hexdigest()[:10]
    cache_dir = Path.home() / ".epi" / "view-cache" / f"{epi_path.stem}_{cache_key}"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


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


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _find_native_viewer_command(epi_path: Path) -> tuple[list[str], Path] | None:
    """Return a native desktop viewer command when one is available."""
    repo_root = _repo_root()
    viewer_root = repo_root / "epi-viewer"
    file_arg = str(epi_path)

    if sys.platform == "win32":
        packaged = viewer_root / "dist" / "win-unpacked" / "EPI Viewer.exe"
        if packaged.exists():
            return [str(packaged), file_arg], packaged.parent

        dev_electron = viewer_root / "node_modules" / "electron" / "dist" / "electron.exe"
        main_js = viewer_root / "main.js"
        if dev_electron.exists() and main_js.exists():
            return [str(dev_electron), str(main_js), file_arg], viewer_root

    elif sys.platform == "darwin":
        packaged = viewer_root / "dist" / "mac" / "EPI Viewer.app" / "Contents" / "MacOS" / "EPI Viewer"
        if packaged.exists():
            return [str(packaged), file_arg], packaged.parent

        dev_electron = viewer_root / "node_modules" / "electron" / "dist" / "Electron.app" / "Contents" / "MacOS" / "Electron"
        main_js = viewer_root / "main.js"
        if dev_electron.exists() and main_js.exists():
            return [str(dev_electron), str(main_js), file_arg], viewer_root

    else:
        packaged = viewer_root / "dist" / "linux-unpacked" / "epi-viewer"
        if packaged.exists():
            return [str(packaged), file_arg], packaged.parent

        dev_electron = viewer_root / "node_modules" / "electron" / "dist" / "electron"
        main_js = viewer_root / "main.js"
        if dev_electron.exists() and main_js.exists():
            return [str(dev_electron), str(main_js), file_arg], viewer_root

    if importlib.util.find_spec("webview") is not None:
        python_exe = Path(sys.executable)
        viewer_script = repo_root / "epi_viewer.py"
        if viewer_script.exists():
            if sys.platform == "win32":
                pythonw = python_exe.parent / "pythonw.exe"
                launcher = pythonw if pythonw.exists() else python_exe
            else:
                launcher = python_exe
            return [str(launcher), str(viewer_script), file_arg], repo_root

    return None


def _open_native_viewer(epi_path: Path) -> bool:
    """Open `.epi` in a native desktop window when a viewer app is available."""
    launch = _find_native_viewer_command(epi_path)
    if not launch:
        return False

    command, cwd = launch
    popen_kwargs = {
        "cwd": str(cwd),
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "close_fds": True,
    }
    if sys.platform == "win32":
        creationflags = 0
        creationflags |= getattr(subprocess, "DETACHED_PROCESS", 0)
        creationflags |= getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        if creationflags:
            popen_kwargs["creationflags"] = creationflags

    try:
        subprocess.Popen(command, **popen_kwargs)
        return True
    except Exception:
        return False

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
    report["viewer_version"] = getattr(manifest, "viewer_version", None)
    return report


def _inject_viewer_context(viewer_path: Path, context: dict) -> None:
    """Inject verification context into extracted viewer.html."""
    html = viewer_path.read_text(encoding="utf-8")
    context_json = _html_safe_json_dumps(context, indent=2)
    script_tag = f'<script id="epi-view-context" type="application/json">{context_json}</script>'
    placeholder_tag = '<script id="epi-view-context" type="application/json">{}</script>'

    if placeholder_tag in html:
        html = html.replace(placeholder_tag, script_tag, 1)
    else:
        head_close_index = html.find("</head>")
        if head_close_index != -1:
            head_html = html[:head_close_index]
            existing_pattern = r'<script id="epi-view-context" type="application/json">[\s\S]*?</script>'
            if re.search(existing_pattern, head_html, flags=re.DOTALL):
                head_html = re.sub(existing_pattern, script_tag, head_html, count=1, flags=re.DOTALL)
                html = f"{head_html}{html[head_close_index:]}"
            else:
                html = html.replace("</head>", f"{script_tag}\n</head>", 1)
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

    _steps = _read_steps_if_exists(extracted_dir / "steps.jsonl")
    _session_start = next(
        (s for s in _steps if isinstance(s, dict) and s.get("kind") == "session.start"), None
    )
    _workflow_name = (_session_start or {}).get("content", {}).get("workflow_name") or getattr(manifest, "workflow_name", None)
    _source_name = _workflow_name or resolved_path.name

    return {
        "source_name": _source_name,
        "file_size": resolved_path.stat().st_size if resolved_path.exists() else 0,
        "archive_base64": archive_base64,
        "manifest": manifest.model_dump(mode="json"),
        "steps": _steps,
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
    jszip_js = assets["jszip_js"]
    app_js = assets["app_js"]
    css_styles = assets["css_styles"]
    crypto_js = assets["crypto_js"]

    if not template_html or jszip_js is None or app_js is None or css_styles is None or crypto_js is None:
        raise FileNotFoundError("Decision viewer assets are not available in this install.")

    payload = {
        "cases": [_build_preloaded_case_payload(extracted_dir, resolved_path)],
        "ui": {
            "view": "case",
            "embeddedArtifactMode": True,
        },
    }
    payload_json = _html_safe_json_dumps(payload, indent=2)
    preload_tag = f'<script id="epi-preloaded-cases" type="application/json">{payload_json}</script>'

    html = inline_viewer_assets(
        template_html,
        css_styles=css_styles,
        jszip_js=jszip_js,
        crypto_js=crypto_js,
        app_js=app_js,
        prepend_html=preload_tag,
    )

    from epi_core._version import get_version

    current_version_marker = f"v{get_version()}"
    if "__EPI_VERSION__" in html:
        return html.replace("__EPI_VERSION__", current_version_marker)
    return html


def _refresh_viewer_html(extracted_dir: Path, resolved_path: Path) -> Path:
    """
    Regenerate viewer.html from the extracted artifact contents.

    This keeps the viewer aligned with append-only files like review.json that
    may have been added after the original viewer was baked into the artifact.
    """
    viewer_path = extracted_dir / "viewer.html"
    try:
        manifest = EPIContainer.read_manifest(resolved_path)
        viewer_version = getattr(manifest, "viewer_version", "minimal")
        viewer_html = EPIContainer._create_embedded_viewer(
            extracted_dir, manifest, viewer_version=viewer_version
        )
        viewer_path.write_text(viewer_html, encoding="utf-8")
        return viewer_path
    except (FileNotFoundError, OSError):
        if viewer_path.exists():
            return viewer_path
        raise


def view(
    ctx: typer.Context,
    epi_file: str = typer.Argument(..., help="Path or name of .epi file to view"),
    extract: str = typer.Option(None, "--extract", help="Destination directory to extract the viewer.html and assets instead of opening browser"),
    browser: bool = typer.Option(False, "--browser", help="Open in the browser review flow (default behavior)."),
    native: bool = typer.Option(False, "--native", help="Force the native desktop viewer instead of the browser review flow."),
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
    except FileNotFoundError:
        console.print(f"[red][X] File not found:[/red] {epi_file}")
        console.print("[dim]   Searched in: ./epi-recordings/[/dim]")
        console.print("[dim]   Try: epi ls   to see available recordings[/dim]")
        raise typer.Exit(1)

    try:
        EPIContainer.detect_container_format(resolved_path)
    except Exception:
        console.print(f"[red][X] Not a valid .epi file:[/red] {resolved_path.name}")
        console.print("[dim]   The file may be corrupt or incomplete.[/dim]")
        raise typer.Exit(1)

    if extract:
        dest = Path(extract)
        dest.mkdir(parents=True, exist_ok=True)
        EPIContainer.unpack(resolved_path, dest)
        viewer_path = dest / "viewer.html"
        try:
            viewer_html = _create_decision_ops_viewer(dest, resolved_path)
            viewer_path.write_text(viewer_html, encoding="utf-8")
        except Exception:
            viewer_path = _refresh_viewer_html(dest, resolved_path)
            _inject_viewer_context(viewer_path, _build_viewer_context(resolved_path))
        console.print(f"[green][OK][/green] Extracted to: {dest}")
        console.print(f"   Open in browser: {dest / 'viewer.html'}")
        _print_share_hint()
        raise typer.Exit(0)

    if native and _open_native_viewer(resolved_path):
        console.print(f"[green][OK][/green] Opened native viewer: {resolved_path.name}")
        console.print("[dim]Use [cyan]epi view[/cyan] to open the browser review flow instead.[/dim]")
        _print_share_hint()
        return

    # Use a persistent viewer cache (Docker-volume approach): no race condition
    # between browser rendering and temp-file deletion.
    viewer_dir = _get_persistent_viewer_dir(resolved_path)

    try:
        viewer_context = _build_viewer_context(resolved_path)

        EPIContainer.unpack(resolved_path, viewer_dir)

        # Use the full decision-ops viewer (preloads all case data) unless
        # a specific single-page shell like "forensic" is requested.
        viewer = viewer_dir / "viewer.html"
        manifest = EPIContainer.read_manifest(resolved_path)
        viewer_version = getattr(manifest, "viewer_version", "minimal")
        try:
            if viewer_version == "forensic":
                # Force single-page forensic document shell
                raise ValueError("Forensic shell requested")
            viewer_html = _create_decision_ops_viewer(viewer_dir, resolved_path)
            viewer.write_text(viewer_html, encoding="utf-8")
        except Exception:
            viewer = _refresh_viewer_html(viewer_dir, resolved_path)
            _inject_viewer_context(viewer, viewer_context)

        _open_in_browser(viewer)
        console.print(f"[green][OK][/green] Opened: {resolved_path.name}")
        _print_share_hint()

    except typer.Exit:
        raise  # Re-raise typer exits cleanly
    except KeyboardInterrupt:
        console.print("\n[yellow]Cancelled[/yellow]")
        raise typer.Exit(130)
    except PermissionError as e:
        console.print(f"[red][X] Permission denied:[/red] {e}")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red][X] Unexpected error:[/red] {e}")
        raise typer.Exit(1)
