"""
Simple identity mapping CLI helpers for epi-recorder.

Stores a small `identity_map.json` under the user's `~/.epi` directory and
provides helper functions for registering and exporting mappings.

This is intentionally minimal: it avoids becoming an identity provider and
only provides a durable, user-controlled mapping between local agent names
and external DIDs (e.g. AGT `did:*` identifiers).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Any


def _state_dir() -> Path:
    p = Path.home() / ".epi"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _mapping_path() -> Path:
    return _state_dir() / "identity_map.json"


def _load_map() -> Dict[str, Any]:
    p = _mapping_path()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_map(mapping: Dict[str, Any]) -> None:
    p = _mapping_path()
    # Ensure parent directory exists before writing
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(mapping, indent=2, ensure_ascii=False), encoding="utf-8")


def register_agent(agent_name: str, did: str, public_key: str | None = None, trust_tier: str | None = None) -> None:
    """Register or update a mapping for `agent_name` -> `did`.

    This is intentionally a simple index used by exporters; it is not a full
    identity system.
    """
    mapping = _load_map()
    mapping[agent_name] = {
        "did": did,
        "public_key": public_key,
        "trust_tier": trust_tier,
    }
    _write_map(mapping)


def export_mapping(out_path: Path) -> Path:
    mapping = _load_map()
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(mapping, indent=2, ensure_ascii=False), encoding="utf-8")
    return out_path


def import_mapping(in_path: Path) -> None:
    try:
        data = json.loads(Path(in_path).read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValueError(f"Invalid mapping file: {exc}")
    if not isinstance(data, dict):
        raise ValueError("Mapping file must contain a JSON object mapping agent names to DID info")
    existing = _load_map()
    existing.update(data)
    _write_map(existing)
