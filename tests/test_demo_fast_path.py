"""epi demo fast path: record → seal → verify without gateway."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from epi_cli.main import app as cli_app

runner = CliRunner()


@pytest.fixture
def demo_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(tmp_path)
    home = tmp_path / "epi_home"
    home.mkdir()
    monkeypatch.setenv("EPI_HOME", str(home))
    monkeypatch.setenv("EPI_KEYS_DIR", str(home / "keys"))
    monkeypatch.setenv("EPI_TRUSTED_KEYS_DIR", str(home / "trusted_keys"))
    monkeypatch.setenv("EPI_NOTARIZE", "0")
    monkeypatch.setenv("EPI_TELEMETRY_HINTS", "0")
    monkeypatch.setenv("EPI_TELEMETRY", "0")
    return tmp_path


def test_demo_no_browser_produces_verified_epi(demo_cwd: Path):
    result = runner.invoke(cli_app, ["demo", "--no-browser"])
    assert result.exit_code == 0, result.output
    assert "record · seal · verify · view" in result.output or "Sealed artifact" in result.output
    epi = demo_cwd / "epi-recordings" / "demo_refund.epi"
    assert epi.is_file(), f"missing {epi}; output was:\n{result.output}"
    assert epi.stat().st_size > 10_000
    assert "integrity=PASS" in result.output or "Offline verify" in result.output
    # intentional demo secret must not leak
    from epi_core.container import EPIContainer

    steps = EPIContainer.read_steps(epi)
    assert "sk-" + ("d" * 40) not in str(steps)


def test_demo_help_mentions_review_flag():
    result = runner.invoke(cli_app, ["demo", "--help"])
    assert result.exit_code == 0
    assert "--review" in result.output or "review" in result.output.lower()
