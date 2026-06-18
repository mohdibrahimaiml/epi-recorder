from epi_core import telemetry


def test_telemetry_does_not_create_id_before_opt_in(monkeypatch, tmp_path):
    monkeypatch.setenv("EPI_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("EPI_TELEMETRY_OPT_IN", raising=False)

    assert telemetry.is_enabled() is False
    assert telemetry.build_event("epi.verify.completed", {"command": "verify"}) is None
    assert telemetry.telemetry_config_path().exists() is False
    assert telemetry.track_event("epi.verify.completed", {"command": "verify"}) is False
    assert telemetry.telemetry_queue_path().exists() is False


def test_enable_creates_install_id_and_builds_safe_event(monkeypatch, tmp_path):
    monkeypatch.setenv("EPI_HOME", str(tmp_path / "home"))

    config = telemetry.enable()
    assert config["install_id"]

    event = telemetry.build_event(
        "epi.verify.completed",
        {"command": "verify", "artifact_bytes": 123},
    )

    assert event is not None
    assert event["install_id"] == config["install_id"]
    assert event["metadata"]["artifact_bytes"] == 123


def test_banned_metadata_is_not_sent(monkeypatch, tmp_path):
    monkeypatch.setenv("EPI_HOME", str(tmp_path / "home"))
    telemetry.enable()

    assert telemetry.track_event("epi.verify.completed", {"prompt": "do not send"}) is False
    assert telemetry.telemetry_queue_path().exists() is False


def test_failed_telemetry_send_is_queued_and_flushed(monkeypatch, tmp_path):
    monkeypatch.setenv("EPI_HOME", str(tmp_path / "home"))
    telemetry.enable()
    sent = []

    def _offline(url, payload, *, timeout=2.0):  # noqa: ANN001
        return False

    monkeypatch.setattr(telemetry, "send_json", _offline)
    assert telemetry.track_event("epi.verify.completed", {"command": "verify", "success": True}) is False
    queue_path = telemetry.telemetry_queue_path()
    assert queue_path.exists()
    assert "epi.verify.completed" in queue_path.read_text(encoding="utf-8")

    def _online(url, payload, *, timeout=2.0):  # noqa: ANN001
        sent.append((url, payload))
        return True

    monkeypatch.setattr(telemetry, "send_json", _online)
    result = telemetry.flush_queued_events()

    assert result["sent"] == 1
    assert result["remaining"] == 0
    assert result["dropped"] == 0
    assert sent[0][1]["event_name"] == "epi.verify.completed"
    assert queue_path.exists() is False


def test_pilot_signup_requires_contact_consent(monkeypatch, tmp_path):
    monkeypatch.setenv("EPI_HOME", str(tmp_path / "home"))
    telemetry.enable()

    try:
        telemetry.build_pilot_signup(
            email="pilot@example.com",
            use_case="agt integration",
            consent_to_contact=False,
        )
    except telemetry.TelemetryError as exc:
        assert "consent" in str(exc).lower()
    else:
        raise AssertionError("expected pilot signup consent failure")


def test_validate_inbound_event_rejects_unknown_metadata():
    payload = {
        "schema_version": telemetry.TELEMETRY_SCHEMA_VERSION,
        "install_id": "id-1",
        "event_name": "epi.verify.completed",
        "timestamp": "2026-04-12T00:00:00Z",
        "metadata": {"command": "verify", "repo_name": "private/repo"},
    }

    try:
        telemetry.validate_event_payload(payload)
    except telemetry.TelemetryError as exc:
        assert "banned" in str(exc).lower()
    else:
        raise AssertionError("expected validation failure")


import os
from pathlib import Path


def test_record_first_use_emits_only_once(monkeypatch, tmp_path):
    monkeypatch.setenv("EPI_HOME", str(tmp_path / "home"))
    telemetry.enable()

    # Mock send_json to force queuing.
    monkeypatch.setattr(telemetry, "send_json", lambda url, payload, *, timeout=2.0: False)

    assert telemetry.is_first_use_recorded() is False
    assert telemetry.record_first_use() is True
    assert telemetry.is_first_use_recorded() is True

    # Second call should be a no-op but still return True.
    assert telemetry.record_first_use() is True

    queue = telemetry._read_jsonl(telemetry.telemetry_queue_path())
    first_use_events = [q for q in queue if q["payload"]["event_name"] == "epi.first_use"]
    assert len(first_use_events) == 1


def test_record_first_use_is_no_op_when_disabled(monkeypatch, tmp_path):
    monkeypatch.setenv("EPI_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("EPI_TELEMETRY_OPT_IN", raising=False)

    assert telemetry.is_enabled() is False
    assert telemetry.record_first_use() is False
    assert telemetry.is_first_use_recorded() is False


def test_recording_emits_record_completed_event(monkeypatch, tmp_path):
    monkeypatch.setenv("EPI_HOME", str(tmp_path / "home"))
    telemetry.enable()
    monkeypatch.setattr(telemetry, "send_json", lambda url, payload, *, timeout=2.0: False)

    from epi_recorder import EpiRecorderSession

    output = tmp_path / "test.epi"
    with EpiRecorderSession(str(output), workflow_name="test"):
        pass

    assert output.exists()
    queue = telemetry._read_jsonl(telemetry.telemetry_queue_path())
    record_events = [q for q in queue if q["payload"]["event_name"] == "epi.record.completed"]
    assert len(record_events) == 1
    assert record_events[0]["payload"]["metadata"]["success"] is True
    assert record_events[0]["payload"]["metadata"]["artifact_count"] == 1

    # A first_use event should also be queued.
    first_use_events = [q for q in queue if q["payload"]["event_name"] == "epi.first_use"]
    assert len(first_use_events) == 1


def test_recording_does_not_emit_telemetry_when_disabled(monkeypatch, tmp_path):
    monkeypatch.setenv("EPI_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("EPI_TELEMETRY_OPT_IN", raising=False)

    from epi_recorder import EpiRecorderSession

    output = tmp_path / "test.epi"
    with EpiRecorderSession(str(output), workflow_name="test"):
        pass

    assert output.exists()
    assert telemetry.telemetry_queue_path().exists() is False
