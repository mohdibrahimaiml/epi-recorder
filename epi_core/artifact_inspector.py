"""
Shared helpers for validating and inspecting portable .epi artifacts.

These helpers keep the CLI and gateway aligned on what counts as a valid,
shareable EPI bundle without changing the artifact format itself.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

from epi_core.container import EPI_LEGACY_MIMETYPE, EPIContainer
from epi_core.schemas import ManifestModel
from epi_core.trust import verify_embedded_manifest_signature


class ArtifactInspectionError(ValueError):
    """Raised when a .epi artifact is structurally invalid or unsafe to trust."""


@dataclasses.dataclass(frozen=True)
class ArtifactInspectionResult:
    manifest: ManifestModel
    integrity_ok: bool
    mismatches: dict[str, str]
    signature_valid: bool | None
    signer_name: str | None
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
    - valid legacy ZIP artifact or EPI envelope
    - mimetype file present and correct in the embedded ZIP payload
    - manifest.json present and schema-valid
    - steps.jsonl present
    - integrity intact
    - signature either valid or absent (unsigned)
    """
    if not epi_path.exists():
        raise FileNotFoundError(f"EPI file not found: {epi_path}")

    try:
        names = set(EPIContainer.list_members(epi_path))
        if "mimetype" not in names:
            raise ArtifactInspectionError("Missing mimetype file in .epi archive")
        mimetype_value = EPIContainer.read_member_text(epi_path, "mimetype").strip()
        if mimetype_value != EPI_LEGACY_MIMETYPE:
            raise ArtifactInspectionError(
                f"Invalid mimetype: expected '{EPI_LEGACY_MIMETYPE}', got '{mimetype_value}'"
            )
        if "manifest.json" not in names:
            raise ArtifactInspectionError("Missing manifest.json in .epi archive")
        if "steps.jsonl" not in names:
            raise ArtifactInspectionError("Missing steps.jsonl in .epi archive")
        steps_count = EPIContainer.count_steps(epi_path)
    except ValueError as exc:
        raise ArtifactInspectionError(str(exc)) from exc

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
