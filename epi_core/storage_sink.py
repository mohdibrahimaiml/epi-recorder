"""Customer-owned storage (M4): every sealed `.epi` goes to the vendor's own
S3-compatible bucket. EPI Cloud never sees these bytes or credentials.

- Config: ``EPI_STORAGE_URL=s3://bucket[/prefix]`` (+ optional
  ``EPI_STORAGE_ENDPOINT`` for MinIO/R2/GCS, ``EPI_STORAGE_REGION``).
- Credentials: ``AWS_ACCESS_KEY_ID`` / ``AWS_SECRET_ACCESS_KEY``
  (+ optional ``AWS_SESSION_TOKEN``), else the ``~/.aws/credentials`` profile
  (``AWS_PROFILE`` or ``default``). Never logged, never persisted: the outbox
  stores only host + bucket + key, and every log line is redacted.
- Delivery is outbox-first (same pattern as the witness outbox): a seal with
  no network queues locally and `flush` retries later. Sealing never fails
  because storage is down.
- Signing is SigV4 over HTTPS, implemented here with stdlib only (no boto3
  dependency on the seal path). The Authorization header is byte-identical
  to AWS's own signer (see tests/test_storage_sink.py::test_sigv4_matches_botocore).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import threading
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

STORAGE_URL_ENV = "EPI_STORAGE_URL"
STORAGE_ENDPOINT_ENV = "EPI_STORAGE_ENDPOINT"
STORAGE_REGION_ENV = "EPI_STORAGE_REGION"
DEFAULT_REGION = "us-east-1"

_BUCKET_RE = re.compile(r"^[a-z0-9][a-z0-9.\-]{1,61}[a-z0-9]$")
_REGION_RE = re.compile(r"^[a-z0-9\-]{2,32}$")


@dataclass
class StorageTarget:
    """Parsed destination. No credentials — those stay in env/profile."""

    endpoint: str
    bucket: str
    prefix: str
    region: str


@dataclass
class StorageCredentials:
    access: str
    secret: str
    session_token: str | None = None

    def __repr__(self) -> str:  # never leak the secret into logs/tracebacks
        return f"StorageCredentials(access={self.access!r}, secret='***')"


def parse_storage_url(
    url: str, *, region: str | None = None, endpoint: str | None = None
) -> StorageTarget:
    """Parse s3://bucket[/prefix]. Credentials in the URL are refused."""
    raw = (url or "").strip()
    parts = urllib.parse.urlsplit(raw)
    if parts.scheme != "s3" or not parts.netloc:
        raise ValueError(
            "EPI_STORAGE_URL must look like s3://bucket[/prefix], "
            f"got {redact_url(raw)!r}"
        )
    if parts.username or parts.password:
        raise ValueError("Put credentials in AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY, not the URL.")
    bucket = parts.netloc
    if not _BUCKET_RE.match(bucket):
        raise ValueError(f"Invalid bucket name {bucket!r}.")
    prefix = parts.path.strip("/")
    chosen_region = region or os.getenv(STORAGE_REGION_ENV) or DEFAULT_REGION
    if not _REGION_RE.match(chosen_region):
        raise ValueError(f"Invalid region {chosen_region!r}.")
    custom = endpoint or os.getenv(STORAGE_ENDPOINT_ENV)
    if custom:
        base = custom.rstrip("/")
        if not base.startswith(("http://", "https://")):
            raise ValueError(
                f"EPI_STORAGE_ENDPOINT must be an http(s) URL, got {redact_url(base)!r}"
            )
        return StorageTarget(endpoint=base, bucket=bucket, prefix=prefix, region=chosen_region)
    if chosen_region == "us-east-1":
        host = "s3.amazonaws.com"
    else:
        host = f"s3.{chosen_region}.amazonaws.com"
    return StorageTarget(
        endpoint=f"https://{bucket}.{host}", bucket=bucket, prefix=prefix, region=chosen_region
    )


def object_url(target: StorageTarget, key: str) -> str:
    """Public-shape URL for a key. Path style on custom endpoints (MinIO/R2/GCS
    interop), virtual-hosted style on AWS."""
    if os.getenv(STORAGE_ENDPOINT_ENV) or not target.endpoint.endswith("amazonaws.com"):
        return f"{target.endpoint}/{target.bucket}/{key}"
    return f"{target.endpoint}/{key}"


def object_key_for(prefix: str, file_sha256: str) -> str:
    """Content-addressed key: identical bytes land on the same object."""
    name = f"{file_sha256}.epi"
    return f"{prefix}/{name}" if prefix else name


def load_credentials() -> StorageCredentials:
    """Env first, then the shared credentials file. Raises LookupError."""
    access = os.getenv("AWS_ACCESS_KEY_ID")
    secret = os.getenv("AWS_SECRET_ACCESS_KEY")
    if access and secret:
        return StorageCredentials(access, secret, os.getenv("AWS_SESSION_TOKEN"))
    profile = os.getenv("AWS_PROFILE", "default")
    for candidate in (Path.home() / ".aws" / "credentials",):
        try:
            import configparser

            parser = configparser.ConfigParser()
            parser.read(candidate)
            if parser.has_section(profile):
                access = parser.get(profile, "aws_access_key_id", fallback="")
                secret = parser.get(profile, "aws_secret_access_key", fallback="")
                if access and secret:
                    return StorageCredentials(
                        access,
                        secret,
                        parser.get(profile, "aws_session_token", fallback=None) or None,
                    )
        except Exception:
            continue
    raise LookupError(
        "No storage credentials: set AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY "
        "(+ optional AWS_SESSION_TOKEN) or configure ~/.aws/credentials."
    )


def redact_url(url: str) -> str:
    """Strip userinfo so endpoints are safe to log."""
    try:
        parts = urllib.parse.urlsplit(url)
        if not parts.username:
            return url
        netloc = parts.hostname or ""
        if parts.port:
            netloc += f":{parts.port}"
        return urllib.parse.urlunsplit(
            (parts.scheme, netloc, parts.path, parts.query, parts.fragment)
        )
    except Exception:
        return "<unparseable-url>"


def _hmac(key: bytes, data: str) -> bytes:
    return hmac.new(key, data.encode("utf-8"), hashlib.sha256).digest()


def sign_v4(
    access: str,
    secret: str,
    region: str,
    method: str,
    url: str,
    headers: dict[str, str],
    body: bytes,
    *,
    amz_date: str | None = None,
    session_token: str | None = None,
) -> dict[str, str]:
    """SigV4 Authorization headers for one request (byte-identical to botocore).

    Note: query strings pass through verbatim (callers here never use them).
    URL-encode + sort params first if a future caller adds a query string.
    """
    parts = urllib.parse.urlsplit(url)
    host = parts.netloc
    path = parts.path or "/"
    query = parts.query
    stamped = dict(headers)
    stamped["host"] = host
    stamp = amz_date or datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    stamped["x-amz-date"] = stamp
    payload_hash = stamped.get("x-amz-content-sha256") or hashlib.sha256(body).hexdigest()
    stamped["x-amz-content-sha256"] = payload_hash
    if session_token:
        stamped["x-amz-security-token"] = session_token
    names = sorted(k.lower() for k in stamped)
    lowered = {k.lower(): v for k, v in stamped.items()}
    canonical_headers = "".join(f"{n}:{lowered[n].strip()}\n" for n in names)
    canonical_request = "\n".join(
        [method.upper(), path, query, canonical_headers, ";".join(names), payload_hash]
    )
    scope = f"{stamp[:8]}/{region}/s3/aws4_request"
    string_to_sign = "\n".join(
        [
            "AWS4-HMAC-SHA256",
            stamp,
            scope,
            hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
        ]
    )
    signing_key = _hmac(
        _hmac(_hmac(_hmac(f"AWS4{secret}".encode(), stamp[:8]), region), "s3"), "aws4_request"
    )
    signature = hmac.new(signing_key, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
    out = dict(headers)
    out["host"] = host
    out["x-amz-date"] = stamp
    out["x-amz-content-sha256"] = payload_hash
    if session_token:
        out["x-amz-security-token"] = session_token
    out["Authorization"] = (
        f"AWS4-HMAC-SHA256 Credential={access}/{scope}, "
        f"SignedHeaders={';'.join(names)}, Signature={signature}"
    )
    return out


def put_object(
    data: bytes,
    dest_key: str,
    target: StorageTarget,
    creds: StorageCredentials,
    *,
    timeout_seconds: int = 30,
) -> None:
    """PUT bytes to the customer's bucket (raises on any failure)."""
    url = object_url(target, dest_key)
    payload_hash = hashlib.sha256(data).hexdigest()
    headers = sign_v4(
        creds.access,
        creds.secret,
        target.region,
        "PUT",
        url,
        {
            "x-amz-content-sha256": payload_hash,
            "Content-Length": str(len(data)),
            "Content-Type": "application/octet-stream",
        },
        data,
        session_token=creds.session_token,
    )
    req = urllib.request.Request(url, data=data, headers=headers, method="PUT")
    try:
        with urllib.request.urlopen(req, timeout=timeout_seconds) as res:
            if res.status not in (200, 201, 204):
                raise OSError(f"storage PUT failed: HTTP {res.status}")
    except Exception as exc:
        raise OSError(f"storage PUT to {redact_url(url)} failed: {exc}") from exc


# ---------------------------------------------------------------------------
# Outbox (offline queue). Same durability pattern as the witness outbox:
# O_APPEND appends, a file lock guards rewrites, secrets never persisted.
# ---------------------------------------------------------------------------


def storage_outbox_path() -> Path:
    base = os.environ.get("EPI_HOME")
    if base:
        return Path(base) / "storage_outbox.jsonl"
    return Path.home() / ".epi" / "storage_outbox.jsonl"


def _read_outbox(path: Path) -> list[dict]:
    try:
        if not path.is_file():
            return []
        entries = []
        for line in path.read_text(encoding="utf-8").splitlines():
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


def _rewrite_outbox(entries: list[dict], path: Path) -> None:
    from epi_core.webhook import _OutboxFileLock

    path.parent.mkdir(parents=True, exist_ok=True)
    with _OutboxFileLock(path, timeout=30.0):
        tmp = path.with_name(path.name + f".tmp-{os.getpid()}")
        tmp.write_text(
            "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in entries),
            encoding="utf-8",
        )
        os.replace(tmp, path)


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def queue_storage_upload(local_path: str, file_sha256: str, target: StorageTarget) -> dict:
    """Queue a file for upload. Never raises, never stores secrets."""
    stamp = f"{local_path}|{file_sha256}|{_utc_now_iso()}"
    entry = {
        "id": hashlib.sha256(stamp.encode()).hexdigest()[:16],
        "created_at": _utc_now_iso(),
        "local_path": local_path,
        "file_sha256": file_sha256,
        "endpoint": target.endpoint,
        "bucket": target.bucket,
        "prefix": target.prefix,
        "region": target.region,
        "dest_key": object_key_for(target.prefix, file_sha256),
        "attempts": 0,
        "pending": True,
        "last_error": "",
    }
    path = storage_outbox_path()
    entries = _read_outbox(path)
    entries.append(entry)
    _rewrite_outbox(entries, path)
    return entry


def pending_uploads(path: Path | None = None) -> list[dict]:
    """Pending outbox entries (never raises)."""
    target = Path(path) if path else storage_outbox_path()
    return [e for e in _read_outbox(target) if e.get("pending")]


def _deliver_entry(entry: dict, *, timeout_seconds: int = 30) -> None:
    local = Path(entry["local_path"])
    data = local.read_bytes()
    if hashlib.sha256(data).hexdigest() != entry["file_sha256"]:
        raise OSError(f"{local} changed since sealing; refusing to upload a different file")
    target = StorageTarget(
        endpoint=entry["endpoint"],
        bucket=entry["bucket"],
        prefix=entry.get("prefix", ""),
        region=entry["region"],
    )
    put_object(data, entry["dest_key"], target, load_credentials(), timeout_seconds=timeout_seconds)


def flush_storage_outbox(
    path: Path | None = None, *, timeout_seconds: float = 30, deadline: float | None = None
) -> dict[str, int]:
    """Upload every pending entry. Returns counts; failures stay queued.

    Stops early past `deadline` (monotonic seconds) so a piggyback flush on
    the seal path can never slow recording past its budget.
    """
    import time as _time

    target = Path(path) if path else storage_outbox_path()
    entries = _read_outbox(target)
    delivered, failed = 0, 0
    for entry in entries:
        if not entry.get("pending"):
            continue
        if deadline is not None and _time.monotonic() >= deadline:
            break
        try:
            _deliver_entry(entry, timeout_seconds=max(1, int(timeout_seconds)))
            entry["pending"] = False
            delivered += 1
        except Exception as exc:
            entry["attempts"] = int(entry.get("attempts", 0)) + 1
            message = str(exc)
            for secret_env in ("AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"):
                value = os.getenv(secret_env)
                if value:
                    message = message.replace(value, "***")
            entry["last_error"] = message[:300]
            entry["pending"] = True
            failed += 1
    _rewrite_outbox([e for e in entries if e.get("pending")], target)
    return {"delivered": delivered, "failed": failed}


def heartbeat_payload(*, ok: bool, count: int, object_lock: str = "unknown") -> dict:
    """Vendor-reported storage health for EPI Cloud (no file data, no secrets)."""
    return {"ok": ok, "count": count, "object_lock": object_lock, "checked_at": _utc_now_iso()}


def _report_heartbeat(target_ok: bool, count: int) -> None:
    """Best-effort heartbeat to EPI Cloud. Never raises, never blocks sealing."""
    try:
        url = (os.getenv("EPI_CLOUD_URL") or "").rstrip("/")
        org = os.getenv("EPI_CLOUD_ORG") or ""
        key = os.getenv("EPI_CLOUD_API_KEY") or ""
        if not (url and org and key):
            return
        body = json.dumps(heartbeat_payload(ok=target_ok, count=count)).encode("utf-8")
        req = urllib.request.Request(
            f"{url}/v1/orgs/{org}/storage-target/check",
            data=body,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as res:
            res.read()
    except Exception:
        pass


def _storage_timeout() -> float:
    """Max seconds a seal waits for the customer-bucket upload (default 10)."""
    try:
        return max(0.5, float(os.environ.get("EPI_STORAGE_TIMEOUT") or 10.0))
    except (TypeError, ValueError):
        return 10.0


def store_customer_copy(
    path: str, *, workflow_id: str | None = None, storage_url: str | None = None
) -> dict:
    """Upload one sealed `.epi` to the customer's bucket (outbox-first).

    Queues the file, delivers from a daemon thread, and waits at most
    EPI_STORAGE_TIMEOUT. Returns {"stored": True, "key": ...} or
    {"stored": False, "reason": ...}. Never raises: sealing must not fail
    because storage is down.
    """
    del workflow_id
    try:
        import time as _time

        budget = _storage_timeout()
        started = _time.monotonic()
        url = storage_url if storage_url is not None else os.getenv(STORAGE_URL_ENV, "")
        if not url:
            return {"stored": False, "reason": "not-configured"}
        target = parse_storage_url(url)
        local = Path(path)
        digest = hashlib.sha256(local.read_bytes()).hexdigest()
        entry = queue_storage_upload(str(local), digest, target)
        outcome: dict[str, bool] = {}

        def _run() -> None:
            try:
                _deliver_entry(entry)
                outcome["delivered"] = True
            except Exception:
                outcome["delivered"] = False

        thread = threading.Thread(target=_run, name="epi-storage-upload", daemon=True)
        thread.start()
        thread.join(timeout=budget)
        if outcome.get("delivered"):
            entries = _read_outbox(storage_outbox_path())
            kept = [e for e in entries if e.get("id") != entry["id"]]
            _rewrite_outbox(kept, storage_outbox_path())
            # Piggyback: a healthy seal also retries older queued uploads,
            # so files stop needing a manual flush. Bounded by the same
            # budget; the seal never fails because of it.
            remaining = budget - (_time.monotonic() - started)
            flushed = {"delivered": 0, "failed": 0}
            if remaining > 1:
                flushed = flush_storage_outbox(
                    timeout_seconds=remaining, deadline=started + budget
                )
            _report_heartbeat(True, 1 + flushed["delivered"])
            return {"stored": True, "key": entry["dest_key"]}
        _report_heartbeat(False, len(pending_uploads()))
        return {"stored": False, "reason": "queued: still in flight or unreachable"}
    except Exception as exc:
        return {"stored": False, "reason": str(exc)[:200]}
