"""
OpenAI Agents-style event bridge for EPI Recorder.

This is a lightweight adapter for event streams that look like the OpenAI
Agents SDK output. It does not require the SDK at import time. Instead, it
accepts generic event objects or dictionaries and maps the most useful agent
events onto EPI's agent-native step model.

Usage:
    from epi_recorder import record
    from epi_recorder.integrations import OpenAIAgentsRecorder

    with record("agent.epi") as epi:
        with OpenAIAgentsRecorder(epi, agent_name="support-agent") as recorder:
            for event in agent_result.stream_events():
                recorder.consume(event)
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Optional

from epi_recorder.api import EpiRecorderSession


def _to_mapping(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return dict(value)
    if hasattr(value, "model_dump"):
        dumped = value.model_dump()
        if isinstance(dumped, dict):
            return dict(dumped)
    if hasattr(value, "dict"):
        dumped = value.dict()
        if isinstance(dumped, dict):
            return dict(dumped)
    if hasattr(value, "__dict__"):
        return {
            key: item
            for key, item in vars(value).items()
            if not key.startswith("_")
        }
    return {"value": value}


def _get_attr_or_key(value: Any, name: str) -> Any:
    if isinstance(value, dict):
        return value.get(name)
    return getattr(value, name, None)


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "approved", "yes", "allow", "allowed"}
    return bool(value)


def _first_present(value: Any, *names: str) -> Any:
    for name in names:
        found = _get_attr_or_key(value, name)
        if found is not None:
            return found
    return None


def _extract_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        return text or None
    if isinstance(value, list):
        parts = [_extract_text(item) for item in value]
        joined = "\n".join(part for part in parts if part)
        return joined or None
    if isinstance(value, dict):
        for key in ("text", "summary", "content", "output_text", "reason", "notes", "arguments"):
            text = _extract_text(value.get(key))
            if text:
                return text
        if "content" in value:
            return _extract_text(value["content"])
        return None

    mapping = _to_mapping(value)
    if mapping and mapping != {"value": value}:
        return _extract_text(mapping)
    return str(value)


class OpenAIAgentsRecorder:
    """
    Bridge OpenAI Agents-style stream events into EPI agent steps.

    This is intentionally conservative: it handles the most useful agent events
    (messages, tool calls/results, approvals, handoffs, memory events, and
    high-level state transitions) and falls back to `agent.state` for anything
    unknown so evidence is still preserved.
    """

    def __init__(
        self,
        session: EpiRecorderSession,
        *,
        agent_name: str = "openai-agent",
        user_input: Optional[Any] = None,
        goal: Optional[str] = None,
        session_id: Optional[str] = None,
        task_id: Optional[str] = None,
        parent_run_id: Optional[str] = None,
        attempt: int = 1,
        resume_from: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ):
        self._session = session
        self._agent = session.agent_run(
            agent_name,
            agent_type="openai-agent",
            user_input=user_input,
            goal=goal,
            session_id=session_id,
            task_id=task_id,
            parent_run_id=parent_run_id,
            attempt=attempt,
            resume_from=resume_from,
            metadata=metadata,
        )
        self._started = False
        self._closed = False
        self._active_agent_name = agent_name
        self._tool_calls: dict[str, str] = {}

    def _ensure_started(self) -> None:
        if not self._started:
            self._agent.start()
            self._started = True

    def close(self, *, success: bool = True, **metadata: Any) -> None:
        if self._closed:
            return
        self._ensure_started()
        self._agent.finish(success=success, **metadata)
        self._closed = True

    def _consume_agent_update(self, event: dict[str, Any], event_type: str) -> None:
        new_agent = _first_present(event, "new_agent", "agent", "current_agent")
        new_agent_payload = _to_mapping(new_agent)
        new_agent_name = _first_present(new_agent_payload, "name", "agent_name") or _extract_text(new_agent)
        if new_agent_name and new_agent_name != self._active_agent_name:
            self._agent.handoff(str(new_agent_name), reason="OpenAI Agents event updated the active agent", event_type=event_type)
            self._active_agent_name = str(new_agent_name)
            return
        self._agent.state("agent_updated", event_type=event_type, event=event)

    def _consume_run_item(self, item: Any, event_type: str) -> None:
        payload = _to_mapping(item)
        item_type = str(_first_present(payload, "type", "item_type") or event_type)

        if item_type in {"message", "message_output_item", "assistant_message", "user_message"}:
            role = _first_present(payload, "role") or "assistant"
            content = _extract_text(payload) or payload
            self._agent.message(str(role), content, event_type=item_type)
            return

        if item_type in {"tool_call", "tool_call_item", "function_call"}:
            tool_name = _first_present(payload, "tool_name", "name") or "tool"
            tool_input = _first_present(payload, "arguments", "input", "tool_input")
            call_id = _first_present(payload, "call_id", "tool_call_id", "id")
            if call_id:
                self._tool_calls[str(call_id)] = str(tool_name)
            self._agent.tool_call(str(tool_name), tool_input, call_id=call_id, event_type=item_type)
            return

        if item_type in {"tool_result", "tool_call_output_item", "function_call_output", "tool_output"}:
            call_id = _first_present(payload, "call_id", "tool_call_id", "id")
            tool_name = _first_present(payload, "tool_name", "name")
            if not tool_name and call_id:
                tool_name = self._tool_calls.get(str(call_id))
            output = _first_present(payload, "output", "result", "content")
            status = _first_present(payload, "status") or "success"
            self._agent.tool_result(str(tool_name or "tool"), output, status=str(status), call_id=call_id, event_type=item_type)
            return

        if item_type in {"reasoning", "reasoning_item", "plan"}:
            summary = _extract_text(payload) or "Model reasoning step"
            self._agent.plan(summary, event_type=item_type)
            return

        if item_type in {"handoff", "handoff_call_item"}:
            to_agent = _first_present(payload, "to_agent", "agent_name", "target_agent") or "agent"
            self._agent.handoff(str(to_agent), reason=_extract_text(payload), event_type=item_type)
            return

        if item_type in {"approval_request", "approval_request_item"}:
            action = _first_present(payload, "action", "name") or "approval_required"
            self._agent.approval_request(str(action), reason=_extract_text(payload), event_type=item_type)
            return

        if item_type in {"approval_response", "approval_response_item"}:
            action = _first_present(payload, "action", "name") or "approval_required"
            self._agent.approval_response(
                str(action),
                approved=_coerce_bool(_first_present(payload, "approved", "allowed", "decision")),
                reviewer=_first_present(payload, "reviewer", "reviewed_by"),
                notes=_extract_text(payload),
                event_type=item_type,
            )
            return

        if item_type in {"memory_read", "memory_read_item"}:
            memory_key = _first_present(payload, "memory_key", "key", "store") or "memory"
            self._agent.memory_read(
                str(memory_key),
                query=_first_present(payload, "query"),
                source=_first_present(payload, "source"),
                result_count=_first_present(payload, "result_count"),
                value=_first_present(payload, "value", "content"),
                event_type=item_type,
            )
            return

        if item_type in {"memory_write", "memory_write_item"}:
            memory_key = _first_present(payload, "memory_key", "key", "store") or "memory"
            self._agent.memory_write(
                str(memory_key),
                _first_present(payload, "value", "content"),
                operation=str(_first_present(payload, "operation") or "set"),
                destination=_first_present(payload, "destination"),
                event_type=item_type,
            )
            return

        if item_type in {"run_error", "error"}:
            self._agent.error(_extract_text(payload) or "OpenAI agent error", event_type=item_type)
            return

        if item_type in {"final_output", "final_response"}:
            self._agent.decision(
                "final_output",
                output=_first_present(payload, "output", "content") or _extract_text(payload),
                event_type=item_type,
            )
            return

        self._agent.state("openai_agents.run_item", item_type=item_type, item=payload)

    def consume(self, event: Any) -> Any:
        self._ensure_started()
        payload = _to_mapping(event)
        event_type = str(_first_present(payload, "type", "event", "event_type") or type(event).__name__)

        if event_type == "agent_updated_stream_event":
            self._consume_agent_update(payload, event_type)
            return event

        if event_type == "run_item_stream_event":
            self._consume_run_item(_first_present(payload, "item", "data") or payload, event_type)
            return event

        if event_type in {"raw_model_stream_event", "response.output_text.delta", "response.completed"}:
            text = _extract_text(_first_present(payload, "delta", "text", "content", "response"))
            if text:
                self._agent.message("assistant", text, event_type=event_type, stream=True)
            else:
                self._agent.state("openai_agents.model_event", event_type=event_type, event=payload)
            return event

        if event_type in {"response.failed", "run.failed"}:
            self._agent.error(_extract_text(payload) or event_type, event_type=event_type)
            return event

        self._agent.state("openai_agents.event", event_type=event_type, event=payload)
        return event

    def consume_many(self, events: Iterable[Any]) -> int:
        count = 0
        for event in events:
            self.consume(event)
            count += 1
        return count

    def __enter__(self) -> "OpenAIAgentsRecorder":
        self._ensure_started()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        if exc_val is not None:
            self._agent.error(exc_val, event_type="context_exit")
        self.close(success=exc_type is None)
        return False


def record_openai_agent_events(
    events: Iterable[Any],
    session: EpiRecorderSession,
    *,
    agent_name: str = "openai-agent",
    user_input: Optional[Any] = None,
    goal: Optional[str] = None,
    session_id: Optional[str] = None,
    task_id: Optional[str] = None,
    parent_run_id: Optional[str] = None,
    attempt: int = 1,
    resume_from: Optional[str] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> OpenAIAgentsRecorder:
    """
    Consume an iterable of OpenAI Agents-style events into the active EPI session.
    """
    recorder = OpenAIAgentsRecorder(
        session,
        agent_name=agent_name,
        user_input=user_input,
        goal=goal,
        session_id=session_id,
        task_id=task_id,
        parent_run_id=parent_run_id,
        attempt=attempt,
        resume_from=resume_from,
        metadata=metadata,
    )
    with recorder:
        recorder.consume_many(events)
    return recorder
