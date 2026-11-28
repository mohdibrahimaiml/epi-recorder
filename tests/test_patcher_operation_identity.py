"""Legacy monkeypatch producer emits ``epi-operation/v1`` identity.

A fake ``openai`` module is installed so the real patched function runs without
the SDK or network.
"""

from __future__ import annotations

import sys
import types

import pytest

from epi_core.container import EPIContainer
from epi_core.operation_identity import audit_event_sequence
from epi_recorder import patcher
from epi_recorder.api import record

LLM_KINDS = {"llm.request", "llm.pre_commit", "llm.response", "llm.error"}


class _Message:
    role = "assistant"
    content = "hi"


class _Choice:
    message = _Message()
    finish_reason = "stop"


class _Usage:
    prompt_tokens = 1
    completion_tokens = 1
    total_tokens = 2


class _Response:
    model = "gpt-4"
    choices = [_Choice()]
    usage = _Usage()


class _Delta:
    def __init__(self, content=None) -> None:
        self.content = content
        self.tool_calls = None


class _StreamChoice:
    def __init__(self, content) -> None:
        self.delta = _Delta(content)
        self.finish_reason = None


class _Chunk:
    def __init__(self, content) -> None:
        self.choices = [_StreamChoice(content)]


def _install_fake_openai(monkeypatch, *, chunks=None, error=None) -> type:
    """Install a minimal openai>=1 module tree and return the patched class."""

    class Completions:
        def create(self, *args, **kwargs):
            if error is not None:
                raise error
            if kwargs.get("stream"):
                return iter(chunks or [])
            return _Response()

    mod_openai = types.ModuleType("openai")
    mod_openai.__version__ = "1.0.0"
    mod_resources = types.ModuleType("openai.resources")
    mod_chat = types.ModuleType("openai.resources.chat")
    mod_completions = types.ModuleType("openai.resources.chat.completions")
    mod_completions.Completions = Completions
    mod_chat.completions = mod_completions
    mod_resources.chat = mod_chat
    mod_openai.resources = mod_resources

    monkeypatch.setitem(sys.modules, "openai", mod_openai)
    monkeypatch.setitem(sys.modules, "openai.resources", mod_resources)
    monkeypatch.setitem(sys.modules, "openai.resources.chat", mod_chat)
    monkeypatch.setitem(sys.modules, "openai.resources.chat.completions", mod_completions)
    monkeypatch.setattr(patcher, "_original_methods", {}, raising=False)
    return Completions


@pytest.fixture
def _reset_context():
    yield
    patcher.set_recording_context(None)


def _llm_steps(path) -> list[dict]:
    return [s for s in EPIContainer.read_steps(path) if s.get("kind") in LLM_KINDS]


def _op_ids(steps: list[dict]) -> set:
    return {
        ((s.get("content") or {}).get("correlation") or {}).get("operation_id")
        for s in steps
    }


def _run(tmp_path, monkeypatch, *, chunks=None, error=None, stream=False):
    completions_cls = _install_fake_openai(monkeypatch, chunks=chunks, error=error)
    epi_file = tmp_path / "run.epi"
    with record(str(epi_file)) as epi:
        patcher.set_recording_context(epi.recording_context)
        try:
            assert patcher.patch_openai() is True
            client = completions_cls()
            if stream:
                for _ in client.create(model="gpt-4", messages=[], stream=True):
                    pass
            else:
                client.create(model="gpt-4", messages=[{"role": "user", "content": "hi"}])
        finally:
            patcher.set_recording_context(None)
    return epi_file


def test_non_stream_call_is_correlated(tmp_path, monkeypatch, _reset_context):
    steps = _llm_steps(_run(tmp_path, monkeypatch))
    assert [s["kind"] for s in steps] == ["llm.request", "llm.pre_commit", "llm.response"]
    assert len(_op_ids(steps)) == 1
    assert audit_event_sequence(steps)["status"] == "complete"


def test_streaming_call_is_correlated(tmp_path, monkeypatch, _reset_context):
    steps = _llm_steps(
        _run(tmp_path, monkeypatch, chunks=[_Chunk("a"), _Chunk("b")], stream=True)
    )
    assert [s["kind"] for s in steps] == ["llm.request", "llm.pre_commit", "llm.response"]
    assert len(_op_ids(steps)) == 1
    assert audit_event_sequence(steps)["status"] == "complete"


def test_error_is_correlated(tmp_path, monkeypatch, _reset_context):
    with pytest.raises(RuntimeError):
        _run(tmp_path, monkeypatch, error=RuntimeError("boom"))
    # Artifact was written by the record() context manager despite the raise.
    steps = _llm_steps(tmp_path / "run.epi")
    assert [s["kind"] for s in steps] == ["llm.request", "llm.pre_commit", "llm.error"]
    assert len(_op_ids(steps)) == 1
    assert audit_event_sequence(steps)["status"] == "complete"
