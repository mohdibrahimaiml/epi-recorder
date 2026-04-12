from __future__ import annotations

from types import SimpleNamespace

from epi_recorder.integrations.opentelemetry import EPISpanExporter


def test_tool_spans_emit_native_tool_response_kind():
    exporter = EPISpanExporter.__new__(EPISpanExporter)
    span = SimpleNamespace(
        name="tool.lookup_order",
        attributes={"tool.name": "lookup_order"},
        status=None,
    )

    assert exporter._infer_step_kind(span) == "tool.response"
    assert exporter._extract_tool_name(span) == "lookup_order"
