"""MCP tool implementations (transport-independent).

Pure functions returning JSON-serializable dicts, registered by both the
stdio server (``server.py``) and the Streamable HTTP server (``http.py``.

File delivery: ``epi_seal_record`` returns the artifact bytes as base64
plus filename and SHA-256. A server-side filesystem path is meaningless
to a remote host, so the bytes — not the path — are the primary result.
"""

from __future__ import annotations

import base64
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from epi_mcp.records import SCOPE_NOTE, export_summary, seal_record, verify_artifact

NOT_CAPTURED = [
    "hidden reasoning",
    "inaccessible system state",
    "unobserved external actions",
]


def _artifact_payload(epi_path: str | Path) -> dict[str, Any]:
    raw = Path(epi_path).read_bytes()
    return {
        "filename": Path(epi_path).name,
        "epi_b64": base64.b64encode(raw).decode("ascii"),
        "size_bytes": len(raw),
    }


def epi_seal_record_tool(
    events: list[dict[str, Any]],
    goal: str = "MCP caller-provided record",
    output_path: str | None = None,
) -> dict[str, Any]:
    """Seal caller-provided observable events. Returns file bytes + verdicts."""
    sealed = seal_record(events, goal=goal, output_path=output_path)
    check = verify_artifact(sealed["epi_path"])
    sealed["seal_check"] = {
        "integrity_ok": check["integrity_ok"],
        "signature_valid": check["signature_valid"],
        "trust_level": check["trust_level"],
    }
    sealed.update(_artifact_payload(sealed["epi_path"]))
    sealed["sealed_at"] = datetime.now(timezone.utc).isoformat()
    sealed["not_captured"] = NOT_CAPTURED
    return sealed


def epi_verify_tool(epi_path: str) -> dict[str, Any]:
    """Verify a .epi file the caller provides (path or URL the server can read)."""
    return verify_artifact(epi_path)


def epi_export_summary_tool(epi_path: str, max_steps: int = 50) -> dict[str, Any]:
    """Read back a sealed timeline."""
    return export_summary(epi_path, max_steps=max_steps)
