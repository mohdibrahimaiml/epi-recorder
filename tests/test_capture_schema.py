from epi_core.capture import CAPTURE_SPEC_VERSION, CaptureBatchModel, CaptureEventModel


def test_capture_event_lifts_ids_and_defaults_provenance():
    event = CaptureEventModel.model_validate(
        {
            "kind": "llm.request",
            "content": {"message": "hello"},
            "meta": {
                "trace_id": "trace-123",
                "decision_id": "decision-456",
                "source": "openai-proxy",
                "capture_mode": "imported",
            },
        }
    )

    assert event.schema_version == CAPTURE_SPEC_VERSION
    assert event.event_id.startswith("evt_")
    assert event.trace_id == "trace-123"
    assert event.decision_id == "decision-456"
    assert event.provenance.source == "openai-proxy"
    assert event.provenance.capture_mode == "imported"
    assert event.provenance.trust_class == "verified_imported"
    assert event.meta["capture_spec_version"] == CAPTURE_SPEC_VERSION
    assert event.meta["provenance"]["trust_class"] == "verified_imported"


def test_capture_event_accepts_connector_friendly_aliases():
    event = CaptureEventModel.model_validate(
        {
            "eventType": "tool.call",
            "payload": {"tool": "lookup_order", "input": {"order_id": "123"}},
            "traceId": "trace-js-123",
            "workflowName": "Refund approvals",
            "sourceApp": "n8n",
            "captureMode": "imported",
            "bridgeWarning": "Captured by connector adapter",
        }
    )

    assert event.kind == "tool.call"
    assert event.content["tool"] == "lookup_order"
    assert event.trace_id == "trace-js-123"
    assert event.workflow_name == "Refund approvals"
    assert event.source_app == "n8n"
    assert event.provenance.source == "n8n"
    assert event.provenance.capture_mode == "imported"
    assert event.provenance.notes == "Captured by connector adapter"


def test_capture_event_wraps_non_dict_connector_payload():
    event = CaptureEventModel.model_validate(
        {
            "type": "agent.message",
            "data": "Approved by reviewer",
        }
    )

    assert event.kind == "agent.message"
    assert event.content == {"value": "Approved by reviewer"}


def test_capture_batch_counts_and_normalizes_items():
    batch = CaptureBatchModel.from_items(
        [
            {"kind": "llm.request", "content": {"prompt": "hi"}},
            {"kind": "policy.check", "content": {"rule_id": "R001"}, "meta": {"capture_mode": "manual"}},
        ]
    )

    assert batch.schema_version == CAPTURE_SPEC_VERSION
    assert batch.batch_id.startswith("batch_")
    assert batch.count == 2
    assert batch.items[0].event_id.startswith("evt_")
    assert batch.items[1].provenance.trust_class == "partial"
