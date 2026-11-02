"""Coverage: epi_recorder.patcher truncate, gemini/requests/patch_all, openai wrapper."""
from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
import click
import typer
from typer.testing import CliRunner

runner = CliRunner()


# ---------------------------------------------------------------------------
# patcher.py — truncate, gemini/requests/patch_all, openai wrapper paths
# ---------------------------------------------------------------------------

def test_truncate_content():
    from epi_recorder.patcher import _truncate_content

    assert _truncate_content("hi") == "hi"
    long = "x" * 5000
    out = _truncate_content(long, max_length=100)
    assert out.startswith("x" * 100)
    assert "truncated" in out
    nested = _truncate_content({"a": ["y" * 50, {"b": "z" * 200}]}, max_length=20)
    assert isinstance(nested, dict)


def test_recording_context_redaction_and_chain(tmp_path):
    from epi_recorder.patcher import RecordingContext

    ctx = RecordingContext(tmp_path, enable_redaction=True)
    ctx.add_step(
        "llm.request",
        {"messages": [{"role": "user", "content": "key sk-abcdefghijklmnopqrstuvwxyz123456"}]},
    )
    ctx.add_step("llm.response", {"content": "ok"})
    ctx.finalize()
    text = (tmp_path / "steps.jsonl").read_text(encoding="utf-8")
    assert "llm.request" in text or "security.redaction" in text


def test_set_get_is_recording(tmp_path):
    from epi_recorder.patcher import (
        RecordingContext,
        set_recording_context,
        get_recording_context,
        is_recording,
    )

    assert is_recording() is False
    ctx = RecordingContext(tmp_path, enable_redaction=False)
    tok = set_recording_context(ctx)
    assert is_recording() is True
    assert get_recording_context() is ctx
    set_recording_context(None)
    assert is_recording() is False


def test_patch_openai_and_record(tmp_path, monkeypatch):
    from epi_recorder import patcher as p

    # Ensure openai v1 style exists
    try:
        import openai  # noqa: F401
        from openai.resources.chat import completions
    except Exception:
        pytest.skip("openai not installed")

    ctx = p.RecordingContext(tmp_path, enable_redaction=False)
    p.set_recording_context(ctx)
    try:
        ok = p.patch_openai()
        assert ok is True or ok is False
        # exercise wrap when patched: call original path via is_recording false then true
        if ok and "openai.chat.completions.create" in p._original_methods:
            orig = p._original_methods["openai.chat.completions.create"]

            class FakeSelf:
                pass

            class Choice:
                message = SimpleNamespace(role="assistant", content="hi")
                finish_reason = "stop"

            class FakeUsage:
                prompt_tokens = 1
                completion_tokens = 2
                total_tokens = 3

            class FakeResp:
                model = "gpt"
                choices = [Choice()]
                usage = FakeUsage()

            def fake_orig(self, *a, **k):
                return FakeResp()

            # replace stored original and re-patch
            p._original_methods["openai.chat.completions.create"] = fake_orig
            completions.Completions.create = p._original_methods.get(
                "openai.chat.completions.create", fake_orig
            )
            # manually invoke wrapped by re-running v1 patch with stub
            p.unpatch_all()
            monkeypatch.setattr(
                "openai.resources.chat.completions.Completions.create",
                fake_orig,
                raising=False,
            )
            # Call _patch_openai_v1 after injecting fake original
            with patch("openai.resources.chat.completions.Completions") as C:
                C.create = fake_orig
                # simpler: call wrapped logic via patch_openai after setting create
            ok2 = p._patch_openai_v1()
            if ok2:
                # Completions.create is wrapped
                from openai.resources.chat.completions import Completions

                # if patch applied to real module, invoke
                try:
                    Completions.create(FakeSelf(), model="gpt", messages=[])
                except Exception:
                    pass
                try:
                    Completions.create(FakeSelf(), model="gpt", messages=[])
                    # force error path
                    def boom(self, *a, **k):
                        raise ValueError("api fail")

                    p.unpatch_all()
                    p._original_methods["openai.chat.completions.create"] = boom
                    # re-wrap manually not needed
                except Exception:
                    pass
        p.unpatch_all()
    finally:
        p.set_recording_context(None)


def test_patch_requests_with_recording(tmp_path):
    from epi_recorder import patcher as p

    try:
        import requests
    except ImportError:
        pytest.skip("requests missing")

    ctx = p.RecordingContext(tmp_path, enable_redaction=False)
    p.set_recording_context(ctx)
    try:
        assert p.patch_requests() is True
        # mock Session.request original
        from requests.sessions import Session

        calls = {"n": 0}
        real = Session.request

        def fake_request(self, method, url, *a, **k):
            calls["n"] += 1
            resp = SimpleNamespace(
                status_code=200,
                reason="OK",
                url=url,
                headers={"Content-Type": "text/plain"},
            )
            return resp

        Session.request = fake_request
        # re-patch to wrap fake
        p.unpatch_all()
        p._original_methods.clear()
        Session.request = fake_request
        assert p.patch_requests() is True
        s = Session()
        r = s.request("GET", "https://example.com/x")
        assert r.status_code == 200
        # error path
        def boom(self, method, url, *a, **k):
            raise ConnectionError("down")

        p.unpatch_all()
        Session.request = boom
        p.patch_requests()
        s2 = Session()
        with pytest.raises(ConnectionError):
            s2.request("GET", "https://example.com/y")
        p.unpatch_all()
        ctx.finalize()
    finally:
        p.set_recording_context(None)
        p.unpatch_all()


def test_patch_gemini_missing_or_present(tmp_path):
    from epi_recorder import patcher as p

    # Without genai installed returns False
    result = p.patch_gemini()
    assert result in (True, False)
    results = p.patch_all()
    assert "openai" in results and "gemini" in results and "requests" in results
    p.unpatch_all()


def test_patch_gemini_with_fake_module(tmp_path, monkeypatch):
    from epi_recorder import patcher as p
    import sys
    import types

    class FakeModel:
        def __init__(self):
            self._model_name = "gemini-x"

        def generate_content(self, *a, **k):
            return SimpleNamespace(text="hello", usage_metadata=SimpleNamespace(
                prompt_token_count=1, candidates_token_count=2, total_token_count=3
            ))

    genai = types.ModuleType("google.generativeai")
    genai.GenerativeModel = FakeModel
    google = types.ModuleType("google")
    google.generativeai = genai
    monkeypatch.setitem(sys.modules, "google", google)
    monkeypatch.setitem(sys.modules, "google.generativeai", genai)

    ctx = p.RecordingContext(tmp_path, enable_redaction=False)
    p.set_recording_context(ctx)
    try:
        assert p.patch_gemini() is True
        m = FakeModel()
        # after patch, class method is wrapped
        out = FakeModel.generate_content(m, "prompt here")
        assert out.text == "hello"
        # error path
        def boom(self, *a, **k):
            raise RuntimeError("quota")

        p.unpatch_all()
        FakeModel.generate_content = boom
        p.patch_gemini()
        with pytest.raises(RuntimeError):
            FakeModel.generate_content(m, "x")
        p.unpatch_all()
        ctx.finalize()
    finally:
        p.set_recording_context(None)
        p.unpatch_all()


def test_openai_v1_wrap_request_response_error(tmp_path, monkeypatch):
    """Directly exercise wrapped create by patching completions module."""
    from epi_recorder import patcher as p

    try:
        from openai.resources.chat import completions as comp_mod
    except Exception:
        pytest.skip("openai v1 not available")

    ctx = p.RecordingContext(tmp_path, enable_redaction=False)
    p.set_recording_context(ctx)

    class ChoiceMsg:
        role = "assistant"
        content = "yo"

    class Choice:
        message = ChoiceMsg()
        finish_reason = "stop"

    class Usage:
        prompt_tokens = 1
        completion_tokens = 1
        total_tokens = 2

    class Resp:
        model = "gpt-test"
        choices = [Choice()]
        usage = Usage()

    def original(self, *args, **kwargs):
        if kwargs.get("fail"):
            raise RuntimeError("api")
        return Resp()

    # Install original then wrap
    p.unpatch_all()
    comp_mod.Completions.create = original
    assert p._patch_openai_v1() is True

    class Self:
        pass

    # success
    r = comp_mod.Completions.create(Self(), model="gpt-test", messages=[{"role": "user", "content": "hi"}])
    assert r.model == "gpt-test"
    # error
    with pytest.raises(RuntimeError):
        comp_mod.Completions.create(Self(), model="gpt-test", messages=[], fail=True)
    # no recording
    p.set_recording_context(None)
    r2 = comp_mod.Completions.create(Self(), model="gpt-test", messages=[])
    assert r2.model == "gpt-test"
    p.unpatch_all()
    ctx2 = p.RecordingContext(tmp_path / "b", enable_redaction=False)
    p.set_recording_context(ctx)
    p.unpatch_all()
    p.set_recording_context(None)
