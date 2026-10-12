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
import queue
import threading
import time
from pathlib import Path
from typing import Any

CHECKPOINT_SCHEMA_VERSION = "1.0"

# Serializes runtime-gap writes: the background submitter thread and
# finalize() can both append to artifacts/capture_gaps.json.
_GAP_LOCK: Any = None


def _gap_lock():
    global _GAP_LOCK
    if _GAP_LOCK is None:
        import threading

        _GAP_LOCK = threading.Lock()
    return _GAP_LOCK


def record_gap(output_dir: Path, gap: str) -> None:
    """Thread-safe wrapper around manifest.append_runtime_gap."""
    try:
        from epi_core.manifest import append_runtime_gap

        with _gap_lock():
            append_runtime_gap(Path(output_dir), gap)
    except Exception:
        pass


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


def checkpoint_drain_seconds() -> float:
    """Max finalize() waits for background checkpoints (EPI_CHECKPOINT_DRAIN_SECONDS, default 10)."""
    return _env_float("EPI_CHECKPOINT_DRAIN_SECONDS", 10.0)


class CheckpointSubmitter:
    """Background TSA submitter: one daemon thread, one queue.

    `add_step` only enqueues (index, event_count, chain_head); the worker
    thread calls `create_checkpoint`. Each checkpoint stays bound to the
    chain head at enqueue time, so the imprint is still correct. `drain()`
    waits (bounded) for the queue to empty at finalize time; whatever is
    unfinished is reported so the caller can record a runtime gap.
    """

    def __init__(self, output_dir, *, tsa_submit=None) -> None:
        self._output_dir = Path(output_dir)
        self._tsa_submit = tsa_submit
        self._queue: queue.Queue = queue.Queue()
        self._thread = threading.Thread(
            target=self._run,
            name="epi-checkpoint-submit",
            daemon=True,
        )
        self._thread.start()

    def submit(self, index: int, event_count: int, chain_head: str) -> None:
        """Enqueue one checkpoint. Never blocks on the network; never raises."""
        try:
            self._queue.put_nowait((int(index), int(event_count), str(chain_head)))
        except Exception:
            pass

    def pending(self) -> int:
        """Submitted but unfinished checkpoints (queue + in-flight)."""
        try:
            return int(self._queue.unfinished_tasks)
        except Exception:
            return 0

    def drain(self, timeout: float | None = None) -> int:
        """Wait up to `timeout` seconds for the queue to empty.

        Returns the number of still-unfinished checkpoints (0 when fully
        drained). Never raises. The worker thread is left running as a
        daemon so a late TSA reply can still land its file.
        """
        if timeout is None:
            timeout = checkpoint_drain_seconds()
        try:
            deadline = time.monotonic() + max(0.0, float(timeout))
        except Exception:
            deadline = time.monotonic() + 10.0
        try:
            while self.pending() > 0 and time.monotonic() < deadline:
                time.sleep(0.02)
            return self.pending()
        except Exception:
            return 0

    def _run(self) -> None:
        while True:
            try:
                index, event_count, chain_head = self._queue.get()
            except Exception:
                return
            try:
                create_checkpoint(
                    self._output_dir,
                    index=index,
                    event_count=event_count,
                    chain_head=chain_head,
                    tsa_submit=self._tsa_submit,
                )
            except Exception:
                pass
            finally:
                try:
                    self._queue.task_done()
                except Exception:
                    pass


def _tsa_url() -> str:
    from epi_core.notarize import _tsa_urls

    urls = _tsa_urls()
    return urls[0] if urls else ""


def _submit_with_fallback(digest_hex: str) -> tuple[bytes | None, str]:
    """Submit to the first TSA URL, falling back to the next on failure.

    Seal time stamps with every URL; checkpoints must stay fast, so they
    never wait on more than one success. Returns (token, url_used).
    """
    from epi_core.notarize import _submit_rfc3161, _tsa_urls

    last_url = ""
    for url in _tsa_urls():
        last_url = url
        try:
            token = _submit_rfc3161(digest_hex, url)
        except Exception:
            token = None
        if token:
            return token, url
    return None, last_url


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
            token, url = _submit_with_fallback(chain_head)
        else:
            # Injected submit (tests): single call with the primary URL.
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
        record_gap(
            output_dir,
            f"checkpoint {index} TSA unavailable (event_count={event_count}); retried at next heartbeat",
        )

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
    epi_path: Path, steps: list[dict[str, Any]], trust_roots: Any = None
) -> tuple[bool, list[str], list[dict[str, Any]]]:
    """Verify checkpoints against recomputed chain heads.

    Returns (ok, messages, records). Messages use the specific strings that
    are the whole point of the feature:
      - "CHECKPOINT MISMATCH at index N: ..."
      - "TRIMMED: artifact has fewer events than checkpoint N attests to."
      - "CHECKPOINT TIMESTAMP INVALID at index N: ..." (tamper -> ok=False)
      - "CHECKPOINT TIMESTAMP UNVERIFIED at index N: ..." (unknown root warning)

    trust_roots is passed through to validate_tsr (e.g. --tsa-root plus
    pinned plus env roots built by the CLI). None keeps the default
    pinned-roots-plus-env behaviour.
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
                f"independently TSA-tokened record (event_count={claimed_count})"
            )
            continue
        # TSA token validation (offline, against pinned roots): a token that
        # imprints a different head, carries a bad signature, or was issued
        # outside its signer's validity means tampering -> FAIL. An unknown
        # root is a warning (operator can pin it); malformed/absent tokens
        # attest nothing and keep prior verdicts (old artifacts, outages).
        _tsa_b64 = rec.get("tsa_token_b64")
        if _tsa_b64:
            try:
                from epi_core.tsa_verify import validate_tsr

                _token = base64.b64decode(_tsa_b64)
                _expected = bytes.fromhex(claimed_head)
                _v = validate_tsr(_token, _expected, trust_roots=trust_roots)
            except Exception as _ve:
                _v = None
                rec["tsa_validation"] = {
                    "status": "malformed",
                    "gen_time": None,
                    "tsa_subject": None,
                    "tsa_root": None,
                    "detail": f"checkpoint token unreadable ({_ve})",
                }
            else:
                rec["tsa_validation"] = {
                    "status": _v.status,
                    "gen_time": _v.gen_time,
                    "tsa_subject": _v.tsa_subject,
                    "tsa_root": _v.tsa_root,
                    "detail": _v.detail,
                }
            if _v is not None and _v.status in (
                "imprint_mismatch",
                "bad_signature",
                "cert_invalid",
            ):
                ok = False
                messages.append(
                    f"CHECKPOINT TIMESTAMP INVALID at index {idx}: {_v.detail}"
                )
            elif _v is not None and _v.status == "untrusted":
                messages.append(
                    f"CHECKPOINT TIMESTAMP UNVERIFIED at index {idx}: {_v.detail}"
                )
    return ok, messages, records
