"""Artifact container and model types."""
from __future__ import annotations

from epi_core.artifact_inspector import ArtifactInspectionError, ensure_shareable_artifact
from epi_core.container import (
    EPI_MIMETYPE,
    EPI_SUPPORTED_UPLOAD_MIMETYPES,
    EPIContainer,
)
from epi_core.schemas import ManifestModel, StepModel

open_artifact = EPIContainer


def is_epi_mimetype(value: str | None) -> bool:
    return value == EPI_MIMETYPE


supported_upload_mimetypes = EPI_SUPPORTED_UPLOAD_MIMETYPES

__all__ = [
    "ArtifactInspectionError",
    "EPIContainer",
    "EPI_MIMETYPE",
    "EPI_SUPPORTED_UPLOAD_MIMETYPES",
    "ManifestModel",
    "StepModel",
    "ensure_shareable_artifact",
    "is_epi_mimetype",
    "open_artifact",
    "supported_upload_mimetypes",
]
