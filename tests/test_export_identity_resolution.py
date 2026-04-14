import json
from pathlib import Path

import epi_cli.identity as identity
from epi_recorder.integrations.agt.exporter import export_workspace_to_agt


def test_export_workspace_resolves_identity(tmp_path: Path, monkeypatch):
    # Redirect identity state dir to tmp path to avoid touching real home
    monkeypatch.setattr(identity, "_state_dir", lambda: tmp_path / ".epi")

    # Register a mapping
    identity.register_agent("claims-agent", "did:key:xyz", public_key="ed25519:abc", trust_tier="standard")

    ws = tmp_path / "ws"
    ws.mkdir()

    manifest = {
        "workflow_id": "wf-claims",
        "created_at": "2025-01-01T00:00:00Z",
        "signature": "sig-abc",
        "governance": {"identity": {"value": "claims-agent"}},
    }
    (ws / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    steps = [{"index": 0, "kind": "session.start", "content": {}, "timestamp": "2025-01-01T00:00:00Z"}]
    (ws / "steps.jsonl").write_text("\n".join(json.dumps(s) for s in steps), encoding="utf-8")

    out = tmp_path / "out" / "export.json"
    export_workspace_to_agt(ws, out)

    data = json.loads(out.read_text(encoding="utf-8"))
    assert data.get("agent") is not None
    assert data["agent"].get("id") == "did:key:xyz"
    assert data["agent"].get("public_key") == "ed25519:abc"
    assert data["agent"].get("trust_tier") == "standard"
