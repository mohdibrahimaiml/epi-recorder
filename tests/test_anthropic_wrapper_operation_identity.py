"""Anthropic wrapper emits ``epi-operation/v1`` identity on every lifecycle step."""

from __future__ import annotations

import pytest

from epi_core.container import EPIContainer
from epi_core.operation_identity import SCHEME, audit_event_sequence
from epi_recorder.api import record
from epi_recorder.wrappers.anthropic import TracedMessages

LLM_KINDS = {"llm.request", "llm.pre_commit", "llm.response", "llm.error"}


class _Usage:
    input_tokens = 3
    output_tokens = 2


class _Response:
    content = [{"type": "text", "text": "hello"}]
    model = "claude-x"
    id = "msg_1"
    role = "assistant"
    stop_reason = "end_turn"
    usage = _Usage()


class _Message:
    model = "claude-x"
    id = "msg_stream"
    usage = None


class _Delta:
    def __init__(self, text=None, stop_reason=None) -> None:
        self.text = text
        self.stop_reason = stop_reason
        self.partial_json = None


class _Chunk:
    def __init__(self, text=None, stop_reason=None, message=None) -> None:
        self.delta = _Delta(text, stop_reason)
        self.content_block = None
        self.message = message
        self.usage = None


class _Messages:
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


def _client(**kwargs) -> TracedMessages:
    return TracedMessages(_Messages(**kwargs))


def _llm_steps(epi_file) -> list[dict]:
    return [s for s in EPIContainer.read_steps(epi_file) if s.get("kind") in LLM_KINDS]


def _assert_governed_complete(steps: list[dict]) -> None:
    llm = [s for s in steps if s.get("kind") in LLM_KINDS]
    ids = {
        (s.get("content") or {}).get("correlation", {}).get("operation_id") for s in llm
    }
    assert len(ids) == 1, ids
    for step in llm:
        corr = (step.get("content") or {}).get("correlation") or {}
        assert corr.get("scheme") == SCHEME
        assert corr.get("group_id")
        assert corr.get("attempt") == 1
    audit = audit_event_sequence(llm)
    assert audit["status"] == "complete", audit


def test_non_stream_call_is_auditable(tmp_path):
    epi_file = tmp_path / "run.epi"
    with record(str(epi_file)):
        _client(response=_Response()).create(
            model="claude-x", max_tokens=16, messages=[{"role": "user", "content": "hi"}]
        )
    steps = _llm_steps(epi_file)
    assert [s["kind"] for s in steps] == ["llm.request", "llm.pre_commit", "llm.response"]
    _assert_governed_complete(steps)


def test_non_stream_error_emits_terminal_error(tmp_path):
    epi_file = tmp_path / "run.epi"
    with record(str(epi_file)):
        with pytest.raises(RuntimeError):
            _client(error=RuntimeError("boom")).create(
                model="claude-x", max_tokens=16, messages=[{"role": "user", "content": "hi"}]
            )
    steps = _llm_steps(epi_file)
    assert [s["kind"] for s in steps] == ["llm.request", "llm.pre_commit", "llm.error"]
    _assert_governed_complete(steps)


def test_stream_call_is_auditable(tmp_path):
    epi_file = tmp_path / "run.epi"
    chunks = [_Chunk(message=_Message()), _Chunk(text="hi"), _Chunk(stop_reason="end_turn")]
    with record(str(epi_file)):
        for _ in _client(chunks=chunks).stream(
            model="claude-x", max_tokens=16, messages=[{"role": "user", "content": "hi"}]
        ):
            pass
    steps = _llm_steps(epi_file)
    assert [s["kind"] for s in steps] == ["llm.request", "llm.pre_commit", "llm.response"]
    _assert_governed_complete(steps)


def test_abandoned_stream_records_cancelled_terminal(tmp_path):
    epi_file = tmp_path / "run.epi"
    chunks = [_Chunk(message=_Message()), _Chunk(text="partial"), _Chunk(text="never")]
    with record(str(epi_file)):
        stream = _client(chunks=chunks).stream(
            model="claude-x", max_tokens=16, messages=[{"role": "user", "content": "hi"}]
        )
        next(stream)
        stream.close()
    steps = _llm_steps(epi_file)
    assert [s["kind"] for s in steps] == ["llm.request", "llm.pre_commit", "llm.response"]
    terminal = steps[-1].get("content") or {}
    assert terminal.get("cancelled") is True
    assert terminal.get("stop_reason") == "cancelled"
    _assert_governed_complete(steps)


def test_stream_error_emits_terminal_error(tmp_path):
    epi_file = tmp_path / "run.epi"
    with record(str(epi_file)):
        with pytest.raises(RuntimeError):
            for _ in _client(error=RuntimeError("stream failed")).stream(
                model="claude-x", max_tokens=16, messages=[{"role": "user", "content": "hi"}]
            ):
                pass
    steps = _llm_steps(epi_file)
    assert [s["kind"] for s in steps] == ["llm.request", "llm.pre_commit", "llm.error"]
    _assert_governed_complete(steps)


def test_two_calls_get_distinct_operation_ids(tmp_path):
    epi_file = tmp_path / "run.epi"
    with record(str(epi_file)):
        client = _client(response=_Response())
        client.create(model="claude-x", max_tokens=8, messages=[{"role": "user", "content": "1"}])
        client.create(model="claude-x", max_tokens=8, messages=[{"role": "user", "content": "2"}])
    llm = _llm_steps(epi_file)
    ids = {(s.get("content") or {})["correlation"]["operation_id"] for s in llm}
    assert len(ids) == 2
    audit = audit_event_sequence(llm)
    assert audit["status"] == "complete"
    assert audit["counts"] == {"started": 2, "completed": 2, "orphaned": 0}
