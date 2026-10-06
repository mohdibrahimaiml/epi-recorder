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
from epi_mcp.idp import describe_identity

SCOPE_NOTE = (
    "Seals the record provided by the caller. Does not prove the "
    "originating run is complete; anything the caller did not supply is not in the record."
)

_SERVER_KEY_NAME = "default"


def _key_manager() -> KeyManager:
    """Server key manager. EPI_MCP_KEYS_DIR overrides the location (tests)."""
    import os

    override = os.environ.get("EPI_MCP_KEYS_DIR")
    return KeyManager(Path(override) if override else None)


def derived_signing_key(key_name: str):
    """Deterministic per-caller Ed25519 key, or None when no seed is configured.

    Hosts with ephemeral disks (Render free tier, containers) lose generated
    key files on every restart, so a caller's signer changes each time and
    can never be pinned with ``epi keys trust``. Deriving the key from a
    server-only seed keeps each caller's signer stable. The seed is
    ``EPI_SIGNING_SEED`` or ``EPI_OAUTH_SECRET`` -- never the static bearer
    token, which clients hold and could use to recompute other callers' keys.
    Whoever holds the seed can sign as any caller; guard it like a root key.
    """
    import hmac as _hmac
    import os

    seed = (os.environ.get("EPI_SIGNING_SEED") or os.environ.get("EPI_OAUTH_SECRET") or "").strip()
    if not seed:
        return None
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    raw = _hmac.new(
        seed.encode("utf-8"), f"epi-mcp-signing-key-v1:{key_name}".encode("utf-8"), hashlib.sha256
    ).digest()
    return Ed25519PrivateKey.from_private_bytes(raw)


def _server_private_key():
    km = _key_manager()
    if not km.has_key(_SERVER_KEY_NAME):
        km.generate_keypair(_SERVER_KEY_NAME)
    return km.load_private_key(_SERVER_KEY_NAME), km


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


FIDELITY_VALUES = ("verbatim", "summary", "hash_only")


def _parse_ts(value: Any) -> str | None:
    """Return an ISO-8601 UTC string for a caller timestamp, or None if unusable."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


_STEP_FIELDS = {"index", "timestamp", "kind", "content", "trace_id", "span_id", "parent_span_id"}

# Who produced a step. Without this the schema guesses, and labelled a user's
# own message as "reasoning". Only kinds with a certain origin are set; the
# rest keep the schema's default. A valid caller-supplied value wins.
_SOURCE_TYPE_BY_KIND = {
    "user.message": "user",
    "artifact.attached": "user",
    "redaction.omitted": "system",
}
_SOURCE_TYPES = ("user", "tool", "reasoning", "system")


def _normalize_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normalize caller events without inventing content or times.

    - ``content`` is kept verbatim (a bare string becomes ``{"text": ...}``).
    - A caller-supplied ``timestamp`` (or ``ts``) is kept; otherwise the server
      clock is used. Either way ``content._epi_provenance`` records the
      ``timestamp_source`` ("caller" or "server_received"), the server
      ``received_at`` and the caller's ``fidelity`` label (verbatim | summary |
      hash_only | unspecified). It lives inside ``content`` so the step
      hash-chain covers it.
    - Unknown top-level caller fields are preserved under
      ``content._caller_fields`` rather than silently dropped.
    - Every step is tagged ``caller_provided`` for the capture manifest.
    """
    out: list[dict[str, Any]] = []
    received = _utc_now_iso()
    for i, event in enumerate(events):
        if not isinstance(event, dict):
            raise ValueError(f"event {i} must be an object, got {type(event).__name__}")
        raw = dict(event)
        content = raw.get("content", {})
        if not isinstance(content, dict):
            content = {"text": content}
        content = dict(content)

        caller_ts = _parse_ts(raw.get("ts")) or _parse_ts(raw.get("timestamp"))
        fidelity = raw.get("fidelity")
        extras = {
            k: v
            for k, v in raw.items()
            if k not in _STEP_FIELDS and k not in {"ts", "fidelity"}
        }
        content["_epi_capture"] = {
            "capture_path": "caller_provided",
            "gateway_enforcement": "not_applicable",
            "streaming": False,
        }
        content["_epi_provenance"] = {
            "timestamp_source": "caller" if caller_ts else "server_received",
            "received_at": received,
            "fidelity": fidelity if fidelity in FIDELITY_VALUES else "unspecified",
        }
        if extras:
            content["_caller_fields"] = extras
        step: dict[str, Any] = {
            "index": i,
            "kind": str(raw.get("kind") or "custom"),
            "timestamp": caller_ts or received,
            "content": content,
        }
        for k in ("trace_id", "span_id", "parent_span_id"):
            if raw.get(k):
                step[k] = raw[k]
        source = raw.get("source_type")
        source = source if source in _SOURCE_TYPES else _SOURCE_TYPE_BY_KIND.get(step["kind"])
        if source:
            step["source_type"] = source
        out.append(step)
    return out


def _chain_steps(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Link steps with prev_hash exactly as the recorder does, so
    ``epi verify`` performs a real chain check instead of passing vacuously.
    """
    from epi_core.schemas import StepModel
    from epi_core.serialize import get_canonical_hash

    chained: list[dict[str, Any]] = []
    prev = "CHAIN_START"
    for st in steps:
        model = StepModel(**st, prev_hash=prev)
        chained.append(model.model_dump(mode="json", exclude_none=True))
        prev = get_canonical_hash(model, format="json")
    return chained


def describe_fidelity(steps: list[dict[str, Any]]) -> dict[str, Any]:
    """Server-computed honesty report about how the record was supplied."""
    total = len(steps)
    by_fidelity: dict[str, int] = {}
    caller_ts = 0
    for st in steps:
        prov = st["content"]["_epi_provenance"]
        by_fidelity[prov["fidelity"]] = by_fidelity.get(prov["fidelity"], 0) + 1
        if prov["timestamp_source"] == "caller":
            caller_ts += 1
    distinct_ts = len({st["timestamp"] for st in steps})
    warnings: list[str] = []
    if total and caller_ts < total:
        warnings.append(
            f"{total - caller_ts} of {total} events have no caller timestamp; "
            "the sealer assigned its own receive time, so the sealed order is "
            "not a timeline of when things happened."
        )
    if total > 1 and distinct_ts == 1:
        warnings.append("All events share one timestamp.")
    unlabelled = by_fidelity.get("unspecified", 0)
    if unlabelled:
        warnings.append(
            f"{unlabelled} of {total} events do not say whether their content "
            "is verbatim, a summary, or hash-only."
        )
    summaries = by_fidelity.get("summary", 0)
    if summaries:
        warnings.append(
            f"{summaries} of {total} events are summaries, not verbatim text. "
            "For stronger evidence, seal the full text of those messages."
        )
    unnamed = sum(
        1
        for st in steps
        if st.get("kind") == "tool.call"
        and not any(st["content"].get(k) for k in ("tool", "name", "tool_name"))
    )
    if unnamed:
        warnings.append(
            f"{unnamed} tool.call events have no tool name; a reader cannot tell which tool was called."
        )
    undecided = sum(
        1
        for st in steps
        if st.get("kind") == "agent.decision"
        and not any(st["content"].get(k) for k in ("decision", "verdict"))
    )
    if undecided:
        warnings.append(
            f"{undecided} agent.decision events have no decision field; a reader sees only '?'."
        )
    kinds = {str(st.get("kind")) for st in steps}
    if "user.message" not in kinds and "agent.run.start" not in kinds:
        warnings.append(
            "No user message or run-start event: the request that began the work is not in the record."
        )
    return {
        "events": total,
        "by_fidelity": by_fidelity,
        "caller_timestamps": caller_ts,
        "server_assigned_timestamps": total - caller_ts,
        "distinct_timestamps": distinct_ts,
        "chain": "prev_hash linked (tamper-evident ordering)",
        "warnings": warnings,
    }


def seal_record(
    events: list[dict[str, Any]],
    *,
    goal: str = "MCP caller-provided record",
    output_path: str | Path | None = None,
    key_name: str = _SERVER_KEY_NAME,
    identity: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Seal caller-provided events into a signed .epi artifact.

    Returns paths, hashes, and the scope note. Raises ValueError on bad
    input; never seals an empty record.
    """
    if not events:
        raise ValueError("events must be a non-empty list")
    steps = _chain_steps(_normalize_events(events))
    fidelity = describe_fidelity(steps)

    workdir = Path(tempfile.mkdtemp(prefix="epi_mcp_seal_"))
    (workdir / "steps.jsonl").write_text(
        "\n".join(json.dumps(s, ensure_ascii=False) for s in steps) + "\n",
        encoding="utf-8",
    )
    (workdir / "environment.json").write_text(
        json.dumps(
            {
                "sealed_by": "epi_mcp",
                "capture_scope": "caller-provided",
                "fidelity": fidelity,
                "sealer_identity": describe_identity(identity),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    # Declare the record's limits inside the signed artifact so the viewer
    # and `epi verify` show them as Known Gaps, not only the chat message.
    (workdir / "artifacts").mkdir(exist_ok=True)
    (workdir / "artifacts" / "capture_gaps.json").write_text(
        json.dumps(fidelity["warnings"], indent=2), encoding="utf-8"
    )

    manifest = ManifestModel(
        goal=goal,
        notes=SCOPE_NOTE,
        tags=["mcp", "caller-provided"],
    )

    private_key = derived_signing_key(key_name)
    if private_key is None:
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
        "fidelity": fidelity,
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
        {
            "index": s.get("index"),
            "kind": s.get("kind"),
            "timestamp": s.get("timestamp"),
            "content": s.get("content"),
        }
        for s in steps[:max_steps]
    ]
    return {"steps_total": len(steps), "steps_shown": len(timeline), "timeline": timeline}
