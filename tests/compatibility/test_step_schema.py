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
    "source_type",
}


def test_step_model_fields_are_frozen():
    actual = set(StepModel.model_fields.keys())
    assert actual == FROZEN_STEP_FIELDS, (
        f"StepModel fields changed.\n"
        f"Added: {actual - FROZEN_STEP_FIELDS}\n"
        f"Removed: {FROZEN_STEP_FIELDS - actual}"
    )


def test_step_model_source_type_auto_population():
    # Test tool response mapping
    s = StepModel(index=0, kind="tool.response", content={})
    assert s.source_type == "tool"

    # Test user approval response mapping
    s = StepModel(index=1, kind="agent.approval.response", content={})
    assert s.source_type == "user"

    # Test agent message mapping by role
    s1 = StepModel(index=2, kind="agent.message", content={"role": "user"})
    assert s1.source_type == "user"
    s2 = StepModel(index=3, kind="agent.message", content={"role": "system"})
    assert s2.source_type == "system"
    s3 = StepModel(index=4, kind="agent.message", content={"role": "assistant"})
    assert s3.source_type == "reasoning"

    # Test LLM and decision steps mapping to reasoning
    s = StepModel(index=5, kind="llm.request", content={})
    assert s.source_type == "reasoning"
    s = StepModel(index=6, kind="agent.decision", content={})
    assert s.source_type == "reasoning"

    # Test system / validation steps
    s = StepModel(index=7, kind="validation.pass", content={"validator": "test", "result": "pass"})
    assert s.source_type == "system"
    s = StepModel(index=8, kind="security.redaction", content={})
    assert s.source_type == "system"

    # Test explicit overriding
    s = StepModel(index=9, kind="tool.response", content={}, source_type="user")
    assert s.source_type == "user"
