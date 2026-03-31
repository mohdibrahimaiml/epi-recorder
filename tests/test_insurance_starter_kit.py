from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from epi_cli.export_summary import summary
from epi_core.container import EPIContainer


def _load_insurance_module():
    starter_path = Path(__file__).resolve().parents[1] / "examples" / "starter_kits" / "insurance_claim" / "agent.py"
    spec = importlib.util.spec_from_file_location("insurance_claim_agent", starter_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_insurance_claim_starter_kit_runs_and_exports_decision_record(tmp_path, monkeypatch):
    module = _load_insurance_module()
    starter_dir = Path(__file__).resolve().parents[1] / "examples" / "starter_kits" / "insurance_claim"
    policy_path = starter_dir / "epi_policy.json"
    (tmp_path / "epi_policy.json").write_text(policy_path.read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    output_path = tmp_path / "insurance_case.epi"
    decision = module.run_claim_denial_demo(output_file=str(output_path))

    assert output_path.exists()
    assert decision["decision"] == "deny_claim"

    manifest = EPIContainer.read_manifest(output_path)
    assert manifest.analysis_status == "complete", f"Insurance demo analysis failed: {manifest.analysis_error}"

    unpacked = EPIContainer.unpack(output_path)
    policy_eval = json.loads((unpacked / "policy_evaluation.json").read_text(encoding="utf-8"))
    assert policy_eval["policy_id"] == "insurance-claim-denial-demo"
    assert policy_eval["controls_evaluated"] >= 5

    summary_path = tmp_path / "decision_record.html"
    summary(str(output_path), out=summary_path, text=False)
    html = summary_path.read_text(encoding="utf-8")
    assert "EPI Decision Record" in html
    assert "Policy Compliance Summary" in html
