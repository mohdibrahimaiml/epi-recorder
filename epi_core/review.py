"""
EPI Review — Human confirmation record for fault analysis.

The review is additive: it is appended to the existing sealed artifact
without modifying steps.jsonl, analysis.json, or manifest.json.
The original seal remains intact. The review carries its own signature.

Review outcomes:
    confirmed_fault  — reviewer agrees the flagged behavior is a genuine fault.
    dismissed        — reviewer has a legitimate explanation (expected behavior).
    skipped          — reviewer deferred the decision.
"""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


REVIEW_VERSION = "1.0.0"


class ReviewRecord:
    """
    Structured review of one or more faults from analysis.json.

    Build via ReviewRecord.create(), then serialise with to_json().
    """

    def __init__(
        self,
        reviewed_by: str,
        reviews: list[dict],
        reviewed_at: Optional[str] = None,
    ):
        self.reviewed_by = reviewed_by
        self.reviews = reviews
        self.reviewed_at = reviewed_at or datetime.now(timezone.utc).isoformat()
        self.review_version = REVIEW_VERSION
        self.review_signature: Optional[str] = None  # set after signing

    def content_hash(self) -> str:
        """SHA-256 of the canonical content (for signing)."""
        payload = json.dumps(
            {
                "review_version": self.review_version,
                "reviewed_by": self.reviewed_by,
                "reviewed_at": self.reviewed_at,
                "reviews": self.reviews,
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def sign(self, private_key) -> None:
        """Sign the review with an Ed25519 private key."""
        from cryptography.hazmat.primitives import serialization
        hash_bytes = bytes.fromhex(self.content_hash())
        sig_bytes = private_key.sign(hash_bytes)
        pub_hex = private_key.public_key().public_bytes(
            serialization.Encoding.Raw,
            serialization.PublicFormat.Raw,
        ).hex()
        self.review_signature = f"ed25519:{pub_hex}:{sig_bytes.hex()}"

    def to_dict(self) -> dict:
        return {
            "review_version": self.review_version,
            "reviewed_by": self.reviewed_by,
            "reviewed_at": self.reviewed_at,
            "reviews": self.reviews,
            "review_signature": self.review_signature,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: dict) -> "ReviewRecord":
        r = cls(
            reviewed_by=data["reviewed_by"],
            reviews=data["reviews"],
            reviewed_at=data.get("reviewed_at"),
        )
        r.review_signature = data.get("review_signature")
        return r


def add_review_to_artifact(epi_path: Path, review: ReviewRecord) -> None:
    """
    Append review.json to an existing .epi artifact.

    Uses ZIP append mode — the original files are untouched.
    The manifest is NOT modified, preserving the original seal.

    Args:
        epi_path: Path to the .epi file.
        review:   Signed ReviewRecord to embed.

    Raises:
        FileNotFoundError: if epi_path doesn't exist.
        ValueError: if epi_path is not a valid ZIP.
    """
    import os
    import tempfile
    import zipfile

    if not epi_path.exists():
        raise FileNotFoundError(f"Artifact not found: {epi_path}")
    if not zipfile.is_zipfile(epi_path):
        raise ValueError(f"Not a valid .epi file: {epi_path}")

    fd, temp_name = tempfile.mkstemp(
        prefix=f"{epi_path.stem}_review_",
        suffix=epi_path.suffix,
        dir=str(epi_path.parent),
    )
    os.close(fd)
    temp_path = Path(temp_name)

    try:
        with zipfile.ZipFile(epi_path, "r") as src, zipfile.ZipFile(temp_path, "w") as dst:
            for item in src.infolist():
                if item.filename == "review.json":
                    continue
                dst.writestr(item, src.read(item.filename))

            dst.writestr("review.json", review.to_json(), compress_type=zipfile.ZIP_DEFLATED)

        temp_path.replace(epi_path)
    finally:
        temp_path.unlink(missing_ok=True)


def read_review(epi_path: Path) -> Optional[ReviewRecord]:
    """
    Read review.json from a .epi artifact, or return None if not present.
    """
    import zipfile

    if not epi_path.exists() or not zipfile.is_zipfile(epi_path):
        return None

    with zipfile.ZipFile(epi_path, "r") as zf:
        review_entries = [info for info in zf.infolist() if info.filename == "review.json"]
        if not review_entries:
            return None
        try:
            latest_review = review_entries[-1]
            data = json.loads(zf.read(latest_review).decode("utf-8"))
            return ReviewRecord.from_dict(data)
        except Exception:
            return None


def make_review_entry(
    fault: dict,
    outcome: str,
    notes: str,
    reviewer: str,
) -> dict:
    """
    Build a single review entry dict for inclusion in ReviewRecord.reviews.

    Args:
        fault:   The fault dict from analysis.json (primary_fault or secondary_flags item).
        outcome: One of "confirmed_fault", "dismissed", "skipped".
        notes:   Free-text reviewer notes.
        reviewer: Reviewer identity string (email or name).
    """
    return {
        "fault_step": fault.get("step_number"),
        "rule_id": fault.get("rule_id"),
        "fault_type": fault.get("fault_type"),
        "outcome": outcome,
        "notes": notes,
        "reviewer": reviewer,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
