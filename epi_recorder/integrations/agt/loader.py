"""
Input loaders for importing AGT evidence into the neutral AGT bundle contract.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .schema import AGTBundleMetadataModel, AGTBundleModel, coerce_agt_bundle

DEFAULT_AGT_IMPORT_MANIFEST = "agt_import_manifest.json"

_JSON_SECTION_FILENAMES: dict[str, str] = {
    "audit_logs": "audit_logs.json",
    "flight_recorder": "flight_recorder.json",
    "compliance_report": "compliance_report.json",
    "policy_document": "policy_document.json",
    "runtime_context": "runtime_context.json",
    "slo_data": "slo_data.json",
    "annex_json": "annex_iv.json",
    "review": "review.json",
}
_TEXT_SECTION_FILENAMES: dict[str, str] = {
    "annex_markdown": "annex_iv.md",
}
_ALL_SECTION_NAMES = tuple(_JSON_SECTION_FILENAMES) + tuple(_TEXT_SECTION_FILENAMES)
_EXECUTION_EVIDENCE_SECTIONS = ("audit_logs", "flight_recorder")
_KNOWN_AGT_FILENAMES = tuple(_JSON_SECTION_FILENAMES.values()) + tuple(_TEXT_SECTION_FILENAMES.values())


class AGTInputError(ValueError):
    """Raised when an AGT import input cannot be resolved into a bundle."""


class _AGTImportManifestFilesModel(BaseModel):
    audit_logs: str | None = None
    flight_recorder: str | None = None
    compliance_report: str | None = None
    policy_document: str | None = None
    runtime_context: str | None = None
    slo_data: str | None = None
    annex_json: str | None = None
    annex_markdown: str | None = None
    review: str | None = None

    model_config = ConfigDict(extra="forbid")


class _AGTImportManifestModel(BaseModel):
    metadata: AGTBundleMetadataModel = Field(default_factory=AGTBundleMetadataModel)
    files: _AGTImportManifestFilesModel

    model_config = ConfigDict(extra="forbid")


def load_agt_input(path: Path) -> AGTBundleModel:
    """Load AGT input from a bundle JSON file, an evidence directory, or a manifest."""

    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"AGT input not found: {path}")

    if path.is_dir():
        return _load_directory(path)

    if not path.is_file():
        raise AGTInputError(f"AGT input must be a file or directory: {path}")

    payload = _read_json_file(path, section_name="input file")
    try:
        return coerce_agt_bundle(payload)
    except Exception as bundle_error:
        if not isinstance(payload, Mapping) or "files" not in payload:
            single_section_hint = _single_section_file_hint(path)
            raise AGTInputError(
                "AGT JSON input did not match a supported import shape. "
                f"{_supported_input_shapes_message()} "
                f"{single_section_hint}".strip()
            ) from bundle_error

        try:
            manifest = _AGTImportManifestModel.model_validate(payload)
        except ValidationError as manifest_error:
            raise AGTInputError(
                f"Invalid AGT import manifest at {path}: {_flatten_validation_error(manifest_error)}"
            ) from manifest_error
        return _assemble_bundle(path.parent, manifest=manifest)


def _load_directory(directory: Path) -> AGTBundleModel:
    manifest_path = directory / DEFAULT_AGT_IMPORT_MANIFEST
    manifest: _AGTImportManifestModel | None = None
    if manifest_path.exists():
        payload = _read_json_file(manifest_path, section_name="AGT import manifest")
        try:
            manifest = _AGTImportManifestModel.model_validate(payload)
        except ValidationError as exc:
            raise AGTInputError(
                f"Invalid AGT import manifest at {manifest_path}: {_flatten_validation_error(exc)}"
            ) from exc
    elif not _discover_present_sections(directory):
        expected = ", ".join(_KNOWN_AGT_FILENAMES)
        raise AGTInputError(
            f"No recognized AGT files were found in directory: {directory}. "
            f"Expected files like {expected}. "
            f"If your filenames differ, add {DEFAULT_AGT_IMPORT_MANIFEST} with a top-level 'files' mapping."
        )
    return _assemble_bundle(directory, manifest=manifest)


def _assemble_bundle(
    root: Path,
    *,
    manifest: _AGTImportManifestModel | None = None,
) -> AGTBundleModel:
    resolved_files = _resolve_section_paths(root, manifest=manifest)
    _validate_manifest_targets(resolved_files, root, manifest=manifest)

    payload: dict[str, Any] = {}
    for section_name in _JSON_SECTION_FILENAMES:
        section_path = resolved_files.get(section_name)
        if section_path is not None:
            payload[section_name] = _read_json_file(section_path, section_name=section_name)

    annex_markdown_path = resolved_files.get("annex_markdown")
    if annex_markdown_path is not None:
        payload["annex_markdown"] = annex_markdown_path.read_text(encoding="utf-8")

    if not payload.get("audit_logs") and not payload.get("flight_recorder"):
        present_sections = _discover_present_sections_from_resolved_files(resolved_files)
        present_text = ", ".join(present_sections) if present_sections else "none"
        raise AGTInputError(
            "AGT input is missing execution evidence. "
            "Need at least one of audit_logs.json or flight_recorder.json. "
            f"Found recognized sections: {present_text}. "
            f"If your filenames differ, add {DEFAULT_AGT_IMPORT_MANIFEST}."
        )

    metadata = (
        manifest.metadata.model_copy(deep=True)
        if manifest is not None
        else AGTBundleMetadataModel()
    )
    _apply_metadata_fallbacks(metadata, payload.get("annex_json"))
    payload["metadata"] = metadata.model_dump(mode="json", exclude_none=True)

    try:
        return coerce_agt_bundle(payload)
    except Exception as exc:
        raise AGTInputError(f"Invalid AGT evidence input: {exc}") from exc


def _resolve_section_paths(
    root: Path,
    *,
    manifest: _AGTImportManifestModel | None,
) -> dict[str, Path | None]:
    resolved: dict[str, Path | None] = {
        key: root / filename for key, filename in _JSON_SECTION_FILENAMES.items()
    }
    resolved.update({key: root / filename for key, filename in _TEXT_SECTION_FILENAMES.items()})

    for key, value in list(resolved.items()):
        if value is not None and not value.exists():
            resolved[key] = None

    if manifest is None:
        return resolved

    for section_name in _ALL_SECTION_NAMES:
        configured = getattr(manifest.files, section_name)
        if configured is None:
            continue
        configured_path = Path(configured)
        if not configured_path.is_absolute():
            configured_path = (root / configured_path).resolve()
        resolved[section_name] = configured_path
    return resolved


def _validate_manifest_targets(
    resolved_files: Mapping[str, Path | None],
    root: Path,
    *,
    manifest: _AGTImportManifestModel | None,
) -> None:
    if manifest is None:
        return

    missing: list[str] = []
    for section_name in _ALL_SECTION_NAMES:
        configured = getattr(manifest.files, section_name)
        if configured is None:
            continue
        resolved_path = resolved_files.get(section_name)
        if resolved_path is None or not resolved_path.exists():
            display_path = Path(configured)
            if not display_path.is_absolute():
                display_path = (root / display_path).resolve()
            missing.append(f"{section_name} -> {display_path}")

    if missing:
        joined = "; ".join(missing)
        raise AGTInputError(
            f"AGT import manifest references missing file(s): {joined}. "
            "Fix those paths or remove the unused entries."
        )


def _read_json_file(path: Path, *, section_name: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise AGTInputError(
            f"Invalid JSON in AGT section '{section_name}': {exc.msg} "
            f"(line {exc.lineno}, column {exc.colno}) in {path}"
        ) from exc
    except OSError as exc:
        raise AGTInputError(f"Could not read AGT section '{section_name}' from {path}: {exc}") from exc


def _apply_metadata_fallbacks(
    metadata: AGTBundleMetadataModel,
    annex_json: Any,
) -> None:
    if not isinstance(annex_json, Mapping):
        return

    if metadata.system_name is None:
        system_name = annex_json.get("system_name")
        if isinstance(system_name, str) and system_name.strip():
            metadata.system_name = system_name.strip()

    if metadata.provider is None:
        provider = annex_json.get("provider")
        if isinstance(provider, str) and provider.strip():
            metadata.provider = provider.strip()


def _flatten_validation_error(exc: ValidationError) -> str:
    parts: list[str] = []
    for error in exc.errors():
        location = ".".join(str(part) for part in error.get("loc", ())) or "manifest"
        message = error.get("msg", "invalid value")
        parts.append(f"{location}: {message}")
    return "; ".join(parts)


def _supported_input_shapes_message() -> str:
    return (
        "Supported AGT inputs are: "
        "a neutral AGT bundle JSON with sections like audit_logs / flight_recorder, "
        "a directory containing files like audit_logs.json or flight_recorder.json, "
        f"or an AGT import manifest JSON with a top-level 'files' mapping (default name: {DEFAULT_AGT_IMPORT_MANIFEST})."
    )


def _single_section_file_hint(path: Path) -> str:
    if path.name not in _KNOWN_AGT_FILENAMES:
        return ""
    return (
        f"'{path.name}' looks like a single AGT section file, not a full import input. "
        f"Pass the directory containing the rest of the AGT files or create {DEFAULT_AGT_IMPORT_MANIFEST}."
    )


def _discover_present_sections(directory: Path) -> list[str]:
    present: list[str] = []
    for section_name, filename in _JSON_SECTION_FILENAMES.items():
        if (directory / filename).exists():
            present.append(section_name)
    for section_name, filename in _TEXT_SECTION_FILENAMES.items():
        if (directory / filename).exists():
            present.append(section_name)
    return present


def _discover_present_sections_from_resolved_files(
    resolved_files: Mapping[str, Path | None],
) -> list[str]:
    return sorted(section_name for section_name, section_path in resolved_files.items() if section_path is not None)


__all__ = ["AGTInputError", "DEFAULT_AGT_IMPORT_MANIFEST", "load_agt_input"]
