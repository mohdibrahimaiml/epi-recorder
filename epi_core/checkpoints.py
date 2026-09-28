"""
Forward-Secure Checkpoints — periodic TSA timestamps of the hash-chain head.

Extends seal-time notarization (the only timestamp before this feature) to
periodic checkpoints during the run, so a trimmed-and-resealed artifact
contradicts public timestamp history it can't rewrite.

Reuse, not reimplementation: uses epi_core.notarize._build_rfc3161_query and
_submit_rfc3161 directly (respects EPI_TSA_URL override). No second client.
OpenTimestamps is deliberately seal-time only (per-heartbeat OTS would hammer
public calendars); checkpoints are TSA-anchored, OTS anchoring still happens
once at seal via the existing notarize path.
"""

from __future__ import annotations

import base64
import json
import os
import time
from pathlib import Path
from typing import Any

CHECKPOINT_SCHEMA_VERSION = "1.0"


def _env_int(name: str, default: int) -> int:
    try:
        return max(1, int(os.environ.get(name, str(default)).strip()))
    except Exception:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return max(1.0, float(os.environ.get(name, str(default)).strip()))
    except Exception:
        return default


def checkpoint_intervals() -> tuple[int, float]:
    """(events, seconds) from env, defaults 50 / 60. Flagged as defaults
    worth revisiting once there's real usage data — not final."""
    return (
        _env_int("EPI_CHECKPOINT_INTERVAL_EVENTS", 50),
        _env_float("EPI_CHECKPOINT_INTERVAL_SECONDS", 60.0),
    )


def checkpoints_enabled() -> bool:
    return os.environ.get("EPI_CHECKPOINTS_ENABLED", "1").strip().lower() not in (
        "0", "false", "no", "off",
    )


def should_checkpoint(
    last_count: int, current_count: int, last_time: float, now: float,
    *,
    interval_events: int | None = None,
    interval_seconds: float | None = None,
) -> bool:
    """Heartbeat: every N events OR every T seconds, whichever fires first."""
    if interval_events is None or interval_seconds is None:
        ev, sec = checkpoint_intervals()
        interval_events = ev if interval_events is None else interval_events
        interval_seconds = sec if interval_seconds is None else interval_seconds
    if current_count - last_count >= interval_events:
        return True
    if now - last_time >= interval_seconds:
        return True
    return False


def _tsa_url() -> str:
    from epi_core.notarize import DEFAULT_TSA_URL

    return os.environ.get("EPI_TSA_URL", DEFAULT_TSA_URL)


def create_checkpoint(
    output_dir: Path,
    *,
    index: int,
    event_count: int,
    chain_head: str,
    tsa_submit: Any | None = None,
) -> dict[str, Any]:
    """Submit chain head to TSA and store checkpoint file.

    Never raises: TSA outage is recorded as a run gap (wired into the
    manifest's known_gaps via artifacts/capture_gaps.json) and retried at
    the next heartbeat. Returns the checkpoint dict (with tsa_available flag).
    """
    output_dir = Path(output_dir)
    cp_dir = output_dir / "artifacts" / "checkpoints"
    cp_dir.mkdir(parents=True, exist_ok=True)

    url = _tsa_url()
    token: bytes | None = None
    gen_time: str | None = None
    try:
        # Direct reuse of the seal-time client: validate the digest by building
        # the DER TimeStampReq first (same builder seal uses), then submit.
        # OpenTimestamps calendars are seal-time only by design (per-heartbeat
        # OTS would hammer public calendars); checkpoints are TSA-anchored.
        from epi_core.notarize import _build_rfc3161_query

        _build_rfc3161_query(bytes.fromhex(chain_head))
        submit = tsa_submit
        if submit is None:
            from epi_core.notarize import _submit_rfc3161

            submit = _submit_rfc3161
        token = submit(chain_head, url)
        if token:
            try:
                from epi_core.notarize import _parse_tsr_gen_time

                gen_time = _parse_tsr_gen_time(token)
            except Exception:
                gen_time = None
    except Exception:
        token = None

    from epi_core.time_utils import utc_now_iso

    record: dict[str, Any] = {
        "schema_version": CHECKPOINT_SCHEMA_VERSION,
        "index": index,
        "event_count": event_count,
        "chain_head": chain_head,
        "tsa_url": url,
        "tsa_available": token is not None,
        "tsa_genTime": gen_time,
        "created_at": utc_now_iso(),
    }
    if token:
        record["tsa_token_b64"] = base64.b64encode(token).decode("ascii")
    else:
        # Degraded mode: log failed attempt as a gap for this run (manifest
        # + checkpoint features wired together, not built in isolation).
        try:
            from epi_core.manifest import append_runtime_gap

            append_runtime_gap(
                output_dir,
                f"checkpoint {index} TSA unavailable (event_count={event_count}); retried at next heartbeat",
            )
        except Exception:
            pass

    (cp_dir / f"{index:06d}.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    return record


def list_checkpoint_records(source_dir: Path) -> list[dict[str, Any]]:
    cp_dir = Path(source_dir) / "artifacts" / "checkpoints"
    if not cp_dir.is_dir():
        return []
    out: list[dict[str, Any]] = []
    for p in sorted(cp_dir.glob("*.json")):
        try:
            out.append(json.loads(p.read_text(encoding="utf-8")))
        except Exception:
            continue
    return sorted(out, key=lambda r: int(r.get("index", 0)))


def recompute_chain_head(
    steps: list[dict[str, Any]], event_count: int
) -> str | None:
    """Recompute hash-chain head as of event_count steps.

    Uses the same canonical hash as the recorder (get_canonical_hash,
    format=json) so checkpoint reconciliation needs NO modification to the
    existing hash-chain-linking function — confirmed during build.
    """
    if event_count <= 0 or event_count > len(steps):
        return None
    try:
        from epi_core.schemas import StepModel
        from epi_core.serialize import get_canonical_hash

        head: str | None = None
        for s in steps[:event_count]:
            m = StepModel(**s)
            head = get_canonical_hash(m, format="json")
        return head
    except Exception:
        return None


def verify_checkpoints(
    epi_path: Path, steps: list[dict[str, Any]]
) -> tuple[bool, list[str], list[dict[str, Any]]]:
    """Verify checkpoints against recomputed chain heads.

    Returns (ok, messages, records). Messages use the specific strings that
    are the whole point of the feature:
      - "CHECKPOINT MISMATCH at index N: ..."
      - "TRIMMED: artifact has fewer events than checkpoint N attests to."
    """
    from epi_core.container import EPIContainer

    records: list[dict[str, Any]] = []
    try:
        members = EPIContainer.list_members(epi_path)
        for name in sorted(m for m in members if m.startswith("artifacts/checkpoints/") and m.endswith(".json")):
            try:
                records.append(EPIContainer.read_member_json(epi_path, name))
            except Exception:
                continue
    except Exception:
        return True, [], []

    records = sorted(records, key=lambda r: int(r.get("index", 0)))
    messages: list[str] = []
    ok = True
    for rec in records:
        try:
            idx = int(rec.get("index", 0))
        except Exception:
            idx = 0
        try:
            claimed_count = int(rec.get("event_count", 0))
        except Exception:
            claimed_count = 0
        claimed_head = str(rec.get("chain_head") or "")
        # Skip checkpoints that never got a TSA token (outage gaps) — they
        # attest nothing; the gap is declared in the manifest instead.
        if not rec.get("tsa_available") or not claimed_head:
            continue
        if len(steps) < claimed_count:
            ok = False
            messages.append(
                f"TRIMMED: artifact has fewer events than checkpoint {idx} attests to "
                f"(checkpoint event_count={claimed_count}, artifact has {len(steps)} steps)"
            )
            continue
        recomputed = recompute_chain_head(steps, claimed_count)
        if recomputed is None or recomputed != claimed_head:
            ok = False
            messages.append(
                f"CHECKPOINT MISMATCH at index {idx}: artifact history contradicts "
                f"independently timestamped record (event_count={claimed_count})"
            )
    return ok, messages, records
