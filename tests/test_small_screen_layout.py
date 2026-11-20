"""Layout guards for the places a first-time user meets on a small screen.

Found by a normal-user pass: the Decision Record crushed four tiles into one
row on a phone, the How it works code card ran off the screen, and `epi ls`
squashed eight columns into "D…" fragments on an 80-column terminal.
"""

from __future__ import annotations

import inspect
import io
from pathlib import Path

from rich.console import Console

REPO = Path(__file__).resolve().parents[1]
SITE = REPO / "website"


def test_decision_record_template_stacks_on_phones() -> None:
    from epi_cli import export_summary

    source = inspect.getsource(export_summary)
    assert "@media (max-width: 760px)" in source
    assert ".summary-grid {{ grid-template-columns: repeat(2, minmax(0, 1fr))" in source
    assert "overflow-wrap: anywhere" in source


def test_published_example_records_have_the_phone_layout() -> None:
    for name in ("decision-record-example.html", "naic-claim-override.html"):
        html = (SITE / "assets" / "demo" / name).read_text(encoding="utf-8")
        assert "@media (max-width: 760px)" in html, name


def test_card_grids_cannot_be_stretched_by_wide_code() -> None:
    css = (SITE / "css" / "zenjin-epi.css").read_text(encoding="utf-8")
    assert ".z-tri-grid {\n  display: grid;" in css
    start = css.index(".z-tri-grid {")
    assert "grid-template-columns: minmax(0, 1fr);" in css[start : start + 300]


def test_verifier_does_not_show_the_zip_library_bug_prefix() -> None:
    js = (SITE / "js" / "home-verify.js").read_text(encoding="utf-8")
    assert "replace(/^\\s*Bug\\s*:\\s*/i,'')" in js


def _ls_output(width: int, tmp_path: Path, monkeypatch) -> str:
    import shutil

    from typer.testing import CliRunner

    from epi_cli import ls as ls_mod
    from epi_cli.main import app

    rec = tmp_path / "epi-recordings"
    rec.mkdir()
    shutil.copy(SITE / "assets" / "demo" / "decision-example.epi", rec / "decision-example.epi")
    monkeypatch.chdir(tmp_path)
    buf = io.StringIO()
    monkeypatch.setattr(ls_mod, "console", Console(file=buf, width=width, force_terminal=False))
    result = CliRunner().invoke(app, ["ls"])
    assert result.exit_code == 0, result.output
    return buf.getvalue()


def test_ls_is_readable_on_an_80_column_terminal(tmp_path: Path, monkeypatch) -> None:
    out = _ls_output(80, tmp_path, monkeypatch)
    assert "decision-example.epi" in out
    assert "Goal" in out
    assert "Tags" not in out and "Metrics" not in out


def test_ls_shows_every_column_on_a_wide_terminal(tmp_path: Path, monkeypatch) -> None:
    out = _ls_output(140, tmp_path, monkeypatch)
    for header in ("Goal", "Tags", "Metrics"):
        assert header in out, header
