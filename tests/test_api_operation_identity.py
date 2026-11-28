"""Manual recording API emits ``epi-operation/v1`` identity when linked.

Unlinked legacy calls stay name-based: the recorder must not pretend it can pair
two calls the caller never associated.
"""

from __future__ import annotations

import pytest

from epi_core.container import EPIContainer
from epi_core.operation_identity import SCHEME, audit_event_sequence
from epi_recorder.api import record

LIFECYCLE = {
    "llm.request",
    "llm.pre_commit",
    "llm.response",
    "llm.error",
    "tool.call",
    "tool.response",
    "agent.approval.request",
    "agent.approval.response",
}


def _steps(path) -> list[dict]:
    return [s for s in EPIContainer.read_steps(path) if s.get("kind") in LIFECYCLE]


def _op_id(step: dict) -> str | None:
    return ((step.get("content") or {}).get("correlation") or {}).get("operation_id")


def test_operation_context_manager_is_complete(tmp_path):
    epi_file = tmp_path / "run.epi"
    with record(str(epi_file)) as epi:
        agent = epi.agent_run("a")
        with agent.operation("tool", "payment.execute", payload={"amount": 5}) as op:
            op.complete({"ok": True})

    steps = _steps(epi_file)
    assert [s["kind"] for s in steps] == ["tool.call", "tool.response"]
    assert len({_op_id(s) for s in steps}) == 1
    audit = audit_event_sequence(steps)
    assert audit["status"] == "complete", audit


def test_operation_exception_records_error_terminal(tmp_path):
    epi_file = tmp_path / "run.epi"
    with record(str(epi_file)) as epi:
        agent = epi.agent_run("a")
        with pytest.raises(RuntimeError):
            with agent.operation("tool", "flaky"):
                raise RuntimeError("tool failed")

    steps = _steps(epi_file)
    assert [s["kind"] for s in steps] == ["tool.call", "tool.response"]
    assert steps[-1]["content"]["ok"] is False
    assert "tool failed" in steps[-1]["content"]["error"]
    assert audit_event_sequence(steps)["status"] == "complete"


def test_tool_call_and_result_link_by_call_id(tmp_path):
    epi_file = tmp_path / "run.epi"
    with record(str(epi_file)) as epi:
        agent = epi.agent_run("a")
        agent.tool_call("lookup", {"id": 1}, call_id="c-1")
        agent.tool_result("lookup", {"found": True}, call_id="c-1")

    steps = _steps(epi_file)
    assert len({_op_id(s) for s in steps}) == 1
    assert all(_op_id(s) for s in steps)
    assert audit_event_sequence(steps)["status"] == "complete"


def test_tool_call_and_result_link_by_operation_id(tmp_path):
    epi_file = tmp_path / "run.epi"
    with record(str(epi_file)) as epi:
        agent = epi.agent_run("a")
        agent.tool_call("lookup", {"id": 1}, operation_id="op-1")
        agent.tool_result("lookup", {"found": True}, operation_id="op-1")

    steps = _steps(epi_file)
    assert {_op_id(s) for s in steps} == {"op-1"}
    assert audit_event_sequence(steps)["status"] == "complete"


def test_unlinked_manual_calls_stay_name_based(tmp_path):
    epi_file = tmp_path / "run.epi"
    with record(str(epi_file)) as epi:
        agent = epi.agent_run("a")
        agent.tool_call("lookup", {"id": 1})
        agent.tool_result("lookup", {"found": True})

    steps = _steps(epi_file)
    assert all(_op_id(s) is None for s in steps)
    audit = audit_event_sequence(steps)
    assert audit["status"] == "consistent_scope_unknown"
    assert audit["basis"] == "name_based"


def test_approval_terminal_links_by_operation_id(tmp_path):
    epi_file = tmp_path / "run.epi"
    with record(str(epi_file)) as epi:
        agent = epi.agent_run("a")
        agent.approval_request("refund", approval_id="r-1", operation_id="ap-1")
        agent.approval_response("refund", approved=True, operation_id="ap-1")

    steps = _steps(epi_file)
    assert {_op_id(s) for s in steps} == {"ap-1"}
    assert audit_event_sequence(steps)["status"] == "complete"


def test_log_chat_emits_one_identity(tmp_path):
    epi_file = tmp_path / "run.epi"
    with record(str(epi_file)) as epi:
        epi.log_chat(
            model="gpt-4",
            messages=[{"role": "user", "content": "hi"}],
            response_content="hello",
        )
    steps = _steps(epi_file)
    assert [s["kind"] for s in steps] == ["llm.request", "llm.response"]
    assert len({_op_id(s) for s in steps}) == 1
    assert audit_event_sequence(steps)["status"] == "complete"


def test_split_llm_logging_links_by_operation_id(tmp_path):
    epi_file = tmp_path / "run.epi"
    with record(str(epi_file)) as epi:
        epi.log_llm_request("gpt-4", {"messages": []}, operation_id="llm-1")
        epi.log_llm_response({"choices": []}, operation_id="llm-1")
    steps = _steps(epi_file)
    assert {_op_id(s) for s in steps} == {"llm-1"}
    assert audit_event_sequence(steps)["status"] == "complete"


def test_split_llm_logging_without_id_stays_legacy(tmp_path):
    epi_file = tmp_path / "run.epi"
    with record(str(epi_file)) as epi:
        epi.log_llm_request("gpt-4", {"messages": []})
        epi.log_llm_response({"choices": []})
    steps = _steps(epi_file)
    assert all(_op_id(s) is None for s in steps)
    assert audit_event_sequence(steps)["status"] == "consistent_scope_unknown"


def test_two_operations_get_distinct_ids(tmp_path):
    epi_file = tmp_path / "run.epi"
    with record(str(epi_file)) as epi:
        agent = epi.agent_run("a")
        with agent.operation("tool", "one") as op:
            op.complete(1)
        with agent.operation("tool", "two") as op:
            op.complete(2)
    steps = _steps(epi_file)
    ids = {_op_id(s) for s in steps}
    assert len(ids) == 2
    audit = audit_event_sequence(steps)
    assert audit["status"] == "complete"
    assert audit["counts"] == {"started": 2, "completed": 2, "orphaned": 0}


def test_operation_rejects_unknown_family(tmp_path):
    epi_file = tmp_path / "run.epi"
    with record(str(epi_file)) as epi:
        agent = epi.agent_run("a")
        with pytest.raises(ValueError):
            agent.operation("payment", "x")
