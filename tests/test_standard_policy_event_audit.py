"""Standard policy must not inherit the strict-mode correlation ceiling.

Strict is the claim-ready policy: an artifact whose operation identity cannot be
proven is a WARN there. Standard makes no such claim, so it must keep its
pre-existing verdicts — legacy and empty-lifecycle artifacts must not suddenly
warn just because the audit got more honest.

These tests pin both halves: the new ceiling applies to strict only.
"""

from __future__ import annotations

import json

from typer.testing import CliRunner

from epi_cli.main import app
from epi_core.container import EPIContainer
from epi_core.operation_identity import make_correlation
from epi_recorder.api import record

runner = CliRunner()


def _seal(tmp_path, monkeypatch, steps) -> object:
    monkeypatch.setenv("EPI_KEYS_DIR", str(tmp_path / "keys"))
    monkeypatch.setenv("EPI_NOTARIZE", "0")
    path = tmp_path / "run.epi"
    with record(str(path), goal="policy matrix", auto_sign=True) as epi:
        for kind, content in steps:
            epi.log_step(kind, content)
    return path


def _pin(tmp_path, artifact) -> object:
    manifest = EPIContainer.read_member_json(artifact, "manifest.json")
    trusted = tmp_path / "trusted"
    trusted.mkdir(exist_ok=True)
    (trusted / "producer.pub").write_text(manifest["public_key"], encoding="utf-8")
    return trusted


def _verify(monkeypatch, artifact, trusted, *extra):
    monkeypatch.setenv("EPI_TRUSTED_KEYS_DIR", str(trusted))
    monkeypatch.setenv("EPI_KEYS_DIR", str(trusted.parent / "verifier-keys"))
    result = runner.invoke(app, ["verify", str(artifact), "--json", *extra])
    report = json.loads(result.stdout)
    return result.exit_code, report


LEGACY_STEPS = [
    ("tool.call", {"tool": "lookup", "call_id": "c-1", "input": {"id": 1}}),
    ("tool.response", {"tool": "lookup", "call_id": "c-1", "ok": True}),
]

EMPTY_STEPS = [
    ("agent.decision", {"decision": "proceed"}),
]

_GOVERNED = make_correlation("opg_test", "opo_test")
GOVERNED_STEPS = [
    ("llm.request", {"model": "m", "messages": [], "correlation": _GOVERNED}),
    ("llm.response", {"model": "m", "choices": [], "correlation": _GOVERNED}),
]


# ---------------------------------------------------------------- legacy 4.11.2


def test_legacy_artifact_standard_still_passes(tmp_path, monkeypatch):
    artifact = _seal(tmp_path, monkeypatch, LEGACY_STEPS)
    trusted = _pin(tmp_path, artifact)

    exit_code, report = _verify(monkeypatch, artifact, trusted)
    assert report["facts"]["event_audit"]["status"] == "consistent_scope_unknown"
    assert report["facts"]["completeness_ok"] is True
    assert report["decision"]["status"] == "PASS", report["decision"]
    assert exit_code == 0
    assert "operation identity" not in report["decision"]["reason"]


def test_legacy_artifact_strict_ceiling_is_warn(tmp_path, monkeypatch):
    artifact = _seal(tmp_path, monkeypatch, LEGACY_STEPS)
    trusted = _pin(tmp_path, artifact)

    exit_code, report = _verify(monkeypatch, artifact, trusted, "--policy", "strict")
    assert report["decision"]["status"] == "WARN", report["decision"]
    assert "operation identity" in report["decision"]["reason"]
    assert exit_code == 0  # WARN never fails a script


# ---------------------------------------------------------------- no lifecycle events


def test_empty_lifecycle_artifact_standard_still_passes(tmp_path, monkeypatch):
    artifact = _seal(tmp_path, monkeypatch, EMPTY_STEPS)
    trusted = _pin(tmp_path, artifact)

    exit_code, report = _verify(monkeypatch, artifact, trusted)
    assert report["facts"]["event_audit"]["status"] == "no_observed_lifecycle_events"
    assert report["facts"]["completeness_ok"] is True
    assert report["decision"]["status"] == "PASS", report["decision"]
    assert exit_code == 0


def test_empty_lifecycle_artifact_strict_passes_without_coverage_claim(
    tmp_path, monkeypatch
):
    artifact = _seal(tmp_path, monkeypatch, EMPTY_STEPS)
    trusted = _pin(tmp_path, artifact)

    _exit_code, report = _verify(monkeypatch, artifact, trusted, "--policy", "strict")
    # Nothing was audited, so nothing failed. The status stays honest and the
    # reason must not read as a coverage claim.
    assert report["facts"]["event_audit"]["status"] == "no_observed_lifecycle_events"
    assert report["decision"]["status"] == "PASS", report["decision"]
    assert "does not establish" in report["decision"]["reason"]


# ---------------------------------------------------------------- governed


def test_governed_artifact_passes_both_policies(tmp_path, monkeypatch):
    artifact = _seal(tmp_path, monkeypatch, GOVERNED_STEPS)
    trusted = _pin(tmp_path, artifact)

    _exit_code, standard = _verify(monkeypatch, artifact, trusted)
    assert standard["facts"]["event_audit"]["status"] == "complete"
    assert standard["decision"]["status"] == "PASS"

    _exit_code, strict = _verify(monkeypatch, artifact, trusted, "--policy", "strict")
    assert strict["decision"]["status"] == "PASS", strict["decision"]
    assert "capture scope not declared" in strict["decision"]["reason"]
