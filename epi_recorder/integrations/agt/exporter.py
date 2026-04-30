"""
Export helpers: convert a sealed `.epi` artifact into an AGT-style
audit JSON bundle so governance systems can ingest EPI evidence.

This module is intentionally conservative: it reads the sealed artifact,
extracts manifest/steps/policy_evaluation when present, and emits a
normalized audit JSON with integrity metadata. Fields are optional so
consumers may pick what they need.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from epi_core.container import EPIContainer


def _resolve_agent_identity_from_manifest(manifest: Any) -> Optional[Dict[str, Any]]:
    """Attempt to resolve an agent identity using the local identity map.

    Returns a dict with keys `id`, `name`, `version`, and optional
    `public_key` and `trust_tier` when a mapping is found.
    """
    try:
        import epi_cli.identity as identity
    except Exception:
        identity = None

    def _get(m, key):
        if isinstance(m, dict):
            return m.get(key)
        return getattr(m, key, None)

    gov = _get(manifest, "governance") or {}
    candidates: List[str] = []
    if isinstance(gov, dict):
        identity_block = gov.get("identity") or {}
        if isinstance(identity_block, dict) and identity_block.get("value"):
            candidates.append(identity_block.get("value"))
        if gov.get("agent_name"):
            candidates.append(gov.get("agent_name"))
        if gov.get("agent_id"):
            candidates.append(gov.get("agent_id"))

    approved = _get(manifest, "approved_by")
    if approved:
        candidates.append(approved)

    # Clean candidates preserving order and removing falsy
    seen = set()
    cleaned = []
    for c in candidates:
        if not c:
            continue
        if c in seen:
            continue
        seen.add(c)
        cleaned.append(c)

    # Try to resolve using identity map
    mapping = {}
    if identity is not None:
        try:
            mapping = identity._load_map()  # type: ignore[attr-defined]
        except Exception:
            mapping = {}

    for cand in cleaned:
        # If this already looks like a DID, return it directly
        if isinstance(cand, str) and cand.startswith("did:"):
            return {"id": cand, "name": _get(manifest, "approved_by") or None}

        # Look up mapping by name
        info = mapping.get(cand) if isinstance(mapping, dict) else None
        if isinstance(info, dict) and info.get("did"):
            return {
                "id": info.get("did"),
                "name": cand,
                "version": None,
                "public_key": info.get("public_key"),
                "trust_tier": info.get("trust_tier"),
            }

    # Fallback: if governance.agent_identity exists, use it
    if isinstance(gov, dict):
        ident = gov.get("agent_identity")
        if isinstance(ident, dict) and ident.get("id"):
            return ident
        
        identity_block = gov.get("identity") or {}
        if isinstance(identity_block, dict) and identity_block.get("value"):
            return {"id": identity_block.get("value"), "name": gov.get("agent_name") or None}

    return None


def _parse_iso(ts: Optional[str]) -> Optional[datetime]:
    if ts is None:
        return None
    if isinstance(ts, (int, float)):
        try:
            return datetime.fromtimestamp(float(ts), tz=timezone.utc)
        except Exception:
            return None
    if isinstance(ts, str):
        try:
            # Accept Z suffix
            if ts.endswith("Z"):
                ts = ts.replace("Z", "+00:00")
            return datetime.fromisoformat(ts)
        except Exception:
            return None
    return None


def _sha256_hex_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _summarize_execution(steps: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not steps:
        return {"steps": 0, "duration_ms": 0}

    times = [t for t in (_parse_iso(s.get("timestamp")) for s in steps) if t is not None]
    if times:
        start = min(times)
        end = max(times)
        duration_ms = int((end - start).total_seconds() * 1000)
    else:
        duration_ms = 0

    return {"steps": len(steps), "duration_ms": duration_ms}


def _transform_step_to_event(step: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    kind = (step.get("kind") or "").lower()
    content = step.get("content") or {}
    timestamp = step.get("timestamp")

    if kind.startswith("llm.request") or kind == "guardrails.llm.call":
        payload = json.dumps(content, sort_keys=True, ensure_ascii=False)
        return {
            "type": "llm_call",
            "direction": "request" if "request" in kind else "call",
            "timestamp": timestamp,
            "provider": content.get("provider"),
            "model": content.get("model"),
            "input_hash": f"sha256:{hashlib.sha256(payload.encode('utf-8')).hexdigest()}",
        }

    if kind.startswith("llm.response"):
        payload = json.dumps(content, sort_keys=True, ensure_ascii=False)
        return {
            "type": "llm_call",
            "direction": "response",
            "timestamp": timestamp,
            "output_hash": f"sha256:{hashlib.sha256(payload.encode('utf-8')).hexdigest()}",
        }

    if kind.startswith("agent.decision") or kind == "agent.decision" or (kind == "agent.step" and content.get("subtype") == "guardrails"):
        return {
            "type": "decision",
            "timestamp": timestamp,
            "action": content.get("action") or content.get("subtype") or "guard_validation",
            "result": content.get("decision") or content.get("status") or content.get("outcome"),
            "policy_id": (content.get("policy_id") or (content.get("policy") or {}).get("id")),
            "governance": content.get("governance") or step.get("governance") or None,
            "metadata": {
                "iteration": content.get("iteration_index"),
                "validators": content.get("validators", [])
            }
        }

    if kind == "security.redaction" or kind.startswith("security.redaction"):
        return {
            "type": "redaction",
            "timestamp": timestamp,
            "fields": content.get("fields") or content.get("redacted") or None,
        }

    # Generic fallback: include light-weight metadata for relevant kinds
    if kind in {"tool.call", "tool.response", "file.write", "shell.command"}:
        return {
            "type": "event",
            "subtype": kind,
            "timestamp": timestamp,
            "summary": content.get("summary") or content.get("tool") or None,
        }

    return None


def export_epi_to_agt(epi_path: Path, out_path: Path, *, include_raw: bool = False) -> Path:
    """Read an existing `.epi` file and write an AGT-style audit JSON.

    The output is intentionally minimal and additive so it can be used as
    a normalized audit record for governance tooling. Fields are optional.
    """
    epi_path = Path(epi_path)
    out_path = Path(out_path)
    manifest = EPIContainer.read_manifest(epi_path)
    steps = EPIContainer.read_steps(epi_path)

    # Execution summary
    execution = _summarize_execution(steps)

    # Try to obtain a policy evaluation block if present
    try:
        policy_eval = EPIContainer.read_member_json(epi_path, "policy_evaluation.json")
    except Exception:
        policy_eval = None

    # Transform steps into events
    events: List[Dict[str, Any]] = []
    for s in steps:
        ev = _transform_step_to_event(s)
        if ev is not None:
            events.append(ev)

    # Agent identity: attempt to resolve via local identity map, fall back to raw fields
    agent = _resolve_agent_identity_from_manifest(manifest) or None

    # Integrity: manifest signature + file hash
    try:
        raw_bytes = epi_path.read_bytes()
        file_hash = hashlib.sha256(raw_bytes).hexdigest()
    except Exception:
        file_hash = None

    agt_payload: Dict[str, Any] = {
        "audit_id": f"epi_{str(manifest.workflow_id)}",
        "timestamp": manifest.created_at.isoformat() if manifest.created_at else None,
        "agent": agent,
        "execution": execution,
        "policy": policy_eval or None,
        "events": events,
        "integrity": {
            "epi_signature": manifest.signature,
            "file_hash": f"sha256:{file_hash}" if file_hash else None,
        },
    }

    if include_raw:
        # Attach raw manifest and steps for completeness when requested
        agt_payload.setdefault("raw", {})["manifest"] = manifest.model_dump(mode="json")
        agt_payload.setdefault("raw", {})["steps"] = steps

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(agt_payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return out_path


def _read_json_file(path: Path) -> Optional[Dict[str, Any]]:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return None


def _read_steps_jsonl(path: Path) -> List[Dict[str, Any]]:
    steps: List[Dict[str, Any]] = []
    try:
        text = Path(path).read_text(encoding="utf-8")
    except Exception:
        return steps
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            steps.append(json.loads(line))
        except Exception:
            continue
    return steps


def export_workspace_to_agt(workspace_dir: Path, out_path: Path, *, include_raw: bool = False) -> Path:
    """Create an AGT-style export from an unpacked workspace directory.

    This reads `manifest.json`, `steps.jsonl`, and optionally
    `policy_evaluation.json` from `workspace_dir` and emits a normalized
    AGT JSON at `out_path`.
    """
    workspace_dir = Path(workspace_dir)
    manifest = _read_json_file(workspace_dir / "manifest.json") or {}
    steps = _read_steps_jsonl(workspace_dir / "steps.jsonl")

    execution = _summarize_execution(steps)

    policy_eval = _read_json_file(workspace_dir / "policy_evaluation.json")

    events: List[Dict[str, Any]] = []
    for s in steps:
        ev = _transform_step_to_event(s)
        if ev is not None:
            events.append(ev)

    # Agent identity: attempt to resolve via local identity map, fall back to raw fields
    agent = _resolve_agent_identity_from_manifest(manifest) or None

    # Integrity: sha256 of concatenated artifact bytes we know about
    hasher = hashlib.sha256()
    for name in ("manifest.json", "steps.jsonl", "policy_evaluation.json"):
        p = workspace_dir / name
        if p.exists():
            try:
                hasher.update(p.read_bytes())
            except Exception:
                pass
    file_hash = hasher.hexdigest()

    agt_payload: Dict[str, Any] = {
        "audit_id": f"workspace_{str(manifest.get('workflow_id') or 'unknown')}",
        "timestamp": None,
        "agent": agent,
        "execution": execution,
        "policy": policy_eval or None,
        "events": events,
        "integrity": {
            "workspace_hash": f"sha256:{file_hash}",
        },
    }

    # created_at may be present as string
    created_at = manifest.get("created_at") if isinstance(manifest, dict) else None
    if created_at:
        dt = _parse_iso(created_at)
        if dt:
            agt_payload["timestamp"] = dt.isoformat()
        else:
            agt_payload["timestamp"] = str(created_at)

    if include_raw:
        agt_payload.setdefault("raw", {})["manifest"] = manifest
        agt_payload.setdefault("raw", {})["steps"] = steps

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(agt_payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return out_path
