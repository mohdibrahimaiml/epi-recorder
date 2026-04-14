import json
from pathlib import Path

from epi_core.schemas import ManifestModel
from epi_core.container import EPIContainer


def test_exporter_basic(tmp_path: Path):
    src = tmp_path / "src"
    src.mkdir()

    steps = [
        {
            "index": 0,
            "timestamp": "2026-04-14T10:00:00Z",
            "kind": "agent.decision",
            "content": {
                "action": "approve_claim",
                "decision": "ALLOW",
                "policy_id": "policy-1",
            },
        }
    ]

    # write steps.jsonl
    steps_path = src / "steps.jsonl"
    steps_path.write_text("\n".join(json.dumps(s) for s in steps), encoding="utf-8")

    manifest = ManifestModel(cli_command="pytest:agt_export", goal="test-goal", tags=["test"])
    out_epi = tmp_path / "output.epi"

    # Pack without analysis to keep test light-weight
    EPIContainer.pack(src, manifest, out_epi, signer_function=None, generate_analysis=False)

    from epi_recorder.integrations.agt.exporter import export_epi_to_agt

    out_agt = tmp_path / "output.agt.json"
    export_epi_to_agt(out_epi, out_agt, include_raw=True)

    payload = json.loads(out_agt.read_text(encoding="utf-8"))
    assert payload["audit_id"].startswith("epi_")
    assert payload["execution"]["steps"] == 1
    assert any(e.get("type") == "decision" for e in payload["events"]) is True
    # signature may be None when no signer_function provided
    assert payload["integrity"].get("epi_signature") == manifest.signature
