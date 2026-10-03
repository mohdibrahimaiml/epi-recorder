"""Post-seal summary: honest policy status without a new user command."""

from __future__ import annotations

import json
from pathlib import Path

from epi_core.artifact_summary import (
    build_artifact_run_summary,
    format_artifact_run_summary_lines,
)
from epi_core.container import EPIContainer
from epi_core.policy import EPIPolicy
from epi_core.schemas import ManifestModel
from tests.helpers.artifacts import make_decision_workspace


def test_summary_reports_missing_policy_as_heuristic(tmp_path: Path, monkeypatch):
    # Isolate cwd: pack falls back to ./epi_policy.json by design (run from
    # project root), so a repo checkout cwd would otherwise leak its policy
    # into this no-policy seal.
    monkeypatch.chdir(tmp_path)
    ws = make_decision_workspace(tmp_path)
    out = tmp_path / "no_policy.epi"
    EPIContainer.pack(ws, ManifestModel(cli_command="test", goal="demo"), out)

    s = build_artifact_run_summary(out, signed=False)
    assert s["exists"] is True
    assert s["policy_status"] == "missing"
    lines = "\n".join(format_artifact_run_summary_lines(out, signed=False))
    assert "heuristic only" in lines.lower() or "missing" in lines.lower()
    assert "epi view" in lines


def test_summary_reports_applied_policy(tmp_path: Path, monkeypatch):
    ws = make_decision_workspace(tmp_path)
    # Minimal valid typed policy in cwd so load_policy finds it during pack
    policy = {
        "policy_format_version": "2.0",
        "policy_id": "demo-rules",
        "system_name": "demo-agent",
        "system_version": "1.0",
        "policy_version": "1",
        "rules": [
            {
                "id": "R001",
                "name": "Fraud check before deny",
                "severity": "critical",
                "description": "Must run fraud check before deny.",
                "type": "sequence_guard",
                "required_before": "deny_claim",
                "must_call": "run_fraud_check",
            }
        ],
    }
    policy_path = tmp_path / "epi_policy.json"
    policy_path.write_text(json.dumps(policy), encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    out = tmp_path / "with_policy.epi"
    EPIContainer.pack(ws, ManifestModel(cli_command="test", goal="demo"), out)

    s = build_artifact_run_summary(out)
    assert s["policy_status"] == "applied"
    assert s["policy_id"] == "demo-rules"
    assert s["rules_evaluated"] is not None
    lines = "\n".join(format_artifact_run_summary_lines(out))
    assert "applied" in lines.lower()
    assert "demo-rules" in lines


def test_summary_missing_file_safe():
    s = build_artifact_run_summary(Path("does-not-exist-xyz.epi"))
    assert s["exists"] is False
    lines = format_artifact_run_summary_lines(Path("does-not-exist-xyz.epi"))
    assert lines
