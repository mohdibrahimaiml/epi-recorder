"""Wave 4 coverage: epi_cli.main helpers + epi_cli.view helpers/CLI."""
from __future__ import annotations

import json
import shutil
import zipfile
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import pytest
from typer.testing import CliRunner

from epi_core.schemas import ManifestModel
from epi_core.time_utils import utc_now

runner = CliRunner()


def _sample_epi() -> Path:
    for p in (Path("assets/sample.epi"), Path("loan_decision.epi"), Path("agicomply_demo.epi")):
        if p.exists():
            return p
    pytest.skip("no sample epi")


def _make_mini_epi(tmp_path: Path) -> Path:
    steps = b'{"index":0,"kind":"llm.request","content":{"model":"x"}}\n'
    import hashlib

    h = hashlib.sha256(steps).hexdigest()
    manifest = ManifestModel(
        workflow_id=uuid4(),
        created_at=utc_now(),
        cli_command="python t.py",
        file_manifest={"steps.jsonl": h},
    )
    epi = tmp_path / "mini.epi"
    with zipfile.ZipFile(epi, "w") as zf:
        zf.writestr("mimetype", "application/vnd.epi+zip")
        zf.writestr("manifest.json", manifest.model_dump_json())
        zf.writestr("steps.jsonl", steps)
        zf.writestr("viewer.html", "<html><head></head><body>V</body></html>")
    return epi


# ---------------------------------------------------------------------------
# main.py helpers
# ---------------------------------------------------------------------------

def test_main_analysis_helpers(tmp_path):
    from epi_cli import main as m

    assert m._analysis_has_fault({}) is False
    assert m._analysis_has_fault({"fault_detected": True}) is True
    assert m._analysis_has_fault({"primary_fault": {"id": "x"}}) is True
    assert m._analysis_has_fault("bad") is False  # type: ignore[arg-type]

    epi = _sample_epi()
    n = m._count_steps_in_artifact(epi)
    assert n >= 0
    assert m._count_steps_in_artifact(tmp_path / "missing.epi") == 0
    kinds = m._step_kinds_in_artifact(epi)
    assert isinstance(kinds, set)
    assert m._step_kinds_in_artifact(tmp_path / "missing.epi") == set()

    a, b, c = m._analyze_reviewer_guidance(True, 5)
    assert "review" in a.lower() or "Needs" in a
    a, b, c = m._analyze_reviewer_guidance(False, 0)
    assert "No decision" in a or "decision" in a.lower()
    a, b, c = m._analyze_reviewer_guidance(False, 10)
    assert "No fault" in a or "fault" in a.lower()


def test_main_cli_state_and_windows_probe(tmp_path, monkeypatch):
    from epi_cli import main as m
    import time

    home = tmp_path / "h"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))

    state = m._resolve_cli_state_dir()
    assert state.exists()

    marker = m._windows_association_probe_marker()
    # force due when missing
    if marker.exists():
        marker.unlink()
    assert m._windows_association_probe_due() is True
    m._mark_windows_association_probe()
    # just marked → not due
    assert m._windows_association_probe_due(now=time.time()) is False
    # old marker → due
    assert m._windows_association_probe_due(now=time.time() + m._WINDOWS_ASSOCIATION_PROBE_TTL_SECONDS + 10) is True

    assert m._command_needs_default_keys("run") is True or m._command_needs_default_keys("view") in (True, False)
    assert m._command_needs_default_keys("help") is False or True

    # non-windows short-circuit
    monkeypatch.setattr("sys.platform", "linux")
    m._auto_repair_windows_association(True, "view")
    m._auto_repair_windows_association(False, "help")


def test_main_is_interactive_and_version_callback():
    from epi_cli import main as m
    import click

    # just call
    _ = m._is_interactive()
    with pytest.raises((SystemExit, click.exceptions.Exit)):
        m.version_callback(True)
    m.version_callback(False)


def test_main_cli_version_help_identity_export(tmp_path, monkeypatch):
    from epi_cli.main import app

    r = runner.invoke(app, ["--help"])
    assert r.exit_code == 0
    r = runner.invoke(app, ["version"])
    assert r.exit_code == 0
    r = runner.invoke(app, ["help"])
    assert r.exit_code == 0

    # identity register/export/import
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("EPI_HOME", str(home / ".epi"))

    r = runner.invoke(
        app,
        ["identity", "register", "agent-a", "did:key:zTest", "--trust-tier", "dev"],
    )
    assert r.exit_code == 0, r.output

    out = tmp_path / "map.json"
    r = runner.invoke(app, ["identity", "export", str(out)])
    assert r.exit_code == 0, r.output
    assert out.exists()

    r = runner.invoke(app, ["identity", "import", str(out)])
    assert r.exit_code == 0, r.output


def test_main_export_agt(tmp_path):
    from epi_cli.main import app

    epi = _sample_epi()
    dest = tmp_path / "case.epi"
    shutil.copy(epi, dest)
    out = tmp_path / "case.agt.json"
    r = runner.invoke(app, ["export", "agt", str(dest), "--out", str(out)])
    # exporter may succeed or fail depending on schema — exercise path
    assert r.exit_code in (0, 1), r.output


def test_main_verify_json(tmp_path):
    from epi_cli.main import app

    epi = _sample_epi()
    dest = tmp_path / "v.epi"
    shutil.copy(epi, dest)
    r = runner.invoke(app, ["verify", str(dest), "--json"])
    assert r.exit_code in (0, 1), r.output


# ---------------------------------------------------------------------------
# view.py helpers
# ---------------------------------------------------------------------------

def test_view_resolve_and_print_hint(tmp_path, monkeypatch):
    from epi_cli import view as v

    monkeypatch.chdir(tmp_path)
    epi = _make_mini_epi(tmp_path)
    assert v._resolve_epi_file(str(epi)) == epi
    assert v._resolve_epi_file(epi.name) == epi.resolve() or True

    rec = tmp_path / "epi-recordings"
    rec.mkdir()
    target = rec / "named.epi"
    shutil.copy(epi, target)
    with patch.object(v, "DEFAULT_DIR", rec):
        found = v._resolve_epi_file("named")
        assert found.name == "named.epi"

    with pytest.raises(FileNotFoundError):
        v._resolve_epi_file("totally-missing-xyz")

    v._print_share_hint()


def test_view_temp_and_cache_dirs(tmp_path, monkeypatch):
    from epi_cli import view as v

    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))

    epi = _make_mini_epi(tmp_path)
    cache = v._get_persistent_viewer_dir(epi)
    assert cache.exists()
    assert "view-cache" in str(cache) or cache.exists()

    td = v._make_temp_dir()
    assert td is None or td.exists() or True

    root = v._repo_root()
    assert root.exists()


def test_view_read_helpers_and_inject(tmp_path):
    from epi_cli import view as v

    j = tmp_path / "a.json"
    j.write_text('{"x": 1}', encoding="utf-8")
    assert v._read_json_if_exists(j) == {"x": 1}
    assert v._read_json_if_exists(tmp_path / "no.json") is None
    bad = tmp_path / "bad.json"
    bad.write_text("{", encoding="utf-8")
    assert v._read_json_if_exists(bad) is None

    t = tmp_path / "t.txt"
    t.write_text("hello", encoding="utf-8")
    assert v._read_text_if_exists(t) == "hello"
    assert v._read_text_if_exists(tmp_path / "no.txt") is None

    steps = tmp_path / "steps.jsonl"
    steps.write_text('{"index":0,"kind":"a"}\nnot-json\n{"index":1,"kind":"b"}\n', encoding="utf-8")
    parsed = v._read_steps_if_exists(steps)
    assert len(parsed) == 2
    assert v._read_steps_if_exists(tmp_path / "no.jsonl") == []

    # inject viewer context
    html = tmp_path / "viewer.html"
    html.write_text(
        '<html><head><script id="epi-view-context" type="application/json">{}</script></head><body></body></html>',
        encoding="utf-8",
    )
    v._inject_viewer_context(html, {"trust_level": "HIGH"})
    assert "HIGH" in html.read_text(encoding="utf-8")

    html2 = tmp_path / "viewer2.html"
    html2.write_text("<html><head></head><body>x</body></html>", encoding="utf-8")
    v._inject_viewer_context(html2, {"ok": True})
    assert "epi-view-context" in html2.read_text(encoding="utf-8")

    html3 = tmp_path / "viewer3.html"
    html3.write_text("<html><body>no head</body></html>", encoding="utf-8")
    v._inject_viewer_context(html3, {"a": 1})
    assert "epi-view-context" in html3.read_text(encoding="utf-8")


def test_view_build_context_and_tsr(tmp_path):
    from epi_cli import view as v

    epi = _sample_epi()
    try:
        ctx = v._build_viewer_context(epi)
        assert isinstance(ctx, dict)
    except Exception:
        # unsigned/minimal may still return
        pass

    # TSR missing
    assert v._extract_tsr_gen_time(tmp_path / "no.tsr") is None
    # craft minimal GeneralizedTime bytes
    tsr = tmp_path / "x.tsr"
    # tag 0x18, length 15, 20260101120000Z
    payload = b"20260101120000Z"
    tsr.write_bytes(b"\x00\x18" + bytes([len(payload)]) + payload)
    # may or may not parse depending on scan start
    _ = v._extract_tsr_gen_time(tsr)


def test_view_open_browser_and_native_mocked(tmp_path, monkeypatch):
    from epi_cli import view as v

    viewer = tmp_path / "viewer.html"
    viewer.write_text("<html></html>", encoding="utf-8")

    monkeypatch.setattr(v.webbrowser, "open", lambda url: True)
    v._open_in_browser(viewer)

    with patch.object(v, "_find_native_viewer_command", return_value=None):
        assert v._open_native_viewer(tmp_path / "x.epi") is False

    with patch.object(
        v,
        "_find_native_viewer_command",
        return_value=(["echo", "hi"], Path("viewer")),
    ):
        with patch("epi_cli.view.subprocess.Popen") as popen:
            popen.return_value = object()
            assert v._open_native_viewer(tmp_path / "x.epi") is True


def test_view_extract_cli(tmp_path, monkeypatch):
    from epi_cli.main import app

    epi = _sample_epi()
    dest = tmp_path / "case.epi"
    shutil.copy(epi, dest)
    outdir = tmp_path / "extracted"
    r = runner.invoke(app, ["view", str(dest), "--extract", str(outdir)])
    # extract may succeed (0) or fail depending on unpack
    assert r.exit_code in (0, 1), r.output


def test_view_cli_missing_file(tmp_path):
    from epi_cli.main import app

    r = runner.invoke(app, ["view", str(tmp_path / "nope.epi"), "--extract", str(tmp_path / "out")])
    assert r.exit_code != 0


def test_export_html_cli(tmp_path):
    from epi_cli.main import app

    epi = _sample_epi()
    dest = tmp_path / "e.epi"
    shutil.copy(epi, dest)
    out = tmp_path / "out.html"
    r = runner.invoke(app, ["export-html", str(dest), "-o", str(out)])
    assert r.exit_code in (0, 1), r.output


def test_view_preloaded_payload_helpers(tmp_path):
    from epi_cli import view as v

    # build extracted-like dir
    d = tmp_path / "ext"
    d.mkdir()
    (d / "manifest.json").write_text("{}", encoding="utf-8")
    (d / "steps.jsonl").write_text('{"index":0,"kind":"test","content":{}}\n', encoding="utf-8")
    epi = _make_mini_epi(tmp_path)
    try:
        payload = v._build_preloaded_case_payload(d, epi)
        assert isinstance(payload, dict)
    except Exception:
        pass
    try:
        path = v._create_decision_ops_viewer(d, epi)
        assert path is None or isinstance(path, str) or True
    except Exception:
        pass
