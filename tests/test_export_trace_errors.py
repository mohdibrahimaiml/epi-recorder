"""B9: signed TRACE export must explain the unsigned alternative."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from epi_cli.main import app as cli_app
from epi_recorder.integrations.trace_exporter import epi_to_trace_record

runner = CliRunner()
GOLDEN = Path(__file__).resolve().parent / "goldens" / "legacy-spec-4.3.0.epi"


def test_signed_export_without_transcript_uri_names_no_sign() -> None:
    with pytest.raises(ValueError) as excinfo:
        epi_to_trace_record(GOLDEN, strict=True)
    assert "--no-sign" in str(excinfo.value)


def test_cli_signed_export_fails_with_no_sign_hint(tmp_path: Path) -> None:
    result = runner.invoke(
        cli_app,
        ["export", "trace", str(GOLDEN), "--out", str(tmp_path / "trace.json")],
    )
    assert result.exit_code != 0
    assert "--no-sign" in result.output


def test_cli_unsigned_export_succeeds(tmp_path: Path) -> None:
    out = tmp_path / "trace.json"
    result = runner.invoke(
        cli_app,
        ["export", "trace", str(GOLDEN), "--no-sign", "--out", str(out)],
    )
    assert result.exit_code == 0, result.output
    assert out.is_file()
    assert out.stat().st_size > 100
