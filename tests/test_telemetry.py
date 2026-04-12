from epi_core import telemetry


def test_telemetry_does_not_create_id_before_opt_in(monkeypatch, tmp_path):
    monkeypatch.setenv("EPI_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("EPI_TELEMETRY_OPT_IN", raising=False)

    assert telemetry.is_enabled() is False
    assert telemetry.build_event("epi.verify.completed", {"command": "verify"}) is None
    assert telemetry.telemetry_config_path().exists() is False


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
