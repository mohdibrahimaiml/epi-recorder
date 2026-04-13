from __future__ import annotations

import json
from pathlib import Path

import pytest

from epi_core import telemetry


pytestmark = pytest.mark.unit


def test_telemetry_disable_cycle_env_opt_in_and_no_pre_opt_in_id(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("EPI_HOME", str(tmp_path))
    monkeypatch.delenv("EPI_TELEMETRY_OPT_IN", raising=False)

    assert telemetry.status()["enabled"] is False
    assert telemetry.get_install_id(create=False) is None
    assert not telemetry.telemetry_config_path().exists()

    enabled = telemetry.enable()
    assert enabled["install_id"]
    assert telemetry.status()["enabled"] is True

    disabled = telemetry.disable()
    assert disabled["enabled"] is False
    assert telemetry.status()["enabled"] is False

    monkeypatch.setenv("EPI_TELEMETRY_OPT_IN", "true")
    assert telemetry.status()["enabled"] is True
    assert telemetry.status()["enabled_by_env"] is True


def test_telemetry_test_event_queues_sanitized_payload_on_network_failure(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("EPI_HOME", str(tmp_path))
    telemetry.enable()
    monkeypatch.setattr(telemetry, "send_json", lambda *args, **kwargs: False)

    sent = telemetry.track_event(
        "telemetry.test",
        {"command": "telemetry test", "success": True, "source": "cli", "prompt": "drop me"},
    )

    assert sent is False
    assert not telemetry.telemetry_queue_path().exists()

    sent = telemetry.track_event(
        "telemetry.test",
        {"command": "telemetry test", "success": True, "source": "cli"},
    )
    queued = telemetry.telemetry_queue_path().read_text(encoding="utf-8")

    assert sent is False
    assert "telemetry.test" in queued
    assert "prompt" not in queued


def test_pilot_signup_email_consent_and_linking(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("EPI_HOME", str(tmp_path))
    telemetry.enable()

    with pytest.raises(telemetry.TelemetryError, match="valid email"):
        telemetry.build_pilot_signup(
            email="bad-email",
            use_case="governance",
            consent_to_contact=True,
        )

    with pytest.raises(telemetry.TelemetryError, match="consent"):
        telemetry.build_pilot_signup(
            email="pilot@example.com",
            use_case="governance",
            consent_to_contact=False,
        )

    signup = telemetry.build_pilot_signup(
        email="pilot@example.com",
        org="EPI Labs",
        role="reviewer",
        use_case="governance",
        consent_to_contact=True,
        link_telemetry=True,
    )

    assert signup["install_id"] == telemetry.get_install_id(create=False)
    assert telemetry.validate_pilot_signup_payload(signup)["email"] == "pilot@example.com"


def test_inbound_telemetry_rejects_remote_prompt_path_and_key_fields():
    payload = {
        "schema_version": telemetry.TELEMETRY_SCHEMA_VERSION,
        "install_id": "install-1",
        "event_name": "epi.verify.completed",
        "timestamp": "2026-04-12T00:00:00Z",
        "metadata": {"command": "verify", "success": True},
    }
    assert telemetry.validate_event_payload(payload)["metadata"]["command"] == "verify"

    for banned_key in ("prompt", "path", "api_key"):
        bad = json.loads(json.dumps(payload))
        bad["metadata"][banned_key] = "secret"
        with pytest.raises(telemetry.TelemetryError):
            telemetry.validate_event_payload(bad)
