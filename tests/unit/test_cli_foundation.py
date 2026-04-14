from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from epi_cli.main import app
from tests.helpers.artifacts import make_decision_epi


pytestmark = pytest.mark.unit
runner = CliRunner()


def test_cli_integrate_dry_run_writes_nothing(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["integrate", "pytest", "--dry-run"])

    assert result.exit_code == 0, result.output
    assert "DRY-RUN" in result.output
    assert not (tmp_path / ".epi" / "examples").exists()


def test_cli_verify_view_and_export_summary_offline(tmp_path: Path):
    artifact, _ = make_decision_epi(tmp_path, signed=True)
    extract_dir = tmp_path / "extract"
    summary_path = tmp_path / "decision-record.html"

    verify = runner.invoke(app, ["verify", str(artifact)])
    view = runner.invoke(app, ["view", str(artifact), "--extract", str(extract_dir)])
    export = runner.invoke(
        app,
        ["export-summary", "summary", str(artifact), "--out", str(summary_path)],
    )

    assert verify.exit_code == 0, verify.output
    assert view.exit_code == 0, view.output
    assert export.exit_code == 0, export.output
    assert (extract_dir / "viewer.html").exists()
    assert "EPI Decision Record" in summary_path.read_text(encoding="utf-8")


def test_cli_telemetry_status_enable_disable_cycle(tmp_path: Path):
    env = {"EPI_HOME": str(tmp_path)}

    status_before = runner.invoke(app, ["telemetry", "status"], env=env)
    enabled = runner.invoke(app, ["telemetry", "enable", "--no-pilot-prompt"], env=env)
    disabled = runner.invoke(app, ["telemetry", "disable"], env=env)

    assert status_before.exit_code == 0, status_before.output
    assert "Enabled: no" in status_before.output
    assert enabled.exit_code == 0, enabled.output
    assert disabled.exit_code == 0, disabled.output
