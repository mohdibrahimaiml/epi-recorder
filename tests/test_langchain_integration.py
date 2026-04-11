from __future__ import annotations

from uuid import uuid4

from epi_recorder.integrations.langchain import EPICallbackHandler


class _DummySession:
    def __init__(self):
        self.logged: list[tuple[str, dict]] = []

    def log_step(self, kind: str, payload: dict) -> None:
        self.logged.append((kind, payload))


def test_on_chain_start_tolerates_missing_serialized_payload(monkeypatch):
    handler = EPICallbackHandler()
    session = _DummySession()
    monkeypatch.setattr(handler, "_get_session", lambda: session)

    handler.on_chain_start(
        None,
        {"text": "Quarterly financial report"},
        run_id=uuid4(),
    )

    assert session.logged
    kind, payload = session.logged[0]
    assert kind == "chain.start"
    assert payload["name"] == "unknown"
    assert "text" in payload["inputs"]


def test_tool_callbacks_emit_native_epi_tool_steps(monkeypatch):
    handler = EPICallbackHandler()
    session = _DummySession()
    monkeypatch.setattr(handler, "_get_session", lambda: session)
    run_id = uuid4()

    handler.on_tool_start(
        {"name": "lookup_order"},
        '{"order_id":"123"}',
        run_id=run_id,
    )
    handler.on_tool_end({"status": "paid"}, run_id=run_id)

    assert [kind for kind, _ in session.logged] == ["tool.call", "tool.response"]
    assert session.logged[0][1]["tool"] == "lookup_order"
    assert session.logged[1][1]["tool"] == "lookup_order"
    assert session.logged[1][1]["status"] == "success"
