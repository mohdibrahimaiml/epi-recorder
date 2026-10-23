"""B8: the trust hint mentions a witness log only when one exists."""

from __future__ import annotations

import shutil
from pathlib import Path

from typer.testing import CliRunner

from epi_cli.main import app as cli_app
from epi_core.container import EPIContainer
from epi_core.keys import key_fingerprint
from tests.test_did_onboarding import _hermetic, _keypair_for, _sealed_with

runner = CliRunner()


def _pin(epi: Path, name: str):
    fp = key_fingerprint(EPIContainer.read_manifest(epi).public_key)
    return runner.invoke(
        cli_app,
        ["keys", "trust", str(epi), "--name", name, "--fingerprint", fp],
    )


def test_witness_log_hint_is_conditional(monkeypatch, tmp_path: Path) -> None:
    _hermetic(monkeypatch, tmp_path)
    monkeypatch.chdir(tmp_path)
    private, key_hex = _keypair_for("witness-hint")
    epi = _sealed_with(private, key_hex, tmp_path, "witness-hint", None)

    no_log = _pin(epi, "no-log")
    assert no_log.exit_code == 0, no_log.output
    assert "--witness-log" not in no_log.output

    # Fresh pin so the success branch prints the hint again.
    shutil.rmtree(tmp_path / "home" / "trusted", ignore_errors=True)
    (tmp_path / "received.jsonl").write_text("", encoding="utf-8")

    with_log = _pin(epi, "with-log")
    assert with_log.exit_code == 0, with_log.output
    assert "--witness-log received.jsonl" in with_log.output
