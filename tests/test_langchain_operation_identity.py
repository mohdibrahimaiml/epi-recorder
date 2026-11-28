"""LangChain adapter emits ``epi-operation/v1`` identity.

Runs without ``langchain-core`` installed: the adapter falls back to a stub
base class, and callbacks are invoked directly, so this is the only coverage
for the adapter's correlation contract in minimal environments.
"""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from epi_core.operation_identity import SCHEME, audit_event_sequence
from epi_recorder.adapters.langchain import EpiCallbackHandler

LIFECYCLE_KINDS = {
    "llm.call",
    "llm.request",
    "llm.pre_commit",
    "llm.response",
    "llm.error",
    "tool.call",
    "tool.response",
}


class _CaptureSession:
    def __init__(self) -> None:
        self.steps: list[tuple[str, dict]] = []

    def log(self, kind: str, content=None, **kwargs):
        self.steps.append((kind, dict(content or {})))


def _steps(session: _CaptureSession) -> list[dict]:
    return [
        {"index": i, "kind": kind, "content": content}
        for i, (kind, content) in enumerate(session.steps)
        if kind in LIFECYCLE_KINDS
    ]


def _corr(content: dict) -> dict:
    return content.get("correlation") or {}


def test_llm_call_and_response_share_one_identity():
    session = _CaptureSession()
    handler = EpiCallbackHandler(session)
    rid = uuid4()
    handler.on_llm_start({"name": "gpt"}, ["hi"], run_id=rid)
    handler.on_llm_end(SimpleNamespace(generations=[]), run_id=rid)

    steps = _steps(session)
    assert [s["kind"] for s in steps] == ["llm.call", "llm.response"]
    ids = {_corr(s["content"]).get("operation_id") for s in steps}
    assert len(ids) == 1 and None not in ids
    for step in steps:
        assert _corr(step["content"])["scheme"] == SCHEME
        # The framework identifier is preserved as metadata, not as the key.
        assert _corr(step["content"])["external_id"] == str(rid)
    assert audit_event_sequence(steps)["status"] == "complete"


def test_chat_model_start_is_correlated():
    session = _CaptureSession()
    handler = EpiCallbackHandler(session)
    rid = uuid4()
    handler.on_chat_model_start(
        {"name": "chat"}, [[SimpleNamespace(content="hello")]], run_id=rid
    )
    handler.on_llm_end(SimpleNamespace(generations=[]), run_id=rid)
    steps = _steps(session)
    assert [s["kind"] for s in steps] == ["llm.call", "llm.response"]
    assert audit_event_sequence(steps)["status"] == "complete"


def test_llm_error_is_a_correlated_terminal():
    session = _CaptureSession()
    handler = EpiCallbackHandler(session)
    rid = uuid4()
    handler.on_llm_start({"name": "gpt"}, ["hi"], run_id=rid)
    handler.on_llm_error(ValueError("rate limited"), run_id=rid)

    steps = _steps(session)
    assert [s["kind"] for s in steps] == ["llm.call", "llm.response"]
    assert steps[-1]["content"]["ok"] is False
    assert audit_event_sequence(steps)["status"] == "complete"


def test_tool_lifecycle_is_correlated():
    session = _CaptureSession()
    handler = EpiCallbackHandler(session)
    rid = uuid4()
    handler.on_tool_start({"name": "lookup"}, "id=1", run_id=rid)
    handler.on_tool_end({"status": "ok"}, run_id=rid)

    steps = _steps(session)
    assert [s["kind"] for s in steps] == ["tool.call", "tool.response"]
    ids = {_corr(s["content"]).get("operation_id") for s in steps}
    assert len(ids) == 1
    assert steps[0]["content"]["call_id"] == str(rid)  # legacy key preserved
    assert audit_event_sequence(steps)["status"] == "complete"


def test_tool_error_is_a_correlated_terminal():
    session = _CaptureSession()
    handler = EpiCallbackHandler(session)
    rid = uuid4()
    handler.on_tool_start({"name": "lookup"}, "id=1", run_id=rid)
    handler.on_tool_error(RuntimeError("timeout"), run_id=rid)
    steps = _steps(session)
    assert steps[-1]["content"]["ok"] is False
    assert audit_event_sequence(steps)["status"] == "complete"


def test_concurrent_runs_do_not_share_identity():
    session = _CaptureSession()
    handler = EpiCallbackHandler(session)
    a, b = uuid4(), uuid4()
    handler.on_llm_start({"name": "gpt"}, ["a"], run_id=a)
    handler.on_llm_start({"name": "gpt"}, ["b"], run_id=b)
    handler.on_llm_end(SimpleNamespace(generations=[]), run_id=b)
    handler.on_llm_end(SimpleNamespace(generations=[]), run_id=a)

    steps = _steps(session)
    by_run = {}
    for step in steps:
        by_run.setdefault(step["content"]["run_id"], set()).add(
            _corr(step["content"])["operation_id"]
        )
    assert all(len(ids) == 1 for ids in by_run.values())
    assert len({next(iter(ids)) for ids in by_run.values()}) == 2
    assert audit_event_sequence(steps)["status"] == "complete"


def test_terminal_without_start_is_an_orphan_not_ungoverned():
    session = _CaptureSession()
    handler = EpiCallbackHandler(session)
    handler.on_llm_end(SimpleNamespace(generations=[]), run_id=uuid4())
    steps = _steps(session)
    assert len(steps) == 1
    assert _corr(steps[0]["content"]).get("scheme") == SCHEME
    audit = audit_event_sequence(steps)
    assert audit["status"] == "incomplete"
    assert len(audit["orphan_terminals"]) == 1
    assert audit["ungoverned_steps"] == []


def test_every_lifecycle_step_is_correlated():
    session = _CaptureSession()
    handler = EpiCallbackHandler(session)
    handler.on_llm_start({"name": "gpt"}, ["a"], run_id=uuid4())
    handler.on_tool_start({"name": "lookup"}, "x", run_id=uuid4())
    assert len(_steps(session)) == 2
    for step in _steps(session):
        assert _corr(step["content"]).get("scheme") == SCHEME
