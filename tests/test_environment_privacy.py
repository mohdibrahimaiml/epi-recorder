"""A sealed artifact must not carry the builder's machine with it.

``environment.json`` is shipped to whoever receives the file. Interpreter paths,
argv, PIDs and the CPU model describe the builder's laptop — usernames, project
names, hostnames — not the run.
"""

from __future__ import annotations

import json

from epi_recorder.environment import capture_full_environment


def test_default_snapshot_has_no_host_details(monkeypatch):
    monkeypatch.delenv("EPI_ENV_FULL", raising=False)

    env = capture_full_environment(redact_env_vars=False)

    assert "executable" not in env["python"]
    assert "argv" not in env["python"]
    assert "pid" not in env["python"]
    assert "ppid" not in env["python"]
    assert "processor" not in env["os"]
    assert "memory" not in env["os"]
    assert env["host_details"]["redacted"] is True
    assert "python.executable" in env["host_details"]["fields"]
    # The shape a reviewer needs is still there.
    assert env["python"]["version"]
    assert env["os"]["system"]


def test_argv_becomes_a_count_not_a_path(monkeypatch):
    monkeypatch.delenv("EPI_ENV_FULL", raising=False)

    env = capture_full_environment(redact_env_vars=False)

    assert isinstance(env["python"].get("argv_count"), int)
    assert env["python"]["argv_count"] >= 1


def test_full_detail_is_opt_in(monkeypatch):
    monkeypatch.setenv("EPI_ENV_FULL", "1")

    env = capture_full_environment(redact_env_vars=False)

    assert "pid" in env["python"]
    assert "executable" in env["python"]
    assert "host_details" not in env


def test_saved_snapshot_on_disk_is_scrubbed(monkeypatch, tmp_path):
    import json

    from epi_recorder.environment import save_environment_snapshot

    monkeypatch.delenv("EPI_ENV_FULL", raising=False)
    out = tmp_path / "environment.json"
    save_environment_snapshot(out, redact_env_vars=False)

    written = json.loads(out.read_text(encoding="utf-8"))
    assert "pid" not in written["python"]
    assert "executable" not in written["python"]
    assert "processor" not in written["os"]


def test_host_environment_variables_are_not_captured(monkeypatch):
    """USER is the username; HOME/PWD/PYTHONPATH are folders. None ship."""
    monkeypatch.delenv("EPI_ENV_FULL", raising=False)
    secrets = {
        "USER": "dell",
        "HOME": "C:\\Users\\dell",
        "PWD": "C:\\Users\\dell\\epi-recorder",
        "PYTHONPATH": "C:\\Users\\dell\\epi-recorder",
        "VIRTUAL_ENV": "C:\\Users\\dell\\venv",
    }
    for k, v in secrets.items():
        monkeypatch.setenv(k, v)

    env = capture_full_environment(redact_env_vars=False)
    blob = json.dumps(env)

    for name, value in secrets.items():
        assert value not in blob, f"{name} value leaked into environment.json"
        assert f"env.{name}" in env["host_details"]["fields"], f"{name} not declared"

    # The harmless, useful ones survive.
    for keep in ("TERM", "LANG", "SHELL"):
        monkeypatch.setenv(keep, f"value-of-{keep}")
    env2 = capture_full_environment(redact_env_vars=False)
    assert env2["environment_variables"].get("TERM") == "value-of-TERM"


def test_sealed_artifact_contains_no_host_values(monkeypatch, tmp_path):
    """End to end: the bytes handed to a counterparty carry no host detail."""
    from epi_recorder import get_current_session, record

    monkeypatch.delenv("EPI_ENV_FULL", raising=False)
    secrets = {
        "USER": "qa-private-user",
        "HOME": "C:\\Users\\qa-private-user",
        "PWD": "C:\\Users\\qa-private-user\\client-acme",
        "PYTHONPATH": "C:\\Users\\qa-private-user\\client-acme",
        "VIRTUAL_ENV": "C:\\Users\\qa-private-user\\venv",
    }
    for k, v in secrets.items():
        monkeypatch.setenv(k, v)

    out = tmp_path / "case.epi"
    with record(str(out)):
        session = get_current_session()
        assert session is not None
        session.log_step("tool.call", {"tool": "lookup"})

    data = out.read_bytes()
    for name, value in secrets.items():
        assert value.encode() not in data, f"{name} value found in the sealed file"
    assert b"qa-private-user" not in data
