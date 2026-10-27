"""
Human approver registry and approver-held keys (step 3a).

Who counts as a *human approver* is a decision the verifier makes locally, kept
in its own directory. It is separate by construction from the trusted *signer*
keys in :mod:`epi_core.trust`: pinning a vendor's sealing key must never make
that key an approver. An approval is reported as human-signed only when the key
that signed it is pinned here **and** differs from the key that sealed the run.

Fingerprints use :func:`epi_core.keys.key_fingerprint` only (SHA-256 over the
lowercase hex key text), never a raw-bytes variant.
"""

from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from epi_core.keys import key_fingerprint

APPROVER_VERSION = "1.0.0"
APPROVER_ROLE = "approver"

_SLUG_RE = re.compile(r"[^A-Za-z0-9._-]+")


def _resolve_default_approvers_dir() -> Path:
    """Directory of pinned approver public keys.

    Precedence: ``EPI_TRUSTED_APPROVERS_DIR`` else ``~/.epi/trusted_approvers``.
    Mirrors how :class:`epi_core.trust.TrustRegistry` resolves
    ``EPI_TRUSTED_KEYS_DIR``.
    """
    env_dir = os.environ.get("EPI_TRUSTED_APPROVERS_DIR")
    if env_dir:
        return Path(env_dir).expanduser()
    return Path.home() / ".epi" / "trusted_approvers"


def _resolve_default_approver_keys_dir() -> Path:
    """Directory of approver-held private keys (never the agent keys dir).

    Precedence: ``EPI_APPROVER_KEYS_DIR`` else ``~/.epi/approver_keys``.
    """
    env_dir = os.environ.get("EPI_APPROVER_KEYS_DIR")
    return Path(env_dir).expanduser() if env_dir else (Path.home() / ".epi" / "approver_keys")


def _slug(value: str) -> str:
    """Restrict an approver name to a safe file stem (no path traversal)."""
    token = _SLUG_RE.sub("-", str(value or "").strip())
    token = token.strip("-.")
    if not token or token in (".", ".."):
        raise ValueError(f"Approver name is not usable as a file name: {value!r}")
    return token


def normalize_fingerprint(value: Any) -> str:
    """Whitespace- and case-insensitive fingerprint form for comparison."""
    return "".join(str(value or "").split()).lower()


class ApproverRegistry:
    """One JSON file per approver under ``approvers_dir``."""

    def __init__(self, approvers_dir: Path | None = None):
        self.approvers_dir = (
            Path(approvers_dir) if approvers_dir else _resolve_default_approvers_dir()
        )

    def _path_for(self, name: str) -> Path:
        return self.approvers_dir / f"{_slug(name)}.json"

    def load(self, name: str) -> dict[str, Any] | None:
        path = self._path_for(name)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
        return payload if isinstance(payload, dict) else None

    def list(self) -> list[dict[str, Any]]:
        """All approvers, sorted by name. Unreadable files are skipped."""
        if not self.approvers_dir.exists():
            return []
        entries: list[dict[str, Any]] = []
        for path in sorted(self.approvers_dir.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if isinstance(payload, dict) and payload.get("name"):
                entries.append(payload)
        return sorted(entries, key=lambda item: str(item.get("name", "")))

    def add(
        self,
        name: str,
        public_key_hex: str,
        *,
        roles: list[str] | None = None,
        overwrite: bool = False,
    ) -> Path:
        """Pin *public_key_hex* under *name*. Refuses a name holding a different key."""
        key_hex = str(public_key_hex or "").strip().lower()
        if len(key_hex) != 64:
            raise ValueError(f"Approver public key must be 64 hex chars (got {len(key_hex)})")
        path = self._path_for(name)
        if path.exists() and not overwrite:
            existing = self.load(name) or {}
            if str(existing.get("public_key", "")).strip().lower() != key_hex:
                raise FileExistsError(
                    f"Approver '{name}' is already pinned to a different key. "
                    "Use --overwrite to replace it."
                )
        self.approvers_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "approver_version": APPROVER_VERSION,
            "name": str(name),
            "public_key": key_hex,
            "key_fingerprint": key_fingerprint(key_hex, grouped=False),
            "roles": list(roles or [APPROVER_ROLE]),
            "added_at": _utc_now(),
        }
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return path

    def remove(self, name: str) -> bool:
        path = self._path_for(name)
        if not path.exists():
            return False
        path.unlink()
        return True

    def get_by_key(self, public_key_hex: str) -> dict[str, Any] | None:
        want = "".join(str(public_key_hex or "").split()).lower()
        if len(want) != 64:
            return None
        for entry in self.list():
            if str(entry.get("public_key", "")).strip().lower() == want:
                return entry
        return None

    def name_for_key(self, public_key_hex: str) -> str | None:
        entry = self.get_by_key(public_key_hex)
        return str(entry["name"]) if entry else None

    def is_approver(self, public_key_hex: str) -> bool:
        return self.get_by_key(public_key_hex) is not None


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def reserved_key_reason(public_key_hex: str) -> str | None:
    """Why *public_key_hex* must not be pinned as an approver, or ``None``.

    An approver key held by the agent host proves nothing about a person, so a
    key that is a local agent key, or already pinned as a trusted *signer*, is
    refused (``epi approvers add`` overridable only with ``--force``).
    """
    key_hex = str(public_key_hex or "").strip().lower()
    if len(key_hex) != 64:
        return None
    try:
        from epi_core.trust import _match_local_signing_key_name

        local_name = _match_local_signing_key_name(key_hex)
        if local_name:
            return f"it is a key in the local agent keys directory (key '{local_name}')"
    except Exception:
        pass
    try:
        from epi_core.trust import TrustRegistry

        if TrustRegistry()._is_locally_pinned(key_hex):
            return "it is already pinned as a trusted signer (epi keys trust)"
    except Exception:
        pass
    return None
