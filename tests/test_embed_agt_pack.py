"""Verify the optional embedding of AGT export during packing."""

import json
from pathlib import Path

from epi_core.container import EPIContainer
from epi_core.schemas import ManifestModel


def test_pack_with_embed_agt(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()

    # minimal steps file
    steps = [
        {"index": 0, "kind": "session.start", "content": {"workflow": "t"}, "timestamp": "2025-01-01T00:00:00Z"}
    ]
    (ws / "steps.jsonl").write_text("\n".join(json.dumps(s) for s in steps), encoding="utf-8")

    manifest = ManifestModel(cli_command="test")

    out = tmp_path / "out" / "packed.epi"
    EPIContainer.pack(ws, manifest, out, embed_agt=True)

    # confirm artifact exists inside the .epi payload
    unpack_dir = tmp_path / "unpack"
    EPIContainer.unpack(out, unpack_dir)

    agt_member = unpack_dir / "artifacts" / "agt_export.json"
    assert agt_member.exists(), "Embedded AGT export should exist in the packed artifact"

    # confirm manifest references the embedded file
    m = EPIContainer.read_manifest(out)
    assert "artifacts/agt_export.json" in m.file_manifest
