"""A direct `verify_command(...)` call must behave like the CLI defaults.

Regression guard for the truthy-`OptionInfo` bug: calling the command as a
plain Python function (tests, tools, plugins) used to receive
`typer.Option(False, ...)` *objects*, which are truthy, so every direct call
behaved as if `--web`, `--qr`, `--aiuc1` and `--offline` had been passed —
opening https://epilabs.org/verify in the developer's browser on every run.

The conftest shim would hide that (it swallows the launch), so this test
asserts on the recorded URL list instead: intent, not side effect.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import typer

from epi_cli.verify import verify_command
from epi_core.container import EPIContainer
from epi_core.schemas import ManifestModel


def _sealed(tmp_path: Path) -> Path:
    source = tmp_path / "source"
    source.mkdir()
    (source / "test.txt").write_text("Hello", encoding="utf-8")

    out = tmp_path / "unsigned.epi"
    EPIContainer.pack(source, ManifestModel(cli_command="test"), out)
    return out


def test_direct_verify_call_opens_no_browser(request, tmp_path, capsys):
    artifact = _sealed(tmp_path)

    try:
        verify_command(ctx=MagicMock(), epi_file=artifact)
    except typer.Exit:
        pass

    opened = getattr(request.node, "_epi_browser_urls", [])
    assert opened == [], f"direct verify call opened a browser: {opened}"


def test_direct_verify_call_prints_no_qr_code(request, tmp_path, capsys):
    artifact = _sealed(tmp_path)

    try:
        verify_command(ctx=MagicMock(), epi_file=artifact)
    except typer.Exit:
        pass

    output = capsys.readouterr().out
    assert "Scan this QR code" not in output
