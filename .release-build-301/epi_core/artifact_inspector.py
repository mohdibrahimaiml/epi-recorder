"""
Shared helpers for validating and inspecting portable .epi artifacts.

These helpers keep the CLI and gateway aligned on what counts as a valid,
shareable EPI bundle without changing the artifact format itself.
"""

from __future__ import annotations

import dataclasses
import zipfile
from pathlib import Path
from typing import Optional

from epi_core.container import EPIContainer, EPI_MIMETYPE
from epi_core.schemas import ManifestModel
from epi_core.trust import verify_embedded_manifest_signature


class ArtifactInspectionError(ValueError):
    """Raised when a .epi artifact is structurally invalid or unsafe to trust."""


@dataclasses.dataclass(frozen=True)
class ArtifactInspectionResult:
    manifest: ManifestModel
    integrity_ok: bool
    mismatches: dict[str, str]
    signature_valid: Optional[bool]
    signer_name: Optional[str]
    signature_message: str
    steps_count: int

    @property
    def workflow_id(self) -> str:
        return str(self.manifest.workflow_id)

    @property
    def artifact_created_at(self) -> str:
        return self.manifest.created_at.isoformat()

    @property
    def signature_status(self) -> str:
        return "verified" if self.signature_valid is True else "unsigned"

    @property
    def is_shareable(self) -> bool:
        return self.integrity_ok and self.signature_valid is not False


def inspect_artifact(epi_path: Path) -> ArtifactInspectionResult:
    """
    Validate a .epi file and return the metadata needed for review or sharing.

    Requirements enforced here:
    - valid ZIP archive
    - mimetype file present and correct
    - manifest.json present and schema-valid
    - steps.jsonl present
    - integrity intact
    - signature either valid or absent (unsigned)
    """
    if not epi_path.exists():
        raise FileNotFoundError(f"EPI file not found: {epi_path}")

    if not zipfile.is_zipfile(epi_path):
        raise ArtifactInspectionError(f"Not a valid ZIP file: {epi_path}")

    try:
        with zipfile.ZipFile(epi_path, "r") as archive:
            names = set(archive.namelist())
            if "mimetype" not in names:
                raise ArtifactInspectionError("Missing mimetype file in .epi archive")
            mimetype_value = archive.read("mimetype").decode("utf-8").strip()
            if mimetype_value != EPI_MIMETYPE:
                raise ArtifactInspectionError(
                    f"Invalid mimetype: expected '{EPI_MIMETYPE}', got '{mimetype_value}'"
                )
            if "manifest.json" not in names:
                raise ArtifactInspectionError("Missing manifest.json in .epi archive")
            if "steps.jsonl" not in names:
                raise ArtifactInspectionError("Missing steps.jsonl in .epi archive")
            steps_count = _count_steps_from_archive(archive)
    except UnicodeDecodeError as exc:
        raise ArtifactInspectionError("Corrupt mimetype file in .epi archive") from exc
    except zipfile.BadZipFile as exc:
        raise ArtifactInspectionError("Corrupt ZIP structure in .epi archive") from exc

    try:
        manifest = EPIContainer.read_manifest(epi_path)
    except Exception as exc:
        raise ArtifactInspectionError(str(exc)) from exc

    integrity_ok, mismatches = EPIContainer.verify_integrity(epi_path)
    signature_valid, signer_name, signature_message = verify_embedded_manifest_signature(manifest)

    return ArtifactInspectionResult(
        manifest=manifest,
        integrity_ok=integrity_ok,
        mismatches=mismatches,
        signature_valid=signature_valid,
        signer_name=signer_name,
        signature_message=signature_message,
        steps_count=steps_count,
    )


def ensure_shareable_artifact(epi_path: Path) -> ArtifactInspectionResult:
    """
    Validate an artifact for hosted sharing.

    Share links accept:
    - integrity OK + valid signature
    - integrity OK + unsigned artifact

    Share links reject:
    - structural failures
    - integrity mismatches
    - invalid signatures
    """
    result = inspect_artifact(epi_path)
    if not result.integrity_ok:
        raise ArtifactInspectionError(
            f"Integrity check failed ({len(result.mismatches)} mismatch"
            f"{'' if len(result.mismatches) == 1 else 'es'})"
        )
    if result.signature_valid is False:
        raise ArtifactInspectionError(result.signature_message)
    return result


def _count_steps_from_archive(archive: zipfile.ZipFile) -> int:
    try:
        raw_steps = archive.read("steps.jsonl").decode("utf-8")
    except KeyError as exc:
        raise ArtifactInspectionError("Missing steps.jsonl in .epi archive") from exc
    except UnicodeDecodeError as exc:
        raise ArtifactInspectionError("steps.jsonl is not valid UTF-8") from exc
    return len([line for line in raw_steps.splitlines() if line.strip()])
