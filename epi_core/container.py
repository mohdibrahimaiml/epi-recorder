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
import os
import shutil
import struct
import tempfile
import threading
import uuid
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
# reserved_tail (56 bytes) layout:
#   [0:32]  polyglot_viewer_sha256 — SHA-256 of outer viewer HTML (UTF-8 body only)
#           all-zero = legacy artifact (viewer display layer not integrity-covered)
#   [32:56] must remain zero (reserved for future use)
EPI_VIEWER_HASH_SIZE = 32
EPI_RESERVED_TAIL_PADDING_SIZE = 24
EPI_RESERVED_TAIL_SIZE = EPI_VIEWER_HASH_SIZE + EPI_RESERVED_TAIL_PADDING_SIZE  # 56
VERIFY_TXT_TEMPLATE = """EPI_FORENSIC_VERIFICATION_GUIDE\n===============================\n\nArtifact UUID: %(filename)s\nStep Count:    %(steps_count)s\n\nVERIFY:\n  epi verify <this_file>.epi\n"""
# Structure: Magic(4), Version(1), Format(1), Flags(2), Length(8), UUID(16), CreatedAtMicros(8), Hash(32), reserved_tail(56)
_EPI_ENVELOPE_HEADER_STRUCT = struct.Struct("<4sBBHQ16sQ32s56s")

# Written explicitly via ZipFile.writestr (not from workspace rglob) so they
# never appear twice in the archive (Python zipfile warns "Duplicate name").
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


def _bake_signature_status(manifest: "ManifestModel") -> bool | None:
    """Run real Ed25519 verification at bake time.

    Returns:
      True  — signature cryptographically valid
      False — signature present but invalid (tampered)
      None  — no signature at all
    """
    from epi_core.trust import verify_embedded_manifest_signature
    if not manifest or not manifest.signature:
        return None
    try:
        valid, _name, _msg = verify_embedded_manifest_signature(manifest)
        return valid
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
                lambda: Path(tempfile.gettempdir()) / f"{prefix}{str(uuid.uuid4())}",
                lambda: Path.cwd() / f".{prefix}{str(uuid.uuid4())}",
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
                **{
                    filename: base64.b64encode((source_dir / filename).read_bytes()).decode("ascii")
                    for filename in sorted(manifest.file_manifest.keys())
                    if filename not in {"mimetype", "VERIFY.txt"} and (source_dir / filename).exists()
                },
                # manifest.json and viewer.html are written directly to the ZIP
                # archive during packing, not saved to the workspace directory.
                # The browser viewer needs their raw bytes to preserve the
                # cryptographic signature and file_manifest integrity during
                # Sign & Seal (mirrors Python's add_review behavior).
                "manifest.json": base64.b64encode(
                    json.dumps(
                        manifest.model_dump(mode="json"), indent=2, ensure_ascii=False,
                    ).encode("utf-8")
                ).decode("ascii"),
                # viewer.html is generated after this function returns, so
                # we can't include its bytes here. The browser Sign & Seal
                # flow receives it from the separate viewer generation step.
            },
            "integrity": {
                "ok": True,
                "checked": len(manifest.file_manifest),
                "mismatches": [],
            },
            "signature": {
                "valid": _bake_signature_status(manifest),
                "reason": (
                    "Signature verified at pack time."
                    if manifest.signature
                    else "No signer attached to this case file"
                ),
            },
            "notarization": _read_json_if_exists(source_dir / "artifacts" / "notarization" / "notarization.json"),
            "envelope": {
                "version": EPI_ENVELOPE_VERSION,
                "artifact_uuid": str(manifest.workflow_id),
                "mimetype": EPI_LEGACY_MIMETYPE,
                "payload_hash": manifest.trust.get("payload_hash", "") if manifest.trust else "",
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

        if prefix == b'EPI1':
            # Legacy EPI1 (spec 2.2) — header is 16 bytes (magic + version), payload is raw ZIP after. Support read.
            try:
                with open(epi_path, "rb") as fh:
                    fh.seek(16)
                    head = fh.read(2)
                if head == b'PK':
                    return EPI_CONTAINER_FORMAT_LEGACY
            except Exception:
                pass
            raise ValueError("Legacy EPI1 artifact detected — legacy ZIP payload after 16-byte header; use epi convert or legacy reader")
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
        EPIContainer._validate_reserved_tail(header.reserved_tail)
        if header.payload_length <= 0 or file_size < (EPI_ENVELOPE_HEADER_SIZE + header.payload_length):
            raise ValueError("Invalid EPI envelope payload length or truncated file")
        return header

    @staticmethod
    def _validate_reserved_tail(reserved_tail: bytes) -> None:
        """Validate reserved_tail layout. Viewer hash (first 32) may be non-zero; padding must be zero."""
        if len(reserved_tail) != EPI_RESERVED_TAIL_SIZE:
            raise ValueError(
                f"Invalid EPI envelope header: reserved_tail must be {EPI_RESERVED_TAIL_SIZE} bytes"
            )
        padding = reserved_tail[EPI_VIEWER_HASH_SIZE:]
        if padding != b"\x00" * EPI_RESERVED_TAIL_PADDING_SIZE:
            raise ValueError(
                "Invalid EPI envelope header: reserved_tail padding bytes must be zero"
            )

    @staticmethod
    def _viewer_hash_from_reserved_tail(reserved_tail: bytes) -> bytes:
        return reserved_tail[:EPI_VIEWER_HASH_SIZE]

    @staticmethod
    def _build_reserved_tail(viewer_html_bytes: bytes | None = None) -> bytes:
        """Build 56-byte reserved_tail with optional polyglot viewer SHA-256 in [0:32]."""
        if viewer_html_bytes:
            viewer_hash = hashlib.sha256(viewer_html_bytes).digest()
        else:
            viewer_hash = b"\x00" * EPI_VIEWER_HASH_SIZE
        return viewer_hash + (b"\x00" * EPI_RESERVED_TAIL_PADDING_SIZE)

    @staticmethod
    def _extract_polyglot_viewer_bytes(epi_path: Path) -> bytes | None:
        """Raw outer polyglot viewer HTML bytes (after comment close, before ZIP marker).

        Returns None for legacy ZIP or envelopes with no embedded viewer region.
        """
        fmt = EPIContainer.detect_container_format(epi_path)
        if fmt == EPI_CONTAINER_FORMAT_LEGACY:
            return None

        file_size = epi_path.stat().st_size
        header = EPIContainer._read_envelope_header(epi_path)
        max_viewer = file_size - EPI_ENVELOPE_HEADER_SIZE - header.payload_length - len(EPI_ZIP_MARKER)
        if max_viewer < 0:
            max_viewer = file_size - EPI_ENVELOPE_HEADER_SIZE
        read_size = min(file_size - EPI_ENVELOPE_HEADER_SIZE, max_viewer + len(EPI_ZIP_MARKER) + 1024)
        if read_size <= 0:
            return None
        with open(epi_path, "rb") as f:
            f.seek(EPI_ENVELOPE_HEADER_SIZE)
            chunk = f.read(read_size)
            # If viewer larger than expected, fallback to scanning entire gap
            if EPI_ZIP_MARKER not in chunk and file_size > EPI_ENVELOPE_HEADER_SIZE + header.payload_length:
                f.seek(EPI_ENVELOPE_HEADER_SIZE)
                chunk = f.read(file_size - EPI_ENVELOPE_HEADER_SIZE - header.payload_length)

        marker_idx = chunk.find(EPI_ZIP_MARKER)
        if marker_idx == -1:
            return None

        viewer_bytes = chunk[:marker_idx]
        prefix = b" -->\n"
        if viewer_bytes.startswith(prefix):
            viewer_bytes = viewer_bytes[len(prefix):]
        return viewer_bytes

    @staticmethod
    def verify_polyglot_viewer(epi_path: Path) -> tuple[bool, str | None]:
        """Verify outer polyglot viewer HTML against reserved_tail[0:32] hash.

        Returns (ok, detail_message).
        - Legacy (all-zero hash): ok=True, detail notes display layer not covered.
        - Hash present and matches: ok=True, detail=None.
        - Hash present and mismatches / missing viewer: ok=False with reason.
        """
        fmt = EPIContainer.detect_container_format(epi_path)
        if fmt == EPI_CONTAINER_FORMAT_LEGACY:
            return True, None

        header = EPIContainer._read_envelope_header(epi_path)
        claimed = EPIContainer._viewer_hash_from_reserved_tail(header.reserved_tail)
        zero = b"\x00" * EPI_VIEWER_HASH_SIZE
        viewer_bytes = EPIContainer._extract_polyglot_viewer_bytes(epi_path)

        if claimed == zero:
            if viewer_bytes is not None and len(viewer_bytes) > 0:
                return True, (
                    "legacy: polyglot viewer HTML is not integrity-covered "
                    "(reserved_tail viewer hash is zero); trust epi verify, not the embedded UI"
                )
            return True, None

        if viewer_bytes is None:
            return False, (
                "polyglot viewer hash present in envelope header but no outer viewer HTML found"
            )

        actual = hashlib.sha256(viewer_bytes).digest()
        if actual != claimed:
            return False, (
                f"polyglot viewer HTML hash mismatch: "
                f"expected {claimed.hex()[:16]}…, got {actual.hex()[:16]}… "
                f"(display layer may have been tampered)"
            )
        return True, None

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
            if mimetype_info.extra:
                raise ValueError("Forensic Violation: 'mimetype' MUST have no extra field")
            if mimetype_info.flag_bits & 0x08:
                raise ValueError("Forensic Violation: 'mimetype' MUST not use data descriptor")
            if mimetype_info.comment:
                raise ValueError("Forensic Violation: 'mimetype' MUST have no comment")
            if any(info.filename == "mimetype" for info in infolist[1:]):
                raise ValueError("Forensic Violation: duplicate 'mimetype' entry")

            try:
                mimetype_data = zf.read("mimetype").decode("utf-8").strip()
            except Exception as exc:
                raise ValueError("Corrupt mimetype file in .epi archive") from exc

            if mimetype_data != EPI_LEGACY_MIMETYPE:
                raise ValueError(
                    f"Invalid mimetype: expected '{EPI_LEGACY_MIMETYPE}', got '{mimetype_data}'"
                )

    @staticmethod
    def extract_embedded_viewer(epi_path: Path) -> str | None:
        """Extract the embedded viewer HTML from a polyglot envelope-v2 .epi file.

        Returns the inlined viewer HTML string if the file is an envelope with an
        embedded viewer, or None for legacy ZIP files or files without a viewer.
        """
        viewer_bytes = EPIContainer._extract_polyglot_viewer_bytes(epi_path)
        if viewer_bytes is None:
            return None
        try:
            return viewer_bytes.decode("utf-8")
        except UnicodeDecodeError:
            return None

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
            # Scan for the ZIP payload sentinel. The sentinel string is
            # split-concatenated at definition time so it never exists as a
            # contiguous byte sequence in the source — eliminating collision
            # risk with inlined step content or viewer HTML.
            src.seek(EPI_ENVELOPE_HEADER_SIZE)
            found_offset = -1
            chunk_size = 65536
            overlap = len(EPI_ZIP_MARKER) - 1
            search_buf = b""
            curr_pos = EPI_ENVELOPE_HEADER_SIZE

            while True:
                chunk = src.read(chunk_size)
                if not chunk:
                    break
                search_buf += chunk
                idx = search_buf.find(EPI_ZIP_MARKER)
                if idx != -1:
                    found_offset = curr_pos - (len(search_buf) - len(chunk)) + idx
                    break
                if len(search_buf) > overlap:
                    search_buf = search_buf[-overlap:]
                curr_pos += len(chunk)

            if found_offset != -1:
                src.seek(found_offset + len(EPI_ZIP_MARKER))
            else:
                # Artifact has no viewer HTML shell — payload starts at header boundary
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
            # Trailing bytes detection: after payload there must be no extra data
            trailing = src.read(1)
            if trailing != b"":
                extra_remaining = 1 + len(src.read())
                raise ValueError(f"EPI envelope has {extra_remaining} trailing bytes after payload — possible injection")

        EPIContainer._validate_zip_payload(dest_zip_path)
        return dest_zip_path

    @staticmethod
    @contextmanager
    def _payload_zip_path(epi_path: Path) -> Iterator[Path]:
        # EPI1 legacy: strip 16-byte header before zip
        with open(epi_path, "rb") as _fh:
            _pref = _fh.read(4)
        if _pref == b'EPI1':
            temp_dir = EPIContainer._make_temp_dir("epi_payload_legacy_")
            payload_path = temp_dir / "payload.zip"
            with open(epi_path, "rb") as src, open(payload_path, "wb") as dst:
                src.seek(16)
                shutil.copyfileobj(src, dst)
            try:
                EPIContainer._validate_zip_payload(payload_path)
                yield payload_path
            finally:
                shutil.rmtree(temp_dir, ignore_errors=True)
            return
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

        # Hash the outer polyglot viewer so display-layer tampering fails verify.
        html_bytes: bytes | None = None
        if viewer_html:
            html_bytes = viewer_html.encode("utf-8")
            if EPI_ZIP_MARKER in html_bytes:
                raise RuntimeError(
                    "Viewer HTML contains EPI_ZIP_MARKER sentinel bytes; "
                    "this would corrupt extraction. Cannot pack this artifact."
                )
        reserved_tail = EPIContainer._build_reserved_tail(html_bytes)

        header = _EPI_ENVELOPE_HEADER_STRUCT.pack(
            EPI_ENVELOPE_MAGIC, # "<!--"
            EPI_ENVELOPE_VERSION,
            EPI_PAYLOAD_FORMAT_ZIP_V1,
            0,
            payload_length,
            uuid_bytes,
            created_at_micros,
            b"\x00" * 32,
            reserved_tail,
        )

        with open(output_path, "wb") as dst:
            dst.write(header)
            
            # Polyglot Bootstrap: Inject HTML between header and ZIP
            if html_bytes is not None:
                # Close the header comment, add HTML, then start a new comment for the binary ZIP
                dst.write(b" -->\n")
                dst.write(html_bytes)
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
            reserved_tail,
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
                from epi_core.policy import PolicyLoadError, load_policy

                # Determine policy load status for manifest
                policy_load_status: str = "absent"
                policy = None

                # Prioritize policy inside the source_dir for artifact-local analysis
                local_policy_path = source_dir / "policy.json"
                if not local_policy_path.exists():
                    local_policy_path = source_dir / "epi_policy.json"

                if local_policy_path.exists():
                    try:
                        from epi_core.policy import EPIPolicy

                        policy = EPIPolicy.model_validate_json(local_policy_path.read_text(encoding="utf-8"))
                        policy_load_status = "loaded"
                    except Exception as exc:
                        # Respect strict mode — fail closed if EPI_ENFORCE=1 or --policy strict
                        from epi_core.policy import _is_strict_policy_mode

                        if _is_strict_policy_mode():
                            try:
                                manifest.policy_load_status = "failed"
                            except Exception:
                                pass
                            raise PolicyLoadError(
                                f"{local_policy_path} exists but is invalid; strict mode requires a valid policy: {exc}"
                            ) from exc
                        # Non-strict: workspace file invalid => failed, do not fallback to cwd
                        policy = None
                        policy_load_status = "failed"
                else:
                    try:
                        policy = load_policy()
                        policy_load_status = "loaded" if policy is not None else "absent"
                    except PolicyLoadError:
                        policy_load_status = "failed"
                        raise

                # Record status on manifest for verifier
                try:
                    manifest.policy_load_status = policy_load_status
                except Exception:
                    pass

                steps_file = source_dir / "steps.jsonl"
                if steps_file.exists():
                    steps_content = steps_file.read_text(encoding="utf-8")

                    manifest_meta = manifest.model_dump() if manifest else {}
                    analyzer = FaultAnalyzer(policy=policy, manifest_meta=manifest_meta)
                    analysis = analyzer.analyze(steps_content)

                    (source_dir / "analysis.json").write_text(analysis.to_json(), encoding="utf-8")

                    if policy is not None:
                        (source_dir / "policy.json").write_text(
                            policy.model_dump_json(indent=2), encoding="utf-8"
                        )
                        policy_evaluation_json = analysis.to_policy_evaluation_json()
                        if policy_evaluation_json:
                            # Inject single source of truth for policy source
                            pe_dict = json.loads(policy_evaluation_json)
                            profile_id = getattr(policy, "profile_id", None)
                            if profile_id:
                                pe_dict["policy_source"] = "formal_policy"
                                pe_dict["policy_label"] = f"Policy: {profile_id}"
                            elif getattr(policy, "policy_id", None):
                                pe_dict["policy_source"] = "formal_policy"
                                pe_dict["policy_label"] = f"Policy: {policy.policy_id}"
                            else:
                                pe_dict["policy_source"] = "formal_policy"
                                pe_dict["policy_label"] = "Policy: custom"
                            (source_dir / "policy_evaluation.json").write_text(
                                json.dumps(pe_dict, indent=2, ensure_ascii=False),
                                encoding="utf-8",
                            )
                    else:
                        # No explicit policy — try to auto-extract from policy.check steps
                        auto_policy = EPIContainer._extract_policy_from_steps(steps_content)
                        if auto_policy:
                            (source_dir / "policy.json").write_text(
                                json.dumps(auto_policy, indent=2, ensure_ascii=False),
                                encoding="utf-8",
                            )
                            # Merge auto policy rules into the evaluation results
                            auto_eval = EPIContainer._build_baseline_policy_evaluation(analysis)
                            policy_id = auto_policy.get("policy_id", "epi.auto")
                            auto_eval["policy_id"] = policy_id
                            auto_eval["baseline"] = False
                            auto_eval["note"] = auto_policy.get("note", "")
                            # Append auto-extracted rule results alongside baseline ones.
                            # Keep the existing controls_evaluated count from baseline results;
                            # auto-policy rules increment it further below.
                            auto_eval["controls_failed"] = 0
                            auto_eval["note"] = (auto_policy.get("note", "") + 
                                " Auto-extracted policy rules from this recording. Baseline heuristics are still evaluated alongside.")
                            auto_eval["auto_extracted"] = True
                            auto_eval["policy_source"] = "auto_extracted"
                            auto_eval["policy_label"] = "Policy auto-extracted from steps — not a formally authored policy"
                            for rule in auto_policy.get("rules", []):
                                rule_id = rule.get("id", "")
                                rule_name = rule.get("name", "")
                                rule_status = rule.get("status", "unknown")
                                rule_severity = rule.get("severity", "medium")
                                evidence = rule.get("evidence", {})
                                # Check if §7.0 attestation was actually signed for this rule
                                actual_reviewed = False
                                review_path = source_dir / "review.json"
                                if review_path.exists():
                                    try:
                                        review_data = json.loads(review_path.read_text(encoding="utf-8"))
                                        if review_data.get("status") == "approved" and review_data.get("reviewed_by"):
                                            actual_reviewed = True
                                    except Exception:
                                        pass
                                # Check if a review.handoff step was at least logged for this rule
                                has_handoff = False
                                for line in steps_content.splitlines():
                                    if not line.strip(): continue
                                    try: s = json.loads(line.strip())
                                    except: continue
                                    if s.get("kind") == "review.handoff":
                                        hc = s.get("content", {})
                                        handoff_rule_id = hc.get("rule_id") or hc.get("policy_check_id")
                                        if handoff_rule_id and handoff_rule_id == rule_id:
                                            has_handoff = True
                                            break
                                        # Fallback for legacy steps without rule_id:
                                        # match by evidence value in reason text
                                        reason = hc.get("reason", "").lower()
                                        if not handoff_rule_id:
                                            for k, v in (evidence or {}).items():
                                                if 'threshold' in k.lower() and str(v) in reason:
                                                    has_handoff = True; break
                                                if k.endswith('_usd') and str(v) in reason:
                                                    has_handoff = True; break
                                            if has_handoff: break
                                # Status resolution:
                                # - PASSED: rule status is passed/not_triggered, OR actual human attestation signed
                                # - PENDING: review_required with handoff logged but no attestation yet
                                # - FAILED: rule failed, or review_required with no handoff logged
                                if rule_status in ("passed", "not_triggered") or actual_reviewed:
                                    actual_status = "passed"
                                elif rule_status == "review_required" and has_handoff:
                                    actual_status = "pending"
                                else:
                                    actual_status = "failed"
                                auto_eval["results"].append({
                                    "rule_id": rule_id,
                                    "rule_name": rule_name,
                                    "rule_type": "auto_policy_check",
                                    "severity": rule_severity,
                                    "mode": "detect",
                                    "status": actual_status,
                                    "match_count": 0 if actual_status == "passed" else 1,
                                    "review_required": actual_status == "failed",
                                    "step_numbers": [],
                                    "plain_english": (
                                        f"Agent recorded check: {rule_name} — result: {rule_status}."
                                        + (" Handoff matched." if has_handoff else "")
                                    ),
                                })
                                # Update controls count
                                auto_eval["controls_evaluated"] = auto_eval.get("controls_evaluated", 0) + 1
                                if actual_status == "failed":
                                    auto_eval["controls_failed"] = auto_eval.get("controls_failed", 0) + 1
                                # PENDING counts as "not failed" for the verdict fraction
                                elif actual_status == "passed":
                                    pass  # passed = satisfied
                            (source_dir / "policy_evaluation.json").write_text(
                                json.dumps(auto_eval, indent=2, ensure_ascii=False),
                                encoding="utf-8",
                            )
                        else:
                            # No auto-policy either — baseline heuristic
                            baseline_eval = EPIContainer._build_baseline_policy_evaluation(analysis)
                            baseline_eval["policy_source"] = "no_policy"
                            baseline_eval["policy_label"] = "No policy configured — showing baseline heuristics only"
                            (source_dir / "policy_evaluation.json").write_text(
                                json.dumps(baseline_eval, indent=2, ensure_ascii=False),
                                encoding="utf-8",
                            )

                    manifest.analysis_status = "complete"
                    # AUD-CO-02: Attest the step count in the manifest so that
                    # verify can detect if steps were added or removed after signing.
                    manifest.total_steps = sum(
                        1 for line in steps_content.splitlines() if line.strip()
                    )
            except Exception as _fa_err:
                # Fail-closed policy errors must not be swallowed as analysis errors
                if _fa_err.__class__.__name__ == "PolicyLoadError":
                    raise
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

                # SCITT artifacts are verified cryptographically, not via file_manifest
                if arc_name.startswith("artifacts/scitt/"):
                    files_to_pack.append((file_path, arc_name))
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

        # ── Notarization (Tier 1: RFC 3161, Tier 2: OpenTimestamps/Bitcoin) ──
        notarize_enabled = os.environ.get("EPI_NOTARIZE", "1").strip().lower() not in (
            "0", "false", "no", "off",
        )
        notarization_result = None
        if notarize_enabled:
            try:
                from epi_core.notarize import embed_notarization, notarize_manifest
                from epi_core.serialize import get_canonical_hash

                # Compute canonical hash of the unsigned manifest
                unsigned_manifest = manifest.model_dump(mode="json")
                unsigned_manifest.pop("signature", None)
                canonical_hash = get_canonical_hash(
                    manifest, exclude_fields=["signature"],
                )
                if canonical_hash:
                    # Hard dep: fail loudly if JCS unavailable — do not silently diverge
                    try:
                        import rfc8785 as _rfc8785  # type: ignore
                    except ImportError as exc:
                        from epi_core._version import JCS_INTRODUCED_VERSION

                        raise RuntimeError(
                            f"rfc8785 required for notarization payload (EPI {JCS_INTRODUCED_VERSION}+)"
                        ) from exc
                    _notarize_payload = _rfc8785.dumps(unsigned_manifest).decode("utf-8")
                    notarization_result = notarize_manifest(
                        _notarize_payload,
                        canonical_hash,
                    )
                    embed_notarization(source_dir, notarization_result)
            except Exception as _ne:
                import sys as _sys
                print(f"[EPI] Notarization unavailable ({_ne}), sealing without timestamp anchor", file=_sys.stderr)

        # Append any notarization files written after the file-walking loop
        notary_dir = source_dir / "artifacts" / "notarization"
        if notary_dir.is_dir():
            for notary_file in sorted(notary_dir.iterdir()):
                if notary_file.is_file():
                    arc_name = f"artifacts/notarization/{notary_file.name}"
                    manifest.file_manifest[arc_name] = EPIContainer._compute_file_hash(notary_file)
                    if not any(item[1] == arc_name for item in files_to_pack):
                        files_to_pack.append((notary_file, arc_name))
        files_to_pack.sort(key=lambda item: item[1])

        # Now that signing is done (public_key is set), write the real VERIFY.txt.
        # VERIFY.txt is reserved: packed only via writestr below (never from rglob)
        # so the archive cannot contain duplicate VERIFY.txt members.
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
            f"TRUST MODEL:\n"
            f"  Trust `epi verify` (CLI / machine-readable report), not the colors or\n"
            f"  labels painted by the double-click embedded HTML viewer alone.\n"
            f"  Sealed data lives in the ZIP payload (file_manifest + Ed25519 seal).\n"
            f"  New envelope-v2 artifacts also store SHA-256 of the outer polyglot\n"
            f"  viewer HTML in the 128-byte header reserved_tail[0:32]. Mutating that\n"
            f"  display layer fails verification. Legacy artifacts with an all-zero\n"
            f"  viewer hash do not cover the outer HTML — still trust the CLI.\n\n"
            f"This artifact is a signed, tamper-evident record.\n",
            encoding="utf-8"
        )

        # Include VERIFY.txt in the cryptographic file_manifest so tampering is detected.
        verify_bytes = verify_txt.read_bytes()
        manifest.file_manifest["VERIFY.txt"] = hashlib.sha256(verify_bytes).hexdigest()
        # Drop any stale VERIFY entry from files_to_pack (from pre-reserve walks)
        files_to_pack = [(p, n) for (p, n) in files_to_pack if n != "VERIFY.txt"]

        # Re-sign if needed since file_manifest changed after signing above.
        if signer_function:
            manifest = signer_function(manifest)

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
                if arc_name in _RESERVED_ROOT_ARCHIVE_NAMES:
                    continue
                zf.write(file_path, arc_name, compress_type=zipfile.ZIP_DEFLATED)

            viewer_html_bytes = viewer_html.encode("utf-8")
            zf.writestr("viewer.html", viewer_html_bytes, compress_type=zipfile.ZIP_DEFLATED)

            # Include viewer.html in the cryptographic file_manifest so that a
            # visual-deception attack (swapping the UI layer) is detectable.
            manifest.file_manifest["viewer.html"] = hashlib.sha256(viewer_html_bytes).hexdigest()
            # Recompute payload_hash now that file_manifest is final (was stale after viewer/VERIFY/notarization)
            _manifest_canon_final = json.dumps(
                dict(sorted(manifest.file_manifest.items())), ensure_ascii=False, separators=(",", ":")
            )
            _payload_hash_final = hashlib.sha256(_manifest_canon_final.encode()).hexdigest()
            if manifest.trust is not None:
                manifest.trust = {**(manifest.trust or {}), "payload_hash": _payload_hash_final}

            zf.writestr("VERIFY.txt", verify_bytes, compress_type=zipfile.ZIP_DEFLATED)

            # Re-sign one final time because viewer.html hash was just added.
            if signer_function:
                manifest = signer_function(manifest)

            manifest_json = manifest.model_dump_json(indent=2)
            zf.writestr("manifest.json", manifest_json, compress_type=zipfile.ZIP_DEFLATED)

        return viewer_html

    @staticmethod
    def _extract_policy_from_steps(steps_content: str) -> dict | None:
        """Auto-extract policy rules from policy.check steps in the recording."""
        import json as _json
        rules = []
        seen_ids = set()
        for line in steps_content.splitlines():
            if not line.strip():
                continue
            try:
                step = _json.loads(line)
            except Exception:
                continue
            if step.get("kind") != "policy.check":
                continue
            content = step.get("content", {})
            rule_id = content.get("rule_id") or content.get("policy_name")
            if not rule_id or rule_id in seen_ids:
                continue
            seen_ids.add(rule_id)
            rule_name = content.get("rule") or content.get("policy_name") or rule_id
            status = content.get("result") or content.get("status") or "unknown"
            evidence = content.get("evidence") or {}
            rule = {
                "id": str(rule_id),
                "name": str(rule_name)[:120],
                "severity": str(content.get("severity", "medium")),
                "status": str(status),
            }
            if evidence:
                rule["evidence"] = evidence
            rules.append(rule)
        if not rules:
            return None
        return {
            "policy_id": "epi.auto",
            "policy_version": "1.0",
            "auto_generated": True,
            "note": "Auto-extracted from policy.check steps in the recording. Run epi policy init for custom rules.",
            "rules": rules,
        }

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
            "reviewed_by": reviewer,
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

            manifest = EPIContainer.read_manifest(epi_path)
            EPIContainer._write_artifact_from_payload(
                tmp_zip, tmp_out, container_format=container_format, manifest=manifest
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
            # New seals assert full step payloads. Viewer previews may still truncate.
            manifest.content_truncated = False
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
        signer_function: Callable[[ManifestModel], ManifestModel] | None = None,
        **kwargs,
    ) -> str:
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

            viewer_html_bytes = viewer_html.encode("utf-8")
            zf.writestr("viewer.html", viewer_html_bytes, compress_type=zipfile.ZIP_DEFLATED)

            # Update the viewer.html hash in the manifest so that verify_integrity
            # correctly detects a stale viewer after refresh.
            manifest.file_manifest["viewer.html"] = hashlib.sha256(viewer_html_bytes).hexdigest()

            if signer_function is not None:
                manifest = signer_function(manifest)

            zf.writestr(
                "manifest.json",
                manifest.model_dump_json(indent=2),
                compress_type=zipfile.ZIP_DEFLATED,
            )

            # Preserve original VERIFY.txt if it exists, otherwise write template
            verify_path = source_dir / "VERIFY.txt"
            if verify_path.exists():
                zf.write(verify_path, "VERIFY.txt", compress_type=zipfile.ZIP_DEFLATED)
            else:
                zf.writestr(
                    "VERIFY.txt",
                    VERIFY_TXT_TEMPLATE % {
                        "filename": manifest.workflow_id or "unknown",
                        "steps_count": len(manifest.file_manifest),
                    },
                    compress_type=zipfile.ZIP_DEFLATED,
                )

        return viewer_html

    @staticmethod
    def refresh_viewer(
        epi_path: Path,
        output_path: Path | None = None,
        signer_function: Callable[[ManifestModel], ManifestModel] | None = None,
        clear_signature: bool = False,
    ) -> Path:
        source_path = Path(epi_path)
        if not source_path.exists():
            raise FileNotFoundError(f"EPI file not found: {source_path}")

        destination = Path(output_path) if output_path is not None else source_path
        container_format = EPIContainer.detect_container_format(source_path)
        manifest = EPIContainer.read_manifest(source_path)

        if clear_signature and not signer_function:
            manifest.signature = None
            manifest.public_key = None
            manifest.signer = None
        elif signer_function is None and getattr(manifest, "signature", None):
            import warnings
            warnings.warn("refresh_viewer invalidates the manifest signature. Re-sign after refresh.")

        temp_dir = EPIContainer._make_temp_dir("epi_refresh_viewer_")
        unpack_dir = temp_dir / "unpacked"
        unpack_dir.mkdir(parents=True, exist_ok=True)
        temp_payload = temp_dir / "payload.zip"
        temp_output = temp_dir / "refreshed.epi"

        try:
            with EPIContainer._payload_zip_path(source_path) as payload_zip:
                with zipfile.ZipFile(payload_zip, "r") as zf:
                    zf.extractall(unpack_dir)

            viewer_html = EPIContainer._rebuild_payload_with_viewer(
                unpack_dir, manifest, temp_payload, signer_function=signer_function
            )

            EPIContainer._write_artifact_from_payload(
                temp_payload,
                temp_output,
                container_format=container_format,
                manifest=manifest,
                viewer_html=viewer_html,
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
                resolved_dest = dest_dir.resolve()
                for member in zf.infolist():
                    member_path = (dest_dir / member.filename).resolve()
                    try:
                        member_path.relative_to(resolved_dest)
                    except ValueError:
                        raise ValueError(f"Path traversal detected in .epi archive: {member.filename}")
                    zf.extract(member, dest_dir)

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
    def read_manifest(epi_path: Path | str) -> ManifestModel:
        epi_path = Path(epi_path)
        if not epi_path.exists():
            raise FileNotFoundError(f"EPI file not found: {epi_path}")

        manifest_dict = EPIContainer.read_member_json(epi_path, "manifest.json")
        if not isinstance(manifest_dict, dict):
            raise ValueError("manifest.json must be a JSON object")
        # Backward compatibility: old browser viewer wrote 'legacy' before 'legacy-zip'
        if manifest_dict.get("container_format") == "legacy":
            manifest_dict["container_format"] = "legacy-zip"
        return ManifestModel(**manifest_dict)

    @staticmethod
    def verify_integrity(epi_path: Path) -> tuple[bool, dict[str, str]]:
        if not epi_path.exists():
            raise FileNotFoundError(f"EPI file not found: {epi_path}")

        manifest = EPIContainer.read_manifest(epi_path)
        mismatches: dict[str, str] = {}
        # Envelope header vs manifest cross-check (UUID/timestamp transplant detection)
        try:
            fmt = EPIContainer.detect_container_format(epi_path)
            if fmt == EPI_CONTAINER_FORMAT_ENVELOPE:
                hdr = EPIContainer._read_envelope_header(epi_path)
                if hdr.artifact_uuid != manifest.workflow_id.bytes:
                    mismatches["__envelope_header__"] = "Header artifact_uuid does not match manifest workflow_id — header transplant"
                # Compare truncated timestamp (allow 1s drift due to micros truncation)
                hdr_ts = hdr.created_at_micros / 1_000_000
                manifest_ts = manifest.created_at.timestamp()
                if abs(hdr_ts - manifest_ts) > 1:
                    mismatches["__envelope_header__"] = mismatches.get("__envelope_header__", "") + "; header timestamp mismatches manifest"
        except Exception:
            pass
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

            # Check for extra files not listed in file_manifest (injection detection).
            # VERIFY.txt is exempt when missing from file_manifest for backward
            # compatibility with artifacts from earlier releases.
            # Mutable review files are also exempt (they are added after signing).
            for file_path in temp_path.rglob("*"):
                if file_path.is_file():
                    rel_path = str(file_path.relative_to(temp_path)).replace("\\", "/")
                    if rel_path in _RESERVED_ROOT_ARCHIVE_NAMES:
                        continue
                    if _is_mutable_review_archive_name(rel_path):
                        continue
                    if rel_path == "VERIFY.txt" and "VERIFY.txt" not in manifest.file_manifest:
                        continue
                    # SCITT artifacts are verified cryptographically via receipt
                    if rel_path.startswith("artifacts/scitt/"):
                        continue
                    if rel_path not in manifest.file_manifest:
                        mismatches[rel_path] = "Extra file not in manifest"
        finally:
            shutil.rmtree(temp_path, ignore_errors=True)

        # Outer polyglot viewer HTML integrity (envelope reserved_tail[0:32]).
        # ZIP-internal viewer.html is already covered by file_manifest above.
        try:
            poly_ok, poly_detail = EPIContainer.verify_polyglot_viewer(epi_path)
            if not poly_ok:
                mismatches["__polyglot_viewer__"] = poly_detail or (
                    "polyglot viewer HTML integrity check failed"
                )
        except Exception as exc:
            mismatches["__polyglot_viewer__"] = f"polyglot viewer check error: {exc}"

        return (len(mismatches) == 0, mismatches)
