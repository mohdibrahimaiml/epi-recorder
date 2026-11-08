"""Per-signing-key seal ledger: sequence numbers, links, and burns.

Every seal made with a given signing key gets a monotonic number and a link
to the last *committed* seal (``prev_seq`` / ``prev_content_digest``). The
number and link live inside the signed manifest (``ManifestModel.seal_chain``)
and in the witness report, so the customer can see a seal the vendor never
reported: a missing number, two different seals with the same number, or a
link that does not point at the seal it claims.

State lives per key at ``$EPI_HOME/seal_ledger/<key_fingerprint>.json``
(``~/.epi`` when EPI_HOME is unset; ``EPI_SEAL_LEDGER_DIR`` overrides both).

Concurrency, deliberately:

* Allocation is serialized across threads AND processes with the same lock
  file mechanism as the witness outbox (``epi_core.filelock``).
* ``prev_seq`` is the last *committed* seal, not ``seq - 1``. Two seals can be
  allocated and sealed concurrently (the gateway does this); a seal cannot
  link to a number whose digest is not known yet.
* A reservation that never commits is a **burn** (a number spent with no
  seal). Burns are only recorded when the holder is gone: a dead pid on this
  host, the same thread moving on, or older than
  ``EPI_SEAL_LEDGER_STALE_SECONDS`` (default 600). A live reservation held by
  another thread/process is never burned.
* A burn is *vendor-declared* evidence, not proof. ``epi witness audit``
  reports it as its own finding and never counts the number as clean, because
  a vendor could otherwise hide seal #57 by calling it burned.

Receiver-side audit helpers (``analyze``) use the stdlib only.
"""

from __future__ import annotations

import json
import os
import socket
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from epi_core.filelock import FileLock

STATE_VERSION = 1
GENESIS = "genesis"
DEFAULT_STALE_SECONDS = 600.0
_LOG_NAME_SUFFIX = ".log.jsonl"

_LOCAL_LOCK = threading.Lock()


# ---------------------------------------------------------------------------
# Paths and small helpers
# ---------------------------------------------------------------------------


def ledger_dir() -> Path:
    """Directory holding one state file per signing key."""
    override = os.environ.get("EPI_SEAL_LEDGER_DIR")
    if override:
        return Path(override).expanduser()
    base = os.environ.get("EPI_HOME")
    if base:
        return Path(base).expanduser() / "seal_ledger"
    return Path.home() / ".epi" / "seal_ledger"


def _safe_fingerprint(key_fingerprint: str) -> str:
    clean = "".join(
        ch for ch in str(key_fingerprint or "").lower() if ch.isalnum() or ch in "-_"
    )
    return clean or "unknown"


def state_path(key_fingerprint: str) -> Path:
    return ledger_dir() / f"{_safe_fingerprint(key_fingerprint)}.json"


def _log_path(key_fingerprint: str) -> Path:
    return ledger_dir() / f"{_safe_fingerprint(key_fingerprint)}{_LOG_NAME_SUFFIX}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stale_seconds() -> float:
    try:
        return max(
            0.0,
            float(
                os.environ.get("EPI_SEAL_LEDGER_STALE_SECONDS")
                or DEFAULT_STALE_SECONDS
            ),
        )
    except (TypeError, ValueError):
        return DEFAULT_STALE_SECONDS


def _hostname() -> str:
    try:
        return socket.gethostname()
    except Exception:
        return ""


def _pid_alive(pid: int) -> bool:
    """Whether a process on THIS host is still running.

    Windows: ``os.kill(pid, 0)`` terminates the process (CPython maps it to
    TerminateProcess), so liveness goes through OpenProcess instead.
    """
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    try:
        if os.name == "nt":  # pragma: no cover - exercised on Windows CI
            import ctypes
            from ctypes import wintypes

            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            ERROR_INVALID_PARAMETER = 87
            STILL_ACTIVE = 259
            kernel32 = ctypes.windll.kernel32
            kernel32.OpenProcess.restype = ctypes.c_void_p
            kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
            handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
            if not handle:
                # No such pid means dead; access denied means "cannot tell",
                # which must count as alive so we never burn a live seal.
                if kernel32.GetLastError() == ERROR_INVALID_PARAMETER:
                    return False
                return True
            try:
                code = wintypes.DWORD()
                if kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                    return code.value == STILL_ACTIVE
                return True
            finally:
                kernel32.CloseHandle(handle)
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except Exception:
        # Cannot tell: assume alive so a reservation is never burned early.
        return True


def _new_state(key_fingerprint: str) -> dict[str, Any]:
    now = _now()
    return {
        "version": STATE_VERSION,
        "ledger_id": str(uuid.uuid4()),
        "key_fingerprint": _safe_fingerprint(key_fingerprint),
        "seq": 0,
        "last_committed_seq": 0,
        "last_content_digest": None,
        "last_sealed_at": None,
        "pending": {},
        "burns": [],
        "created_at": now,
        "updated_at": now,
    }


def _normalize_state(state: dict[str, Any], key_fingerprint: str) -> dict[str, Any]:
    if not isinstance(state.get("ledger_id"), str) or not state.get("ledger_id"):
        state["ledger_id"] = str(uuid.uuid4())
    state["version"] = int(state.get("version") or STATE_VERSION)
    state["key_fingerprint"] = _safe_fingerprint(
        state.get("key_fingerprint") or key_fingerprint
    )
    try:
        state["seq"] = max(0, int(state.get("seq") or 0))
    except (TypeError, ValueError):
        state["seq"] = 0
    try:
        state["last_committed_seq"] = max(0, int(state.get("last_committed_seq") or 0))
    except (TypeError, ValueError):
        state["last_committed_seq"] = 0
    pending = state.get("pending")
    state["pending"] = {
        str(k): v for k, v in (pending or {}).items() if isinstance(v, dict)
    } if isinstance(pending, dict) else {}
    burns = state.get("burns")
    state["burns"] = [b for b in (burns or []) if isinstance(b, dict)]
    return state


def _load_state(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    return _normalize_state(data, path.stem)


def _write_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp-{os.getpid()}-{threading.get_ident()}")
    tmp.write_text(
        json.dumps(state, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp, path)


def _append_log(path: Path, record: dict[str, Any]) -> None:
    """Append one committed/burned record to the key's local history."""
    try:
        data = (json.dumps(record, ensure_ascii=False) + "\n").encode("utf-8")
        fd = os.open(str(path), os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
        try:
            view = memoryview(data)
            while view:
                written = os.write(fd, view)
                view = view[written:]
        finally:
            os.close(fd)
    except Exception:
        pass


def _as_dict(chain: Any) -> dict[str, Any]:
    if chain is None:
        return {}
    if hasattr(chain, "model_dump"):
        try:
            data = chain.model_dump()
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}
    if isinstance(chain, dict):
        return dict(chain)
    return {}


# ---------------------------------------------------------------------------
# Reservations
# ---------------------------------------------------------------------------


def _burnable(info: dict[str, Any], now_ts: float) -> bool:
    """Whether a reservation is abandoned (never while its holder may live).

    Only two signals count: the holder's pid is dead on this host, or the
    reservation is older than ``EPI_SEAL_LEDGER_STALE_SECONDS``. A reservation
    held by a live pid is never burned, even from the same process/thread:
    several seals can be in flight at once.
    """
    try:
        allocated_ts = float(info.get("allocated_ts") or 0)
    except (TypeError, ValueError):
        allocated_ts = 0.0
    host = str(info.get("host") or "")
    if host == _hostname() or not host:
        try:
            pid = int(info.get("pid"))
        except (TypeError, ValueError):
            pid = 0
        if pid > 0 and not _pid_alive(pid):
            return True
    return (now_ts - allocated_ts) > _stale_seconds()


def _reap(state: dict[str, Any]) -> None:
    pending = state.get("pending") or {}
    if not pending:
        state["pending"] = {}
        state["burns"] = list(state.get("burns") or [])[-1000:]
        return
    now_ts = time.time()
    keep: dict[str, Any] = {}
    burns = list(state.get("burns") or [])
    for key, info in pending.items():
        try:
            seq = int(key)
        except (TypeError, ValueError):
            continue
        if _burnable(info, now_ts):
            burns.append(
                {
                    "seq": seq,
                    "at": _now(),
                    "pid": info.get("pid"),
                    "host": info.get("host"),
                    "reason": "reservation abandoned before the seal completed",
                }
            )
        else:
            keep[str(seq)] = info
    state["pending"] = keep
    state["burns"] = burns[-1000:]


def _debug_enabled() -> bool:
    return str(os.environ.get("EPI_SEAL_LEDGER_DEBUG") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _debug(message: str, exc: BaseException | None = None) -> None:
    if not _debug_enabled():
        return
    import sys
    import traceback

    print(f"[seal-ledger] {message}", file=sys.stderr)
    if exc is not None:
        traceback.print_exception(type(exc), exc, exc.__traceback__, file=sys.stderr)


def allocate(key_fingerprint: str) -> dict[str, Any] | None:
    """Reserve the next number for this key. Returns the seal_chain dict.

    Never raises. Returns None when no state can be written (e.g. a read-only
    home), in which case the seal is still signed but unsequenced.
    """
    fingerprint = _safe_fingerprint(key_fingerprint)
    if not fingerprint or fingerprint == "unknown":
        return None
    path = state_path(fingerprint)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        return None
    try:
        with _LOCAL_LOCK, FileLock(path, timeout=10.0):
            state = _load_state(path) or _new_state(fingerprint)
            _reap(state)
            seq = int(state.get("seq") or 0) + 1
            state["seq"] = seq
            state["pending"] = dict(state.get("pending") or {})
            state["pending"][str(seq)] = {
                "pid": os.getpid(),
                "thread": threading.get_ident(),
                "host": _hostname(),
                "allocated_at": _now(),
                "allocated_ts": time.time(),
            }
            state["updated_at"] = _now()
            _write_state(path, state)
            prev_seq = int(state.get("last_committed_seq") or 0)
            prev_digest = state.get("last_content_digest")
            return {
                "ledger_id": str(state["ledger_id"]),
                "key_fingerprint": fingerprint,
                "seq": seq,
                "prev_seq": prev_seq,
                "prev_content_digest": str(prev_digest) if prev_digest else GENESIS,
            }
    except Exception as exc:
        _debug(f"allocate failed for {fingerprint}", exc)
        return None


def commit(
    chain: Any,
    content_digest: str,
    *,
    sealed_at: str | None = None,
) -> bool:
    """Mark this reservation sealed, storing the digest the next seal links to.

    Re-signing an already-committed seal (viewer refresh, transparency receipt)
    is a no-op: its number is not spent twice.
    """
    data = _as_dict(chain)
    fingerprint = _safe_fingerprint(str(data.get("key_fingerprint") or ""))
    try:
        seq = int(data.get("seq"))
    except (TypeError, ValueError):
        return False
    if fingerprint == "unknown" or seq < 1 or not content_digest:
        _debug(f"commit rejected invalid chain seq={seq}")
        return False
    path = state_path(fingerprint)
    try:
        with _LOCAL_LOCK, FileLock(path, timeout=10.0):
            state = _load_state(path)
            if state is None:
                # State was wiped between allocate and commit. Do not invent a
                # new chain that would silently reuse this number.
                _debug(f"commit found no ledger state for {fingerprint} seq={seq}")
                return False
            if str(state.get("ledger_id")) != str(data.get("ledger_id")):
                _debug(
                    f"commit ledger mismatch {data.get('ledger_id')} != "
                    f"{state.get('ledger_id')} seq={seq}"
                )
                return False
            pending = state.get("pending") or {}
            if str(seq) not in pending:
                _debug(f"commit found no reservation for seq={seq} (burns={state.get('burns')})")
                return False
            del pending[str(seq)]
            state["pending"] = pending
            # Commits may arrive out of order (concurrent seals): the link for
            # the NEXT seal is the highest committed number, never a regression.
            if seq >= int(state.get("last_committed_seq") or 0):
                state["last_committed_seq"] = seq
                state["last_content_digest"] = str(content_digest)
                state["last_sealed_at"] = sealed_at or _now()
            state["updated_at"] = _now()
            _write_state(path, state)
            _append_log(
                _log_path(fingerprint),
                {
                    "ledger_id": state.get("ledger_id"),
                    "key_fingerprint": fingerprint,
                    "seq": seq,
                    "content_digest": str(content_digest),
                    "at": state["updated_at"],
                },
            )
            return True
    except Exception as exc:
        _debug(f"commit failed for {fingerprint} seq={seq}", exc)
        return False


def commit_from_manifest(chain: Any, content_digest: str) -> bool:
    """Commit the chain carried by a freshly written, signed manifest."""
    return commit(chain, content_digest)


def load(key_fingerprint: str) -> dict[str, Any] | None:
    return _load_state(state_path(key_fingerprint))


def all_states() -> list[dict[str, Any]]:
    base = ledger_dir()
    try:
        paths = sorted(base.glob("*.json"))
    except OSError:
        return []
    states: list[dict[str, Any]] = []
    for path in paths:
        if path.name.endswith(".lock"):
            continue
        state = _load_state(path)
        if state and state.get("key_fingerprint"):
            states.append(state)
    return states


def heartbeat_fields(state: dict[str, Any]) -> dict[str, Any]:
    """The last-committed view a heartbeat reports for one ledger."""
    burns = [
        int(b["seq"])
        for b in (state.get("burns") or [])
        if isinstance(b, dict) and isinstance(b.get("seq"), int)
    ]
    return {
        "ledger_id": str(state.get("ledger_id") or ""),
        "key_fingerprint": str(state.get("key_fingerprint") or ""),
        "last_seq": int(state.get("last_committed_seq") or 0),
        "last_content_digest": state.get("last_content_digest"),
        "burned_seqs": sorted(set(burns)),
    }


# ---------------------------------------------------------------------------
# Audit (receiver side; stdlib only)
# ---------------------------------------------------------------------------


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _identity(entry: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(entry.get("content_digest") or ""),
        str(entry.get("manifest_hash") or ""),
        str(entry.get("file_sha256") or ""),
        str(entry.get("workflow_id") or ""),
    )


def _digest_at(entries: list[dict[str, Any]]) -> str | None:
    digests = {str(e.get("content_digest") or "") for e in entries}
    digests.discard("")
    return next(iter(digests)) if len(digests) == 1 else None


def analyze(entries: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Structural audit of one customer witness log.

    Groups by ``(key_fingerprint, ledger_id)`` and reports missing numbers,
    forks, chain breaks, tail gaps, vendor-declared burns and new chains.
    Entries without ``seal_seq`` are "unsequenced", never errors.
    """
    seals: list[dict[str, Any]] = []
    heartbeats: list[dict[str, Any]] = []
    approval_executed: list[dict[str, Any]] = []
    unsequenced: list[dict[str, Any]] = []
    for entry in entries or []:
        if not isinstance(entry, dict):
            continue
        kind = str(entry.get("type") or "")
        if kind == "epi.heartbeat":
            heartbeats.append(entry)
            continue
        if kind == "epi.approval_executed":
            approval_executed.append(entry)
            continue
        seq = _int_or_none(entry.get("seal_seq"))
        if seq is None or seq < 1:
            unsequenced.append(entry)
            continue
        seals.append(entry)

    order: list[tuple[str, str]] = []
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for entry in seals:
        group_key = (
            str(entry.get("key_fingerprint") or ""),
            str(entry.get("ledger_id") or ""),
        )
        if group_key not in grouped:
            order.append(group_key)
        grouped.setdefault(group_key, []).append(entry)

    # A key with more than one ledger: every ledger after the first one seen is
    # a NEW CHAIN (state wiped, restored elsewhere, or a second machine). It is
    # shown as a warning, never hidden, and never silently merged.
    key_order: dict[str, list[str]] = {}
    for key_fingerprint, ledger_id in order:
        key_order.setdefault(key_fingerprint, []).append(ledger_id)

    chains: list[dict[str, Any]] = []
    for key_fingerprint, ledger_id in order:
        items = grouped[(key_fingerprint, ledger_id)]
        by_seq: dict[int, list[dict[str, Any]]] = {}
        for entry in items:
            by_seq.setdefault(int(entry["seal_seq"]), []).append(entry)
        seqs = sorted(by_seq)
        max_seq = seqs[-1]
        min_seq = seqs[0]

        missing_all = [s for s in range(1, max_seq + 1) if s not in by_seq]

        forks: list[dict[str, Any]] = []
        for seq in seqs:
            variants = {_identity(e) for e in by_seq[seq]}
            if len(variants) > 1:
                forks.append(
                    {
                        "seq": seq,
                        "digests": sorted({identity[0] for identity in variants if identity[0]}),
                        "workflows": sorted({identity[3] for identity in variants if identity[3]}),
                    }
                )

        breaks: list[dict[str, Any]] = []
        unverified_links = 0
        for seq in seqs:
            for entry in by_seq[seq]:
                prev_seq = _int_or_none(entry.get("prev_seq"))
                if prev_seq is None:
                    prev_seq = seq - 1 if seq > 1 else 0
                prev_digest = entry.get("prev_content_digest")
                if prev_seq <= 0:
                    if prev_digest not in (None, "", GENESIS):
                        breaks.append(
                            {
                                "seq": seq,
                                "prev_seq": 0,
                                "expected": GENESIS,
                                "got": prev_digest,
                            }
                        )
                    continue
                previous = by_seq.get(prev_seq)
                if not previous:
                    unverified_links += 1
                    continue
                expected = _digest_at(previous)
                if expected is None:
                    # Previous number is itself a fork: reported there.
                    unverified_links += 1
                    continue
                if str(prev_digest or "") != expected:
                    breaks.append(
                        {
                            "seq": seq,
                            "prev_seq": prev_seq,
                            "expected": expected,
                            "got": prev_digest,
                        }
                    )

        own_heartbeats = [
            h
            for h in heartbeats
            if str(h.get("ledger_id") or "") == ledger_id
            and (
                not key_fingerprint
                or not h.get("key_fingerprint")
                or str(h.get("key_fingerprint")) == key_fingerprint
            )
        ]
        burned_seqs = sorted(
            {
                int(s)
                for h in own_heartbeats
                for s in (h.get("burned_seqs") or [])
                if _int_or_none(s) is not None and int(s) > 0
            }
        )
        heartbeat_last = max(
            (_int_or_none(h.get("last_seq")) or 0 for h in own_heartbeats), default=0
        )
        burned_missing = [s for s in burned_seqs if s not in by_seq]
        burn_conflicts = [s for s in burned_seqs if s in by_seq]
        missing = [s for s in missing_all if s not in burned_seqs]

        tail_gap = None
        if heartbeat_last > max_seq:
            # Numbers the heartbeat claims but the log does not contain. A
            # number the vendor itself declared burned is a warning, not a
            # tail gap: it is still visible, just not verifiable.
            tail_missing = [
                seq
                for seq in range(max_seq + 1, heartbeat_last + 1)
                if seq not in burned_seqs
            ]
            if tail_missing:
                tail_gap = {
                    "heartbeat_last_seq": heartbeat_last,
                    "received_last_seq": max_seq,
                    "missing_count": len(tail_missing),
                    "declared_burns": [
                        seq for seq in range(max_seq + 1, heartbeat_last + 1)
                        if seq in burned_seqs
                    ],
                }

        contiguous = not missing_all
        denominator = max(1, max(max_seq, heartbeat_last))
        burn_rate = len(burned_seqs) / denominator

        new_chain = len(key_order.get(key_fingerprint, [])) > 1 and (
            key_order[key_fingerprint][0] != ledger_id
        )

        chains.append(
            {
                "key_fingerprint": key_fingerprint,
                "ledger_id": ledger_id,
                "count": len(items),
                "first_seq": min_seq,
                "last_seq": max_seq,
                "missing": missing,
                "missing_all": missing_all,
                "forks": forks,
                "chain_breaks": breaks,
                "unverified_links": unverified_links,
                "burned": burned_missing,
                "burn_conflicts": burn_conflicts,
                "burn_rate": round(burn_rate, 4),
                "denominator": denominator,
                "tail_gap": tail_gap,
                "contiguous": contiguous,
                "new_chain": new_chain,
                "heartbeats": len(own_heartbeats),
            }
        )

    problems = {
        "missing": sum(len(c["missing"]) for c in chains),
        "forks": sum(len(c["forks"]) for c in chains),
        "chain_breaks": sum(len(c["chain_breaks"]) for c in chains),
        "tail_gaps": sum(1 for c in chains if c["tail_gap"]),
        "approval_reuse": 0,
    }
    by_request: dict[str, list[dict[str, Any]]] = {}
    for entry in approval_executed:
        request_id = str(entry.get("request_id") or "")
        if request_id:
            by_request.setdefault(request_id, []).append(entry)
    approval_reuse = [
        {
            "request_id": request_id,
            "count": len(items),
            "received_at": sorted(
                str(item.get("received_at") or "") for item in items
            ),
        }
        for request_id, items in by_request.items()
        if len(items) > 1
    ]
    problems["approval_reuse"] = len(approval_reuse)
    warnings = {
        "burned": sum(len(c["burned"]) for c in chains),
        "new_chains": sum(1 for c in chains if c["new_chain"]),
        "unverified_links": sum(c["unverified_links"] for c in chains),
        "burn_conflicts": sum(len(c["burn_conflicts"]) for c in chains),
    }
    return {
        "reports": len(seals),
        "heartbeats": len(heartbeats),
        "chains": chains,
        "unsequenced": len(unsequenced),
        "approval_executed": len(approval_executed),
        "approval_reuse": approval_reuse,
        "problems": problems,
        "warnings": warnings,
        "ok": all(value == 0 for value in problems.values()),
    }
