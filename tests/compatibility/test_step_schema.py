"""
Lock the StepModel field set.
"""

from epi_core.schemas import StepModel

FROZEN_STEP_FIELDS = {
    "index",
    "timestamp",
    "kind",
    "content",
    "trace_id",
    "span_id",
    "parent_span_id",
    "prev_hash",
    "governance",
}


def test_step_model_fields_are_frozen():
    actual = set(StepModel.model_fields.keys())
    assert actual == FROZEN_STEP_FIELDS, (
        f"StepModel fields changed.\n"
        f"Added: {actual - FROZEN_STEP_FIELDS}\n"
        f"Removed: {FROZEN_STEP_FIELDS - actual}"
    )
