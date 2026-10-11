"""Signed webhooks + customer witness outbox.

`send_signed_webhook` moved here from `epi_gateway/approval_notify.py`
(which re-exports it, so the gateway and its tests are unchanged).

The customer witness (docs/WITNESS.md): after every seal, a small
hash-only payload (`schema: epi-witness/v1`) is reported to endpoint(s)
the customer controls. Delivery must never fail or slow the seal, so each
payload is first appended to a local outbox file and delivered from a
daemon thread; `epi witness flush` retries whatever is undelivered.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import tempfile
import threading
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("epi.witness")

_APPEND_LOCK = threading.Lock()


class _OutboxFileLock:
    """Cross-process exclusive lock for the outbox file (stdlib only).

    Windows has no atomic O_APPEND (CPython emulates it as seek+write, so
    concurrent seals overwrite each other). The lock is an adjacent
    `<outbox>.lock` file created with O_CREAT|O_EXCL, which IS atomic on
    Windows and POSIX. Stale locks (crashed holder) are reaped by mtime.
    Never raises: on timeout the caller proceeds unlocked with a warning
    (availability over perfection; contention windows are milliseconds).
    """

    def __init__(
        self, outbox: Path, *, timeout: float = 10.0, stale_after: float = 30.0
    ) -> None:
        self._lock_path = Path(str(outbox) + ".lock")
        self._timeout = max(0.5, float(timeout))
        self._stale_after = max(1.0, float(stale_after))
        self._locked = False

    def __enter__(self) -> bool:
        import time as _time

        deadline = _time.monotonic() + self._timeout
        try:
            self._lock_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            return False
        while True:
            try:
                fd = os.open(str(self._lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.close(fd)
                self._locked = True
                return True
            except FileExistsError:
                try:
                    age = _time.time() - self._lock_path.stat().st_mtime
                    if age > self._stale_after:
                        self._lock_path.unlink(missing_ok=True)
                        continue
                except OSError:
                    pass
            except OSError:
                return False
            if _time.monotonic() >= deadline:
                logger.warning("Witness outbox lock timed out; proceeding unlocked")
                return False
            _time.sleep(0.01)

    def __exit__(self, *exc) -> None:
        if self._locked:
            try:
                self._lock_path.unlink(missing_ok=True)
            except OSError:
                pass
            self._locked = False


WITNESS_SCHEMA = "epi-witness/v1"

# Members and manifest fields a legitimate post-seal step may add without
# touching the sealed evidence (e.g. `epi-register` embeds a transparency
# receipt under governance.scitt and re-signs). Everything else is covered.
_POST_SEAL_MEMBER_PREFIXES = ("artifacts/scitt/", "artifacts/transparency/")
_POST_SEAL_GOVERNANCE_KEYS = ("scitt", "transparency")


def witness_content_digest(manifest: Any) -> str:
    """SHA-256 over the sealed manifest minus post-seal additions.

    Covers every manifest field (workflow id, goal, timestamps, signing key,
    file hashes, ...) except the signature, transparency entries added under
    governance after sealing, and transparency members in file_manifest. A
    re-packaged file that still carries the witnessed evidence keeps this
    digest; any change to the evidence itself changes it.
    """
    import rfc8785

    data = manifest.model_dump(mode="json") if hasattr(manifest, "model_dump") else dict(manifest)
    data.pop("signature", None)
    governance = data.get("governance")
    if isinstance(governance, dict):
        governance = {k: v for k, v in governance.items() if k not in _POST_SEAL_GOVERNANCE_KEYS}
        data["governance"] = governance or None
    files = data.get("file_manifest")
    if isinstance(files, dict):
        data["file_manifest"] = {
            k: v for k, v in files.items() if not k.startswith(_POST_SEAL_MEMBER_PREFIXES)
        }
    return hashlib.sha256(rfc8785.dumps(data)).hexdigest()


def send_signed_webhook(
    webhook_url: str,
    payload: dict,
    *,
    secret: str | None = None,
    timeout_seconds: int = 10,
    extra_headers: dict[str, str] | None = None,
) -> None:
    """POST JSON with an HMAC header. Failures are logged, never raised.

    Same format (and retry shape) as the original gateway approval webhook:
    `X-EPI-Signature: sha256=<hex>` when a secret is set. Retries with
    0/1/2/4 s backoff like before — callers that need bounded latency pass a
    small `timeout_seconds` and run this on a background thread.
    """
    if not str(webhook_url or "").strip():
        return

    payload_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if secret:
        digest = hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()
        headers["X-EPI-Signature"] = f"sha256={digest}"
    for key, value in (extra_headers or {}).items():
        if key and value is not None:
            headers[str(key)] = str(value)

    delays = [0, 1, 2, 4]
    for attempt, delay in enumerate(delays, start=1):
        if delay:
            time.sleep(delay)
        try:
            request = urllib.request.Request(
                webhook_url,
                data=payload_bytes,
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=timeout_seconds):
                return
        except Exception as exc:
            if attempt < len(delays):
                logger.warning(
                    "Webhook attempt %s failed for %s: %s",
                    attempt,
                    webhook_url,
                    exc,
                )
            else:
                logger.warning(
                    "Webhook failed after %s attempts for %s: %s",
                    len(delays),
                    webhook_url,
                    exc,
                )


def seal_signature_header(
    payload_bytes: bytes, private_key_bytes: bytes, key_name: str
) -> str:
    """Ed25519 signature of the witness body: `ed25519:<keyname>:<hex>`.

    The customer verifies it with the vendor's pinned public key, so the
    witness record is authenticated even without a shared HMAC secret.
    """
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    signature = Ed25519PrivateKey.from_private_bytes(bytes(private_key_bytes)).sign(
        bytes(payload_bytes)
    )
    return f"ed25519:{key_name}:{signature.hex()}"


def outbox_path() -> Path:
    """`~/.epi/witness_outbox.jsonl`, honouring `EPI_HOME` as the state dir."""
    base = os.environ.get("EPI_HOME")
    if base:
        return Path(base) / "witness_outbox.jsonl"
    return Path.home() / ".epi" / "witness_outbox.jsonl"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_outbox(path: Path | None = None) -> list[dict[str, Any]]:
    """All outbox entries (one JSON object per line). Never raises."""
    target = Path(path) if path else outbox_path()
    try:
        if not target.is_file():
            return []
        entries = []
        for line in target.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except Exception:
                continue
            if isinstance(entry, dict):
                entries.append(entry)
        return entries
    except Exception:
        return []


def _write_outbox(entries: list[dict[str, Any]], path: Path) -> None:
    with _OutboxFileLock(path, timeout=30.0):
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + f".tmp-{os.getpid()}")
        tmp.write_text(
            "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in entries),
            encoding="utf-8",
        )
        os.replace(tmp, path)


def append_outbox_entry(
    payload: dict[str, Any],
    urls: list[str],
    *,
    headers: dict[str, str] | None = None,
    path: Path | None = None,
) -> dict[str, Any]:
    """Append one witness entry with all urls pending. Returns the entry.

    `headers` carries public authentication material (the Ed25519 seal
    signature). The HMAC secret is never persisted; flush re-reads it from
    the environment or a flag.

    The append is one unbuffered O_APPEND syscall (plus an in-process lock),
    so concurrent seals — threads or separate processes — cannot interleave
    or lose entries. Marking delivery still rewrites the file (interactive
    flush/status paths, single operator).
    """
    target = Path(path) if path else outbox_path()
    entry = {
        "id": hashlib.sha256(
            f"{_utc_now_iso()}|{json.dumps(payload, sort_keys=True)}|{os.getpid()}".encode()
        ).hexdigest()[:16],
        "created_at": _utc_now_iso(),
        "payload": payload,
        "headers": dict(headers or {}),
        "pending": list(urls),
        "delivered": {},
        "last_error": None,
    }
    data = (json.dumps(entry, ensure_ascii=False) + "\n").encode("utf-8")
    target.parent.mkdir(parents=True, exist_ok=True)
    with _APPEND_LOCK, _OutboxFileLock(target, timeout=10.0):
        fd = os.open(str(target), os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
        try:
            view = memoryview(data)
            while view:
                written = os.write(fd, view)
                view = view[written:]
        finally:
            os.close(fd)
    return entry


def _mark_delivered(path: Path, entry_id: str, url: str) -> None:
    entries = read_outbox(path)
    changed = False
    for entry in entries:
        if entry.get("id") == entry_id:
            pending = [u for u in (entry.get("pending") or []) if u != url]
            entry["pending"] = pending
            delivered = entry.get("delivered") or {}
            delivered[url] = _utc_now_iso()
            entry["delivered"] = delivered
            entry["last_error"] = None
            changed = True
    if changed:
        _write_outbox(entries, path)


def _mark_error(path: Path, entry_id: str, error: str) -> None:
    entries = read_outbox(path)
    changed = False
    for entry in entries:
        if entry.get("id") == entry_id:
            entry["last_error"] = str(error)[:300]
            changed = True
    if changed:
        _write_outbox(entries, path)


def _post_once(
    url: str,
    payload: dict[str, Any],
    *,
    secret: str | None,
    extra_headers: dict[str, str] | None,
    timeout_seconds: int,
) -> None:
    """Single POST without retries (the outbox + flush is the retry layer)."""
    payload_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if secret:
        digest = hmac.new(
            secret.encode("utf-8"), payload_bytes, hashlib.sha256
        ).hexdigest()
        headers["X-EPI-Signature"] = f"sha256={digest}"
    for key, value in (extra_headers or {}).items():
        if key and value is not None:
            headers[str(key)] = str(value)
    request = urllib.request.Request(url, data=payload_bytes, headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=timeout_seconds):
        return


def deliver_entry(
    entry: dict[str, Any],
    *,
    secret: str | None = None,
    extra_headers: dict[str, str] | None = None,
    timeout_seconds: int = 10,
    path: Path | None = None,
) -> dict[str, Any]:
    """Deliver one entry's pending urls. Returns {"delivered": [...], "failed": {url: error}}."""
    target = Path(path) if path else outbox_path()
    stored_headers = dict(entry.get("headers") or {})
    stored_headers.update(extra_headers or {})
    delivered: list[str] = []
    failed: dict[str, str] = {}
    for url in list(entry.get("pending") or []):
        try:
            _post_once(
                url,
                entry["payload"],
                secret=secret,
                extra_headers=stored_headers,
                timeout_seconds=timeout_seconds,
            )
        except Exception as exc:
            failed[url] = str(exc)[:300]
            _mark_error(target, str(entry.get("id")), f"{url}: {exc}")
        else:
            delivered.append(url)
            _mark_delivered(target, str(entry.get("id")), url)
    return {"delivered": delivered, "failed": failed}


def deliver_in_background(
    entry: dict[str, Any],
    *,
    secret: str | None = None,
    extra_headers: dict[str, str] | None = None,
    timeout_seconds: int = 10,
    path: Path | None = None,
) -> threading.Thread:
    """Deliver one entry from a daemon thread. Never raises, never blocks seal."""

    def _run() -> None:
        try:
            deliver_entry(
                entry,
                secret=secret,
                extra_headers=extra_headers,
                timeout_seconds=timeout_seconds,
                path=path,
            )
        except Exception as exc:
            logger.warning("Background witness delivery failed: %s", exc)

    thread = threading.Thread(target=_run, name="epi-witness-deliver", daemon=True)
    thread.start()
    return thread


def flush_outbox(
    *,
    secret: str | None = None,
    timeout_seconds: int = 10,
    path: Path | None = None,
) -> dict[str, Any]:
    """Retry every undelivered entry. Returns {"entries": n, "delivered": [...], "failed": {...}}."""
    target = Path(path) if path else outbox_path()
    summary: dict[str, Any] = {"entries": 0, "delivered": [], "failed": {}}
    for entry in read_outbox(target):
        if not entry.get("pending"):
            continue
        summary["entries"] += 1
        # NOTE: per-entry secrets are not stored (the outbox holds hashes and
        # counts only, never secrets); flush reuses one secret if given.
        result = deliver_entry(
            entry, secret=secret, timeout_seconds=timeout_seconds, path=target
        )
        summary["delivered"].extend(result["delivered"])
        summary["failed"].update(result["failed"])
    return summary


def witness_timeout() -> float:
    """Max seconds record() waits for witness delivery (EPI_WITNESS_TIMEOUT, default 5)."""
    try:
        return max(0.5, float(os.environ.get("EPI_WITNESS_TIMEOUT") or 5.0))
    except ValueError:
        return 5.0


def split_witness_urls(value: str | None) -> list[str]:
    """Comma-separated witness URLs (a vendor can witness to several customer systems)."""
    return [u.strip() for u in str(value or "").split(",") if u.strip()]


def build_witness_payload(
    *,
    workflow_id: str,
    manifest_hash: str,
    file_sha256: str,
    public_key: str | None,
    content_digest: str | None = None,
    key_fingerprint: str | None,
    steps: int,
    sealed_at: str,
    seal_timestamp: dict[str, Any],
    goal: str | None = None,
) -> dict[str, Any]:
    """Hash-only seal report. No content and no step data — hashes and counts only."""
    payload: dict[str, Any] = {
        "schema": WITNESS_SCHEMA,
        "type": "epi.sealed",
        "workflow_id": workflow_id,
        "manifest_hash": manifest_hash,
        "file_sha256": file_sha256,
        "content_digest": content_digest,
        "public_key": public_key,
        "key_fingerprint": key_fingerprint,
        "steps": int(steps),
        "sealed_at": sealed_at,
        "seal_timestamp": dict(seal_timestamp),
    }
    if goal is not None:
        payload["goal"] = goal
    return payload


def stage_seal_report(
    epi_path: Path,
    *,
    urls: list[str],
    key_name: str | None = None,
    private_key_bytes: bytes | None = None,
    goal: str | None = None,
    path: Path | None = None,
) -> dict[str, Any] | None:
    """Build the witness payload from the FINAL file and append it to the outbox.

    Synchronous but purely local (hashing + one file append, milliseconds).
    Returns the entry, or None when there is nothing to send or staging fails.
    """
    targets = [u for u in (urls or []) if str(u or "").strip()]
    if not targets:
        return None
    try:
        from epi_core.container import EPIContainer
        from epi_core.serialize import get_canonical_hash

        epi_path = Path(epi_path)
        manifest = EPIContainer.read_manifest(epi_path)
        manifest_hash = get_canonical_hash(manifest, exclude_fields=["signature"])
        file_sha256 = hashlib.sha256(epi_path.read_bytes()).hexdigest()
        public_key = getattr(manifest, "public_key", None)
        fingerprint = (
            hashlib.sha256(str(public_key).encode("utf-8")).hexdigest()[:16]
            if public_key
            else None
        )
        total_steps = getattr(manifest, "total_steps", None)
        if total_steps is None:
            try:
                total_steps = len(EPIContainer.read_steps(epi_path))
            except Exception:
                total_steps = 0
        try:
            notar = EPIContainer.read_member_json(
                epi_path, "artifacts/notarization/notarization.json"
            )
        except Exception:
            notar = None
        if isinstance(notar, dict) and notar.get("tsa_token_available"):
            seal_ts: dict[str, Any] = {
                "status": "present",
                "gen_time": notar.get("tsa_genTime"),
            }
        else:
            seal_ts = {"status": "none", "gen_time": None}
        payload = build_witness_payload(
            workflow_id=str(getattr(manifest, "workflow_id", "")),
            manifest_hash=manifest_hash,
            file_sha256=file_sha256,
            content_digest=witness_content_digest(manifest),
            public_key=public_key,
            key_fingerprint=fingerprint,
            steps=int(total_steps or 0),
            sealed_at=_utc_now_iso(),
            seal_timestamp=seal_ts,
            goal=goal,
        )
        headers: dict[str, str] = {}
        if private_key_bytes and key_name:
            try:
                headers["X-EPI-Seal-Signature"] = seal_signature_header(
                    json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                    private_key_bytes,
                    key_name,
                )
            except Exception as exc:
                logger.warning("Witness seal signature failed: %s", exc)
        return append_outbox_entry(payload, targets, headers=headers, path=path)
    except Exception as exc:
        logger.warning("Witness staging failed: %s", exc)
        return None


def report_seal(
    epi_path: Path,
    *,
    urls: list[str],
    secret: str | None = None,
    key_name: str | None = None,
    private_key_bytes: bytes | None = None,
    goal: str | None = None,
    timeout_seconds: float | None = None,
    path: Path | None = None,
) -> dict[str, Any] | None:
    """Witness one sealed `.epi` to customer endpoints. Never raises, never slows the seal.

    Stages the hash-only payload to the outbox, delivers from a daemon
    thread, and waits at most `timeout_seconds` (default EPI_WITNESS_TIMEOUT).
    Returns the outbox entry, or None when there is nothing to send.
    """
    entry = stage_seal_report(
        epi_path,
        urls=urls,
        key_name=key_name,
        private_key_bytes=private_key_bytes,
        goal=goal,
        path=path,
    )
    if entry is None:
        return None
    try:
        try:
            budget = (
                witness_timeout()
                if timeout_seconds is None
                else max(0.5, float(timeout_seconds))
            )
        except (TypeError, ValueError):
            budget = 5.0
        thread = deliver_in_background(
            entry,
            secret=secret,
            timeout_seconds=max(1, int(min(10, budget))),
            path=path,
        )
        thread.join(timeout=budget)
        return entry
    except Exception as exc:
        logger.warning("Witness report failed: %s", exc)
        return entry
