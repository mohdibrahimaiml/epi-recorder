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

EPI_ENVELOPE_MAGIC = b"EPI1"
EPI_ENVELOPE_VERSION = 1
EPI_PAYLOAD_FORMAT_ZIP_V1 = 0x01
EPI_ENVELOPE_HEADER_SIZE = 64
_EPI_ENVELOPE_HEADER_STRUCT = struct.Struct("<4sBBHQ32s16s")

_RESERVED_ROOT_ARCHIVE_NAMES = {"mimetype", "manifest.json", "viewer.html"}
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
    def _create_embedded_viewer(source_dir: Path, manifest: ManifestModel) -> str:
        assets = load_viewer_assets()
        template_html = assets["template_html"]
        if not template_html:
            return EPIContainer._create_minimal_viewer(manifest)

        jszip_js = assets["jszip_js"] or ""
        app_js = assets["app_js"] or ""
        crypto_js = assets["crypto_js"] or ""
        css_styles = assets["css_styles"] or ""

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
            raise ValueError(f"Unsupported EPI envelope version: {header.version}")
        if header.payload_format != EPI_PAYLOAD_FORMAT_ZIP_V1:
            raise ValueError(f"Unsupported EPI payload format: {header.payload_format}")
        if header.reserved_flags != 0:
            raise ValueError("Invalid EPI envelope header: reserved flags must be zero")
        if header.reserved_tail != b"\x00" * len(header.reserved_tail):
            raise ValueError("Invalid EPI envelope header: reserved bytes must be zero")
        expected_size = EPI_ENVELOPE_HEADER_SIZE + header.payload_length
        if header.payload_length <= 0 or expected_size != file_size:
            raise ValueError("Invalid EPI envelope payload length")
        return header

    @staticmethod
    def _validate_zip_payload(zip_path: Path) -> None:
        if not zipfile.is_zipfile(zip_path):
            raise ValueError(f"Not a valid ZIP payload: {zip_path}")

        with zipfile.ZipFile(zip_path, "r") as zf:
            try:
                mimetype_data = zf.read("mimetype").decode("utf-8").strip()
            except KeyError as exc:
                raise ValueError("Missing mimetype file in .epi archive") from exc
            except UnicodeDecodeError as exc:
                raise ValueError("Corrupt mimetype file in .epi archive (not valid UTF-8)") from exc

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
    def _write_envelope_from_payload(payload_path: Path, output_path: Path) -> None:
        payload_length = payload_path.stat().st_size
        payload_hash = hashlib.sha256()
        output_path.parent.mkdir(parents=True, exist_ok=True)

        header = _EPI_ENVELOPE_HEADER_STRUCT.pack(
            EPI_ENVELOPE_MAGIC,
            EPI_ENVELOPE_VERSION,
            EPI_PAYLOAD_FORMAT_ZIP_V1,
            0,
            payload_length,
            b"\x00" * 32,
            b"\x00" * 16,
        )

        with open(output_path, "wb") as dst:
            dst.write(header)
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
            payload_hash.digest(),
            b"\x00" * 16,
        )

        with open(output_path, "r+b") as dst:
            dst.write(final_header)

    @staticmethod
    def _write_artifact_from_payload(
        payload_path: Path, output_path: Path, *, container_format: str
    ) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if container_format == EPI_CONTAINER_FORMAT_LEGACY:
            shutil.copyfile(payload_path, output_path)
            return
        if container_format == EPI_CONTAINER_FORMAT_ENVELOPE:
            EPIContainer._write_envelope_from_payload(payload_path, output_path)
            return
        raise ValueError(f"Unsupported container format: {container_format}")

    @staticmethod
    def write_from_payload(
        payload_path: Path, output_path: Path, *, container_format: str
    ) -> None:
        EPIContainer._write_artifact_from_payload(
            payload_path, output_path, container_format=container_format
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
    ) -> None:
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

        if signer_function:
            manifest = signer_function(manifest)

        viewer_html = EPIContainer._create_embedded_viewer(source_dir, manifest)

        with zipfile.ZipFile(payload_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("mimetype", EPI_LEGACY_MIMETYPE, compress_type=zipfile.ZIP_STORED)

            for file_path, arc_name in files_to_pack:
                zf.write(file_path, arc_name, compress_type=zipfile.ZIP_DEFLATED)

            zf.writestr("viewer.html", viewer_html, compress_type=zipfile.ZIP_DEFLATED)

            manifest_json = manifest.model_dump_json(indent=2)
            zf.writestr("manifest.json", manifest_json, compress_type=zipfile.ZIP_DEFLATED)

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
    ) -> None:
        """
        Create a `.epi` file from a source directory.
        """
        with _zip_pack_lock:
            manifest.container_format = container_format
            temp_dir = EPIContainer._make_temp_dir("epi_pack_payload_")
            payload_path = temp_dir / "payload.zip"
            try:
                EPIContainer._pack_zip_payload(
                    source_dir,
                    manifest,
                    payload_path,
                    signer_function=signer_function,
                    preserve_generated=preserve_generated,
                    generate_analysis=generate_analysis,
                    embed_agt=embed_agt,
                )
                EPIContainer._write_artifact_from_payload(
                    payload_path, output_path, container_format=container_format
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
    ) -> None:
        viewer_html = EPIContainer._create_embedded_viewer(source_dir, manifest)
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
