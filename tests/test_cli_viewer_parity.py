"""CLI and viewer must report the same finding at the same step.

Regression guard from the screenshot review: `epi verify` (positional
completeness audit) and the viewer (§3/§6, sealed analysis) once cited
different step numbers for the same file. Both surfaces now use 1-based
step numbers, and this test pins them together on an unambiguous trace:
one orphaned tool call both matchers agree on.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from typer.testing import CliRunner

from epi_cli.main import app as cli_app
from epi_core.container import EPIContainer
from epi_core.schemas import ManifestModel
from epi_core.trust import sign_manifest

runner = CliRunner()
STEP_RE = re.compile(r"at step (\d+)")


def _seal_single_orphan(tmp_path: Path) -> Path:
    """Camera call/response match by tool name; eject call is the lone orphan."""
    src = tmp_path / "source"
    src.mkdir()
    lines = [
        {"index": 0, "kind": "tool.call",
         "content": {"tool": "camera.capture", "input": {}}},
        {"index": 1, "kind": "tool.response",
         "content": {"tool": "camera.capture", "status": "ok"}},
        {"index": 2, "kind": "tool.call",
         "content": {"tool": "actuator.eject", "input": {}}},
    ]
    (src / "steps.jsonl").write_text(
        "\n".join(json.dumps(s) for s in lines) + "\n", encoding="utf-8"
    )
    out = tmp_path / "parity.epi"
    key = Ed25519PrivateKey.generate()
    EPIContainer.pack(
        src,
        ManifestModel(goal="parity", cli_command="pytest parity"),
        out,
        signer_function=lambda m: sign_manifest(m, key, "parity"),
    )
    return out


def test_cli_gap_and_analysis_flag_name_same_step(tmp_path):
    epi_path = _seal_single_orphan(tmp_path)

    result = runner.invoke(cli_app, ["verify", str(epi_path), "--json"])
    assert result.exit_code == 0, result.output
    text = result.output or ""
    report = json.loads(text[text.find("{"): text.rfind("}") + 1])

    cli_steps = sorted(
        {int(m.group(1)) for m in STEP_RE.finditer(json.dumps(report.get("facts", {})))}
    )
    assert cli_steps, "CLI reported no step reference for the orphan"

    raw = json.loads(EPIContainer.read_member_text(epi_path, "analysis.json"))
    flags = ([raw["primary_fault"]] if raw["primary_fault"] else []) + raw[
        "secondary_flags"
    ]
    assert flags, "analyzer flagged nothing"
    analysis_steps = sorted({f["step_number"] for f in flags})

    # Same finding (orphaned eject call), same 1-based step, both surfaces.
    assert cli_steps == analysis_steps == [3]

    # 1-based bounds: every cited step is a real step in the file.
    total = len(
        EPIContainer.read_member_text(epi_path, "steps.jsonl").strip().splitlines()
    )
    assert all(1 <= n <= total for n in cli_steps + analysis_steps)


def test_sealed_controls_failed_matches_results(tmp_path):
    """Guards the controls_failed reset: header must equal failed results."""
    epi_path = _seal_single_orphan(tmp_path)
    evaluation = json.loads(
        EPIContainer.read_member_text(epi_path, "policy_evaluation.json")
    )
    failed = [r for r in evaluation["results"] if r["status"] == "failed"]
    assert evaluation["controls_failed"] == len(failed)
    assert evaluation["controls_evaluated"] == len(evaluation["results"])
