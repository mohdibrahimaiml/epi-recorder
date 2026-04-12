from typer.testing import CliRunner

from epi_cli.main import app


runner = CliRunner()


def test_telemetry_status_does_not_create_install_id(tmp_path):
    result = runner.invoke(app, ["telemetry", "status"], env={"EPI_HOME": str(tmp_path)})

    assert result.exit_code == 0
    assert "Enabled: no" in result.output
    assert (tmp_path / "telemetry.json").exists() is False


def test_telemetry_enable_with_pilot_signup(monkeypatch, tmp_path):
    sent = []

    def _fake_send(url, payload, *, timeout=2.0):  # noqa: ANN001
        sent.append((url, payload))
        return True

    monkeypatch.setattr("epi_core.telemetry.send_json", _fake_send)
    result = runner.invoke(
        app,
        [
            "telemetry",
            "enable",
            "--join-pilot",
            "--email",
            "pilot@example.com",
            "--org",
            "EPI Labs",
            "--role",
            "founder",
            "--use-case",
            "agt integration",
            "--link-telemetry",
            "--consent-to-contact",
        ],
        env={"EPI_HOME": str(tmp_path)},
    )

    assert result.exit_code == 0, result.output
    assert (tmp_path / "telemetry.json").exists()
    assert (tmp_path / "pilot_signup.json").exists()
    assert sent
    assert sent[0][1]["email"] == "pilot@example.com"
    assert sent[0][1]["link_telemetry"] is True
