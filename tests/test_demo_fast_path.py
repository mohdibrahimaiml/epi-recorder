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


def test_demo_push_helper_false_when_not_logged_in(demo_cwd: Path, capsys):
    from epi_cli.dev import _demo_push_if_logged_in

    epi = demo_cwd / "run.epi"
    epi.write_bytes(b"fake")
    assert _demo_push_if_logged_in(epi) is False
    out = capsys.readouterr().out
    assert "epi cloud login" in out


def test_demo_push_helper_true_when_push_succeeds(demo_cwd: Path, monkeypatch, capsys):
    import json

    from epi_cli.dev import _demo_push_if_logged_in

    (demo_cwd / "epi_home" / "cloud.json").write_text(
        json.dumps({"url": "https://cloud.test", "org_id": "org_1", "api_key": "k",
                    "customer": "Acme Bank"}),
        encoding="utf-8",
    )

    class _OkRunner:
        def invoke(self, app, args):
            class R:
                exit_code = 0
                output = "ok"

            return R()

    monkeypatch.setattr("typer.testing.CliRunner", _OkRunner)
    epi = demo_cwd / "run.epi"
    epi.write_bytes(b"fake")
    assert _demo_push_if_logged_in(epi) is True
    out = capsys.readouterr().out
    assert "Pushed to cloud" in out
    assert "Acme Bank" in out


def test_demo_done_lines_pushed_uses_saved_host(demo_cwd: Path):
    import json

    from epi_cli.dev import _demo_cloud_host, _demo_done_lines
    from pathlib import Path as _Path

    assert _demo_cloud_host() == "cloud.epilabs.org"
    (demo_cwd / "epi_home" / "cloud.json").write_text(
        json.dumps({"url": "https://example.test/"}), encoding="utf-8"
    )
    assert _demo_cloud_host() == "example.test"
    pushed = "\n".join(_demo_done_lines(epi_path=_Path("a.epi"), pushed=True))
    assert "open example.test -> Share" in pushed
    assert "Not shared yet" not in pushed
    missing = "\n".join(_demo_done_lines(epi_path=_Path("a.epi"), pushed=False))
    assert "Not shared yet: run epi cloud login, then epi demo again" in missing
    assert "epi verify a.epi" in missing
    assert "epi view a.epi" in missing
    assert "-> Share" not in missing


def test_demo_end_panel_when_not_logged_in(demo_cwd: Path):
    result = runner.invoke(cli_app, ["demo", "--no-browser"])
    assert result.exit_code == 0, result.output
    assert "Not shared yet: run epi cloud login, then epi demo again" in result.output
    assert "epi verify" in result.output
    assert "-> Share" not in result.output
