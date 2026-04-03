"""Smoke test for v2.8.0 policy and fault analysis."""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

from epi_core.container import EPIContainer
from epi_core.schemas import ManifestModel


POLICY = {
    "system_name": "smoke-test-agent",
    "system_version": "1.0",
    "policy_version": "2026-03-16",
    "rules": [
        {
            "id": "R010",
            "name": "Large Transaction Approval",
            "severity": "high",
            "description": "Amounts above 10k require human approval.",
            "type": "threshold_guard",
            "threshold_value": 10000,
            "threshold_field": "amount",
            "required_action": "human_approval",
        }
    ],
}


def main() -> int:
    temp_root = Path(tempfile.mkdtemp(prefix="epi_smoke_"))
    workspace = temp_root / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)

    try:
        steps = [
            {
                "index": 0,
                "kind": "session.start",
                "content": {"workflow": "payment_flow"},
                "timestamp": "2026-03-16T00:00:00Z",
            },
            {
                "index": 1,
                "kind": "tool.call",
                "content": {"tool": "approve_payment", "amount": 15000.0},
                "timestamp": "2026-03-16T00:00:01Z",
            },
            {
                "index": 2,
                "kind": "session.end",
                "content": {"success": True},
                "timestamp": "2026-03-16T00:00:02Z",
            },
        ]

        (workspace / "steps.jsonl").write_text(
            "\n".join(json.dumps(step) for step in steps) + "\n",
            encoding="utf-8",
        )
        (workspace / "environment.json").write_text(
            json.dumps({"os": "windows", "python": "3.11"}),
            encoding="utf-8",
        )
        (temp_root / "epi_policy.json").write_text(json.dumps(POLICY, indent=2), encoding="utf-8")

        original_cwd = Path.cwd()
        try:
            import os

            os.chdir(temp_root)
            output = temp_root / "smoke.epi"
            EPIContainer.pack(workspace, ManifestModel(file_manifest={}), output)
        finally:
            os.chdir(original_cwd)

        unpack_dir = EPIContainer.unpack(output)
        analysis_path = unpack_dir / "analysis.json"
        if not analysis_path.exists():
            raise RuntimeError("analysis.json not produced")

        analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
        primary_fault = analysis.get("primary_fault") or {}

        if not analysis.get("fault_detected"):
            raise RuntimeError("fault_detected was false")
        if primary_fault.get("rule_id") != "R010":
            raise RuntimeError(f"unexpected primary rule_id: {primary_fault.get('rule_id')}")

        print("SMOKE TEST PASSED")
        print(f"artifact: {output}")
        print(f"primary fault: {primary_fault.get('plain_english', '')}")
        return 0
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)
