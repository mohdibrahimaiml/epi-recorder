"""Tests for epi_recorder.adapters.langchain.EpiCallbackHandler.

Uses FakeListLLM / direct callback invocation — no network.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import warnings
from pathlib import Path
from uuid import uuid4

import pytest

# Skip entire module if langchain-core is not installed (optional extra).
pytest.importorskip("langchain_core")

from langchain_core.language_models.fake import FakeListLLM
from langchain_core.outputs import Generation, LLMResult

from epi_recorder import record
from epi_recorder.adapters.langchain import EpiCallbackHandler
from epi_cli.verify import _audit_step_sequence_completeness
from epi_core.container import EPIContainer


class _CaptureSession:
    """Minimal session stand-in for unit-level callback mapping tests."""

    def __init__(self) -> None:
        self.steps: list[tuple[str, dict]] = []

    def log(self, kind: str, content: dict | None = None, **kwargs) -> None:
        payload = dict(content or {})
        payload.update(kwargs)
        self.steps.append((kind, payload))


def test_import_epi_recorder_without_loading_adapter():
    """adapters.langchain is not imported as a side effect of epi_recorder."""
    # Drop adapter modules if a prior test imported them.
    for name in list(sys.modules):
        if name == "epi_recorder.adapters" or name.startswith("epi_recorder.adapters."):
            del sys.modules[name]
    # Re-import package root only
    import importlib

    import epi_recorder

    importlib.reload(epi_recorder)
    assert "epi_recorder.adapters.langchain" not in sys.modules
    assert hasattr(epi_recorder, "record")


def test_llm_call_and_response_via_fake_list_llm(tmp_path: Path):
    out = tmp_path / "fake_llm.epi"
    with record(out, goal="fake llm", auto_sign=True, redact=True) as session:
        handler = EpiCallbackHandler(session)
        llm = FakeListLLM(responses=["approved for $12,000"], callbacks=[handler])
        result = llm.invoke("Should we approve the loan?")
        assert "approved" in result.lower()

    assert out.exists()
    steps = EPIContainer.read_steps(out)
    kinds = [s.get("kind") for s in steps]
    assert "llm.call" in kinds
    assert "llm.response" in kinds

    # Find pairing
    call = next(s for s in steps if s.get("kind") == "llm.call")
    resp = next(s for s in steps if s.get("kind") == "llm.response")
    assert "prompts" in (call.get("content") or {})
    assert (resp.get("content") or {}).get("ok") is True


def test_tool_error_emits_tool_response_for_aud_co_01():
    """Failing tool still produces tool.response → AUD-CO-01 PASS."""
    session = _CaptureSession()
    handler = EpiCallbackHandler(session)
    rid = uuid4()

    handler.on_tool_start(
        {"name": "credit_check"},
        '{"ssn": "//"}',
        run_id=rid,
    )
    handler.on_tool_error(RuntimeError("bureau timeout"), run_id=rid)

    kinds = [k for k, _ in session.steps]
    assert kinds == ["tool.call", "tool.response"]
    call = session.steps[0][1]
    resp = session.steps[1][1]
    assert call["call_id"] == str(rid)
    assert resp["call_id"] == str(rid)
    assert resp["ok"] is False
    assert resp["error"] == "bureau timeout"
    assert not isinstance(resp["error"], BaseException)

    # Shape steps like packer would for the audit helper
    fake_steps = [
        {"index": 0, "kind": "tool.call", "content": call},
        {"index": 1, "kind": "tool.response", "content": resp},
    ]
    ok, gaps = _audit_step_sequence_completeness(fake_steps)
    assert ok is True, gaps


def test_tool_success_pairs_with_call_id():
    session = _CaptureSession()
    handler = EpiCallbackHandler(session)
    rid = uuid4()
    handler.on_tool_start({"name": "lookup"}, "id=1", run_id=rid)
    handler.on_tool_end({"status": "ok"}, run_id=rid)
    assert session.steps[1][1]["ok"] is True
    assert session.steps[0][1]["call_id"] == session.steps[1][1]["call_id"]


def test_llm_error_maps_to_llm_response_ok_false():
    session = _CaptureSession()
    handler = EpiCallbackHandler(session)
    rid = uuid4()
    handler.on_llm_start({"name": "gpt-x"}, ["hi"], run_id=rid)
    handler.on_llm_error(ValueError("rate limited"), run_id=rid)
    assert session.steps[0][0] == "llm.call"
    assert session.steps[1][0] == "llm.response"
    assert session.steps[1][1]["ok"] is False
    assert "rate limited" in session.steps[1][1]["error"]


def test_chain_events_only_top_level():
    # Nested chains are captured (not dropped) with parent_run_id/is_nested
    # for trace completeness — see on_chain_start "Captured nested chains too".
    session = _CaptureSession()
    handler = EpiCallbackHandler(session)
    top = uuid4()
    child = uuid4()
    handler.on_chain_start({"name": "AgentExecutor"}, {"input": "x"}, run_id=top)
    handler.on_chain_start(
        {"name": "inner"}, {"input": "y"}, run_id=child, parent_run_id=top
    )
    handler.on_chain_end({"output": "done"}, run_id=top)
    handler.on_chain_end({"output": "inner"}, run_id=child, parent_run_id=top)

    kinds = [k for k, _ in session.steps]
    assert kinds == ["chain.start", "chain.start", "chain.end", "chain.end"]
    assert session.steps[0][1]["chain"] == "AgentExecutor"
    assert session.steps[1][1]["is_nested"] is True
    assert session.steps[1][1]["parent_run_id"] == str(top)


def test_llm_end_extracts_generations():
    session = _CaptureSession()
    handler = EpiCallbackHandler(session)
    rid = uuid4()
    handler.on_llm_start({"name": "fake"}, ["p"], run_id=rid)
    result = LLMResult(generations=[[Generation(text="hello world")]])
    handler.on_llm_end(result, run_id=rid)
    resp = session.steps[1][1]
    assert resp["ok"] is True
    assert "hello world" in (resp.get("text") or resp.get("generations")[0])


def test_redaction_via_session_log_path(tmp_path: Path):
    """Secrets in prompts are redacted by RecordingContext (not a custom path)."""
    out = tmp_path / "redact.epi"
    secret = "sk-proj-ABCDEFGHIJKLMNOPQRSTUVWX"
    with record(out, goal="redact test", auto_sign=True, redact=True) as session:
        handler = EpiCallbackHandler(session)
        rid = uuid4()
        handler.on_llm_start(
            {"name": "fake"},
            [f"Use key {secret} to call the API"],
            run_id=rid,
        )
        handler.on_llm_end(
            LLMResult(generations=[[Generation(text="ok")]]),
            run_id=rid,
        )

    steps = EPIContainer.read_steps(out)
    blob = json.dumps(steps)
    assert secret not in blob
    assert any(s.get("kind") == "llm.call" for s in steps)


def test_failing_tool_full_artifact_forensic_pass(tmp_path: Path):
    """End-to-end: tool.call + tool.response(error) → epi verify Forensic PASS."""
    out = tmp_path / "tool_fail.epi"
    with record(out, goal="loan decision", auto_sign=True, redact=True) as session:
        handler = EpiCallbackHandler(session)
        # Top-level chain
        chain_id = uuid4()
        handler.on_chain_start(
            {"name": "loan_agent"},
            {"input": "Approve loan for Alice?"},
            run_id=chain_id,
        )
        # LLM
        llm_id = uuid4()
        handler.on_llm_start(
            {"name": "FakeListLLM"},
            ["Decide on the loan"],
            run_id=llm_id,
            parent_run_id=chain_id,
        )
        handler.on_llm_end(
            LLMResult(generations=[[Generation(text="Need credit check")]]),
            run_id=llm_id,
            parent_run_id=chain_id,
        )
        # Tool that fails
        tool_id = uuid4()
        handler.on_tool_start(
            {"name": "credit_check"},
            '{"applicant":"Alice"}',
            run_id=tool_id,
            parent_run_id=chain_id,
        )
        handler.on_tool_error(
            RuntimeError("credit bureau unavailable"),
            run_id=tool_id,
            parent_run_id=chain_id,
        )
        # Final LLM
        llm2 = uuid4()
        handler.on_llm_start(
            {"name": "FakeListLLM"},
            ["Bureau failed; decide conservatively"],
            run_id=llm2,
            parent_run_id=chain_id,
        )
        handler.on_llm_end(
            LLMResult(generations=[[Generation(text="deny")]]),
            run_id=llm2,
            parent_run_id=chain_id,
        )
        handler.on_chain_end({"output": "deny"}, run_id=chain_id)

    assert out.exists()
    steps = EPIContainer.read_steps(out)
    tool_steps = [s for s in steps if s.get("kind") in ("tool.call", "tool.response")]
    assert len(tool_steps) == 2
    ok, gaps = _audit_step_sequence_completeness(steps)
    assert ok is True, gaps

    # CLI verify — use --json so assertions work without a TTY (Windows CI
    # often yields empty Rich stdout when not attached to a console).
    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    proc = subprocess.run(
        [sys.executable, "-m", "epi_cli", "verify", "--json", str(out)],
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
    )
    combined = (proc.stdout or "") + (proc.stderr or "")
    assert proc.returncode == 0, combined
    assert proc.stdout, f"expected JSON report on stdout, got empty. stderr={proc.stderr!r}"
    report = json.loads(proc.stdout)
    facts = report.get("facts") or {}
    # Forensic completeness: sequence + completeness + chain all true
    assert facts.get("completeness_ok") is True, report
    assert facts.get("sequence_ok") is True, report
    assert facts.get("chain_ok") is True, report
    assert facts.get("integrity_ok") is True, report
    decision = (report.get("decision") or {}).get("status")
    assert decision != "FAIL", report


def test_handler_requires_session():
    with pytest.raises(ValueError):
        EpiCallbackHandler(None)  # type: ignore[arg-type]


def test_log_failure_warns_once_does_not_raise():
    """Outside an entered session, log failures must not crash LangChain."""

    class BrokenSession:
        def log(self, kind, content=None, **kwargs):
            raise RuntimeError("Cannot log step outside of context manager")

    handler = EpiCallbackHandler(BrokenSession())
    with pytest.warns(RuntimeWarning, match="could not log step"):
        handler.on_llm_start({"name": "m"}, ["hi"], run_id=uuid4())
    # Second failure: no second warning required (warned flag)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        handler.on_llm_end(
            LLMResult(generations=[[Generation(text="x")]]),
            run_id=uuid4(),
        )
    runtime = [w for w in caught if issubclass(w.category, RuntimeWarning)]
    assert len(runtime) == 0
