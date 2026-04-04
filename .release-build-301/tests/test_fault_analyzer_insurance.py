from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from epi_core.container import EPIContainer
from epi_core.fault_analyzer import FaultAnalyzer
from epi_core.policy import EPIPolicy


def _load_insurance_module():
    starter_path = Path(__file__).resolve().parents[1] / "examples" / "starter_kits" / "insurance_claim" / "agent.py"
    spec = importlib.util.spec_from_file_location("insurance_claim_agent", starter_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_insurance_claim_workflow_produces_no_false_positive_findings(tmp_path, monkeypatch):
    module = _load_insurance_module()
    starter_dir = Path(__file__).resolve().parents[1] / "examples" / "starter_kits" / "insurance_claim"
    policy_path = starter_dir / "epi_policy.json"
    (tmp_path / "epi_policy.json").write_text(policy_path.read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    artifact_path = tmp_path / "insurance_case.epi"
    module.run_claim_denial_demo(output_file=str(artifact_path))

    unpacked = EPIContainer.unpack(artifact_path)
    steps_jsonl = (unpacked / "steps.jsonl").read_text(encoding="utf-8")
    policy = EPIPolicy.model_validate(json.loads((unpacked / "policy.json").read_text(encoding="utf-8")))

    result = FaultAnalyzer(policy=policy).analyze(steps_jsonl)
    analysis_payload = result.to_dict()
    all_findings = ([analysis_payload["primary_fault"]] if analysis_payload.get("primary_fault") else []) + analysis_payload["secondary_flags"]
    heuristic_findings = [item for item in all_findings if item.get("category") == "heuristic_observation"]

    assert heuristic_findings == [], f"False positive findings: {heuristic_findings}"
