"""
Hosted share support for anonymous Phase 1 .epi links.

This module deliberately keeps share metadata separate from the live review
case store so Phase 1 can stay a minimal upload/share feature.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import sqlite3
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote

from epi_core.artifact_inspector import ArtifactInspectionError, ensure_shareable_artifact
from epi_core.container import EPI_MIMETYPE


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _isoformat(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)


def _sanitize_filename(filename: str | None) -> str:
    text = "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "-" for ch in str(filename or "case.epi"))
    text = "-".join(part for part in text.split("-") if part)
    text = text or "case.epi"
    if not text.lower().endswith(".epi"):
        text += ".epi"
    return text


class ShareServiceError(Exception):
    status_code = 400
    retry_after: Optional[int] = None

    def __init__(self, message: str, *, retry_after: int | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class ShareConfigurationError(ShareServiceError):
    status_code = 503


class ShareValidationError(ShareServiceError):
    status_code = 400


class ShareTooLargeError(ShareServiceError):
    status_code = 413


class ShareRateLimitError(ShareServiceError):
    status_code = 429


class ShareQuotaError(ShareServiceError):
    status_code = 429


class ShareNotFoundError(ShareServiceError):
    status_code = 404


class ShareExpiredError(ShareServiceError):
    status_code = 410


@dataclass(frozen=True)
class ShareRecord:
    share_id: str
    object_key: str
    filename: str
    size_bytes: int
    created_at: str
    expires_at: str
    client_key: str
    workflow_id: Optional[str]
    artifact_created_at: Optional[str]
    steps_count: int
    signature_status: str
    signer: Optional[str]
    integrity_ok: bool
    deleted_at: Optional[str] = None


class ShareMetadataStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS shares (
                    share_id TEXT PRIMARY KEY,
                    object_key TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    client_key TEXT NOT NULL,
                    workflow_id TEXT,
                    artifact_created_at TEXT,
                    steps_count INTEGER NOT NULL,
                    signature_status TEXT NOT NULL,
                    signer TEXT,
                    integrity_ok INTEGER NOT NULL,
                    deleted_at TEXT
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_shares_client_created ON shares(client_key, created_at)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_shares_expiry ON shares(expires_at, deleted_at)"
            )
            connection.commit()

    def insert(self, record: ShareRecord) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO shares (
                    share_id, object_key, filename, size_bytes, created_at, expires_at,
                    client_key, workflow_id, artifact_created_at, steps_count,
                    signature_status, signer, integrity_ok, deleted_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.share_id,
                    record.object_key,
                    record.filename,
                    record.size_bytes,
                    record.created_at,
                    record.expires_at,
                    record.client_key,
                    record.workflow_id,
                    record.artifact_created_at,
                    record.steps_count,
                    record.signature_status,
                    record.signer,
                    1 if record.integrity_ok else 0,
                    record.deleted_at,
                ),
            )
            connection.commit()

    def get(self, share_id: str) -> ShareRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT share_id, object_key, filename, size_bytes, created_at, expires_at,
                       client_key, workflow_id, artifact_created_at, steps_count,
                       signature_status, signer, integrity_ok, deleted_at
                FROM shares
                WHERE share_id = ?
                """,
                (share_id,),
            ).fetchone()
        return self._row_to_record(row)

    def quota_bytes_since(self, client_key: str, since_iso: str) -> int:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT COALESCE(SUM(size_bytes), 0) AS total_bytes
                FROM shares
                WHERE client_key = ? AND created_at >= ?
                """,
                (client_key, since_iso),
            ).fetchone()
        return int(row["total_bytes"] if row else 0)

    def mark_expired(self, now_iso: str) -> list[ShareRecord]:
        expired = self.list_expired(now_iso)
        if not expired:
            return []
        share_ids = [record.share_id for record in expired]
        with self._connect() as connection:
            connection.executemany(
                "UPDATE shares SET deleted_at = ? WHERE share_id = ? AND deleted_at IS NULL",
                [(now_iso, share_id) for share_id in share_ids],
            )
            connection.commit()
        return expired

    def list_expired(self, now_iso: str) -> list[ShareRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT share_id, object_key, filename, size_bytes, created_at, expires_at,
                       client_key, workflow_id, artifact_created_at, steps_count,
                       signature_status, signer, integrity_ok, deleted_at
                FROM shares
                WHERE expires_at <= ? AND deleted_at IS NULL
                ORDER BY expires_at ASC
                """,
                (now_iso,),
            ).fetchall()
        return [self._row_to_record(row) for row in rows if row is not None]

    @staticmethod
    def _row_to_record(row: sqlite3.Row | None) -> ShareRecord | None:
        if row is None:
            return None
        return ShareRecord(
            share_id=row["share_id"],
            object_key=row["object_key"],
            filename=row["filename"],
            size_bytes=int(row["size_bytes"]),
            created_at=row["created_at"],
            expires_at=row["expires_at"],
            client_key=row["client_key"],
            workflow_id=row["workflow_id"],
            artifact_created_at=row["artifact_created_at"],
            steps_count=int(row["steps_count"]),
            signature_status=row["signature_status"],
            signer=row["signer"],
            integrity_ok=bool(row["integrity_ok"]),
            deleted_at=row["deleted_at"],
        )


class FileShareObjectStore:
    def __init__(self, root_dir: Path) -> None:
        self.root_dir = Path(root_dir)
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def put_bytes(self, object_key: str, data: bytes, *, content_type: str) -> None:
        target = self.root_dir / object_key
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    def get_bytes(self, object_key: str) -> bytes:
        target = self.root_dir / object_key
        if not target.exists():
            raise ShareNotFoundError("Shared case file not found.")
        return target.read_bytes()

    def delete(self, object_key: str) -> None:
        target = self.root_dir / object_key
        target.unlink(missing_ok=True)


class S3ShareObjectStore:
    def __init__(
        self,
        *,
        endpoint_url: str,
        region_name: str,
        bucket: str,
        access_key_id: str,
        secret_access_key: str,
    ) -> None:
        try:
            import boto3  # type: ignore
        except Exception as exc:  # pragma: no cover - depends on optional install
            raise ShareConfigurationError(
                "Share uploads need boto3 when S3/R2 storage is enabled. Install epi-recorder[gateway]."
            ) from exc

        self.bucket = bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            region_name=region_name,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
        )

    def put_bytes(self, object_key: str, data: bytes, *, content_type: str) -> None:
        self.client.put_object(
            Bucket=self.bucket,
            Key=object_key,
            Body=data,
            ContentType=content_type,
        )

    def get_bytes(self, object_key: str) -> bytes:
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=object_key)
        except Exception as exc:
            raise ShareNotFoundError("Shared case file not found.") from exc
        return response["Body"].read()

    def delete(self, object_key: str) -> None:
        try:
            self.client.delete_object(Bucket=self.bucket, Key=object_key)
        except Exception:
            return


class ShareService:
    def __init__(
        self,
        *,
        enabled: bool,
        storage_dir: Path,
        site_base_url: str,
        api_base_url: str,
        max_upload_bytes: int,
        default_expiry_days: int,
        max_expiry_days: int,
        rate_limit_per_hour: int,
        quota_bytes_per_30d: int,
        ip_hmac_secret: str | None,
        rate_limiter: Any | None = None,
        object_store: Any | None = None,
        s3_endpoint: str | None = None,
        s3_region: str | None = None,
        s3_bucket: str | None = None,
        s3_access_key_id: str | None = None,
        s3_secret_access_key: str | None = None,
    ) -> None:
        self.enabled = bool(enabled)
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.site_base_url = str(site_base_url).rstrip("/")
        self.api_base_url = str(api_base_url).rstrip("/")
        self.max_upload_bytes = int(max_upload_bytes)
        self.default_expiry_days = int(default_expiry_days)
        self.max_expiry_days = int(max_expiry_days)
        self.rate_limit_per_hour = int(rate_limit_per_hour)
        self.quota_bytes_per_30d = int(quota_bytes_per_30d)
        self.ip_hmac_secret = str(ip_hmac_secret or "")
        self.rate_limiter = rate_limiter
        self.metadata_store = ShareMetadataStore(self.storage_dir / "share.sqlite3")
        self.object_store = object_store or self._build_object_store(
            s3_endpoint=s3_endpoint,
            s3_region=s3_region,
            s3_bucket=s3_bucket,
            s3_access_key_id=s3_access_key_id,
            s3_secret_access_key=s3_secret_access_key,
        )
        if self.enabled and not self.ip_hmac_secret:
            raise ShareConfigurationError("Share uploads require EPI_GATEWAY_SHARE_IP_HMAC_SECRET.")

    def _build_object_store(
        self,
        *,
        s3_endpoint: str | None,
        s3_region: str | None,
        s3_bucket: str | None,
        s3_access_key_id: str | None,
        s3_secret_access_key: str | None,
    ) -> Any:
        if s3_endpoint and s3_bucket and s3_access_key_id and s3_secret_access_key:
            return S3ShareObjectStore(
                endpoint_url=s3_endpoint,
                region_name=s3_region or "auto",
                bucket=s3_bucket,
                access_key_id=s3_access_key_id,
                secret_access_key=s3_secret_access_key,
            )
        return FileShareObjectStore(self.storage_dir / "shared-objects")

    def prune_expired(self) -> None:
        if not self.enabled:
            return
        now_iso = _isoformat(_utc_now())
        for record in self.metadata_store.mark_expired(now_iso):
            try:
                self.object_store.delete(record.object_key)
            except Exception:
                continue

    def create_share(
        self,
        body: bytes,
        *,
        filename: str | None,
        client_ip: str,
        expires_days: int | None = None,
    ) -> dict[str, Any]:
        if not self.enabled:
            raise ShareConfigurationError("Hosted sharing is not enabled on this gateway.")

        raw_bytes = bytes(body or b"")
        if len(raw_bytes) > self.max_upload_bytes:
            raise ShareTooLargeError(
                f"Share upload exceeds the {self.max_upload_bytes} byte limit."
            )

        if self.rate_limiter is not None and not self.rate_limiter.is_allowed(client_ip or "unknown"):
            raise ShareRateLimitError(
                "Share upload limit reached. Try again later.",
                retry_after=3600,
            )

        client_key = self._derive_client_key(client_ip)
        rolling_window_start = _isoformat(_utc_now() - timedelta(days=30))
        existing_bytes = self.metadata_store.quota_bytes_since(client_key, rolling_window_start)
        if existing_bytes + len(raw_bytes) > self.quota_bytes_per_30d:
            raise ShareQuotaError("Upload quota exceeded for this client in the last 30 days.")

        expires_in_days = self._normalize_expiry_days(expires_days)
        safe_filename = _sanitize_filename(filename)
        inspection = self._inspect_upload_bytes(raw_bytes)

        share_id = secrets.token_urlsafe(12).rstrip("=")
        object_key = f"cases/{share_id}.epi"
        created_at = _utc_now()
        expires_at = created_at + timedelta(days=expires_in_days)

        record = ShareRecord(
            share_id=share_id,
            object_key=object_key,
            filename=safe_filename,
            size_bytes=len(raw_bytes),
            created_at=_isoformat(created_at),
            expires_at=_isoformat(expires_at),
            client_key=client_key,
            workflow_id=inspection.workflow_id,
            artifact_created_at=inspection.artifact_created_at,
            steps_count=inspection.steps_count,
            signature_status=inspection.signature_status,
            signer=inspection.signer_name,
            integrity_ok=inspection.integrity_ok,
            deleted_at=None,
        )

        self.object_store.put_bytes(object_key, raw_bytes, content_type=EPI_MIMETYPE)
        self.metadata_store.insert(record)
        return self._public_payload(record)

    def get_share_metadata(self, share_id: str) -> dict[str, Any]:
        record = self._resolve_record(share_id)
        return {
            "id": record.share_id,
            "filename": record.filename,
            "size_bytes": record.size_bytes,
            "created_at": record.created_at,
            "expires_at": record.expires_at,
            "workflow_id": record.workflow_id,
            "artifact_created_at": record.artifact_created_at,
            "steps_count": record.steps_count,
            "signature_status": record.signature_status,
            "signer": record.signer,
        }

    def get_share_bytes(self, share_id: str) -> tuple[ShareRecord, bytes]:
        record = self._resolve_record(share_id)
        return record, self.object_store.get_bytes(record.object_key)

    def _resolve_record(self, share_id: str) -> ShareRecord:
        record = self.metadata_store.get(share_id)
        if record is None:
            raise ShareNotFoundError("Shared case link not found.")
        if self._is_expired(record):
            self._expire_record(record)
            raise ShareExpiredError("This shared case link has expired.")
        return record

    def _expire_record(self, record: ShareRecord) -> None:
        self.metadata_store.mark_expired(_isoformat(_utc_now()))
        try:
            self.object_store.delete(record.object_key)
        except Exception:
            return

    def _is_expired(self, record: ShareRecord) -> bool:
        if record.deleted_at:
            return True
        return _parse_iso(record.expires_at) <= _utc_now()

    def _derive_client_key(self, client_ip: str) -> str:
        normalized_ip = str(client_ip or "unknown")
        digest = hmac.new(
            self.ip_hmac_secret.encode("utf-8"),
            normalized_ip.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return digest

    def _normalize_expiry_days(self, expires_days: int | None) -> int:
        days = self.default_expiry_days if expires_days is None else int(expires_days)
        if days < 1:
            raise ShareValidationError("expires_days must be at least 1.")
        if days > self.max_expiry_days:
            raise ShareValidationError(
                f"expires_days cannot be greater than {self.max_expiry_days}."
            )
        return days

    def _inspect_upload_bytes(self, raw_bytes: bytes):
        temp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                delete=False,
                suffix=".epi",
                dir=self.storage_dir,
            ) as temp_file:
                temp_file.write(raw_bytes)
                temp_path = Path(temp_file.name)
            return ensure_shareable_artifact(temp_path)
        except ArtifactInspectionError as exc:
            raise ShareValidationError(str(exc)) from exc
        finally:
            if temp_path is not None:
                try:
                    os.unlink(temp_path)
                except FileNotFoundError:
                    pass

    def _public_payload(self, record: ShareRecord) -> dict[str, Any]:
        return {
            "id": record.share_id,
            "url": f"{self.site_base_url}/cases/?id={quote(record.share_id)}",
            "expires_at": record.expires_at,
            "size_bytes": record.size_bytes,
            "signature_status": record.signature_status,
            "signer": record.signer,
            "steps_count": record.steps_count,
        }
