import json
import sys
import tempfile
from pathlib import Path

from epi_core.schemas import ManifestModel
from epi_core.container import EPIContainer
from epi_recorder.integrations.agt.exporter import export_epi_to_agt
import epi_cli.identity as identity


def run_export_test(tmpdir: str) -> None:
    tmp = Path(tmpdir)
    src = tmp / "src"
    src.mkdir(parents=True, exist_ok=True)

    steps = [
        {
            "index": 0,
            "timestamp": "2026-04-14T10:00:00Z",
            "kind": "agent.decision",
            "content": {"action": "approve_claim", "decision": "ALLOW", "policy_id": "policy-1"},
        }
    ]

    steps_path = src / "steps.jsonl"
    steps_path.write_text("\n".join(json.dumps(s) for s in steps), encoding="utf-8")

    manifest = ManifestModel(cli_command="quicktest:agt_export", goal="quicktest")
    out_epi = tmp / "output.epi"

    EPIContainer.pack(src, manifest, out_epi, signer_function=None, generate_analysis=False)

    out_agt = tmp / "output.agt.json"
    export_epi_to_agt(out_epi, out_agt, include_raw=True)

    payload = json.loads(out_agt.read_text(encoding="utf-8"))
    assert payload["audit_id"].startswith("epi_")
    assert payload["execution"]["steps"] == 1
    assert any(e.get("type") == "decision" for e in payload["events"]) is True
    assert payload["integrity"].get("epi_signature") == manifest.signature


def run_identity_test(tmpdir: str) -> None:
    tmp = Path(tmpdir)
    # Redirect map storage to a test-only directory
    test_map_dir = tmp / "identity"
    # monkeypatch-like override
    identity._state_dir = lambda: test_map_dir

    identity.register_agent("claims-agent", "did:key:xyz", public_key="ed25519:abc", trust_tier="standard")

    out = tmp / "mapping.json"
    identity.export_mapping(out)

    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["claims-agent"]["did"] == "did:key:xyz"

    # Import mapping back and verify stored file
    identity.import_mapping(out)
    stored = json.loads((test_map_dir / "identity_map.json").read_text(encoding="utf-8"))
    assert stored["claims-agent"]["did"] == "did:key:xyz"


def main():
    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            run_export_test(tmpdir)
            run_identity_test(tmpdir)
            print("QUICK TESTS: ALL PASSED")
            sys.exit(0)
        except AssertionError as ae:
            print("QUICK TESTS: FAILED -", ae)
            sys.exit(2)
        except Exception as exc:
            import traceback

            traceback.print_exc()
            sys.exit(3)


if __name__ == "__main__":
    main()
