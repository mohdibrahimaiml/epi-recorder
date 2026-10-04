"""Core seal/verify logic for the EPI MCP server.

Pure functions over epi-recorder primitives. No MCP dependency here so the
logic is testable and reusable without an MCP host.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from epi_core.container import EPIContainer
from epi_core.keys import KeyManager
from epi_core.schemas import ManifestModel
from epi_core.trust import (
    create_verification_report,
    sign_manifest,
    verify_embedded_manifest_signature,
)

SCOPE_NOTE = (
    "Seals the record provided by the caller. Does not prove the "
    "originating run is complete and cannot capture model-internal state."
)

_SERVER_KEY_NAME = "default"


def _key_manager() -> KeyManager:
    """Server key manager. EPI_MCP_KEYS_DIR overrides the location (tests)."""
    import os

    override = os.environ.get("EPI_MCP_KEYS_DIR")
    return KeyManager(Path(override) if override else None)


def _server_private_key():
    km = _key_manager()
    if not km.has_key(_SERVER_KEY_NAME):
        km.generate_keypair(_SERVER_KEY_NAME)
    return km.load_private_key(_SERVER_KEY_NAME), km


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Assign index/timestamp where missing; never invent content."""
    out: list[dict[str, Any]] = []
    for i, event in enumerate(events):
        if not isinstance(event, dict):
            raise ValueError(f"event {i} must be an object, got {type(event).__name__}")
        step = dict(event)
        step.setdefault("index", i)
        step.setdefault("timestamp", _utc_now_iso())
        step.setdefault("kind", "custom")
        if "content" not in step:
            step["content"] = {}
        out.append(step)
    return out


def seal_record(
    events: list[dict[str, Any]],
    *,
    goal: str = "MCP caller-provided record",
    output_path: str | Path | None = None,
    key_name: str = _SERVER_KEY_NAME,
) -> dict[str, Any]:
    """Seal caller-provided events into a signed .epi artifact.

    Returns paths, hashes, and the scope note. Raises ValueError on bad
    input; never seals an empty record.
    """
    if not events:
        raise ValueError("events must be a non-empty list")
    steps = _normalize_events(events)

    workdir = Path(tempfile.mkdtemp(prefix="epi_mcp_seal_"))
    (workdir / "steps.jsonl").write_text(
        "\n".join(json.dumps(s, ensure_ascii=False) for s in steps) + "\n",
        encoding="utf-8",
    )
    (workdir / "environment.json").write_text(
        json.dumps({"sealed_by": "epi_mcp", "capture_scope": "caller-provided"}, indent=2),
        encoding="utf-8",
    )

    manifest = ManifestModel(
        goal=goal,
        notes=SCOPE_NOTE,
        tags=["mcp", "caller-provided"],
    )

    km = _key_manager()
    if not km.has_key(key_name):
        km.generate_keypair(key_name)
    private_key = km.load_private_key(key_name)

    out = Path(output_path) if output_path else workdir / "record.epi"

    EPIContainer.pack(
        workdir,
        manifest,
        out,
        signer_function=lambda m: sign_manifest(m, private_key, key_name),
        preserve_generated=True,
        generate_analysis=False,
    )
    digest = hashlib.sha256(out.read_bytes()).hexdigest()
    return {
        "epi_path": str(out),
        "sha256": digest,
        "steps_sealed": len(steps),
        "scope": "caller-provided",
        "scope_note": SCOPE_NOTE,
    }


def verify_artifact(epi_path: str | Path) -> dict[str, Any]:
    """Verify a .epi file: integrity, signature, identity, trust level."""
    path = Path(epi_path)
    if not path.exists():
        raise FileNotFoundError(f"EPI file not found: {path}")
    manifest = EPIContainer.read_manifest(path)
    integrity_ok, mismatches = EPIContainer.verify_integrity(path)
    signature_valid, signer, message = verify_embedded_manifest_signature(manifest)
    report = create_verification_report(
        integrity_ok=integrity_ok,
        signature_valid=signature_valid,
        signer_name=signer,
        mismatches=mismatches,
        manifest=manifest,
    )
    return {
        "integrity_ok": integrity_ok,
        "signature_valid": signature_valid,
        "signer": signer,
        "verify_message": message,
        "identity_status": report.get("identity", {}).get("status", report.get("identity_status")),
        "trust_level": report.get("trust_level"),
        "trust_message": report.get("trust_message"),
        "mismatches": mismatches,
    }


def export_summary(epi_path: str | Path, *, max_steps: int = 50) -> dict[str, Any]:
    """Read back a sealed timeline (kind + content per step)."""
    path = Path(epi_path)
    if not path.exists():
        raise FileNotFoundError(f"EPI file not found: {path}")
    steps = EPIContainer.read_steps(path)
    timeline = [
        {"index": s.get("index"), "kind": s.get("kind"), "content": s.get("content")}
        for s in steps[:max_steps]
    ]
    return {"steps_total": len(steps), "steps_shown": len(timeline), "timeline": timeline}
