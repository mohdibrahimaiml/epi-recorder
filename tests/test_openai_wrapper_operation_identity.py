"""OpenAI wrapper emits ``epi-operation/v1`` identity on every lifecycle step.

Contract: docs/rfcs/operation-identity-and-event-completeness.md.
A recorded LLM call must be auditable without falling back to event order.
"""

from __future__ import annotations

import pytest

from epi_core.container import EPIContainer
from epi_core.operation_identity import SCHEME, audit_event_sequence
from epi_recorder.api import record
from epi_recorder.wrappers.openai import TracedCompletions

LLM_KINDS = {"llm.request", "llm.pre_commit", "llm.response", "llm.error"}


# ------------------------------------------------------------------ fakes


class _Message:
    role = "assistant"
    content = "hello"
    tool_calls = None
    function_call = None
    refusal = None


class _Choice:
    def __init__(self) -> None:
        self.message = _Message()
        self.finish_reason = "stop"
        self.index = 0


class _Usage:
    prompt_tokens = 3
    completion_tokens = 2
    total_tokens = 5


class _Response:
    def __init__(self) -> None:
        self.choices = [_Choice()]
        self.usage = _Usage()
        self.model = "gpt-4o"
        self.id = "resp_1"
        self.created = 1
        self.system_fingerprint = None


class _Delta:
    def __init__(self, content: str | None) -> None:
        self.content = content
        self.tool_calls = None
        self.function_call = None
        self.reasoning = None
        self.refusal = None


class _StreamChoice:
    def __init__(self, content: str | None, finish_reason: str | None) -> None:
        self.delta = _Delta(content)
        self.finish_reason = finish_reason


class _Chunk:
    def __init__(self, content: str | None, finish_reason: str | None = None) -> None:
        self.choices = [_StreamChoice(content, finish_reason)]
        self.model = "gpt-4o"
        self.id = "resp_stream"
        self.created = 2
        self.system_fingerprint = None
        self.usage = None


class _Completions:
    def __init__(self, *, response=None, chunks=None, error=None) -> None:
        self._response = response
        self._chunks = chunks
        self._error = error

    def create(self, *args, **kwargs):
        if self._error is not None:
            raise self._error
        if kwargs.get("stream"):
            return iter(self._chunks or [])
        return self._response


def _client(**kwargs) -> TracedCompletions:
    return TracedCompletions(_Completions(**kwargs), provider="openai")


def _llm_steps(epi_file) -> list[dict]:
    return [s for s in EPIContainer.read_steps(epi_file) if s.get("kind") in LLM_KINDS]


def _assert_governed_complete(steps: list[dict]) -> str:
    llm = [s for s in steps if s.get("kind") in LLM_KINDS]
    assert llm, "no llm steps recorded"
    operation_ids = {
        (s.get("content") or {}).get("correlation", {}).get("operation_id")
        for s in llm
    }
    assert len(operation_ids) == 1, operation_ids
    operation_id = operation_ids.pop()
    assert operation_id
    for step in llm:
        corr = (step.get("content") or {}).get("correlation") or {}
        assert corr.get("scheme") == SCHEME
        assert corr.get("attempt") == 1
        assert corr.get("group_id")
    audit = audit_event_sequence(llm)
    assert audit["status"] == "complete", audit
    assert audit["families"]["llm"]["basis"] == "operation_identity"
    return operation_id


# ------------------------------------------------------------------ non-streaming


def test_non_stream_call_emits_auditable_identity(tmp_path):
    epi_file = tmp_path / "run.epi"
    with record(str(epi_file)):
        _client(response=_Response()).create(
            model="gpt-4o", messages=[{"role": "user", "content": "hi"}]
        )
    steps = _llm_steps(epi_file)
    assert [s["kind"] for s in steps] == ["llm.request", "llm.pre_commit", "llm.response"]
    _assert_governed_complete(steps)


def test_non_stream_error_emits_terminal_error(tmp_path):
    epi_file = tmp_path / "run.epi"
    with record(str(epi_file)):
        with pytest.raises(RuntimeError):
            _client(error=RuntimeError("boom")).create(
                model="gpt-4o", messages=[{"role": "user", "content": "hi"}]
            )
    steps = _llm_steps(epi_file)
    assert [s["kind"] for s in steps] == ["llm.request", "llm.pre_commit", "llm.error"]
    _assert_governed_complete(steps)


def test_two_calls_get_distinct_operation_ids(tmp_path):
    epi_file = tmp_path / "run.epi"
    with record(str(epi_file)):
        client = _client(response=_Response())
        client.create(model="gpt-4o", messages=[{"role": "user", "content": "1"}])
        client.create(model="gpt-4o", messages=[{"role": "user", "content": "2"}])
    steps = _llm_steps(epi_file)
    operation_ids = {
        (s.get("content") or {})["correlation"]["operation_id"] for s in steps
    }
    assert len(operation_ids) == 2
    audit = audit_event_sequence(steps)
    assert audit["status"] == "complete"
    assert audit["counts"] == {"started": 2, "completed": 2, "orphaned": 0}


# ------------------------------------------------------------------ streaming


def test_stream_call_emits_auditable_identity(tmp_path):
    epi_file = tmp_path / "run.epi"
    chunks = [_Chunk("hel"), _Chunk("lo", finish_reason="stop")]
    with record(str(epi_file)):
        for _ in _client(chunks=chunks).create(
            model="gpt-4o", messages=[{"role": "user", "content": "hi"}], stream=True
        ):
            pass
    steps = _llm_steps(epi_file)
    assert [s["kind"] for s in steps] == ["llm.request", "llm.pre_commit", "llm.response"]
    _assert_governed_complete(steps)


def test_abandoned_stream_records_cancelled_terminal(tmp_path):
    """A consumer that stops iterating must not leave the operation unresolved."""
    epi_file = tmp_path / "run.epi"
    chunks = [_Chunk("partial"), _Chunk("never-consumed")]
    with record(str(epi_file)):
        stream = _client(chunks=chunks).create(
            model="gpt-4o", messages=[{"role": "user", "content": "hi"}], stream=True
        )
        next(stream)
        stream.close()
    steps = _llm_steps(epi_file)
    kinds = [s["kind"] for s in steps]
    assert kinds == ["llm.request", "llm.pre_commit", "llm.response"]
    terminal = (steps[-1].get("content") or {})
    assert terminal.get("cancelled") is True
    assert terminal.get("finish_reason") == "cancelled"
    _assert_governed_complete(steps)


def test_stream_error_emits_terminal_error(tmp_path):
    epi_file = tmp_path / "run.epi"
    with record(str(epi_file)):
        with pytest.raises(RuntimeError):
            for _ in _client(error=RuntimeError("stream failed")).create(
                model="gpt-4o", messages=[{"role": "user", "content": "hi"}], stream=True
            ):
                pass
    steps = _llm_steps(epi_file)
    assert [s["kind"] for s in steps] == ["llm.request", "llm.pre_commit", "llm.error"]
    _assert_governed_complete(steps)


# ------------------------------------------------------------------ conformance


def test_every_llm_step_carries_correlation(tmp_path):
    epi_file = tmp_path / "run.epi"
    chunks = [_Chunk("ok", finish_reason="stop")]
    with record(str(epi_file)):
        _client(response=_Response()).create(
            model="gpt-4o", messages=[{"role": "user", "content": "a"}]
        )
        for _ in _client(chunks=chunks).create(
            model="gpt-4o", messages=[{"role": "user", "content": "b"}], stream=True
        ):
            pass
    llm = _llm_steps(epi_file)
    missing = [
        s["kind"] for s in llm if not ((s.get("content") or {}).get("correlation"))
    ]
    assert missing == [], f"uncorrelated llm steps: {missing}"
    audit = audit_event_sequence(llm)
    assert audit["status"] == "complete"
