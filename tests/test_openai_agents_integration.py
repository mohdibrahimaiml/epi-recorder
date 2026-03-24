from __future__ import annotations

from typing import Any

from epi_recorder.api import AgentRun
from epi_recorder.integrations import OpenAIAgentsRecorder, record_openai_agent_events


class _DummySession:
    def __init__(self) -> None:
        self.steps: list[tuple[str, dict[str, Any]]] = []

    def log_step(self, kind: str, content: dict[str, Any]) -> None:
        self.steps.append((kind, content))

    async def alog_step(self, kind: str, content: dict[str, Any]) -> None:
        self.log_step(kind, content)

    def agent_run(self, agent_name: str, **kwargs: Any) -> AgentRun:
        return AgentRun(self.log_step, self.alog_step, agent_name, **kwargs)


def test_openai_agents_recorder_maps_messages_tools_and_handoffs():
    session = _DummySession()

    events = [
        {"type": "run_item_stream_event", "item": {"type": "message_output_item", "role": "assistant", "content": [{"text": "I can help with that refund."}]}},
        {"type": "run_item_stream_event", "item": {"type": "tool_call_item", "tool_name": "lookup_order", "arguments": {"order_id": "123"}, "call_id": "call_1"}},
        {"type": "run_item_stream_event", "item": {"type": "tool_call_output_item", "call_id": "call_1", "output": {"status": "paid"}}},
        {"type": "agent_updated_stream_event", "new_agent": {"name": "refund-supervisor"}},
        {"type": "run_item_stream_event", "item": {"type": "final_output", "output": {"decision": "approve_refund"}}},
    ]

    with OpenAIAgentsRecorder(session, agent_name="refund-agent", user_input="Refund order 123") as recorder:
        recorder.consume_many(events)

    kinds = [kind for kind, _ in session.steps]
    assert kinds[0] == "agent.run.start"
    assert "agent.message" in kinds
    assert "tool.call" in kinds
    assert "tool.response" in kinds
    assert "agent.handoff" in kinds
    assert "agent.decision" in kinds
    assert kinds[-1] == "agent.run.end"


def test_openai_agents_recorder_falls_back_to_state_for_unknown_events():
    session = _DummySession()

    with OpenAIAgentsRecorder(session, agent_name="ops-agent") as recorder:
        recorder.consume({"type": "mystery_event", "payload": {"x": 1}})

    assert any(kind == "agent.state" for kind, _ in session.steps)


def test_record_openai_agent_events_helper_consumes_iterable():
    session = _DummySession()

    recorder = record_openai_agent_events(
        [
            {"type": "run_item_stream_event", "item": {"type": "reasoning_item", "summary": "Check the order before refunding."}},
            {"type": "run_item_stream_event", "item": {"type": "approval_request_item", "action": "approve_refund", "reason": "Amount is above threshold"}},
            {"type": "run_item_stream_event", "item": {"type": "approval_response_item", "action": "approve_refund", "approved": True, "reviewer": "manager"}},
        ],
        session,
        agent_name="refund-agent",
    )

    assert recorder is not None
    kinds = [kind for kind, _ in session.steps]
    assert kinds[0] == "agent.run.start"
    assert "agent.plan" in kinds
    assert "agent.approval.request" in kinds
    assert "agent.approval.response" in kinds
    assert kinds[-1] == "agent.run.end"
