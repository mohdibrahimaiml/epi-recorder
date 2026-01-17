"""
EPI Core Container - ZIP-based container management for .epi files.

Implements the EPI file format specification:
- mimetype file (uncompressed, first in ZIP)
- Manifest with file hashes
- Steps timeline (NDJSON)
- Artifacts and cache (content-addressed)
"""

import hashlib
import json
import tempfile
import zipfile
from pathlib import Path
from typing import Optional

from epi_core.schemas import ManifestModel


# EPI mimetype constant (vendor-specific MIME type per RFC 6838)
EPI_MIMETYPE = "application/vnd.epi+zip"


class EPIContainer:
    """
    Manages .epi file creation and extraction.
    
    .epi files are ZIP archives with a specific structure:
    - mimetype (must be first, uncompressed)
    - manifest.json (metadata + signatures + file hashes)
    - steps.jsonl (timeline of recorded events)
    - artifacts/ (captured files, content-addressed)
    - cache/ (API/LLM responses)
    - env.json (environment snapshot)
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
    def _create_embedded_viewer(source_dir: Path, manifest: ManifestModel) -> str:
        """
        Create embedded HTML viewer with injected data.
        
        Args:
            source_dir: Directory containing steps.jsonl
            manifest: Manifest to embed
            
        Returns:
            str: Complete HTML with embedded data
        """
        # Load viewer template
        viewer_static_dir = Path(__file__).parent.parent / "epi_viewer_static"
        template_path = viewer_static_dir / "index.html"
        app_js_path = viewer_static_dir / "app.js"
        css_path = viewer_static_dir / "viewer_lite.css"
        
        if not template_path.exists():
            # Fallback: minimal viewer if template not found
            return EPIContainer._create_minimal_viewer(manifest)
        
        # Read template and assets
        template_html = template_path.read_text(encoding="utf-8")
        app_js = app_js_path.read_text(encoding="utf-8") if app_js_path.exists() else ""
        crypto_js_path = viewer_static_dir / "crypto.js"
        crypto_js = crypto_js_path.read_text(encoding="utf-8") if crypto_js_path.exists() else ""
        css_styles = css_path.read_text(encoding="utf-8") if css_path.exists() else ""
        
        # Read steps from steps.jsonl
        steps = []
        steps_file = source_dir / "steps.jsonl"
        if steps_file.exists():
            for line in steps_file.read_text(encoding="utf-8").strip().split("\n"):
                if line:
                    try:
                        steps.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        
        # Create embedded data
        embedded_data = {
            "manifest": manifest.model_dump(mode="json"),
            "steps": steps
        }
        
        # Inject data into template
        data_json = json.dumps(embedded_data, indent=2)
        html_with_data = template_html.replace(
            '<script id="epi-data" type="application/json">\n    {\n        "manifest": {},\n        "steps": []\n    }\n    </script>',
            f'<script id="epi-data" type="application/json">{data_json}</script>'
        )
        
        # Replaces Tailwind CDN with local CSS
        html_with_css = html_with_data.replace(
            '<script src="https://cdn.tailwindcss.com"></script>',
            f'<style>{css_styles}</style>'
        )
        
        # Inline crypto.js and app.js
        js_content = ""
        if crypto_js:
            js_content += f"<script>{crypto_js}</script>\n"
        if app_js:
            js_content += f"<script>{app_js}</script>"
            
        html_with_js = html_with_css.replace(
            '<script src="app.js"></script>',
            js_content
        )
        
        return html_with_js
    
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
        output_path: Path
    ) -> None:
        """
        Create a .epi file from a source directory.
        
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
        if not source_dir.exists():
            raise FileNotFoundError(f"Source directory not found: {source_dir}")
        
        if not source_dir.is_dir():
            raise ValueError(f"Source must be a directory: {source_dir}")
        
        # Ensure output directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Collect all files and compute hashes
        file_manifest = {}
        files_to_pack = []
        
        for file_path in source_dir.rglob("*"):
            if file_path.is_file():
                # Get relative path for archive
                rel_path = file_path.relative_to(source_dir)
                arc_name = str(rel_path).replace("\\", "/")  # Use forward slashes in ZIP
                
                # Compute hash
                file_hash = EPIContainer._compute_file_hash(file_path)
                file_manifest[arc_name] = file_hash
                
                files_to_pack.append((file_path, arc_name))
        
        # Update manifest with file hashes
        manifest.file_manifest = file_manifest
        
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
            
            # 2. Write all other files
            for file_path, arc_name in files_to_pack:
                zf.write(file_path, arc_name, compress_type=zipfile.ZIP_DEFLATED)
            
            # 3. Write embedded viewer
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
            dest_dir = Path(tempfile.mkdtemp(prefix="epi_unpack_"))
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
        with tempfile.TemporaryDirectory(prefix="epi_verify_") as temp_dir:
            temp_path = Path(temp_dir)
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
        
        return (len(mismatches) == 0, mismatches)
