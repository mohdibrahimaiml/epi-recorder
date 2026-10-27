"""
Human review records for EPI artifacts.

Reviews are additive metadata. They do not rewrite the original manifest or the
sealed execution files. New v1.1 reviews are also bound to the exact sealed
artifact evidence and linked into an append-only review ledger.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import zipfile
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from epi_core.container import EPIContainer

LEGACY_REVIEW_VERSION = "1.0.0"
# 1.2.0 adds only the optional approval entry (carried inside `reviews`). The
# record shape itself is unchanged, so an older reader (4.6.x) that drops an
# unknown top-level key still computes the same hash — see the approval block
# below and `tests/test_approvers.py::test_old_reader_hash_is_stable`.
REVIEW_VERSION = "1.2.0"
REVIEW_BINDING_VERSION = "1.0.0"
REVIEW_INDEX_VERSION = "1.0.0"
REVIEW_LEDGER_PREFIX = "reviews/"
REVIEW_LATEST_NAME = "review.json"
REVIEW_INDEX_NAME = "review_index.json"

# A human approval is an entry inside the existing `reviews` list, not a new
# top-level field: old readers keep `reviews` verbatim, so their content hash
# still matches and they never raise a false tamper alarm. Exactly one
# approval entry per record, and no other entries beside it.
APPROVAL_VERSION = "1.0.0"
APPROVAL_ENTRY_TYPE = "approval"
APPROVAL_DECISIONS = ("approve", "deny")


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _safe_token(value: str) -> str:
    token = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip())
    return token.strip("-") or "review"


def _make_review_id(reviewed_at: str, reviewer: str) -> str:
    timestamp = _safe_token(reviewed_at.replace(":", "").replace("+", "Z"))
    reviewer_token = _safe_token(reviewer.lower())[:48]
    return f"review-{timestamp}-{reviewer_token}-{uuid4().hex[:12]}"


def _identity_for(reviewer: str) -> dict[str, Any]:
    return {
        "type": "email" if "@" in reviewer else "name",
        "value": reviewer,
        "role": "Reviewer",
        "org": "Unknown",
        "verified": False,
    }


def _assert_canonical_json_value(value: Any, *, path: str = "$") -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        raise ValueError(
            f"Floats are not allowed in signed review payloads (path={path}, "
            f"value={value!r}). Floats are non-deterministic across platforms and "
            f"JSON encoders, which would break signature reproducibility. "
            f"Convert the value to a string (e.g. f'{value:.6f}') or use the "
            f"helper: epi_core.review.canonicalize_floats(payload)"
        )
    if isinstance(value, list):
        for index, item in enumerate(value):
            _assert_canonical_json_value(item, path=f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError(f"Review JSON object keys must be strings: {path}")
            _assert_canonical_json_value(item, path=f"{path}.{key}")
        return
    raise ValueError(f"Unsupported review JSON value at {path}: {type(value).__name__}")


def canonicalize_floats(value: Any, *, precision: int = 6) -> Any:
    """Recursively convert all ``float`` values in *value* to fixed-precision strings.

    Use this helper before calling :func:`canonical_review_json` when your
    review payload contains numeric confidence scores or other floating-point
    fields::

        payload = canonicalize_floats({"score": 0.95, "threshold": 0.7})
        json_str = canonical_review_json(payload)   # now safe to sign

    Args:
        value:     The dict, list, or scalar to process.  Any ``float`` found
                   (at any nesting depth) is replaced by
                   ``f"{float_value:.{precision}f}"``.
        precision: Number of decimal places to use.  Defaults to 6.

    Returns:
        A new structure identical to *value* but with all floats replaced by
        deterministic decimal strings.
    """
    if isinstance(value, float):
        return f"{value:.{precision}f}"
    if isinstance(value, dict):
        return {k: canonicalize_floats(v, precision=precision) for k, v in value.items()}
    if isinstance(value, list):
        return [canonicalize_floats(item, precision=precision) for item in value]
    return value


def canonical_review_json(value: Any) -> str:
    """Return canonical JSON for review hashing/signing."""
    _assert_canonical_json_value(value)
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def compute_review_hash(review_payload: dict[str, Any]) -> str:
    """Compute the v1 review hash, excluding the mutable hash/signature fields."""
    payload = deepcopy(review_payload)
    payload.pop("review_hash", None)
    payload.pop("review_signature", None)
    return _sha256_bytes(canonical_review_json(payload).encode("utf-8"))


def _legacy_review_hash(review_payload: dict[str, Any]) -> str:
    payload = {
        "review_version": review_payload.get("review_version", LEGACY_REVIEW_VERSION),
        "reviewed_by": review_payload.get("reviewed_by"),
        "reviewed_at": review_payload.get("reviewed_at"),
        "reviews": review_payload.get("reviews") or [],
    }
    return _sha256_bytes(canonical_review_json(payload).encode("utf-8"))


def compute_manifest_sha256(epi_path: Path) -> str:
    return _sha256_bytes(EPIContainer.read_member_bytes(epi_path, "manifest.json"))


def compute_sealed_evidence_sha256(epi_path: Path) -> str:
    """
    Hash the actual files protected by manifest.file_manifest.

    This intentionally excludes review metadata and viewer files because those
    are mutable/additive. Redacted artifacts seal the redacted bytes that are
    actually present in the artifact.
    """
    manifest = EPIContainer.read_manifest(epi_path)
    entries: list[dict[str, str]] = []
    for filename in sorted(manifest.file_manifest):
        try:
            file_hash = _sha256_bytes(EPIContainer.read_member_bytes(epi_path, filename))
        except Exception:
            file_hash = "__missing__"
        entries.append({"path": filename, "sha256": file_hash})
    payload = {"files": entries}
    return _sha256_bytes(canonical_review_json(payload).encode("utf-8"))


def build_artifact_binding(epi_path: Path) -> dict[str, Any]:
    manifest = EPIContainer.read_manifest(epi_path)
    return {
        "binding_version": REVIEW_BINDING_VERSION,
        "binding_type": "epi_artifact",
        "workflow_id": str(manifest.workflow_id),
        "manifest_sha256": compute_manifest_sha256(epi_path),
        "manifest_signature": manifest.signature,
        "manifest_public_key": manifest.public_key,
        "sealed_evidence_sha256": compute_sealed_evidence_sha256(epi_path),
        "container_format": EPIContainer.detect_container_format(epi_path),
    }


class ReviewRecord:
    """Structured human review record."""

    def __init__(
        self,
        reviewed_by: str,
        reviews: list[dict],
        reviewed_at: str | None = None,
        *,
        review_id: str | None = None,
        reviewer_identity: dict[str, Any] | None = None,
        review_version: str = REVIEW_VERSION,
        artifact_binding: dict[str, Any] | None = None,
        previous_review_hash: str | None = None,
        review_hash: str | None = None,
        review_signature: str | None = None,
        case_level_review: bool = False,
        certification_level: str = "audit",
    ):
        self.reviewed_by = reviewed_by
        self.reviews = reviews
        self.reviewed_at = reviewed_at or _utc_now()
        self.review_version = review_version
        self.review_id = review_id
        if self.review_id is None and review_version != LEGACY_REVIEW_VERSION:
            self.review_id = _make_review_id(self.reviewed_at, reviewed_by)
        self.reviewer_identity = reviewer_identity
        if self.reviewer_identity is None and review_version != LEGACY_REVIEW_VERSION:
            self.reviewer_identity = _identity_for(reviewed_by)
        self.artifact_binding = artifact_binding
        self.previous_review_hash = previous_review_hash
        self.review_hash = review_hash
        self.review_signature = review_signature
        self.case_level_review = case_level_review
        self.certification_level = certification_level

    def to_dict(self) -> dict[str, Any]:
        if self.review_version == LEGACY_REVIEW_VERSION and not self.review_id:
            payload = {
                "review_version": self.review_version,
                "reviewed_by": self.reviewed_by,
                "reviewed_at": self.reviewed_at,
                "reviews": self.reviews,
                "review_signature": self.review_signature,
            }
            if self.case_level_review:
                payload["case_level_review"] = True
            return payload

        payload = {
            "review_id": self.review_id,
            "review_version": self.review_version,
            "reviewer_identity": self.reviewer_identity,
            "reviewed_by": self.reviewed_by,
            "reviewed_at": self.reviewed_at,
            "reviews": self.reviews,
            "artifact_binding": self.artifact_binding,
            "previous_review_hash": self.previous_review_hash,
            "review_hash": self.review_hash,
            "review_signature": self.review_signature,
        }
        if self.case_level_review:
            payload["case_level_review"] = True
        payload["certification_level"] = self.certification_level
        return payload

    def content_hash(self) -> str:
        payload = self.to_dict()
        if self.review_version == LEGACY_REVIEW_VERSION and not self.artifact_binding:
            return _legacy_review_hash(payload)
        return compute_review_hash(payload)

    def refresh_hash(self) -> str:
        self.review_hash = self.content_hash()
        return self.review_hash

    def bind_to_artifact(self, epi_path: Path, *, previous_review_hash: str | None = None) -> None:
        if self.review_version == LEGACY_REVIEW_VERSION:
            self.review_version = REVIEW_VERSION
        if not self.review_id:
            self.review_id = _make_review_id(self.reviewed_at, self.reviewed_by)
        if self.reviewer_identity is None:
            self.reviewer_identity = _identity_for(self.reviewed_by)
        self.artifact_binding = build_artifact_binding(epi_path)
        self.previous_review_hash = previous_review_hash
        self.review_signature = None
        self.refresh_hash()

    def sign(self, private_key) -> None:
        """Sign the review hash with an Ed25519 private key."""
        review_hash = self.refresh_hash()
        sig_bytes = private_key.sign(bytes.fromhex(review_hash))
        pub_hex = private_key.public_key().public_bytes(
            serialization.Encoding.Raw,
            serialization.PublicFormat.Raw,
        ).hex()
        self.review_signature = f"ed25519:{pub_hex}:{sig_bytes.hex()}"

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ReviewRecord:
        review_version = str(data.get("review_version") or LEGACY_REVIEW_VERSION)
        return cls(
            reviewed_by=str(data.get("reviewed_by") or "reviewer"),
            reviews=list(data.get("reviews") or []),
            reviewed_at=data.get("reviewed_at"),
            review_id=data.get("review_id"),
            reviewer_identity=data.get("reviewer_identity"),
            review_version=review_version,
            artifact_binding=data.get("artifact_binding"),
            previous_review_hash=data.get("previous_review_hash"),
            review_hash=data.get("review_hash"),
            review_signature=data.get("review_signature"),
            case_level_review=bool(data.get("case_level_review")),
        )


def _review_path(record: ReviewRecord) -> str:
    if not record.review_id:
        record.review_id = _make_review_id(record.reviewed_at, record.reviewed_by)
    return f"{REVIEW_LEDGER_PREFIX}{record.review_id}.json"


def _latest_v11_record(records: list[ReviewRecord]) -> ReviewRecord | None:
    candidates = [record for record in records if record.review_version != LEGACY_REVIEW_VERSION and record.review_hash]
    if not candidates:
        return None
    referenced_hashes = {
        record.previous_review_hash for record in candidates
        if record.previous_review_hash
    }
    tails = [record for record in candidates if record.review_hash not in referenced_hashes]
    if len(tails) == 1:
        return tails[0]
    return sorted(candidates, key=lambda item: (item.reviewed_at or "", item.review_id or ""))[-1]


def _verify_v11_chain(records: list[ReviewRecord]) -> tuple[bool, ReviewRecord | None, list[str]]:
    if not records:
        return True, None, []

    failures: list[str] = []
    by_hash: dict[str, ReviewRecord] = {}
    for record in records:
        if not record.review_hash:
            failures.append(f"Review {record.review_id} is missing review_hash")
            continue
        if record.review_hash in by_hash:
            failures.append(f"Review chain has duplicate review_hash at {record.review_id}")
            continue
        by_hash[record.review_hash] = record

    heads = [record for record in records if not record.previous_review_hash]
    referenced_hashes = {
        record.previous_review_hash for record in records
        if record.previous_review_hash
    }
    tails = [record for record in records if record.review_hash not in referenced_hashes]

    if len(heads) != 1:
        failures.append("Review chain must have exactly one first review")
    if len(tails) != 1:
        failures.append("Review chain must have exactly one latest review")

    for record in records:
        previous_hash = record.previous_review_hash
        if not previous_hash:
            continue
        if previous_hash == record.review_hash:
            failures.append(f"Review chain self-reference at {record.review_id}")
        elif previous_hash not in by_hash:
            failures.append(f"Review chain break at {record.review_id}")

    tail = tails[0] if len(tails) == 1 else _latest_v11_record(records)
    if tail and tail.review_hash in by_hash:
        visited: set[str] = set()
        cursor: ReviewRecord | None = tail
        while cursor is not None:
            if not cursor.review_hash:
                break
            if cursor.review_hash in visited:
                failures.append(f"Review chain cycle at {cursor.review_id}")
                break
            visited.add(cursor.review_hash)
            previous_hash = cursor.previous_review_hash
            cursor = by_hash.get(previous_hash) if previous_hash else None
        if len(visited) != len(records):
            failures.append("Review chain does not connect all v1.1 reviews")

    return not failures, tail, failures


def _load_review_from_member(epi_path: Path, member_name: str) -> ReviewRecord | None:
    try:
        data = EPIContainer.read_member_json(epi_path, member_name)
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    try:
        return ReviewRecord.from_dict(data)
    except Exception:
        return None


def _load_review_from_member_strict(epi_path: Path, member_name: str) -> tuple[ReviewRecord | None, str | None]:
    try:
        data = EPIContainer.read_member_json(epi_path, member_name)
    except Exception as exc:
        return None, f"{member_name} could not be read: {exc}"
    if not isinstance(data, dict):
        return None, f"{member_name} must contain a JSON object"
    try:
        return ReviewRecord.from_dict(data), None
    except Exception as exc:
        return None, f"{member_name} is not a valid review record: {exc}"


def read_review_records(epi_path: Path) -> list[ReviewRecord]:
    """Read append-only v1.1 ledger records, falling back to legacy review.json."""
    if not epi_path.exists():
        return []
    names = EPIContainer.list_members(epi_path)
    ledger_names = sorted(
        name for name in names
        if name.startswith(REVIEW_LEDGER_PREFIX) and name.endswith(".json")
    )
    records = [
        record for name in ledger_names
        if (record := _load_review_from_member(epi_path, name)) is not None
    ]
    if ledger_names:
        return sorted(records, key=lambda item: (item.reviewed_at or "", item.review_id or ""))

    latest = _load_review_from_member(epi_path, REVIEW_LATEST_NAME) if REVIEW_LATEST_NAME in names else None
    return [latest] if latest is not None else []


def read_review(epi_path: Path) -> ReviewRecord | None:
    """Read latest review.json from a .epi artifact, or return None."""
    if not epi_path.exists():
        return None
    try:
        if REVIEW_LATEST_NAME not in EPIContainer.list_members(epi_path):
            return None
        return _load_review_from_member(epi_path, REVIEW_LATEST_NAME)
    except Exception:
        return None


def build_review_index(records: list[ReviewRecord], *, latest_review_id: str | None) -> dict[str, Any]:
    return {
        "review_index_version": REVIEW_INDEX_VERSION,
        "latest_review_id": latest_review_id,
        "reviews": [
            {
                "review_id": record.review_id,
                "path": _review_path(record),
                "reviewed_by": record.reviewed_by,
                "reviewed_at": record.reviewed_at,
                "review_hash": record.review_hash,
                "previous_review_hash": record.previous_review_hash,
                "review_version": record.review_version,
                "case_level_review": bool(record.case_level_review),
            }
            for record in records
            if record.review_id
        ],
    }


def add_review_to_artifact(epi_path: Path, review: ReviewRecord, *, private_key: Any | None = None) -> None:
    """
    Add a review to a .epi artifact.

    New reviews are written to reviews/<review_id>.json, review.json is updated
    to point to the latest review, and review_index.json is regenerated for UI
    navigation. Existing legacy review.json readers remain compatible.
    """
    if not epi_path.exists():
        raise FileNotFoundError(f"Artifact not found: {epi_path}")

    container_format = EPIContainer.detect_container_format(epi_path)
    existing_records = read_review_records(epi_path)
    for record in existing_records:
        if not record.review_id:
            record.review_id = _make_review_id(record.reviewed_at, record.reviewed_by)
    previous = _latest_v11_record([
        record for record in existing_records
        if record.review_version != LEGACY_REVIEW_VERSION and record.review_hash
    ])
    review.bind_to_artifact(epi_path, previous_review_hash=previous.review_hash if previous else None)
    if private_key is not None:
        review.sign(private_key)
    else:
        review.refresh_hash()

    records_by_id = {record.review_id: record for record in existing_records if record.review_id}
    records_by_id[review.review_id] = review
    records = sorted(records_by_id.values(), key=lambda item: (item.reviewed_at or "", item.review_id or ""))
    latest = _latest_v11_record(records) or review
    review_index = build_review_index(records, latest_review_id=latest.review_id)

    temp_dir = EPIContainer._make_temp_dir(f"{epi_path.stem}_review_")
    payload_path = temp_dir / "payload.zip"
    temp_payload = temp_dir / "payload-with-review.zip"
    temp_artifact = temp_dir / epi_path.name
    ledger_paths = {_review_path(record) for record in records}

    try:
        EPIContainer.extract_inner_payload(epi_path, payload_path)

        with zipfile.ZipFile(payload_path, "r") as src, zipfile.ZipFile(temp_payload, "w") as dst:
            for item in src.infolist():
                if item.filename in {REVIEW_LATEST_NAME, REVIEW_INDEX_NAME} or item.filename in ledger_paths:
                    continue
                dst.writestr(item, src.read(item.filename))

            for record in records:
                dst.writestr(_review_path(record), record.to_json(), compress_type=zipfile.ZIP_DEFLATED)
            dst.writestr(REVIEW_LATEST_NAME, latest.to_json(), compress_type=zipfile.ZIP_DEFLATED)
            dst.writestr(
                REVIEW_INDEX_NAME,
                json.dumps(review_index, indent=2, ensure_ascii=False),
                compress_type=zipfile.ZIP_DEFLATED,
            )

        EPIContainer.write_from_payload(temp_payload, temp_artifact, container_format=container_format)
        temp_artifact.replace(epi_path)
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def _verify_review_signature(record: ReviewRecord, expected_hash: str) -> tuple[bool | None, str]:
    if not record.review_signature:
        return None, "Review is unsigned"
    parts = str(record.review_signature).split(":", 2)
    if len(parts) != 3 or parts[0] != "ed25519":
        return False, "Invalid review signature format"
    # Review pub is self-asserted, not registry-bound — verify length and note
    if len(parts[1]) != 64:
        return False, f"Invalid review pubkey length: expected 64 hex, got {len(parts[1])}"
    if len(parts[2]) != 128:
        return False, f"Invalid review sig length: expected 128 hex, got {len(parts[2])}"
    try:
        public_key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(parts[1]))
        signature = bytes.fromhex(parts[2])
        public_key.verify(signature, bytes.fromhex(expected_hash))
        return True, "Review signature valid"
    except InvalidSignature:
        return False, "Review signature does not match review contents"
    except Exception as exc:
        return False, f"Review signature verification failed: {exc}"


def verify_review_trust(epi_path: Path, *, strict: bool = False) -> dict[str, Any]:
    """Verify review metadata, signatures, artifact binding, and ledger chain."""
    report: dict[str, Any] = {
        "enabled": True,
        "strict": strict,
        "status": "verified",
        "review_count": 0,
        "latest_review_id": None,
        "binding_valid": None,
        "chain_valid": None,
        "signature_valid": None,
        "warnings": [],
        "failures": [],
        "reviews": [],
    }

    def warn(message: str, *, strict_failure: bool = False) -> None:
        report["warnings"].append(message)

    names = EPIContainer.list_members(epi_path)
    ledger_names = sorted(
        name for name in names
        if name.startswith(REVIEW_LEDGER_PREFIX) and name.endswith(".json")
    )
    latest_review = read_review(epi_path)
    records: list[ReviewRecord] = []
    ledger_parse_failures: list[str] = []
    if ledger_names:
        for name in ledger_names:
            record, error = _load_review_from_member_strict(epi_path, name)
            if error:
                ledger_parse_failures.append(error)
                continue
            if record is not None:
                records.append(record)
        records = sorted(records, key=lambda item: (item.reviewed_at or "", item.review_id or ""))
    elif latest_review is not None:
        records = [latest_review]
    report["review_count"] = len(records)
    report["failures"].extend(ledger_parse_failures)

    if not records:
        warn("No review records found", strict_failure=True)
        if strict:
            report["failures"].append("No signed artifact-bound review found")
        report["chain_valid"] = None
        _finalize_review_report(report)
        _attach_human_approval(report, epi_path)
        return report

    expected_binding = build_artifact_binding(epi_path)

    if not ledger_names:
        warn("Legacy review.json is present without append-only review ledger", strict_failure=True)

    v11_records = [
        record for record in records
        if record.review_version != LEGACY_REVIEW_VERSION and record.artifact_binding
    ]
    v11_records = sorted(v11_records, key=lambda item: (item.reviewed_at or "", item.review_id or ""))
    any_bad_signature = False
    any_signed = False
    all_binding_valid = True
    valid_bound_signed_count = 0

    for record in records:
        record_dict = record.to_dict()
        expected_hash = record.content_hash()
        signature_valid, signature_message = _verify_review_signature(record, expected_hash)
        if signature_valid is False:
            any_bad_signature = True
            report["failures"].append(signature_message)
        elif signature_valid is True:
            any_signed = True
        else:
            warn(f"Review {record.review_id or '<legacy>'} is unsigned", strict_failure=True)

        binding_valid: bool | None = None
        if record.review_version == LEGACY_REVIEW_VERSION or not record.artifact_binding:
            warn(f"Review {record.review_id or '<legacy>'} is not artifact-bound", strict_failure=True)
            all_binding_valid = False
        else:
            binding_valid = record.artifact_binding == expected_binding
            if not binding_valid:
                all_binding_valid = False
                report["failures"].append(f"Review {record.review_id} does not match this artifact binding")

        hash_is_required = bool(record.artifact_binding or record.review_signature or record.review_hash)
        hash_valid = True
        if record.review_version != LEGACY_REVIEW_VERSION and hash_is_required:
            if not record.review_hash:
                hash_valid = False
                report["failures"].append(f"Review {record.review_id} is missing review_hash")
            elif record.review_hash != expected_hash:
                hash_valid = False
                report["failures"].append(f"Review {record.review_id} review_hash does not match canonical content")

        if (
            record.review_version != LEGACY_REVIEW_VERSION
            and binding_valid is True
            and signature_valid is True
            and hash_valid
        ):
            valid_bound_signed_count += 1

        report["reviews"].append(
            {
                "review_id": record.review_id,
                "review_version": record.review_version,
                "reviewed_by": record.reviewed_by,
                "reviewed_at": record.reviewed_at,
                "review_hash": record.review_hash,
                "expected_hash": expected_hash,
                "signature_valid": signature_valid,
                "signature_message": signature_message,
                "artifact_bound": bool(record.artifact_binding),
                "binding_valid": binding_valid,
            }
        )

    chain_valid, latest, chain_failures = _verify_v11_chain(v11_records)
    report["failures"].extend(chain_failures)

    if latest:
        report["latest_review_id"] = latest.review_id
        if latest_review is None:
            report["failures"].append("review.json latest pointer is missing")
        elif latest_review.review_id != latest.review_id or latest_review.content_hash() != latest.content_hash():
            report["failures"].append("review.json does not match the latest append-only review")
    elif latest_review is not None:
        report["latest_review_id"] = latest_review.review_id

    report["chain_valid"] = chain_valid if v11_records else None
    report["binding_valid"] = all_binding_valid if v11_records else None
    report["signature_valid"] = False if any_bad_signature else (True if any_signed else None)
    if strict and valid_bound_signed_count == 0:
        report["failures"].append("No signed artifact-bound review found")
    _finalize_review_report(report)
    _attach_human_approval(report, epi_path)
    return report


def _finalize_review_report(report: dict[str, Any]) -> None:
    if report["failures"]:
        report["status"] = "failed"
    elif report["warnings"]:
        report["status"] = "warnings"
    else:
        report["status"] = "verified"


def make_review_entry(fault: dict, outcome: str, notes: str, reviewer: str) -> dict:
    return {
        "fault_step": fault.get("step_number"),
        "rule_id": fault.get("rule_id"),
        "fault_type": fault.get("fault_type"),
        "outcome": outcome,
        "notes": notes,
        "reviewer": reviewer,
        "timestamp": _utc_now(),
    }


# ---------------------------------------------------------------------------
# Human approval (review version 1.2.0)
#
# An approval rides inside the existing `reviews` list as a single entry. Old
# readers keep `reviews` verbatim, so their content hash is unchanged and they
# never report a false tamper. `reviewer_identity.verified` is always False on
# records we write: it is the writer's claim, and only the verifier decides.
# ---------------------------------------------------------------------------


def make_approval_entry(
    *,
    approval_id: str | None,
    decision: str,
    action: str,
    reason: str | None,
    approver_name: str,
    key_fingerprint_hex: str,
    case_level: bool = False,
) -> dict[str, Any]:
    """Build the single ``reviews[]`` entry that carries a human approval."""
    return {
        "entry_type": APPROVAL_ENTRY_TYPE,
        "approval_version": APPROVAL_VERSION,
        "approval_id": None if case_level else approval_id,
        "case_level": bool(case_level),
        "decision": decision,
        "action": str(action or ""),
        "reason": str(reason or ""),
        "approver": {
            "name": str(approver_name or ""),
            "key_fingerprint": str(key_fingerprint_hex or ""),
        },
    }


def approval_entry_of(record: ReviewRecord) -> dict[str, Any] | None:
    """The approval entry *record* carries, or ``None`` if it is not one."""
    entries = record.reviews if isinstance(record.reviews, list) else []
    for entry in entries:
        if isinstance(entry, dict) and entry.get("entry_type") == APPROVAL_ENTRY_TYPE:
            return entry
    return None


def is_approval_record(record: ReviewRecord) -> bool:
    return approval_entry_of(record) is not None


def _group_fingerprint(value: str) -> str:
    text = "".join(str(value or "").split()).lower()
    return " ".join(text[i : i + 4] for i in range(0, len(text), 4))


def _fmt_clock(value: str | None) -> str:
    text = str(value or "")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed.strftime("%Y-%m-%d %H:%M UTC")
    except Exception:
        return text or "unknown time"


def _approval_entry_problem(record: ReviewRecord, entry: dict[str, Any]) -> str | None:
    entries = record.reviews if isinstance(record.reviews, list) else None
    if entries is None or len(entries) != 1:
        return "An approval record must carry exactly one entry"
    if not isinstance(entry, dict):
        return "Approval entry is malformed"
    if entry.get("approval_version") != APPROVAL_VERSION:
        return f"Unsupported approval_version: {entry.get('approval_version')!r}"
    if entry.get("decision") not in APPROVAL_DECISIONS:
        return "decision must be 'approve' or 'deny'"
    case_level = entry.get("case_level")
    if not isinstance(case_level, bool):
        return "case_level must be a boolean"
    if case_level:
        if entry.get("approval_id") is not None:
            return "A case-level approval must not carry an approval_id"
    elif not (isinstance(entry.get("approval_id"), str) and entry.get("approval_id")):
        return "approval_id is required for a per-request approval"
    approver = entry.get("approver")
    if not isinstance(approver, dict):
        return "approver is required"
    if not isinstance(approver.get("key_fingerprint"), str) or not approver.get("key_fingerprint"):
        return "approver.key_fingerprint is required"
    for field in ("action", "reason"):
        if not isinstance(entry.get(field, ""), str):
            return f"{field} must be a string"
    return None


def _order_by_chain(records: list[ReviewRecord]) -> list[ReviewRecord]:
    """Records ordered head → tail by the review hash chain.

    Falls back to ``reviewed_at``/``review_id`` when the chain is ambiguous:
    a signer can write ``reviewed_at``, so it is never the primary ordering.
    """
    candidates = [
        record for record in records
        if record.review_hash and record.review_version != LEGACY_REVIEW_VERSION
    ]
    legacy = [record for record in records if record not in candidates]
    ordered: list[ReviewRecord] = []
    heads = [record for record in candidates if not record.previous_review_hash]
    if len(heads) == 1:
        by_previous: dict[str | None, list[ReviewRecord]] = {}
        for record in candidates:
            by_previous.setdefault(record.previous_review_hash, []).append(record)
        cursor: ReviewRecord | None = heads[0]
        seen: set[str] = set()
        while cursor is not None and cursor.review_hash not in seen:
            seen.add(cursor.review_hash)
            ordered.append(cursor)
            nexts = by_previous.get(cursor.review_hash) or []
            cursor = nexts[0] if len(nexts) == 1 else None
    if len(ordered) != len(candidates):
        ordered = sorted(
            candidates, key=lambda item: (item.reviewed_at or "", item.review_id or "")
        )
    ordered.extend(
        sorted(legacy, key=lambda item: (item.reviewed_at or "", item.review_id or ""))
    )
    return ordered


def _approval_scan(
    epi_path: Path, records: list[ReviewRecord], *, registry: Any
) -> dict[str, Any]:
    try:
        manifest = EPIContainer.read_manifest(epi_path)
        sealing_key = str(getattr(manifest, "public_key", None) or "").strip().lower()
    except Exception:
        sealing_key = ""
    try:
        expected_binding = build_artifact_binding(epi_path)
    except Exception:
        expected_binding = None
    v11 = [
        record for record in records
        if record.review_version != LEGACY_REVIEW_VERSION and record.artifact_binding
    ]
    chain_valid, _tail, chain_failures = _verify_v11_chain(v11)
    return {
        "sealing_key": sealing_key,
        "expected_binding": expected_binding,
        "chain_valid": chain_valid,
        "chain_failures": chain_failures,
        "registry": registry,
        "ordered": _order_by_chain(records),
    }


def _classify_approval(
    record: ReviewRecord, entry: dict[str, Any], scan: dict[str, Any]
) -> dict[str, Any]:
    from epi_core.approvers import normalize_fingerprint
    from epi_core.keys import key_fingerprint

    approver_claim = entry.get("approver") if isinstance(entry.get("approver"), dict) else {}
    claimed_name = str(approver_claim.get("name") or "")
    claimed_fp = normalize_fingerprint(approver_claim.get("key_fingerprint"))

    result: dict[str, Any] = {
        "review_id": record.review_id,
        "reviewed_at": record.reviewed_at,
        "approval_id": entry.get("approval_id"),
        "case_level": bool(entry.get("case_level")),
        "decision": entry.get("decision"),
        "action": entry.get("action") or "",
        "claimed_approver_name": claimed_name,
        "approver_name": claimed_name,
        "key_fingerprint": None,
        "approval_id_present": False,
        "classification": "invalid",
        "reason": "",
        "warning": None,
    }

    problem = _approval_entry_problem(record, entry)
    if problem:
        result["reason"] = problem
        return result
    if record.review_version == LEGACY_REVIEW_VERSION or not record.artifact_binding:
        result["reason"] = "Approval is not artifact-bound"
        return result
    if scan["expected_binding"] is not None and record.artifact_binding != scan["expected_binding"]:
        result["reason"] = "Approval does not match this artifact binding"
        return result
    if record.review_hash != record.content_hash():
        result["reason"] = "review_hash does not match canonical content"
        return result
    if not scan["chain_valid"]:
        result["reason"] = (scan["chain_failures"] or ["Review chain is broken"])[0]
        return result

    signature = record.review_signature
    if not signature:
        result["classification"] = "unsigned"
        result["reason"] = "Approval is present but unsigned"
        return result

    parts = str(signature).split(":", 2)
    if len(parts) != 3 or parts[0] != "ed25519" or len(parts[1]) != 64 or len(parts[2]) != 128:
        result["reason"] = "Approval signature is malformed"
        return result
    signing_key = parts[1].lower()
    valid, message = _verify_review_signature(record, record.content_hash())
    if valid is not True:
        result["reason"] = message or "Approval signature is invalid"
        return result

    signing_fp = key_fingerprint(signing_key, grouped=False)
    result["key_fingerprint"] = signing_fp
    if claimed_fp and claimed_fp != signing_fp:
        result["reason"] = "approver.key_fingerprint does not match the signing key"
        return result

    # Sealing-key rule runs before the registry: a sealing key that someone
    # also pinned as an approver still lands here.
    if scan["sealing_key"] and signing_key == scan["sealing_key"]:
        result["classification"] = "signed_by_sealing_key"
        result["reason"] = "Signed by the sealing key (not independent of the agent)"
        return result

    registry_entry = scan["registry"].get_by_key(signing_key)
    if registry_entry is not None:
        result["classification"] = "human_signed"
        result["reason"] = "Signed by a pinned approver key"
        registry_name = str(registry_entry.get("name") or "")
        result["approver_name"] = registry_name or claimed_name
        if registry_name and claimed_name and registry_name != claimed_name:
            result["warning"] = (
                f"Approval claims to be '{claimed_name}' but the key is pinned as "
                f"'{registry_name}'"
            )
        return result

    result["classification"] = "signed_unknown_key"
    result["reason"] = "Valid signature, but the key is not a pinned approver"
    return result


def _human_approval_none_detail(agent_reported: int) -> str:
    if agent_reported > 0:
        return "this run only contains approvals reported by the agent itself"
    return "no human-signed approval on this run"


def _human_approval_detail(
    status: str,
    classifications: list[dict[str, Any]],
    human: list[dict[str, Any]],
) -> str:
    if status == "failed":
        invalid = next(
            (item for item in classifications if item["classification"] == "invalid"), None
        )
        return invalid["reason"] if invalid else "an approval is invalid"
    if status == "unverified":
        item = classifications[0]
        if item["classification"] == "signed_by_sealing_key":
            return "signed by the sealing key (not independent of the agent)"
        if item["classification"] == "unsigned":
            return "an approval is present but unsigned"
        fp = _group_fingerprint(item.get("key_fingerprint") or "")
        return f"signed by an unpinned key (fp {fp}); pin it with: epi approvers add"
    item = human[-1]
    verb = "approved" if item.get("decision") == "approve" else "denied"
    target = f'"{item.get("action")}"' if item.get("action") else "the run (case-level)"
    return (
        f"{item.get('approver_name') or 'an approver'} "
        f"(fp {_group_fingerprint(item.get('key_fingerprint') or '')}) {verb} {target} "
        f"(signed {_fmt_clock(item.get('reviewed_at'))}, approver's clock)"
    )


def verify_human_approvals(epi_path: Path, *, registry: Any = None) -> dict[str, Any]:
    """Classify every human approval and decide whether it satisfies a request.

    ``requirement_met`` is the rule ``epi verify --require-human-approval``
    uses: every sealed ``agent.approval.request`` must have a human-signed
    approval whose latest human-signed decision is ``approve``, or the latest
    human-signed case-level approval must be ``approve`` with no request denied.
    """
    from epi_core.approvers import ApproverRegistry

    report: dict[str, Any] = {
        "status": "none",
        "agent_reported_approvals": 0,
        "approvals": [],
        "requests": [],
        "latest_decision": None,
        "latest_human_signed_review_id": None,
        "requirement_met": False,
        "required": False,
        "present": False,
        "detail": "",
        "warnings": [],
    }

    try:
        steps = EPIContainer.read_steps(epi_path)
    except Exception:
        steps = []

    sealed_requests: list[dict[str, Any]] = []
    for index, step in enumerate(steps):
        if not isinstance(step, dict):
            continue
        content = step.get("content") if isinstance(step.get("content"), dict) else {}
        if step.get("kind") == "agent.approval.request":
            sealed_requests.append(
                {
                    "approval_id": content.get("approval_id"),
                    "action": content.get("action"),
                    "step_index": index,
                }
            )
        elif step.get("kind") == "agent.approval.response":
            report["agent_reported_approvals"] += 1

    try:
        records = read_review_records(epi_path)
    except Exception:
        records = []

    approval_records = [record for record in records if approval_entry_of(record) is not None]
    report["present"] = (
        bool(records) or bool(sealed_requests) or report["agent_reported_approvals"] > 0
    )

    report["requests"] = [
        {
            "approval_id": req["approval_id"],
            "action": req["action"],
            "status": "missing",
            "review_id": None,
        }
        for req in sealed_requests
    ]

    if not approval_records:
        report["detail"] = _human_approval_none_detail(report["agent_reported_approvals"])
        return report

    scan = _approval_scan(epi_path, records, registry=registry or ApproverRegistry())

    classifications = [
        _classify_approval(record, entry, scan)
        for record in records
        if (entry := approval_entry_of(record)) is not None
    ]

    sealed_ids = {str(req["approval_id"]) for req in sealed_requests if req["approval_id"]}
    for item in classifications:
        if item["approval_id"] and str(item["approval_id"]) in sealed_ids:
            item["approval_id_present"] = True
    report["approvals"] = classifications
    report["warnings"] = [item["warning"] for item in classifications if item.get("warning")]

    position = {record.review_id: pos for pos, record in enumerate(scan["ordered"])}
    human = [item for item in classifications if item["classification"] == "human_signed"]
    human.sort(key=lambda item: position.get(item["review_id"], -1))
    if human:
        report["latest_decision"] = human[-1]["decision"]
        report["latest_human_signed_review_id"] = human[-1]["review_id"]

    request_results: list[dict[str, Any]] = []
    for req in sealed_requests:
        approval_id = req["approval_id"]
        match = None
        if approval_id:
            candidates = [
                item for item in human
                if not item["case_level"] and str(item["approval_id"]) == str(approval_id)
            ]
            if candidates:
                match = candidates[-1]
        if match is None:
            status = "missing"
        else:
            status = "approved" if match["decision"] == "approve" else "denied"
        request_results.append(
            {
                "approval_id": approval_id,
                "action": req["action"],
                "status": status,
                "review_id": match["review_id"] if match else None,
            }
        )
    report["requests"] = request_results

    case_level_human = [item for item in human if item["case_level"]]
    latest_case = case_level_human[-1]["decision"] if case_level_human else None
    rule_a = bool(request_results) and all(
        item["status"] == "approved" for item in request_results
    )
    rule_b = latest_case == "approve" and not any(
        item["status"] == "denied" for item in request_results
    )
    report["requirement_met"] = bool(rule_a or rule_b)

    if any(item["classification"] == "invalid" for item in classifications):
        report["status"] = "failed"
    elif human:
        report["status"] = "verified"
    else:
        report["status"] = "unverified"

    report["detail"] = _human_approval_detail(report["status"], classifications, human)
    return report


def _attach_human_approval(report: dict[str, Any], epi_path: Path) -> None:
    try:
        human = verify_human_approvals(epi_path)
    except Exception as exc:
        report["human_approval"] = {
            "status": "none",
            "approvals": [],
            "requests": [],
            "detail": f"human approval not evaluated: {exc}",
        }
        return
    report["human_approval"] = human
    by_id = {item.get("review_id"): item for item in human.get("approvals", [])}
    for entry in report.get("reviews", []):
        item = by_id.get(entry.get("review_id"))
        if item is not None:
            entry["classification"] = item["classification"]
            entry["key_fingerprint"] = item.get("key_fingerprint")
