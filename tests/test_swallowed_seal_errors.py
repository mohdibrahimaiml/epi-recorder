"""Regression tests for the class-A swallowed-exception fixes.

Each test forces the failure path that was previously swallowed and asserts the
failure is now surfaced (or fails closed), not silently dropped.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest
from typer.testing import CliRunner

from epi_cli.main import app as cli_app
from epi_core.schemas import ManifestModel

runner = CliRunner()


def _make_epi(path: Path, members: dict[str, bytes | str]) -> Path:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "mimetype", "application/vnd.epi+zip", compress_type=zipfile.ZIP_STORED
        )
        zf.writestr(
            "manifest.json",
            ManifestModel(cli_command="test", goal="swallow test").model_dump_json(),
        )
        zf.writestr("steps.jsonl", '{"index":0,"kind":"session.start","content":{}}\n')
        for name, data in members.items():
            zf.writestr(name, data)
    return path


# ── fault_analyzer: crashed detector is recorded, not dropped ────────────────

def test_crashed_detector_is_recorded(monkeypatch: pytest.MonkeyPatch):
    from epi_core.fault_analyzer import FaultAnalyzer

    analyzer = FaultAnalyzer(policy=None, manifest_meta={})

    def boom(_steps):
        raise RuntimeError("detector boom")

    monkeypatch.setattr(analyzer, "_pass1_error_continuation", boom)
    result = analyzer.analyze(
        '{"index":0,"kind":"session.start","content":{"workflow_name":"x"}}\n'
    )

    assert any(
        e["pass"] == "_pass1_error_continuation" for e in result.detector_errors
    ), result.detector_errors
    data = result.to_dict()
    assert data["detectors_failed"] == len(result.detector_errors) >= 1
    assert data["detector_errors"][0]["error"].startswith("RuntimeError")


def test_analyze_cli_flags_incomplete_analysis(tmp_path: Path):
    analysis = {
        "fault_detected": False,
        "mode": "heuristic_only",
        "coverage": {"steps_recorded": 2, "coverage_percentage": 100},
        "primary_fault": None,
        "secondary_flags": [],
        "detector_errors": [
            {"pass": "_pass5_prohibition_violation", "error": "RuntimeError: boom"}
        ],
        "detectors_failed": 1,
    }
    epi = _make_epi(tmp_path / "incomplete.epi", {"analysis.json": json.dumps(analysis)})

    result = runner.invoke(cli_app, ["analyze", str(epi)])
    assert result.exit_code == 0, result.output
    assert "Analysis incomplete" in result.output
    # A crashed detector must not read as a clean run.
    assert "No anomalies detected" not in result.output


# ── environment: redaction failure withholds the snapshot ────────────────────

def test_environment_redaction_failure_withholds_snapshot(monkeypatch: pytest.MonkeyPatch):
    import epi_core.redactor as redactor
    import epi_recorder.environment as env

    def boom():
        raise RuntimeError("no redactor available")

    monkeypatch.setattr(redactor, "get_default_redactor", boom)
    monkeypatch.setattr(env, "capture_installed_packages", lambda: {})

    snapshot = env.capture_full_environment(redact_env_vars=True)

    assert snapshot.get("redaction_failed") is True
    assert "no redactor available" in snapshot.get("redaction_error", "")
    # The unredacted snapshot must NOT be returned.
    assert "environment_variables" not in snapshot


# ── manifest: absent vs corrupt capture manifest ─────────────────────────────

def test_read_manifest_from_archive_distinguishes_absent_from_corrupt(tmp_path: Path):
    from epi_core.manifest import read_manifest_from_archive

    absent = _make_epi(tmp_path / "absent.epi", {})
    assert read_manifest_from_archive(absent) is None

    corrupt = _make_epi(tmp_path / "corrupt.epi", {"artifacts/manifest.json": "{not json"})
    with pytest.raises(Exception):
        read_manifest_from_archive(corrupt)


# ── bootstrap: finalize failure warns instead of vanishing ───────────────────

def test_bootstrap_finalize_failure_warns(monkeypatch: pytest.MonkeyPatch, capsys):
    import epi_recorder.bootstrap as bootstrap
    import epi_recorder.patcher as patcher

    class _BadContext:
        def finalize(self):
            raise RuntimeError("finalize boom")

    monkeypatch.setattr(patcher, "get_recording_context", lambda: _BadContext())
    monkeypatch.setattr(patcher, "set_recording_context", lambda _v: None)

    bootstrap._finalize_bootstrap_recording()  # must not raise at shutdown

    err = capsys.readouterr().err
    assert "bootstrap recording finalize failed" in err
    assert "finalize boom" in err
