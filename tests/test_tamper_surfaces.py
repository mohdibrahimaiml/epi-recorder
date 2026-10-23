"""Every command that shows or ships an .epi must flag a tampered file.

Regression: `epi view` printed a fixed "Seal OK", `epi audit` ticked
"Cryptographic" from the signature alone, and `epi export-html` packaged an
altered file as a shareable page.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

from typer.testing import CliRunner

from epi_cli.main import app as cli_app
from tests.test_did_onboarding import _hermetic, _keypair_for, _sealed_with

runner = CliRunner()


def _tampered_copy(src: Path, dst: Path) -> Path:
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "steps.jsonl":
                data = data + b'{"index": 999, "kind": "forged", "content": {}}\n'
            zout.writestr(item, data)
    return dst


def _files(monkeypatch, tmp_path: Path) -> tuple[Path, Path]:
    _hermetic(monkeypatch, tmp_path)
    private, key_hex = _keypair_for("tamper-surfaces")
    good = _sealed_with(private, key_hex, tmp_path, "good", None)
    return good, _tampered_copy(good, tmp_path / "bad.epi")


def test_view_reports_altered_file(monkeypatch, tmp_path: Path) -> None:
    good, bad = _files(monkeypatch, tmp_path)
    monkeypatch.setattr("epi_cli.view._open_in_browser", lambda *_a, **_k: None)

    out = runner.invoke(cli_app, ["view", str(bad)]).output.replace("\n", " ")
    assert "ALTERED" in out
    assert "Seal OK" not in out

    out = runner.invoke(cli_app, ["view", str(good)]).output.replace("\n", " ")
    assert "Seal intact" in out
    assert "ALTERED" not in out


def test_view_extract_marks_altered_folder(monkeypatch, tmp_path: Path) -> None:
    """B7: extraction still works for forensics, but the folder is marked."""
    good, bad = _files(monkeypatch, tmp_path)

    altered = tmp_path / "extract"
    result = runner.invoke(cli_app, ["view", str(bad), "--extract", str(altered)])
    assert result.exit_code != 0
    assert (tmp_path / "extract_ALTERED").is_dir()
    assert not altered.exists()
    assert "_ALTERED" in result.output

    clean = tmp_path / "clean"
    result = runner.invoke(cli_app, ["view", str(good), "--extract", str(clean)])
    assert result.exit_code == 0, result.output
    assert clean.is_dir()
    assert not (tmp_path / "clean_ALTERED").exists()


def test_export_html_refuses_altered_file(monkeypatch, tmp_path: Path) -> None:
    good, bad = _files(monkeypatch, tmp_path)

    result = runner.invoke(cli_app, ["export-html", str(bad), "-o", str(tmp_path / "bad.html")])
    assert result.exit_code != 0
    assert not (tmp_path / "bad.html").exists()

    result = runner.invoke(cli_app, ["export-html", str(good), "-o", str(tmp_path / "good.html")])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "good.html").exists()


def test_audit_crypto_tick_requires_integrity(monkeypatch, tmp_path: Path) -> None:
    good, bad = _files(monkeypatch, tmp_path)

    out = runner.invoke(cli_app, ["audit", str(bad)]).output
    assert "FILE ALTERED" in out

    out = runner.invoke(cli_app, ["audit", str(good)]).output
    assert "FILE ALTERED" not in out


def test_epi_register_finds_file_in_epi_recordings(monkeypatch, tmp_path: Path) -> None:
    """README path: record("demo.epi") lands in epi-recordings/, then `epi-register demo.epi`."""
    import shutil

    from epi_cli.register import app as register_app

    good, _bad = _files(monkeypatch, tmp_path)
    work = tmp_path / "work"
    (work / "epi-recordings").mkdir(parents=True)
    shutil.copy(good, work / "epi-recordings" / "demo.epi")
    monkeypatch.chdir(work)

    result = runner.invoke(register_app, ["demo.epi", "--local"])
    assert "File not found" not in result.output, result.output


def test_own_key_pin_does_not_make_other_senders_fail(monkeypatch, tmp_path: Path) -> None:
    """Pinning the user's own key must not make other senders FAIL."""
    from epi_core.keys import KeyManager

    _hermetic(monkeypatch, tmp_path)
    km = KeyManager(keys_dir=tmp_path / "home" / "keys")
    km.generate_keypair("default")
    km.trust_key("default", trusted_keys_dir=tmp_path / "home" / "trusted")

    private, key_hex = _keypair_for("someone-else")
    other = _sealed_with(private, key_hex, tmp_path, "other", None)
    result = runner.invoke(cli_app, ["verify", str(other)])
    assert result.exit_code == 0, result.output
    assert "NOT A KEY YOU TRUST" not in result.output
