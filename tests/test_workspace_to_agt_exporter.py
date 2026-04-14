"""Tests for the workspace -> AGT exporter."""

import json
from pathlib import Path

from epi_recorder.integrations.agt.exporter import export_workspace_to_agt


def test_export_workspace_to_agt(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()

    manifest = {
        "workflow_id": "wf-123",
        "created_at": "2025-01-01T00:00:00Z",
        "signature": "sig-abc",
        "approved_by": "tester",
        "governance": {"identity": {"value": "agent-xyz"}},
    }
    (ws / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    steps = [
        {"index": 0, "kind": "session.start", "content": {"workflow": "test"}, "timestamp": "2025-01-01T00:00:00Z"},
        {"index": 1, "kind": "llm.request", "content": {"prompt": "hi"}, "timestamp": "2025-01-01T00:00:01Z"},
    ]
    (ws / "steps.jsonl").write_text("\n".join(json.dumps(s) for s in steps), encoding="utf-8")

    out = tmp_path / "out" / "export.json"
    path = export_workspace_to_agt(ws, out, include_raw=True)

    assert path.exists()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["audit_id"].startswith("workspace_")
    assert isinstance(data.get("events"), list)
    assert data.get("raw", {}).get("manifest") is not None
