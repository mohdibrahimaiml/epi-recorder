"""
audit_payload.py — Verify payload hash integrity of a .epi file.

Uses EPIContainer public APIs for manifest/header parsing (no hardcoded binary
offsets) and computes the SHA-256 digest via chunked streaming reads to avoid
loading the entire ZIP payload into RAM.

Usage:
    python audit_payload.py <path-to-file.epi>
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

from epi_core.container import EPIContainer

_CHUNK_SIZE = 64 * 1024  # 64 KB per read; keeps memory usage flat on large files


def _stream_sha256(path: Path, offset: int = 0) -> str:
    """Return the hex SHA-256 of the file contents starting at *offset*.

    Reading is done in :data:`_CHUNK_SIZE` chunks so that multi-GB `.epi` files
    do not cause memory spikes.
    """
    h = hashlib.sha256()
    with path.open("rb") as fh:
        if offset:
            fh.seek(offset)
        while True:
            chunk = fh.read(_CHUNK_SIZE)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def main(epi_path: Path) -> int:
    if not epi_path.exists():
        print(f"[ERROR] File not found: {epi_path}", file=sys.stderr)
        return 1

    # ── 1. Read the manifest using the public EPIContainer API ──────────────
    # This correctly handles all supported envelope versions (EPI1, EPI2,
    # HTML+ZIP polyglot, etc.) without hardcoding binary header offsets.
    try:
        manifest = EPIContainer.read_manifest(epi_path)
    except Exception as exc:  # noqa: BLE001
        print(f"[ERROR] Could not read manifest: {exc}", file=sys.stderr)
        return 1

    manifest_payload_hash: str | None = None
    trust_block = getattr(manifest, "trust", None)
    if isinstance(trust_block, dict):
        manifest_payload_hash = trust_block.get("payload_hash")
    elif trust_block is not None:
        # Pydantic model — access attribute directly if present
        manifest_payload_hash = getattr(trust_block, "payload_hash", None)

    print(f"Manifest payload_hash:  {manifest_payload_hash or '(not present)'}")

    # ── 2. Determine how many bytes to skip (envelope header) ───────────────
    # EPIContainer exposes the raw envelope header length so we don't have to
    # re-implement the offset arithmetic here.  Fallback to 0 if unavailable.
    try:
        header_size: int = EPIContainer.envelope_header_size(epi_path)  # type: ignore[attr-defined]
    except AttributeError:
        # Older builds without envelope_header_size — probe for the payload
        # start via the container reader instead of a hardcoded header size.
        # (A previous revision assumed 38 bytes here; no writer, test, or spec
        # supports that layout, so it is not trusted.)
        with epi_path.open("rb") as fh:
            magic = fh.read(4)
        if magic == b"EPI1":
            probed = EPIContainer.legacy_zip_offset(epi_path)
            if probed is None:
                print("[ERROR] EPI1 magic but no ZIP payload found after header.")
                return 1
            header_size = probed
        elif magic == b"EPI2":
            probed = EPIContainer.legacy_zip_offset(epi_path)
            header_size = probed if probed is not None else 0
        else:
            header_size = 0
            print("[WARN] Unknown magic bytes — hashing entire file content.")

    # ── 3. Stream-hash the payload (everything after the header) ────────────
    actual_hash = _stream_sha256(epi_path, offset=header_size)

    print(f"Actual payload SHA-256: {actual_hash}")

    # ── 4. Compare ──────────────────────────────────────────────────────────
    if manifest_payload_hash is None:
        print("[INFO] No payload_hash in manifest; skipping comparison.")
        return 0

    if actual_hash == manifest_payload_hash:
        print("[OK] Payload hash matches manifest — file integrity confirmed.")
        return 0
    else:
        print(
            "[FAIL] Payload hash MISMATCH — the ZIP payload was modified after "
            "sealing, or the envelope header and manifest are out of sync."
        )
        return 1


if __name__ == "__main__":
    if len(sys.argv) < 2:
        epi_path = Path("refund_case.epi")
    else:
        epi_path = Path(sys.argv[1])
    sys.exit(main(epi_path))
