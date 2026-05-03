"""
EPI Core Container - dual-format container management for .epi files.

Current artifacts use an envelope-based outer container (`EPI1`) that wraps the
existing ZIP payload. Legacy `.epi` artifacts remain supported when the file
itself is the ZIP payload.
"""

from __future__ import annotations

import base64
import hashlib
import json
import shutil
import struct
import tempfile
import threading
import zipfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from epi_core.schemas import ManifestModel
from epi_core.viewer_assets import inline_viewer_assets, load_viewer_assets
from epi_core.workspace import RecordingWorkspaceError, create_recording_workspace

EPI_MIMETYPE = "application/vnd.epi"
EPI_LEGACY_MIMETYPE = "application/vnd.epi+zip"
EPI_SUPPORTED_UPLOAD_MIMETYPES = {
    EPI_MIMETYPE,
    EPI_LEGACY_MIMETYPE,
    "application/octet-stream",
}

EPI_CONTAINER_FORMAT_LEGACY = "legacy-zip"
EPI_CONTAINER_FORMAT_ENVELOPE = "envelope-v2"

# The "Polyglot" Magic: Starts with <!-- to be a valid HTML comment
EPI_ENVELOPE_MAGIC = b"<!--" 
EPI_ENVELOPE_VERSION = 2
EPI_PAYLOAD_FORMAT_ZIP_V1 = 0x01
EPI_ENVELOPE_HEADER_SIZE = 128
EPI_ZIP_MARKER = b"\n<!-- EPI_ZIP_PAYLOAD_START -->\n"
# Structure: Magic(4), Version(1), Format(1), Flags(2), Length(8), UUID(16), CreatedAtMicros(8), Hash(32), Padding(56)
_EPI_ENVELOPE_HEADER_STRUCT = struct.Struct("<4sBBHQ16sQ32s56s")

_RESERVED_ROOT_ARCHIVE_NAMES = {"mimetype", "manifest.json", "viewer.html", "VERIFY.txt"}
_GENERATED_WORKSPACE_FILES = {"analysis.json", "policy.json", "policy_evaluation.json"}
_MUTABLE_REVIEW_ARCHIVE_NAMES = {"review.json", "review_index.json"}

_zip_pack_lock = threading.Lock()


def _is_mutable_review_archive_name(arc_name: str) -> bool:
    return arc_name in _MUTABLE_REVIEW_ARCHIVE_NAMES or arc_name.startswith("reviews/")


@dataclass(frozen=True)
class EPIEnvelopeHeader:
    magic: bytes
    version: int
    payload_format: int
    reserved_flags: int
    payload_length: int
    artifact_uuid: bytes
    created_at_micros: int
    payload_sha256: bytes
    reserved_tail: bytes


def _html_safe_json_dumps(data: object, *, indent: int | None = None) -> str:
    """
    Serialize JSON safely for embedding inside an HTML <script> tag.
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
    Manages `.epi` file creation and extraction for both legacy and envelope formats.
    """

    @staticmethod
    def _compute_file_hash(file_path: Path) -> str:
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
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
    def _create_embedded_viewer(
        source_dir: Path,
        manifest: ManifestModel,
        viewer_version: str = "minimal",
        envelope_header: EPIEnvelopeHeader | None = None,
    ) -> str:
        assets = load_viewer_assets(version=viewer_version)
        template_html = assets["template_html"]
        if not template_html:
            return EPIContainer._create_minimal_viewer(manifest)

        jszip_js = assets["jszip_js"] or ""
        app_js = assets["app_js"] or ""
        crypto_js = assets["crypto_js"] or ""
        css_styles = assets["css_styles"] or ""

        # Polyglot Bootstrap: Allows the .epi file to run as .html
        polyglot_bootstrap = (
            "<!-- <script>\n"
            "// EPI_POLYGLOT_BOOTSTRAP\n"
            "window.addEventListener('DOMContentLoaded', () => {\n"
            "  if (window.location.protocol === 'file:') {\n"
            "    console.log('[EPI] Polyglot mode detected. Self-loading artifact...');\n"
            "  }\n"
            "});\n"
            "</script> -->"
        )

        # During creation, we know it's compliant because we just packed it.
        # But we could also verify if we wanted to be 100% sure.
        mimetype_compliant = True 

        # Derive a human-readable source name:
        # 1. workflow_name from session.start step content (most reliable)
        # 2. cli_command tail
        # 3. short UUID fallback
        _steps_for_name = _read_steps_if_exists(source_dir / "steps.jsonl")
        _session_start = next(
            (s for s in _steps_for_name if isinstance(s, dict) and s.get("kind") == "session.start"),
            None,
        )
        _workflow_name = (
            (_session_start or {}).get("content", {}).get("workflow_name")
            or getattr(manifest, "workflow_name", None)
        )
        _source_name = (
            _workflow_name
            or (manifest.cli_command.split()[-1] if manifest.cli_command else None)
            or f"{str(manifest.workflow_id)[:8]}.epi"
        )

        case_payload = {
            "source_name": _source_name,
            "file_size": 0,
            "archive_base64": None,
            "manifest": manifest.model_dump(mode="json"),
            "steps": _steps_for_name,
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
            "integrity": {
                "ok": True,
                "checked": len(manifest.file_manifest),
                "mismatches": [],
            },
            "signature": {
                "valid": False,
                "reason": (
                    "Open this case file through epi view to verify the signer and file integrity."
                    if manifest.signature
                    else "No signer attached to this case file"
                ),
            },
        }

        preloaded_payload = {
            "cases": [case_payload],
            "ui": {
                "view": "case",
                "embeddedArtifactMode": True,
            },
        }

        data_json = _html_safe_json_dumps(preloaded_payload, indent=2)
        data_tag = f'<script id="epi-preloaded-cases" type="application/json">{data_json}</script>'

        context = {}
        if envelope_header:
            context["envelope"] = {
                "magic": envelope_header.magic.decode("ascii", "ignore"),
                "version": envelope_header.version,
                "payload_length": envelope_header.payload_length,
                "artifact_uuid": envelope_header.artifact_uuid.hex(),
                "created_at_micros": envelope_header.created_at_micros,
                "payload_sha256": envelope_header.payload_sha256.hex(),
            }
        context["mimetype_compliant"] = mimetype_compliant

        html_with_data = template_html
        context_tag = f'<script id="epi-view-context" type="application/json">{json.dumps(context)}</script>'
        if '<script id="epi-view-context" type="application/json">{}</script>' in html_with_data:
            html_with_data = html_with_data.replace('<script id="epi-view-context" type="application/json">{}</script>', context_tag)
        
        if data_tag not in html_with_data:
            if context_tag in html_with_data:
                html_with_data = html_with_data.replace(context_tag, f"{context_tag}\n{data_tag}")
            elif "</head>" in html_with_data:
                html_with_data = html_with_data.replace("</head>", f"{data_tag}\n</head>")

        html_with_scripts = inline_viewer_assets(
            html_with_data,
            css_styles=css_styles,
            jszip_js=jszip_js,
            crypto_js=crypto_js,
            app_js=app_js,
        )

        from epi_core._version import get_version

        current_version_marker = f"v{get_version()}"
        if "__EPI_VERSION__" in html_with_scripts:
            html_with_version = html_with_scripts.replace("__EPI_VERSION__", current_version_marker)
        else:
            html_with_version = html_with_scripts
            for legacy_marker in ("EPI v2.7.2", "EPI v2.2.0"):
                html_with_version = html_with_version.replace(
                    legacy_marker, f"EPI {current_version_marker}"
                )

        return html_with_version

    @staticmethod
    def _create_minimal_viewer(manifest: ManifestModel) -> str:
        return f"""<!DOCTYPE html>
<html>
<head><title>EPI Viewer</title></head>
<body>
<h1>EPI Viewer</h1>
<pre>{manifest.model_dump_json(indent=2)}</pre>
</body>
</html>"""

    @staticmethod
    def detect_container_format(epi_path: Path | str) -> str:
        epi_path = Path(epi_path)
        if not epi_path.exists():
            raise FileNotFoundError(f"EPI file not found: {epi_path}")

        with open(epi_path, "rb") as handle:
            prefix = handle.read(4)

        if prefix == EPI_ENVELOPE_MAGIC:
            EPIContainer._read_envelope_header(epi_path)
            return EPI_CONTAINER_FORMAT_ENVELOPE
        if zipfile.is_zipfile(epi_path):
            EPIContainer._validate_zip_payload(epi_path)
            return EPI_CONTAINER_FORMAT_LEGACY
        raise ValueError("Not a valid .epi file: expected an EPI envelope or legacy ZIP payload")

    @staticmethod
    def container_mimetype(epi_path: Path | str) -> str:
        fmt = EPIContainer.detect_container_format(epi_path)
        if fmt == EPI_CONTAINER_FORMAT_ENVELOPE:
            return EPI_MIMETYPE
        return EPI_LEGACY_MIMETYPE

    @staticmethod
    def _read_envelope_header(epi_path: Path) -> EPIEnvelopeHeader:
        file_size = epi_path.stat().st_size
        if file_size < EPI_ENVELOPE_HEADER_SIZE:
            raise ValueError("EPI envelope is too small to contain a valid header")

        with open(epi_path, "rb") as handle:
            raw = handle.read(EPI_ENVELOPE_HEADER_SIZE)

        try:
            unpacked = _EPI_ENVELOPE_HEADER_STRUCT.unpack(raw)
        except struct.error as exc:
            raise ValueError("Invalid EPI envelope header") from exc

        header = EPIEnvelopeHeader(*unpacked)
        if header.magic != EPI_ENVELOPE_MAGIC:
            raise ValueError("Invalid EPI envelope magic bytes")
        if header.version != EPI_ENVELOPE_VERSION:
            # We support version 2 currently, but might allow backward compatibility later
            if header.version != 1:
                raise ValueError(f"Unsupported EPI envelope version: {header.version}")
        if header.payload_format != EPI_PAYLOAD_FORMAT_ZIP_V1:
            raise ValueError(f"Unsupported EPI payload format: {header.payload_format}")
        if header.reserved_flags != 0:
            raise ValueError("Invalid EPI envelope header: reserved flags must be zero")
        if header.reserved_tail != b"\x00" * len(header.reserved_tail):
            raise ValueError("Invalid EPI envelope header: reserved bytes must be zero")
        if header.payload_length <= 0 or file_size < (EPI_ENVELOPE_HEADER_SIZE + header.payload_length):
            raise ValueError("Invalid EPI envelope payload length or truncated file")
        return header

    @staticmethod
    def _validate_zip_payload(zip_path: Path) -> None:
        if not zipfile.is_zipfile(zip_path):
            raise ValueError(f"Not a valid ZIP payload: {zip_path}")

        with zipfile.ZipFile(zip_path, "r") as zf:
            infolist = zf.infolist()
            if not infolist or infolist[0].filename != "mimetype":
                raise ValueError("Forensic Violation: 'mimetype' MUST be the first file in the .epi ZIP payload.")

            mimetype_info = infolist[0]
            if mimetype_info.compress_type != zipfile.ZIP_STORED:
                raise ValueError("Forensic Violation: 'mimetype' MUST be stored without compression (ZIP_STORED).")

            try:
                mimetype_data = zf.read("mimetype").decode("utf-8").strip()
            except Exception as exc:
                raise ValueError("Corrupt mimetype file in .epi archive") from exc

            if mimetype_data != EPI_LEGACY_MIMETYPE:
                raise ValueError(
                    f"Invalid mimetype: expected '{EPI_LEGACY_MIMETYPE}', got '{mimetype_data}'"
                )

    @staticmethod
    def extract_inner_payload(epi_path: Path, dest_zip_path: Path) -> Path:
        fmt = EPIContainer.detect_container_format(epi_path)
        dest_zip_path.parent.mkdir(parents=True, exist_ok=True)

        if fmt == EPI_CONTAINER_FORMAT_LEGACY:
            EPIContainer._validate_zip_payload(epi_path)
            shutil.copyfile(epi_path, dest_zip_path)
            return dest_zip_path

        header = EPIContainer._read_envelope_header(epi_path)
        sha256 = hashlib.sha256()
        written = 0

        with open(epi_path, "rb") as src, open(dest_zip_path, "wb") as dst:
            # Polyglot-aware extraction: Scan for the unique ZIP marker
            src.seek(EPI_ENVELOPE_HEADER_SIZE)
            buffer = src.read(1024 * 1024) # Check first 1MB for marker
            marker_idx = buffer.find(EPI_ZIP_MARKER)
            
            if marker_idx != -1:
                src.seek(EPI_ENVELOPE_HEADER_SIZE + marker_idx + len(EPI_ZIP_MARKER))
            else:
                # Fallback to standard 128 offset for non-polyglot artifacts
                src.seek(EPI_ENVELOPE_HEADER_SIZE)

            remaining = header.payload_length
            while remaining > 0:
                chunk = src.read(min(65536, remaining))
                if not chunk:
                    raise ValueError("Unexpected end of EPI envelope payload")
                dst.write(chunk)
                sha256.update(chunk)
                written += len(chunk)
                remaining -= len(chunk)

        if written != header.payload_length:
            raise ValueError("Unexpected payload length while extracting EPI envelope")
        if sha256.digest() != header.payload_sha256:
            raise ValueError("EPI envelope payload hash mismatch")

        EPIContainer._validate_zip_payload(dest_zip_path)
        return dest_zip_path

    @staticmethod
    @contextmanager
    def _payload_zip_path(epi_path: Path) -> Iterator[Path]:
        fmt = EPIContainer.detect_container_format(epi_path)
        if fmt == EPI_CONTAINER_FORMAT_LEGACY:
            EPIContainer._validate_zip_payload(epi_path)
            yield epi_path
            return

        temp_dir = EPIContainer._make_temp_dir("epi_payload_")
        payload_path = temp_dir / "payload.zip"
        try:
            EPIContainer.extract_inner_payload(epi_path, payload_path)
            yield payload_path
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    @staticmethod
    def _write_envelope_from_payload(
        payload_path: Path, 
        output_path: Path, 
        manifest: ManifestModel | None = None,
        viewer_html: str | None = None
    ) -> None:
        payload_length = payload_path.stat().st_size
        payload_hash = hashlib.sha256()
        output_path.parent.mkdir(parents=True, exist_ok=True)

        uuid_bytes = manifest.workflow_id.bytes if manifest else b"\x00" * 16
        created_at_micros = int(manifest.created_at.timestamp() * 1_000_000) if manifest else 0

        header = _EPI_ENVELOPE_HEADER_STRUCT.pack(
            EPI_ENVELOPE_MAGIC, # "<!--"
            EPI_ENVELOPE_VERSION,
            EPI_PAYLOAD_FORMAT_ZIP_V1,
            0,
            payload_length,
            uuid_bytes,
            created_at_micros,
            b"\x00" * 32,
            b"\x00" * 56,
        )

        with open(output_path, "wb") as dst:
            dst.write(header)
            
            # Polyglot Bootstrap: Inject HTML between header and ZIP
            if viewer_html:
                # Close the header comment, add HTML, then start a new comment for the binary ZIP
                dst.write(b" -->\n")
                dst.write(viewer_html.encode("utf-8"))
                dst.write(EPI_ZIP_MARKER)

            with open(payload_path, "rb") as src:
                while chunk := src.read(65536):
                    dst.write(chunk)
                    payload_hash.update(chunk)

        final_header = _EPI_ENVELOPE_HEADER_STRUCT.pack(
            EPI_ENVELOPE_MAGIC,
            EPI_ENVELOPE_VERSION,
            EPI_PAYLOAD_FORMAT_ZIP_V1,
            0,
            payload_length,
            uuid_bytes,
            created_at_micros,
            payload_hash.digest(),
            b"\x00" * 56,
        )

        with open(output_path, "r+b") as dst:
            dst.write(final_header)

    @staticmethod
    def _write_artifact_from_payload(
        payload_path: Path, output_path: Path, *, container_format: str, manifest: ManifestModel | None = None, **kwargs
    ) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if container_format == EPI_CONTAINER_FORMAT_LEGACY:
            shutil.copyfile(payload_path, output_path)
            return
        if container_format == EPI_CONTAINER_FORMAT_ENVELOPE:
            # Check if viewer HTML is passed in kwargs
            viewer_html = kwargs.get("viewer_html")
            EPIContainer._write_envelope_from_payload(payload_path, output_path, manifest=manifest, viewer_html=viewer_html)
            return
        raise ValueError(f"Unsupported container format: {container_format}")

    @staticmethod
    def write_from_payload(
        payload_path: Path, output_path: Path, *, container_format: str, manifest: ManifestModel | None = None
    ) -> None:
        EPIContainer._write_artifact_from_payload(
            payload_path, output_path, container_format=container_format, manifest=manifest
        )

    @staticmethod
    def _pack_zip_payload(
        source_dir: Path,
        manifest: ManifestModel,
        payload_path: Path,
        signer_function: Callable[[ManifestModel], ManifestModel] | None = None,
        preserve_generated: bool = False,
        generate_analysis: bool = True,
        embed_agt: bool = False,
        **kwargs,
    ) -> str:
        if not source_dir.exists():
            raise FileNotFoundError(f"Source directory not found: {source_dir}")

        if not source_dir.is_dir():
            raise ValueError(f"Source must be a directory: {source_dir}")

        payload_path.parent.mkdir(parents=True, exist_ok=True)
        manifest.analysis_status = "skipped"
        manifest.analysis_error = None

        if not preserve_generated:
            for generated_name in _GENERATED_WORKSPACE_FILES:
                stale_path = source_dir / generated_name
                stale_path.unlink(missing_ok=True)

        if generate_analysis:
            try:
                from epi_core.fault_analyzer import FaultAnalyzer
                from epi_core.policy import load_policy

                # Prioritize policy inside the source_dir for artifact-local analysis
                local_policy_path = source_dir / "policy.json"
                if not local_policy_path.exists():
                    local_policy_path = source_dir / "epi_policy.json"
                
                if local_policy_path.exists():
                    try:
                        from epi_core.policy import EPIPolicy
                        policy = EPIPolicy.model_validate_json(local_policy_path.read_text(encoding="utf-8"))
                    except Exception:
                        policy = load_policy()
                else:
                    policy = load_policy()

                steps_file = source_dir / "steps.jsonl"
                if steps_file.exists():
                    steps_content = steps_file.read_text(encoding="utf-8")

                    analyzer = FaultAnalyzer(policy=policy)
                    analysis = analyzer.analyze(steps_content)

                    (source_dir / "analysis.json").write_text(analysis.to_json(), encoding="utf-8")

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
                    else:
                        # No explicit policy — generate a minimal baseline evaluation
                        # from heuristic fault detection so every artifact has
                        # policy_evaluation.json for the viewer to display.
                        baseline_eval = EPIContainer._build_baseline_policy_evaluation(analysis)
                        (source_dir / "policy_evaluation.json").write_text(
                            json.dumps(baseline_eval, indent=2, ensure_ascii=False),
                            encoding="utf-8",
                        )

                    manifest.analysis_status = "complete"
            except Exception as _fa_err:
                import sys as _sys

                manifest.analysis_status = "error"
                manifest.analysis_error = str(_fa_err).strip()[:240] or "fault analysis failed"
                warning = (
                    f"[EPI] Warning: fault analysis failed ({_fa_err}), "
                    "packing without analysis.json"
                )
                print(warning, file=_sys.stderr)

        if manifest.analysis_status == "skipped" and (source_dir / "analysis.json").exists():
            manifest.analysis_status = "complete"
            manifest.analysis_error = None

        # Inject a placeholder VERIFY.txt so the file appears in file_manifest;
        # the final content (with the public key) is written after signing below.
        source_info = manifest.source or {}
        gov_info = manifest.governance or {}
        sys_name = source_info.get("system_name") or gov_info.get("system_name") or "EPI_RECORDER"
        sys_ver = source_info.get("system_version") or gov_info.get("system_version") or "1.0"

        verify_txt = source_dir / "VERIFY.txt"
        verify_txt.write_text("EPI_FORENSIC_VERIFICATION_GUIDE (pending signing)\n", encoding="utf-8")

        # Optionally embed an AGT export JSON into the workspace before packing.
        # This is intentionally optional and best-effort: failure to generate
        # the AGT artifact should not abort packing.
        if embed_agt:
            try:
                from epi_recorder.integrations.agt.exporter import (
                    export_workspace_to_agt,
                )

                artifacts_dir = source_dir / "artifacts"
                artifacts_dir.mkdir(parents=True, exist_ok=True)
                agt_out = artifacts_dir / "agt_export.json"
                # include_raw=True to keep manifest/steps for downstream verification
                export_workspace_to_agt(source_dir, agt_out, include_raw=True)
            except Exception as _embed_err:
                import sys as _sys

                manifest.analysis_status = manifest.analysis_status or "error"
                manifest.analysis_error = (
                    str(_embed_err).strip()[:240] or "agt embedding failed"
                )
                warning = f"[EPI] Warning: AGT embedding failed ({_embed_err}), continuing without embedded AGT"
                print(warning, file=_sys.stderr)

        file_manifest: dict[str, str] = {}
        files_to_pack: list[tuple[Path, str]] = []

        for file_path in sorted(source_dir.rglob("*")):
            if file_path.is_file():
                rel_path = file_path.relative_to(source_dir)
                arc_name = str(rel_path).replace("\\", "/")

                if arc_name in _RESERVED_ROOT_ARCHIVE_NAMES:
                    continue

                if not _is_mutable_review_archive_name(arc_name):
                    file_hash = EPIContainer._compute_file_hash(file_path)
                    file_manifest[arc_name] = file_hash
                files_to_pack.append((file_path, arc_name))

        files_to_pack.sort(key=lambda item: item[1])
        manifest.file_manifest = file_manifest

        # Compute a deterministic payload fingerprint: SHA-256 of the sorted
        # file manifest (hash-of-hashes).  Stored in manifest.trust so the
        # viewer can display it even before Ed25519 signing is performed.
        _manifest_canon = json.dumps(
            dict(sorted(file_manifest.items())), ensure_ascii=False, separators=(",", ":")
        )
        _payload_hash = hashlib.sha256(_manifest_canon.encode()).hexdigest()
        
        # LINKAGE: Bind the manifest to the outer envelope and mimetype
        manifest.trust = {
            **(manifest.trust or {}), 
            "payload_hash": _payload_hash,
            "artifact_uuid": str(manifest.workflow_id),
            "mimetype": EPI_LEGACY_MIMETYPE,
            "envelope_version": EPI_ENVELOPE_VERSION
        }

        viewer_version = str(kwargs.get("viewer_version", manifest.viewer_version or "minimal"))
        manifest.viewer_version = viewer_version

        if signer_function:
            manifest = signer_function(manifest)

        # Now that signing is done (public_key is set), write the real VERIFY.txt.
        gov_info_post = manifest.governance or {}
        did_line = f"DID:           {gov_info_post.get('did')}\n" if gov_info_post.get("did") else ""
        verify_txt.write_text(
            f"EPI_FORENSIC_VERIFICATION_GUIDE\n"
            f"===============================\n\n"
            f"Artifact UUID: {manifest.workflow_id}\n"
            f"Created At:    {manifest.created_at.isoformat()}\n"
            f"System:        {sys_name} v{sys_ver}\n"
            f"{did_line}"
            f"\nMANUAL_VERIFICATION_STEPS:\n"
            f"1. Extract manifest.json from this ZIP archive.\n"
            f"2. Verify the Ed25519 signature in manifest.json against the file_manifest hashes.\n"
            f"3. Public Key (Raw Hex): {manifest.public_key or '(unsigned)'}\n\n"
            f"COMMAND LINE:\n"
            f"  python -m epi_cli verify <this_file>.epi\n\n"
            f"This artifact is a signed, tamper-evident record.\n",
            encoding="utf-8"
        )

        # Build temporary header for viewer injection
        uuid_bytes = manifest.workflow_id.bytes
        created_at_micros = int(manifest.created_at.timestamp() * 1_000_000)
        temp_header = EPIEnvelopeHeader(
            magic=EPI_ENVELOPE_MAGIC,
            version=EPI_ENVELOPE_VERSION,
            payload_format=EPI_PAYLOAD_FORMAT_ZIP_V1,
            reserved_flags=0,
            payload_length=0, # Not yet known precisely for the final file
            artifact_uuid=uuid_bytes,
            created_at_micros=created_at_micros,
            payload_sha256=b"\x00" * 32,
            reserved_tail=b"\x00" * 56
        )

        viewer_html = EPIContainer._create_embedded_viewer(
            source_dir, manifest, viewer_version=viewer_version, envelope_header=temp_header
        )

        with zipfile.ZipFile(payload_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("mimetype", EPI_LEGACY_MIMETYPE, compress_type=zipfile.ZIP_STORED)

            for file_path, arc_name in files_to_pack:
                zf.write(file_path, arc_name, compress_type=zipfile.ZIP_DEFLATED)

            zf.writestr("viewer.html", viewer_html, compress_type=zipfile.ZIP_DEFLATED)

            zf.writestr("VERIFY.txt", verify_txt.read_text(encoding="utf-8"), compress_type=zipfile.ZIP_DEFLATED)

            manifest_json = manifest.model_dump_json(indent=2)
            zf.writestr("manifest.json", manifest_json, compress_type=zipfile.ZIP_DEFLATED)

        return viewer_html

    @staticmethod
    def _build_baseline_policy_evaluation(analysis) -> dict:
        """
        Generate a minimal policy_evaluation.json from heuristic analysis when
        no explicit epi_policy.json is configured.

        This ensures every artifact produced without a project-level policy still
        has a policy_evaluation section in the viewer, clearly labelled as
        baseline/heuristic rather than policy-grounded.
        """
        from datetime import datetime, timezone

        # Collect all heuristic fault flags
        all_flags = []
        if analysis.primary_fault is not None:
            all_flags.append(analysis.primary_fault)
        all_flags.extend(analysis.secondary_flags)

        # Map flags to simple results
        error_flags = [f for f in all_flags if "error" in (f.fault_type or "").lower()
                       or "fail" in (f.fault_type or "").lower()]
        other_flags = [f for f in all_flags if f not in error_flags]

        results = []

        # Rule 1 — no execution errors
        results.append({
            "rule_id": "baseline.no_error",
            "rule_name": "No execution errors",
            "rule_type": "baseline",
            "severity": "high",
            "mode": "detect",
            "status": "failed" if error_flags else "passed",
            "match_count": len(error_flags),
            "review_required": bool(error_flags),
            "step_numbers": [f.step_number for f in error_flags],
            "plain_english": (
                f"{len(error_flags)} error fault(s) detected during execution."
                if error_flags
                else "No execution errors detected."
            ),
        })

        # Rule 2 — no heuristic risk patterns
        results.append({
            "rule_id": "baseline.no_risk_pattern",
            "rule_name": "No heuristic risk patterns",
            "rule_type": "baseline",
            "severity": "medium",
            "mode": "detect",
            "status": "failed" if other_flags else "passed",
            "match_count": len(other_flags),
            "review_required": bool(other_flags and any(
                f.severity in ("critical", "high") for f in other_flags
            )),
            "step_numbers": [f.step_number for f in other_flags],
            "plain_english": (
                f"{len(other_flags)} heuristic risk pattern(s) detected."
                if other_flags
                else "No heuristic risk patterns detected."
            ),
        })

        controls_failed = sum(1 for r in results if r["status"] == "failed")

        return {
            "policy_id": "epi.baseline",
            "policy_version": "1.0",
            "baseline": True,
            "note": "No epi_policy.json found. Baseline heuristic evaluation only.",
            "evaluation_timestamp": datetime.now(timezone.utc).isoformat(),
            "evaluation_mode": "heuristic_only",
            "controls_evaluated": len(results),
            "controls_failed": controls_failed,
            "artifact_review_required": analysis.fault_detected,
            "results": results,
        }

    @staticmethod
    def add_review(
        epi_path: "Path | str",
        *,
        reviewer: str,
        status: str,
        notes: str = "",
    ) -> None:
        """
        Attach or update a review.json inside an existing .epi artifact.

        review.json is a mutable file — it is not included in the cryptographic
        file_manifest so adding it does not invalidate the manifest signature.

        Args:
            epi_path: Path to the .epi file to update.
            reviewer:  Name or email of the reviewer.
            status:    "approved" | "rejected" | "escalated" | any string.
            notes:     Optional free-text review notes.

        Raises:
            FileNotFoundError: If the .epi file does not exist.
        """
        from datetime import datetime, timezone

        epi_path = Path(epi_path)
        if not epi_path.exists():
            raise FileNotFoundError(f"EPI file not found: {epi_path}")

        review_data = {
            "reviewer": reviewer,
            "status": status,
            "outcome": status,
            "notes": notes,
            "reviewed_at": datetime.now(timezone.utc).isoformat(),
        }
        review_json = json.dumps(review_data, indent=2, ensure_ascii=False)

        container_format = EPIContainer.detect_container_format(epi_path)
        temp_dir = EPIContainer._make_temp_dir("epi_add_review_")
        tmp_zip = temp_dir / "payload.zip"
        tmp_out = temp_dir / "reviewed.epi"

        try:
            with EPIContainer._payload_zip_path(epi_path) as src_zip:
                with zipfile.ZipFile(src_zip, "r") as zf_in:
                    with zipfile.ZipFile(tmp_zip, "w", zipfile.ZIP_DEFLATED) as zf_out:
                        for item in zf_in.infolist():
                            if item.filename == "review.json":
                                continue  # Replace with updated review
                            zf_out.writestr(item, zf_in.read(item.filename))
                        zf_out.writestr(
                            "review.json", review_json, compress_type=zipfile.ZIP_DEFLATED
                        )

            EPIContainer._write_artifact_from_payload(
                tmp_zip, tmp_out, container_format=container_format
            )
            shutil.move(str(tmp_out), str(epi_path))
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    @staticmethod
    def pack(
        source_dir: Path,
        manifest: ManifestModel,
        output_path: Path,
        signer_function: Callable[[ManifestModel], ManifestModel] | None = None,
        preserve_generated: bool = False,
        container_format: str = EPI_CONTAINER_FORMAT_ENVELOPE,
        generate_analysis: bool = True,
        embed_agt: bool = False,
        **kwargs,
    ) -> None:
        """
        Create a `.epi` file from a source directory.
        """
        with _zip_pack_lock:
            manifest.container_format = container_format
            temp_dir = EPIContainer._make_temp_dir("epi_pack_payload_")
            payload_path = temp_dir / "payload.zip"
            try:
                viewer_html = EPIContainer._pack_zip_payload(
                    source_dir,
                    manifest,
                    payload_path,
                    signer_function=signer_function,
                    preserve_generated=preserve_generated,
                    generate_analysis=generate_analysis,
                    embed_agt=embed_agt,
                    **kwargs,
                )
                EPIContainer._write_artifact_from_payload(
                    payload_path, 
                    output_path, 
                    container_format=container_format, 
                    manifest=manifest,
                    viewer_html=viewer_html # Pass the inlined viewer HTML for polyglot support
                )
            finally:
                shutil.rmtree(temp_dir, ignore_errors=True)

    @staticmethod
    def migrate(
        epi_path: Path,
        output_path: Path,
        *,
        container_format: str = EPI_CONTAINER_FORMAT_ENVELOPE,
    ) -> None:
        with EPIContainer._payload_zip_path(epi_path) as payload_zip:
            temp_dir = EPIContainer._make_temp_dir("epi_migrate_payload_")
            temp_payload = temp_dir / "payload.zip"
            try:
                shutil.copyfile(payload_zip, temp_payload)
                EPIContainer._write_artifact_from_payload(
                    temp_payload, output_path, container_format=container_format
                )
            finally:
                shutil.rmtree(temp_dir, ignore_errors=True)

    @staticmethod
    def _rebuild_payload_with_viewer(
        source_dir: Path,
        manifest: ManifestModel,
        payload_path: Path,
        **kwargs,
    ) -> None:
        viewer_version = str(kwargs.get("viewer_version", "minimal"))
        viewer_html = EPIContainer._create_embedded_viewer(
            source_dir, manifest, viewer_version=viewer_version
        )
        payload_path.parent.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(payload_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("mimetype", EPI_LEGACY_MIMETYPE, compress_type=zipfile.ZIP_STORED)

            for file_path in sorted(source_dir.rglob("*")):
                if not file_path.is_file():
                    continue

                arc_name = str(file_path.relative_to(source_dir)).replace("\\", "/")
                if arc_name in _RESERVED_ROOT_ARCHIVE_NAMES:
                    continue

                zf.write(file_path, arc_name, compress_type=zipfile.ZIP_DEFLATED)

            zf.writestr("viewer.html", viewer_html, compress_type=zipfile.ZIP_DEFLATED)
            zf.writestr(
                "manifest.json",
                manifest.model_dump_json(indent=2),
                compress_type=zipfile.ZIP_DEFLATED,
            )

    @staticmethod
    def refresh_viewer(
        epi_path: Path,
        output_path: Path | None = None,
    ) -> Path:
        source_path = Path(epi_path)
        if not source_path.exists():
            raise FileNotFoundError(f"EPI file not found: {source_path}")

        destination = Path(output_path) if output_path is not None else source_path
        container_format = EPIContainer.detect_container_format(source_path)
        manifest = EPIContainer.read_manifest(source_path)

        temp_dir = EPIContainer._make_temp_dir("epi_refresh_viewer_")
        unpack_dir = temp_dir / "unpacked"
        unpack_dir.mkdir(parents=True, exist_ok=True)
        temp_payload = temp_dir / "payload.zip"
        temp_output = temp_dir / "refreshed.epi"

        try:
            with EPIContainer._payload_zip_path(source_path) as payload_zip:
                with zipfile.ZipFile(payload_zip, "r") as zf:
                    zf.extractall(unpack_dir)

            EPIContainer._rebuild_payload_with_viewer(unpack_dir, manifest, temp_payload)
            EPIContainer._write_artifact_from_payload(
                temp_payload,
                temp_output,
                container_format=container_format,
            )

            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(temp_output), str(destination))
            return destination
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    @staticmethod
    def unpack(epi_path: Path, dest_dir: Path | None = None) -> Path:
        if not epi_path.exists():
            raise FileNotFoundError(f"EPI file not found: {epi_path}")

        if dest_dir is None:
            dest_dir = EPIContainer._make_temp_dir("epi_unpack_")
        else:
            dest_dir.mkdir(parents=True, exist_ok=True)

        with EPIContainer._payload_zip_path(epi_path) as payload_zip:
            with zipfile.ZipFile(payload_zip, "r") as zf:
                zf.extractall(dest_dir)

        return dest_dir

    @staticmethod
    def list_members(epi_path: Path) -> list[str]:
        with EPIContainer._payload_zip_path(epi_path) as payload_zip:
            with zipfile.ZipFile(payload_zip, "r") as zf:
                return zf.namelist()

    @staticmethod
    def read_member_bytes(epi_path: Path, member_name: str) -> bytes:
        with EPIContainer._payload_zip_path(epi_path) as payload_zip:
            with zipfile.ZipFile(payload_zip, "r") as zf:
                try:
                    return zf.read(member_name)
                except KeyError as exc:
                    raise ValueError(f"Missing {member_name} in .epi archive") from exc

    @staticmethod
    def read_member_text(epi_path: Path, member_name: str) -> str:
        try:
            return EPIContainer.read_member_bytes(epi_path, member_name).decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError(f"{member_name} is not valid UTF-8") from exc

    @staticmethod
    def read_member_json(epi_path: Path, member_name: str) -> Any:
        try:
            return json.loads(EPIContainer.read_member_text(epi_path, member_name))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON in {member_name}: {exc}") from exc

    @staticmethod
    def read_steps(epi_path: Path) -> list[dict[str, Any]]:
        try:
            raw_steps = EPIContainer.read_member_text(epi_path, "steps.jsonl")
        except ValueError:
            return []

        steps: list[dict[str, Any]] = []
        for line in raw_steps.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except Exception:
                continue
            if isinstance(payload, dict):
                steps.append(payload)
        return steps

    @staticmethod
    def count_steps(epi_path: Path) -> int:
        return len(EPIContainer.read_steps(epi_path))

    @staticmethod
    def read_step(epi_path: Path, step_index: int) -> dict[str, Any] | None:
        for step in EPIContainer.read_steps(epi_path):
            if step.get("index") == step_index:
                return step
        return None

    @staticmethod
    def read_manifest(epi_path: Path) -> ManifestModel:
        if not epi_path.exists():
            raise FileNotFoundError(f"EPI file not found: {epi_path}")

        manifest_dict = EPIContainer.read_member_json(epi_path, "manifest.json")
        if not isinstance(manifest_dict, dict):
            raise ValueError("manifest.json must be a JSON object")
        return ManifestModel(**manifest_dict)

    @staticmethod
    def verify_integrity(epi_path: Path) -> tuple[bool, dict[str, str]]:
        if not epi_path.exists():
            raise FileNotFoundError(f"EPI file not found: {epi_path}")

        manifest = EPIContainer.read_manifest(epi_path)
        mismatches: dict[str, str] = {}
        temp_path = EPIContainer._make_temp_dir("epi_verify_")
        try:
            EPIContainer.unpack(epi_path, temp_path)
            for filename, expected_hash in manifest.file_manifest.items():
                file_path = temp_path / filename

                if not file_path.exists():
                    mismatches[filename] = "File missing"
                    continue

                actual_hash = EPIContainer._compute_file_hash(file_path)
                if actual_hash != expected_hash:
                    mismatches[filename] = (
                        f"Hash mismatch: expected {expected_hash}, got {actual_hash}"
                    )
        finally:
            shutil.rmtree(temp_path, ignore_errors=True)

        return (len(mismatches) == 0, mismatches)
