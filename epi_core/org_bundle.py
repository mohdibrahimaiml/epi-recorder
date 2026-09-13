"""
Org trust bundles — customer-signed key history for offline verification.

A bundle answers, for an auditor holding only (artifact, bundle file):
  1. did this artifact come from that company?  (envelope signature by the
     customer root named in the artifact's own manifest.governance.org_root)
  2. was the sealing key legitimately the company's key at sealing time?
     (validity windows evaluated at T_seal, never retroactively revoked)

Spec: docs/design/org-trust-bundle.md. v0 implements bundle schema,
issuance, and verification steps 1-6. No revocation workflow, no SCITT
anchoring, no network — anywhere in this module. A function here that
needs a socket is a bug.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ORG_BUNDLE_FORMAT = "epi-org-bundle-v1"


# ---------------------------------------------------------------------------
# Canonical bytes (same JCS discipline as manifest hashing)
# ---------------------------------------------------------------------------

def _canonical_bytes(body: dict) -> bytes:
    try:
        import rfc8785  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "rfc8785 is required for canonical JSON hashing. "
            "Reinstall with `pip install rfc8785>=0.1.4` or `pip install -e .`."
        ) from exc
    return rfc8785.dumps(body)


def fingerprint_pubkey(public_key_hex: str) -> str:
    """SHA-256 fingerprint (hex) of a 32-byte Ed25519 public key."""
    return hashlib.sha256(bytes.fromhex(public_key_hex.strip().lower())).hexdigest()


def _parse_time(value: str, field: str) -> datetime:
    try:
        text = str(value).strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
    except Exception as exc:
        raise ValueError(f"Bundle time field '{field}' is not ISO-8601: {value!r}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _validate_key_entry(entry: dict, index: int) -> dict:
    if not isinstance(entry, dict):
        raise ValueError(f"Bundle key entry {index} must be an object")
    key_id = entry.get("key_id")
    public_key = entry.get("public_key")
    not_before = entry.get("not_before")
    if not key_id or not isinstance(key_id, str):
        raise ValueError(f"Bundle key entry {index} is missing 'key_id'")
    if not public_key or not isinstance(public_key, str):
        raise ValueError(f"Bundle key '{key_id}' is missing 'public_key'")
    try:
        raw = bytes.fromhex(public_key.strip().lower())
    except ValueError as exc:
        raise ValueError(f"Bundle key '{key_id}' public_key is not hex") from exc
    if len(raw) != 32:
        raise ValueError(f"Bundle key '{key_id}' must be 32-byte Ed25519, got {len(raw)}")
    if not not_before:
        raise ValueError(f"Bundle key '{key_id}' is missing 'not_before'")
    _parse_time(not_before, f"keys[{index}].not_before")
    for field in ("not_after", "revoked_at"):
        if entry.get(field) is not None:
            _parse_time(entry[field], f"keys[{index}].{field}")
    status = entry.get("status", "active")
    if not isinstance(status, str):
        raise ValueError(f"Bundle key '{key_id}' status must be a string")
    return {
        "key_id": key_id,
        "public_key": public_key.strip().lower(),
        "not_before": not_before,
        "not_after": entry.get("not_after"),
        "status": status,
        "role": entry.get("role", "sealing"),
        **({"revoked_at": entry["revoked_at"]} if entry.get("revoked_at") else {}),
        **({"revocation_reason": entry["revocation_reason"]} if entry.get("revocation_reason") else {}),
    }


# ---------------------------------------------------------------------------
# Issuance (customer root key required — we never generate or hold it)
# ---------------------------------------------------------------------------

def issue_bundle(
    *,
    bundle_id: str,
    keys: list[dict],
    root_private_key: Any,
    root_public_hex: str,
    version: int = 1,
    issued_at: str | None = None,
) -> dict:
    """Build and customer-sign an org trust bundle (v0).

    Args:
        bundle_id: Stable org identifier (e.g. "acme-corp").
        keys: Key entries with key_id/public_key/not_before (+ optional
            not_after/status/role/revoked_at/revocation_reason).
        root_private_key: Customer's Ed25519 root private key object
            (cryptography Ed25519PrivateKey). Never leaves the caller.
        root_public_hex: Matching root public key (64 hex).
        version: Strictly increasing per bundle_id (caller enforces by
            reading the previous bundle file).
        issued_at: ISO-8601 UTC; defaults to now.
    """
    if not bundle_id or not isinstance(bundle_id, str):
        raise ValueError("bundle_id must be a non-empty string")
    if not isinstance(version, int) or version < 1:
        raise ValueError("version must be a positive integer")
    root_public_hex = root_public_hex.strip().lower()
    if len(root_public_hex) != 64:
        raise ValueError("root_public_hex must be 64 hex chars")
    try:
        root_private_key.public_key()
    except Exception as exc:
        raise ValueError("root_private_key is not a usable Ed25519 private key") from exc

    body = {
        "format": ORG_BUNDLE_FORMAT,
        "bundle_id": bundle_id,
        "version": version,
        "issued_at": issued_at or _utcnow_iso(),
        "issuer_root_fingerprint": fingerprint_pubkey(root_public_hex),
        "root_public_key": root_public_hex,
        "keys": [_validate_key_entry(entry, i) for i, entry in enumerate(keys or [])],
    }
    _parse_time(body["issued_at"], "issued_at")

    digest = hashlib.sha256(_canonical_bytes(body)).digest()
    signature_hex = root_private_key.sign(digest).hex()
    derived = hashlib.sha256(root_public_hex.encode("utf-8")).hexdigest()[:16]
    return {
        **body,
        "signatures": [
            {"key_id": "root", "signature": f"ed25519:{derived}:{signature_hex}"}
        ],
    }


def save_bundle(bundle: dict, path: Path | str) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(bundle, indent=2) + "\n", encoding="utf-8")
    return path


def load_bundle(path: Path | str) -> dict:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Org bundle not found: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValueError(f"Org bundle is not valid JSON: {path} ({exc})") from exc
    if not isinstance(data, dict):
        raise ValueError(f"Org bundle must be a JSON object: {path}")
    return data


# ---------------------------------------------------------------------------
# Verification, steps 2-6 of the design (§5). Offline by construction.
# ---------------------------------------------------------------------------

def _verify_envelope_signature(bundle: dict) -> tuple[bool, bytes, str]:
    """Check the bundle envelope signature. Returns (ok, root_pub_bytes, msg)."""
    signatures = bundle.get("signatures") or []
    if not signatures or not isinstance(signatures, list):
        return False, b"", "Bundle has no signatures"
    sig_entry = signatures[0]
    if not isinstance(sig_entry, dict):
        return False, b"", "Bundle signature entry malformed"
    root_public_hex = bundle.get("root_public_key", "")
    try:
        root_pub = bytes.fromhex(str(root_public_hex).strip().lower())
    except ValueError:
        return False, b"", "Bundle root_public_key is not hex"
    if len(root_pub) != 32:
        return False, b"", "Bundle root_public_key must be 32 bytes"
    raw_sig = str(sig_entry.get("signature") or "")
    parts = raw_sig.split(":")
    signature_hex = parts[-1] if parts else ""
    try:
        signature_bytes = bytes.fromhex(signature_hex)
    except ValueError:
        return False, b"", "Bundle signature is not hex"
    if len(signature_bytes) != 64:
        return False, b"", "Bundle signature must be 64 bytes"
    body = {k: v for k, v in bundle.items() if k != "signatures"}
    digest = hashlib.sha256(_canonical_bytes(body)).digest()
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        from cryptography.exceptions import InvalidSignature

        Ed25519PublicKey.from_public_bytes(root_pub).verify(signature_bytes, digest)
    except InvalidSignature:
        return False, b"", "Bundle envelope signature invalid"
    except Exception as exc:
        return False, b"", f"Bundle signature verification error: {exc}"
    return True, root_pub, "Bundle envelope signature valid"


def verify_artifact_against_bundle(manifest: Any, bundle: dict) -> dict:
    """Validate an artifact's org identity against a bundle (design §5.2-6).

    Args:
        manifest: ManifestModel (or dict with the same fields) carrying
            governance.org_root and created_at.
        bundle: Parsed org bundle dict.

    Returns a report dict with status VALID | INVALID | UNKNOWN. UNKNOWN
    means "cannot decide from these inputs" — never a guess, never valid.
    No network, no env, no local key dirs are touched.
    """
    if not isinstance(bundle, dict) or bundle.get("format") != ORG_BUNDLE_FORMAT:
        return {"status": "INVALID", "reason": "Not an epi-org-bundle-v1 bundle"}

    governance = getattr(manifest, "governance", None) or {}
    if isinstance(manifest, dict):
        governance = manifest.get("governance") or {}
    org_root = (governance.get("org_root") or "").strip().lower() if isinstance(governance, dict) else ""
    if not org_root:
        return {"status": "UNKNOWN", "reason": "Artifact names no org root (governance.org_root absent)"}

    created_at = getattr(manifest, "created_at", None)
    if isinstance(manifest, dict):
        created_at = manifest.get("created_at")
    if isinstance(created_at, str):
        try:
            t_seal = _parse_time(created_at, "manifest.created_at")
        except ValueError as exc:
            return {"status": "INVALID", "reason": str(exc)}
    elif isinstance(created_at, datetime):
        t_seal = created_at.astimezone(timezone.utc) if created_at.tzinfo else created_at.replace(tzinfo=timezone.utc)
    else:
        return {"status": "INVALID", "reason": "Artifact has no usable created_at"}

    sig_ok, root_pub, sig_msg = _verify_envelope_signature(bundle)
    if not sig_ok:
        return {"status": "INVALID", "reason": sig_msg}
    if fingerprint_pubkey(root_pub.hex()) != org_root:
        return {
            "status": "INVALID",
            "reason": "Bundle is signed by a different root than the artifact names",
        }

    try:
        issued_at = _parse_time(bundle.get("issued_at", ""), "bundle.issued_at")
    except ValueError as exc:
        return {"status": "INVALID", "reason": str(exc)}
    if issued_at < t_seal:
        return {
            "status": "UNKNOWN",
            "reason": f"Bundle v{bundle.get('version')} issued {bundle.get('issued_at')} predates artifact sealed {t_seal.isoformat()}; keys added after issue are invisible",
        }

    manifest_pub = (getattr(manifest, "public_key", None) or "").strip().lower()
    if isinstance(manifest, dict):
        manifest_pub = str(manifest.get("public_key") or "").strip().lower()
    match = None
    for entry in bundle.get("keys") or []:
        if not isinstance(entry, dict):
            continue
        if str(entry.get("public_key") or "").strip().lower() == manifest_pub and manifest_pub:
            match = entry
            break
    if match is None:
        return {"status": "UNKNOWN", "reason": "Sealing key not present in bundle (stale bundle or foreign key)"}
    if str(match.get("status", "active")) != "active":
        return {
            "status": "UNKNOWN",
            "reason": f"Key '{match.get('key_id')}' has status '{match.get('status')}' — non-active keys require a v1 verifier",
        }

    try:
        not_before = _parse_time(match["not_before"], "key.not_before")
    except ValueError as exc:
        return {"status": "INVALID", "reason": str(exc)}
    window_end = None
    for field in ("revoked_at", "not_after"):
        if match.get(field):
            try:
                end = _parse_time(match[field], f"key.{field}")
            except ValueError as exc:
                return {"status": "INVALID", "reason": str(exc)}
            window_end = end if window_end is None else min(window_end, end)
    if t_seal < not_before:
        return {
            "status": "INVALID",
            "reason": f"Artifact sealed {t_seal.isoformat()} before key '{match.get('key_id')}' validity starts {match['not_before']}",
        }
    if window_end is not None and not (t_seal < window_end):
        return {
            "status": "INVALID",
            "reason": f"Artifact sealed {t_seal.isoformat()} after key '{match.get('key_id')}' validity ended",
        }

    try:
        from epi_core.trust import verify_signature

        valid, message = verify_signature(manifest, bytes.fromhex(manifest_pub))
    except Exception as exc:
        return {"status": "INVALID", "reason": f"Signature check error: {exc}"}
    if not valid:
        return {"status": "INVALID", "reason": f"Manifest signature invalid against bundle key: {message}"}

    return {
        "status": "VALID",
        "reason": f"Sealing key '{match.get('key_id')}' was valid at sealing time; manifest signature verifies",
        "key_id": match.get("key_id"),
        "bundle_version": bundle.get("version"),
        "bundle_id": bundle.get("bundle_id"),
    }
