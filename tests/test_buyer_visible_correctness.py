"""Buyer-visible correctness: one story across seal summary, analysis.json and `epi analyze`.

Covers:
- Issue #157: a low-severity P11b observation is NOT a fault, and all three
  surfaces must agree (no "FAULT DETECTED", no "no heuristic issues flagged").
- VERIFY.txt states the *sealing* EPI version and a correct verify command.
- manifest.policy is populated when a policy was loaded/evaluated, null when absent.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from epi_cli.main import _analysis_has_fault
from epi_cli.main import app as cli_app
from epi_core._version import get_version
from epi_core.artifact_summary import format_artifact_run_summary_lines
from epi_core.container import EPIContainer
from epi_recorder import get_current_session, record

runner = CliRunner()

POLICY = {"system_name": "Demo", "policy_version": "1.0", "rules": []}


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(tmp_path)
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("EPI_HOME", str(home))
    monkeypatch.setenv("EPI_KEYS_DIR", str(home / "keys"))
    monkeypatch.setenv("EPI_TRUSTED_KEYS_DIR", str(home / "trusted_keys"))
    monkeypatch.setenv("EPI_NOTARIZE", "0")
    monkeypatch.setenv("EPI_TELEMETRY", "0")
    return tmp_path


def _seal(out: Path, *, with_policy: bool = False) -> Path:
    if with_policy:
        (Path.cwd() / "epi_policy.json").write_text(json.dumps(POLICY), encoding="utf-8")
    with record(str(out), goal="buyer-visible") as session:
        assert session is not None
        session.log_step("agent.run.start", {"agent_name": "DemoAgent"})
        # tool.call with no matching tool.response -> P11b (severity low)
        session.log_step("tool.call", {"tool": "refund_lookup", "input": {"id": "A-1"}})
        session.log_step("agent.decision", {"decision": "approve", "content": "ok"})
    return out


# ── Issue #157 ──────────────────────────────────────────────────────────────

def test_p11b_observation_is_consistent_across_surfaces(env: Path):
    out = env / "heuristic.epi"
    _seal(out)

    analysis = EPIContainer.read_member_json(out, "analysis.json")
    assert analysis["fault_detected"] is False
    assert (analysis.get("primary_fault") or {}).get("rule_id") == "P11b"
    assert (analysis.get("primary_fault") or {}).get("severity") == "low"

    # epi analyze must NOT claim FAULT DETECTED for a low observation...
    result = runner.invoke(cli_app, ["analyze", str(out)])
    assert result.exit_code == 0, result.output
    assert "FAULT DETECTED" not in result.output
    assert "no anomalies detected" in result.output.lower()
    # ...but must not hide it either.
    assert "observation" in result.output.lower()
    assert "P11b" in result.output

    # The seal summary must not claim "no heuristic issues flagged".
    lines = "\n".join(format_artifact_run_summary_lines(out))
    assert "no heuristic issues flagged" not in lines
    assert "low-severity observation" in lines


def test_medium_plus_is_still_a_fault():
    # Regression guard: the #157 fix must not downgrade real faults.
    assert _analysis_has_fault({"primary_fault": {"severity": "medium"}}) is True
    assert _analysis_has_fault({"primary_fault": {"severity": "critical"}}) is True
    assert _analysis_has_fault({"fault_detected": True}) is True
    assert _analysis_has_fault({"primary_fault": {"severity": "low"}}) is False
    assert _analysis_has_fault({"primary_fault": {"severity": "info"}}) is False


# ── VERIFY.txt ──────────────────────────────────────────────────────────────

def test_verify_txt_states_the_sealing_version_and_command(env: Path):
    out = env / "versioned.epi"
    _seal(out)

    manifest = EPIContainer.read_manifest(out)
    expected = manifest.producer_version or get_version()
    txt = EPIContainer.read_member_text(out, "VERIFY.txt")

    assert f"EPI Version:   {expected}" in txt
    assert f"Spec Version:  {manifest.spec_version}" in txt
    assert "epi verify <this_file>.epi" in txt
    # The stale hardcoded version string must no longer be the only version shown.
    assert "EPI_RECORDER v1.0" not in txt.split("Artifact UUID")[0]


# ── manifest.policy ─────────────────────────────────────────────────────────

def test_manifest_policy_is_set_when_policy_loaded(env: Path):
    out = env / "policy.epi"
    _seal(out, with_policy=True)

    manifest = EPIContainer.read_manifest(out)
    assert manifest.policy_load_status == "loaded"
    assert manifest.policy is not None
    assert manifest.policy.policy_id
    assert manifest.policy.version == "1.0"
    assert manifest.policy.status == "compliant"
    assert manifest.policy.violation_count == 0


def test_manifest_policy_is_null_when_no_policy(env: Path):
    out = env / "no-policy.epi"
    _seal(out)

    manifest = EPIContainer.read_manifest(out)
    assert manifest.policy_load_status == "absent"
    assert manifest.policy is None
