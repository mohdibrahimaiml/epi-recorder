"""
EPI Core Container - ZIP-based container management for .epi files.

Implements the EPI file format specification:
- mimetype file (uncompressed, first in ZIP)
- Manifest with file hashes
- Steps timeline (NDJSON)
- Artifacts and cache (content-addressed)
"""

import base64
import hashlib
import json
import shutil
import tempfile
import threading
import zipfile
from pathlib import Path
from typing import Optional, Callable

from epi_core.schemas import ManifestModel
from epi_core.viewer_assets import load_viewer_assets
from epi_core.workspace import RecordingWorkspaceError, create_recording_workspace


# EPI mimetype constant (vendor-specific MIME type per RFC 6838)
EPI_MIMETYPE = "application/vnd.epi+zip"
_RESERVED_ROOT_ARCHIVE_NAMES = {"mimetype", "manifest.json", "viewer.html"}
_GENERATED_WORKSPACE_FILES = {"analysis.json", "policy.json", "policy_evaluation.json"}

# Thread-safe lock for ZIP packing operations (prevents concurrent corruption)
_zip_pack_lock = threading.Lock()


def _html_safe_json_dumps(data: object, *, indent: Optional[int] = None) -> str:
    """
    Serialize JSON safely for embedding inside an HTML <script> tag.

    Recorded content can legitimately contain values such as ``</script>`` or
    U+2028/U+2029. Escaping these keeps embedded viewer payloads robust for
    offline viewing and prevents the script block from being cut short.
    """
    text = json.dumps(data, ensure_ascii=False, indent=indent)
    return (
        text.replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


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
            except json.JSONDecodeError:
                continue
    except Exception:
        return []

    return steps


class EPIContainer:
    """
    Manages .epi file creation and extraction.
    
    .epi files are ZIP archives with a specific structure:
    - mimetype (must be first, uncompressed)
    - manifest.json (metadata + signatures + file hashes)
    - steps.jsonl (timeline of recorded events)
    - artifacts/ (captured files, content-addressed)
    - cache/ (API/LLM responses)
    - environment.json (environment snapshot)
    """
    
    @staticmethod
    def _compute_file_hash(file_path: Path) -> str:
        """
        Compute SHA-256 hash of a file.
        
        Args:
            file_path: Path to file
            
        Returns:
            str: Hexadecimal SHA-256 hash
        """
        sha256 = hashlib.sha256()
        
        with open(file_path, "rb") as f:
            # Read in chunks for memory efficiency
            while chunk := f.read(8192):
                sha256.update(chunk)
        
        return sha256.hexdigest()

    @staticmethod
    def _make_temp_dir(prefix: str) -> Path:
        """Create a temp directory with fallbacks for locked system temp paths."""
        try:
            return create_recording_workspace(prefix)
        except RecordingWorkspaceError:
            candidates = [
                lambda: Path(tempfile.gettempdir()) / f"{prefix}{id(object())}",
                lambda: Path.cwd() / f".{prefix}{id(object())}",
            ]

            last_error = None
            for make in candidates:
                try:
                    candidate = make()
                    candidate.mkdir(parents=True, exist_ok=True)
                    probe = candidate / ".epi_probe"
                    probe.write_text("ok", encoding="utf-8")
                    probe.unlink(missing_ok=True)
                    return candidate
                except Exception as exc:
                    last_error = exc

            raise last_error or RuntimeError("Could not create temporary directory")
    
    @staticmethod
    def _create_embedded_viewer(source_dir: Path, manifest: ManifestModel) -> str:
        """
        Create embedded HTML viewer with injected data.
        
        Args:
            source_dir: Directory containing steps.jsonl
            manifest: Manifest to embed
            
        Returns:
            str: Complete HTML with embedded data
        """
        assets = load_viewer_assets()
        template_html = assets["template_html"]
        if not template_html:
            # Fallback: minimal viewer if template not found
            return EPIContainer._create_minimal_viewer(manifest)

        app_js = assets["app_js"] or ""
        crypto_js = assets["crypto_js"] or ""
        css_styles = assets["css_styles"] or ""

        # Create embedded data
        embedded_data = {
            "manifest": manifest.model_dump(mode="json"),
            "steps": _read_steps_if_exists(source_dir / "steps.jsonl"),
            "analysis": _read_json_if_exists(source_dir / "analysis.json"),
            "policy": _read_json_if_exists(source_dir / "policy.json"),
            "policy_evaluation": _read_json_if_exists(source_dir / "policy_evaluation.json"),
            "review": _read_json_if_exists(source_dir / "review.json"),
            "environment": (
                _read_json_if_exists(source_dir / "environment.json")
                or _read_json_if_exists(source_dir / "env.json")
            ),
            "stdout": _read_text_if_exists(source_dir / "stdout.log"),
            "stderr": _read_text_if_exists(source_dir / "stderr.log"),
            "files": {
                filename: base64.b64encode((source_dir / filename).read_bytes()).decode("ascii")
                for filename in sorted(manifest.file_manifest.keys())
                if (source_dir / filename).exists()
            },
        }

        data_json = _html_safe_json_dumps(embedded_data, indent=2)
        data_tag = f'<script id="epi-data" type="application/json">{data_json}</script>'

        html_with_data = template_html
        context_tag = '<script id="epi-view-context" type="application/json">{}</script>'
        if context_tag in html_with_data:
            html_with_data = html_with_data.replace(context_tag, f"{context_tag}\n{data_tag}")
        elif "</head>" in html_with_data:
            html_with_data = html_with_data.replace("</head>", f"{data_tag}\n</head>")

        style_block = f"<style>{css_styles}</style>" if css_styles else ""
        html_with_css = html_with_data.replace(
            '<link rel="stylesheet" href="styles.css">',
            style_block,
        ) if style_block else html_with_data
        if style_block and html_with_css == html_with_data and "</head>" in html_with_css:
            html_with_css = html_with_css.replace("</head>", f"{style_block}\n</head>")

        html_with_scripts = html_with_css.replace(
            '<script src="https://cdn.jsdelivr.net/npm/jszip@3.10.1/dist/jszip.min.js"></script>',
            '',
        )
        if crypto_js:
            html_with_scripts = html_with_scripts.replace(
                '<script src="../epi_viewer_static/crypto.js"></script>',
                f"<script>{crypto_js}</script>",
            )
        if app_js:
            html_with_scripts = html_with_scripts.replace(
                '<script src="app.js"></script>',
                f"<script>{app_js}</script>",
            )

        from epi_core._version import get_version

        current_version_marker = f"v{get_version()}"
        if "__EPI_VERSION__" in html_with_scripts:
            html_with_version = html_with_scripts.replace("__EPI_VERSION__", current_version_marker)
        else:
            html_with_version = html_with_scripts
            # Compatibility fallback for older templates that predate the
            # placeholder-based version injection path.
            for legacy_marker in ("EPI v2.7.2", "EPI v2.2.0"):
                html_with_version = html_with_version.replace(legacy_marker, f"EPI {current_version_marker}")
        
        return html_with_version
    
    @staticmethod
    def _create_minimal_viewer(manifest: ManifestModel) -> str:
        """
        Create minimal fallback viewer if template not found.
        
        Args:
            manifest: Manifest to display
            
        Returns:
            str: Minimal HTML viewer
        """
        return f'''<!DOCTYPE html>
<html>
<head><title>EPI Viewer</title></head>
<body>
<h1>EPI Viewer</h1>
<pre>{manifest.model_dump_json(indent=2)}</pre>
</body>
</html>'''
    
    @staticmethod
    def pack(
        source_dir: Path,
        manifest: ManifestModel,
        output_path: Path,
        signer_function: Optional[Callable[[ManifestModel], ManifestModel]] = None,
        preserve_generated: bool = False,
    ) -> None:
        """
        Create a .epi file from a source directory.
        
        Thread-safe: Uses a module-level lock to prevent concurrent ZIP corruption.
        
        The packing process:
        1. Write mimetype first (uncompressed) per ZIP spec
        2. Hash all files in source_dir
        3. Populate manifest.file_manifest with hashes
        4. Write all files to ZIP
        5. Write manifest.json last
        
        Args:
            source_dir: Directory containing files to pack
            manifest: Manifest model (file_manifest will be populated)
            output_path: Path for output .epi file
            
        Raises:
            FileNotFoundError: If source_dir doesn't exist
            ValueError: If source_dir is not a directory
        """
        # CRITICAL: Acquire lock to prevent concurrent ZIP corruption
        # Multiple threads writing to ZIP simultaneously causes file header mismatches
        with _zip_pack_lock:
            if not source_dir.exists():
                raise FileNotFoundError(f"Source directory not found: {source_dir}")

            if not source_dir.is_dir():
                raise ValueError(f"Source must be a directory: {source_dir}")

            # Ensure output directory exists
            output_path.parent.mkdir(parents=True, exist_ok=True)
            manifest.analysis_status = "skipped"
            manifest.analysis_error = None

            if not preserve_generated:
                # Clear stale generated files before rebuilding them for this pack.
                # This prevents reused workspaces from accidentally sealing old
                # analysis/policy outputs when analyzer or policy loading does not
                # run on the current pass.
                for generated_name in _GENERATED_WORKSPACE_FILES:
                    stale_path = source_dir / generated_name
                    stale_path.unlink(missing_ok=True)

            # ── Fault Intelligence Layer ──────────────────────────────────────
                # Runs BEFORE rglob so analysis.json / policy.json are hashed
                # into file_manifest and covered by the Ed25519 signature.
                try:
                    from epi_core.policy import load_policy
                    from epi_core.fault_analyzer import FaultAnalyzer

                    # Policy lives in the CWD where `epi run` was invoked,
                    # not in the temp source_dir workspace.
                    policy = load_policy()

                    steps_file = source_dir / "steps.jsonl"
                    if steps_file.exists():
                        steps_content = steps_file.read_text(encoding="utf-8")

                        analyzer = FaultAnalyzer(policy=policy)
                        analysis = analyzer.analyze(steps_content)

                        (source_dir / "analysis.json").write_text(
                            analysis.to_json(), encoding="utf-8"
                        )

                        if policy is not None:
                            (source_dir / "policy.json").write_text(
                                policy.model_dump_json(indent=2), encoding="utf-8"
                            )
                            policy_evaluation_json = analysis.to_policy_evaluation_json()
                            if policy_evaluation_json:
                                (source_dir / "policy_evaluation.json").write_text(
                                    policy_evaluation_json,
                                    encoding="utf-8",
                                )

                        manifest.analysis_status = "complete"
                except Exception as _fa_err:
                # Fault analysis must never break packing — but log to stderr
                # so bugs in the analyzer aren't silently invisible.
                    import sys as _sys
                    manifest.analysis_status = "error"
                    manifest.analysis_error = str(_fa_err).strip()[:240] or "fault analysis failed"
                    print(f"[EPI] Warning: fault analysis failed ({_fa_err}), "
                          "packing without analysis.json", file=_sys.stderr)
            # ─────────────────────────────────────────────────────────────────

            if manifest.analysis_status == "skipped" and (source_dir / "analysis.json").exists():
                manifest.analysis_status = "complete"
                manifest.analysis_error = None

            # Collect all files and compute hashes
            file_manifest = {}
            files_to_pack = []
            
            for file_path in sorted(source_dir.rglob("*")):
                if file_path.is_file():
                    # Get relative path for archive
                    rel_path = file_path.relative_to(source_dir)
                    arc_name = str(rel_path).replace("\\", "/")  # Use forward slashes in ZIP

                    if arc_name in _RESERVED_ROOT_ARCHIVE_NAMES:
                        continue
                    
                    # Compute hash
                    file_hash = EPIContainer._compute_file_hash(file_path)
                    file_manifest[arc_name] = file_hash
                    
                    files_to_pack.append((file_path, arc_name))

            files_to_pack.sort(key=lambda item: item[1])
            
            # Update manifest with file hashes.
            # NOTE: viewer.html and manifest.json are intentionally excluded from
            # file_manifest. viewer.html is a generated presentation layer that
            # embeds the manifest itself (circular dependency makes hashing it
            # impossible without a two-phase scheme). manifest.json cannot include
            # its own hash. The evidence data (steps.jsonl, environment.json, artifacts/)
            # is fully covered. The manifest's Ed25519 signature protects integrity
            # of the manifest fields themselves.
            manifest.file_manifest = file_manifest

            # Sign the manifest BEFORE baking the viewer
            if signer_function:
                manifest = signer_function(manifest)

            # Create embedded viewer with data injection
            viewer_html = EPIContainer._create_embedded_viewer(source_dir, manifest)

            # Create ZIP file
            with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
                # 1. Write mimetype FIRST and UNCOMPRESSED (per EPI spec)
                zf.writestr(
                    "mimetype",
                    EPI_MIMETYPE,
                    compress_type=zipfile.ZIP_STORED  # No compression
                )

                # 2. Write all evidence files
                for file_path, arc_name in files_to_pack:
                    zf.write(file_path, arc_name, compress_type=zipfile.ZIP_DEFLATED)

                # 3. Write embedded viewer (derived from manifest data, not hashed)
                zf.writestr(
                    "viewer.html",
                    viewer_html,
                    compress_type=zipfile.ZIP_DEFLATED
                )

                # 4. Write manifest.json LAST (after all files are hashed)
                manifest_json = manifest.model_dump_json(indent=2)
                zf.writestr(
                    "manifest.json",
                    manifest_json,
                    compress_type=zipfile.ZIP_DEFLATED
                )
    
    @staticmethod
    def unpack(epi_path: Path, dest_dir: Optional[Path] = None) -> Path:
        """
        Extract a .epi file to a directory.
        
        Args:
            epi_path: Path to .epi file
            dest_dir: Destination directory (default: temp directory)
            
        Returns:
            Path: Directory where files were extracted
            
        Raises:
            FileNotFoundError: If .epi file doesn't exist
            ValueError: If file is not a valid .epi archive
        """
        if not epi_path.exists():
            raise FileNotFoundError(f"EPI file not found: {epi_path}")
        
        # Create temp directory if no destination specified
        if dest_dir is None:
            dest_dir = EPIContainer._make_temp_dir("epi_unpack_")
        else:
            dest_dir.mkdir(parents=True, exist_ok=True)
        
        # Validate ZIP format
        if not zipfile.is_zipfile(epi_path):
            raise ValueError(f"Not a valid ZIP file: {epi_path}")
        
        # Extract all files
        with zipfile.ZipFile(epi_path, "r") as zf:
            # Verify mimetype
            try:
                mimetype_data = zf.read("mimetype").decode("utf-8").strip()
                if mimetype_data != EPI_MIMETYPE:
                    raise ValueError(
                        f"Invalid mimetype: expected '{EPI_MIMETYPE}', got '{mimetype_data}'"
                    )
            except KeyError:
                raise ValueError("Missing mimetype file in .epi archive")
            except UnicodeDecodeError:
                raise ValueError("Corrupt mimetype file in .epi archive (not valid UTF-8)")
            
            # Extract all files
            zf.extractall(dest_dir)
        
        return dest_dir
    
    @staticmethod
    def read_manifest(epi_path: Path) -> ManifestModel:
        """
        Read manifest.json from a .epi file without full extraction.
        
        Args:
            epi_path: Path to .epi file
            
        Returns:
            ManifestModel: Parsed manifest
            
        Raises:
            FileNotFoundError: If .epi file doesn't exist
            ValueError: If manifest.json is missing or invalid
        """
        if not epi_path.exists():
            raise FileNotFoundError(f"EPI file not found: {epi_path}")
        
        if not zipfile.is_zipfile(epi_path):
            raise ValueError(f"Not a valid ZIP file: {epi_path}")
        
        with zipfile.ZipFile(epi_path, "r") as zf:
            try:
                manifest_data = zf.read("manifest.json").decode("utf-8")
                manifest_dict = json.loads(manifest_data)
                return ManifestModel(**manifest_dict)
            except KeyError:
                raise ValueError("Missing manifest.json in .epi archive")
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON in manifest.json: {e}")
    
    @staticmethod
    def verify_integrity(epi_path: Path) -> tuple[bool, dict[str, str]]:
        """
        Verify file integrity of a .epi archive.
        
        Checks that all files listed in manifest.file_manifest match their stored hashes.
        
        Args:
            epi_path: Path to .epi file
            
        Returns:
            tuple: (all_valid: bool, mismatches: dict[filename: str -> reason: str])
            
        Raises:
            FileNotFoundError: If .epi file doesn't exist
        """
        if not epi_path.exists():
            raise FileNotFoundError(f"EPI file not found: {epi_path}")
        
        manifest = EPIContainer.read_manifest(epi_path)
        mismatches = {}
        
        # Extract to temp directory for verification
        temp_path = EPIContainer._make_temp_dir("epi_verify_")
        try:
            EPIContainer.unpack(epi_path, temp_path)
            
            # Check each file in manifest
            for filename, expected_hash in manifest.file_manifest.items():
                file_path = temp_path / filename
                
                if not file_path.exists():
                    mismatches[filename] = f"File missing"
                    continue
                
                actual_hash = EPIContainer._compute_file_hash(file_path)
                
                if actual_hash != expected_hash:
                    mismatches[filename] = f"Hash mismatch: expected {expected_hash}, got {actual_hash}"
        finally:
            shutil.rmtree(temp_path, ignore_errors=True)
        
        return (len(mismatches) == 0, mismatches)



 
