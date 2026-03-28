"""
EPI Core - Core data structures, serialization, and container management.
"""

from epi_core._version import get_version

__version__ = get_version()

from epi_core.capture import (
    CAPTURE_SPEC_VERSION,
    CaptureBatchModel,
    CaptureEventModel,
    CaptureProvenanceModel,
    build_capture_batch,
    coerce_capture_event,
)
from epi_core.case_store import (
    CaseExportResultModel,
    CaseReviewModel,
    CaseSummaryModel,
    DecisionCaseModel,
)
from epi_core.llm_capture import LLMCaptureRequest, build_llm_capture_events, normalize_provider_name
from epi_core.schemas import ManifestModel, StepModel
from epi_core.serialize import get_canonical_hash

__all__ = [
    "CAPTURE_SPEC_VERSION",
    "CaptureBatchModel",
    "CaptureEventModel",
    "CaptureProvenanceModel",
    "CaseExportResultModel",
    "CaseReviewModel",
    "CaseSummaryModel",
    "DecisionCaseModel",
    "LLMCaptureRequest",
    "build_capture_batch",
    "build_llm_capture_events",
    "coerce_capture_event",
    "ManifestModel",
    "StepModel",
    "get_canonical_hash",
    "normalize_provider_name",
]



 
