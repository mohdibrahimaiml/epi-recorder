"""Data-only is the default seal; the self-opening HTML viewer is opt-in.

`record()`, `epi demo`, `epi record` and `epi run` seal a small data-only
``legacy-zip`` artifact by default. ``with_viewer=True`` / ``--with-viewer``
opts back into the polyglot ``envelope-v2`` shell. Both shapes verify
identically with `epi verify` (Python) and the browser verifier.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from epi_cli.main import app as cli_app
from epi_core.container import (
    EPIContainer,
    EPI_CONTAINER_FORMAT_ENVELOPE,
    EPI_CONTAINER_FORMAT_LEGACY,
)
from epi_core.trust import verify_embedded_manifest_signature
from epi_recorder import get_current_session, record

runner = CliRunner()

# Email-to-a-bank target for a small run. Data-only 5-step seals land far
# below this; accidentally re-embedding the ~270 KB viewer blows straight
# through it (that is the regression this ceiling catches).
SIZE_CEILING_BYTES = 80 * 1024
NODE = shutil.which("node")
NODE_HELPER = Path(__file__).parent / "helpers" / "verify_epi_node.mjs"


@pytest.fixture
def epi_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(tmp_path)
    home = tmp_path / "epi_home"
    home.mkdir()
    monkeypatch.setenv("EPI_HOME", str(home))
    monkeypatch.setenv("EPI_KEYS_DIR", str(home / "keys"))
    monkeypatch.setenv("EPI_TRUSTED_KEYS_DIR", str(home / "trusted_keys"))
    monkeypatch.setenv("EPI_NOTARIZE", "0")
    monkeypatch.setenv("EPI_TELEMETRY", "0")
    monkeypatch.setenv("EPI_TELEMETRY_HINTS", "0")
    return tmp_path


def _js_verify(path: Path) -> dict:
    proc = subprocess.run(
        [NODE, str(NODE_HELPER), str(path)],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, f"node verifier failed:\n{proc.stdout}\n{proc.stderr}"
    return json.loads(proc.stdout)


def _record_five_steps(out: Path, *, with_viewer: bool = False) -> None:
    with record(str(out), goal="five-step", with_viewer=with_viewer):
        s = get_current_session()
        assert s is not None
        for i in range(5):
            s.log_step("tool.call", {"tool": f"lookup-{i}", "id": f"A-{i}"})


def test_record_default_is_data_only(epi_env: Path):
    out = epi_env / "run.epi"
    _record_five_steps(out)

    assert EPIContainer.detect_container_format(out) == EPI_CONTAINER_FORMAT_LEGACY
    assert out.read_bytes()[:2] == b"PK"  # plain ZIP, not a polyglot HTML shell
    manifest = EPIContainer.read_manifest(out)
    assert manifest.container_format == EPI_CONTAINER_FORMAT_LEGACY
    with EPIContainer._payload_zip_path(out) as payload:
        import zipfile

        with zipfile.ZipFile(payload) as zf:
            assert "viewer.html" not in zf.namelist()
    assert "viewer.html" not in (manifest.file_manifest or {})


def test_record_data_only_under_size_ceiling(epi_env: Path):
    out = epi_env / "run.epi"
    _record_five_steps(out)
    size = out.stat().st_size
    # Reported so the sealed size is visible in test output.
    print(f"\n[data-only 5-step run] {size} bytes")
    assert size < SIZE_CEILING_BYTES, f"data-only run was {size} bytes (> {SIZE_CEILING_BYTES})"


def test_record_with_viewer_is_envelope_v2(epi_env: Path):
    out = epi_env / "run-viewer.epi"
    _record_five_steps(out, with_viewer=True)

    assert EPIContainer.detect_container_format(out) == EPI_CONTAINER_FORMAT_ENVELOPE
    assert out.read_bytes()[:4] == b"<!--"
    with EPIContainer._payload_zip_path(out) as payload:
        import zipfile

        with zipfile.ZipFile(payload) as zf:
            assert "viewer.html" in zf.namelist()


def test_both_formats_verify_python_and_cli(epi_env: Path):
    data_only = epi_env / "data.epi"
    with_viewer = epi_env / "viewer.epi"
    _record_five_steps(data_only)
    _record_five_steps(with_viewer, with_viewer=True)

    for path in (data_only, with_viewer):
        manifest = EPIContainer.read_manifest(path)
        assert verify_embedded_manifest_signature(manifest)[0] is True, path.name
        ok, mismatches = EPIContainer.verify_integrity(path)
        assert ok is True, (path.name, mismatches)

        result = runner.invoke(cli_app, ["verify", "--json", str(path)])
        assert result.exit_code == 0, result.output
        report = json.loads(result.stdout)
        assert report["facts"]["integrity_ok"] is True
        assert report["facts"]["signature_valid"] is True


@pytest.mark.skipif(NODE is None, reason="node required for the browser verifier")
def test_both_formats_verify_with_js_verifier(epi_env: Path):
    data_only = epi_env / "data.epi"
    with_viewer = epi_env / "viewer.epi"
    _record_five_steps(data_only)
    _record_five_steps(with_viewer, with_viewer=True)

    results = {p.name: _js_verify(p) for p in (data_only, with_viewer)}
    for name, r in results.items():
        assert r["structure"] is True, (name, r)
        assert r["integrity"] is True, (name, r)
        assert r["mismatches"] == 0, (name, r)
        assert r["signature"] is not False, (name, r)
    # Same data + same seal logic → identical verdict on both shapes.
    assert results["data.epi"]["signature"] == results["viewer.epi"]["signature"]


def test_demo_default_reports_size_and_is_data_only(epi_env: Path):
    result = runner.invoke(cli_app, ["demo", "--no-browser"])
    assert result.exit_code == 0, result.output

    epi = epi_env / "epi-recordings" / "demo_refund.epi"
    assert epi.is_file(), result.output
    flat = " ".join(result.output.split())  # rich wraps long lines
    assert "data-only" in flat
    assert re.search(r"\d[\d,]* bytes", flat), result.output

    assert EPIContainer.detect_container_format(epi) == EPI_CONTAINER_FORMAT_LEGACY
    assert epi.stat().st_size < SIZE_CEILING_BYTES


def test_demo_with_viewer_is_envelope_v2(epi_env: Path):
    result = runner.invoke(cli_app, ["demo", "--no-browser", "--with-viewer"])
    assert result.exit_code == 0, result.output
    flat = " ".join(result.output.split())
    assert "with viewer" in flat, result.output

    epi = epi_env / "epi-recordings" / "demo_refund.epi"
    assert epi.is_file(), result.output
    assert EPIContainer.detect_container_format(epi) == EPI_CONTAINER_FORMAT_ENVELOPE
    assert epi.read_bytes()[:4] == b"<!--"


def _payload_members(path: Path) -> set[str]:
    import zipfile

    with EPIContainer._payload_zip_path(path) as payload:
        with zipfile.ZipFile(payload) as zf:
            return set(zf.namelist())


def test_migrate_preserves_data_only(epi_env: Path):
    src = epi_env / "data.epi"
    _record_five_steps(src)
    assert "viewer.html" not in _payload_members(src)

    to_envelope = epi_env / "data-envelope.epi"
    r1 = runner.invoke(cli_app, ["migrate", str(src), "--out", str(to_envelope)])
    assert r1.exit_code == 0, r1.output
    assert "viewer.html" not in _payload_members(to_envelope)

    to_legacy = epi_env / "data-legacy.epi"
    r2 = runner.invoke(
        cli_app, ["migrate", str(src), "--out", str(to_legacy), "--legacy-zip"]
    )
    assert r2.exit_code == 0, r2.output
    assert "viewer.html" not in _payload_members(to_legacy)


def test_refresh_viewer_refuses_data_only(epi_env: Path):
    src = epi_env / "data.epi"
    _record_five_steps(src)
    before = src.read_bytes()

    result = runner.invoke(cli_app, ["refresh-viewer", str(src)])
    assert result.exit_code == 1, result.output
    assert "data-only" in result.output, result.output
    # Refused: file untouched, still data-only.
    assert src.read_bytes() == before
    assert "viewer.html" not in _payload_members(src)


def test_refresh_viewer_with_viewer_upgrades_data_only(epi_env: Path):
    src = epi_env / "data.epi"
    _record_five_steps(src)

    result = runner.invoke(cli_app, ["refresh-viewer", str(src), "--with-viewer"])
    assert result.exit_code == 0, result.output

    assert EPIContainer.detect_container_format(src) == EPI_CONTAINER_FORMAT_ENVELOPE
    assert "viewer.html" in _payload_members(src)
    ok, mismatches = EPIContainer.verify_integrity(src)
    assert ok is True, mismatches


def test_verify_txt_tells_the_recipient_how_to_open_it(epi_env: Path):
    """A data-only .epi does not open by double-click; VERIFY.txt must say so."""
    import zipfile

    out = epi_env / "data.epi"
    _record_five_steps(out)

    with zipfile.ZipFile(out) as zf:
        verify_txt = zf.read("VERIFY.txt").decode("utf-8")

    assert "HOW TO LOOK AT THIS FILE" in verify_txt
    assert "epi view" in verify_txt
    assert "epi associate" in verify_txt


def test_viewer_carries_a_network_denying_csp_end_to_end(epi_env: Path):
    """The sealed viewer must ship the CSP, in the member and the outer shell.

    "No network calls" is then enforced by the browser, not only by the code
    (docs/FILE-SAFETY.md section 5).
    """
    import zipfile

    out = epi_env / "viewer.epi"
    _record_five_steps(out, with_viewer=True)

    outer = out.read_bytes().split(b"\\n<!-- EPI_ZIP_PAYLOAD_START -->")[0]
    assert b"Content-Security-Policy" in outer
    assert b"connect-src 'none'" in outer

    with EPIContainer._payload_zip_path(out) as payload:
        with zipfile.ZipFile(payload) as zf:
            member = zf.read("viewer.html")
    assert b"Content-Security-Policy" in member
    assert b"connect-src 'none'" in member
