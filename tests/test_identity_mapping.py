import json
from pathlib import Path

import epi_cli.identity as identity


def test_identity_register_and_export(tmp_path: Path, monkeypatch):
    # Redirect state dir to tmp path to avoid touching user home
    monkeypatch.setattr(identity, "_state_dir", lambda: tmp_path / ".epi")

    identity.register_agent("claims-agent", "did:key:xyz", public_key="ed25519:abc", trust_tier="standard")

    out = tmp_path / "mapping.json"
    identity.export_mapping(out)

    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["claims-agent"]["did"] == "did:key:xyz"

    # Test import (merge)
    identity.import_mapping(out)
    stored = json.loads((tmp_path / ".epi" / "identity_map.json").read_text(encoding="utf-8"))
    assert stored["claims-agent"]["did"] == "did:key:xyz"
