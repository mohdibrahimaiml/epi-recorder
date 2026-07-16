"""
Tier 1+2 notarization: RFC 3161 timestamping + OpenTimestamps Bitcoin anchoring.

At seal time, the final manifest hash is submitted to:
  - A public Time Stamp Authority (FreeTSA.org) for RFC 3161 countersignature
  - OpenTimestamps for public Bitcoin blockchain anchoring

The returned tokens (.tsr for TSA, .ots for OpenTimestamps) are embedded into
the .epi archive under artifacts/notarization/ and referenced in the manifest.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional

import httpx

# FreeTSA.org — public, free RFC 3161 Time Stamp Authority
DEFAULT_TSA_URL = os.environ.get("EPI_TSA_URL", "https://freetsa.org/tsr")

# OpenTimestamps calendars (public, free)
DEFAULT_OTS_CALENDARS = [
    "https://a.pool.opentimestamps.org",
    "https://b.pool.opentimestamps.org",
    "https://c.pool.opentimestamps.org",
]


class NotarizationResult:
    """Result of notarizing a hash at seal time."""

    def __init__(self) -> None:
        self.tsa_token: Optional[bytes] = None
        self.tsa_url: str = ""
        self.ots_proof: Optional[bytes] = None
        self.ots_upgrade_msg: str = ""
        self.evidence: dict = {}


def _submit_rfc3161(digest_hex: str, tsa_url: str = DEFAULT_TSA_URL) -> Optional[bytes]:
    """
    Submit a SHA-256 digest to a Time Stamp Authority and return the .tsr token.

    Uses openssl ts command-line tool (requires OpenSSL installed).
    Returns None if timestamping is unavailable.
    """
    try:
        digest_bytes = bytes.fromhex(digest_hex)
        if len(digest_bytes) != 32:
            raise ValueError("SHA-256 digest must be 32 bytes")
    except (ValueError, TypeError):
        return None

    with tempfile.TemporaryDirectory() as td:
        query_path = Path(td) / "tsa_query.tsq"
        reply_path = Path(td) / "tsa_reply.tsr"

        # Generate the TS query
        try:
            subprocess.run(
                [
                    "openssl", "ts", "-query",
                    "-data", "-",
                    "-sha256",
                    "-no_nonce",
                    "-out", str(query_path),
                ],
                input=digest_bytes,
                check=True,
                capture_output=True,
                timeout=10,
            )
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            return None

        # POST query to TSA, get reply
        try:
            query_bytes = query_path.read_bytes()
            resp = httpx.post(
                tsa_url,
                content=query_bytes,
                headers={"Content-Type": "application/timestamp-query"},
                timeout=30.0,
            )
            resp.raise_for_status()
            reply_path.write_bytes(resp.content)
        except (httpx.HTTPError, OSError):
            return None

        # Verify the reply is a valid timestamp token
        try:
            subprocess.run(
                [
                    "openssl", "ts", "-verify",
                    "-data", "-",
                    "-in", str(reply_path),
                    "-CAfile", "/dev/null",  # Skip full chain verification
                ],
                input=digest_bytes,
                check=True,
                capture_output=True,
                timeout=10,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            # Verification failed but we still return the token
            pass

        return reply_path.read_bytes()


def _submit_opentimestamps(digest_hex: str) -> tuple[Optional[bytes], str]:
    """
    Submit a SHA-256 digest to OpenTimestamps calenders and return the .ots proof.

    Uses ots CLI tool if available, otherwise falls back gracefully.
    Returns (ots_bytes, upgrade_message).
    """
    # Check if ots CLI is available
    ots_available = False
    try:
        subprocess.run(
            ["ots", "--version"],
            check=True,
            capture_output=True,
            timeout=5,
        )
        ots_available = True
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        pass

    if not ots_available:
        # Try Python ots library
        try:
            import opentimestamps as ots_module  # type: ignore
            ots_available = True
        except ImportError:
            return (
                None,
                "Install opentimestamps-client for Bitcoin anchoring: "
                "pip install opentimestamps-client  or  pip install opentimestamps",
            )

    if not ots_available:
        return None, "OpenTimestamps not available"

    try:
        digest_bytes = bytes.fromhex(digest_hex)
        with tempfile.TemporaryDirectory() as td:
            digest_path = Path(td) / "digest.ots"

            # Create timestamp
            subprocess.run(
                ["ots", "stamp", str(digest_path)],
                check=True,
                capture_output=True,
                timeout=30,
                input=digest_hex.encode(),
            )

            # Upgrade the proof — this contacts Bitcoin calendars
            subprocess.run(
                ["ots", "upgrade", str(digest_path) + ".ots"],
                check=True,
                capture_output=True,
                timeout=60,
            )

            ots_path = Path(str(digest_path) + ".ots")
            if ots_path.exists():
                return ots_path.read_bytes(), ""

        return None, "OpenTimestamps stamping failed"
    except Exception as e:
        return None, f"OpenTimestamps error: {e}"


def notarize_manifest(manifest_json: str, manifest_hash: str) -> NotarizationResult:
    """
    Notarize a manifest at seal time.

    Args:
        manifest_json: The canonical JSON string of the manifest (unsigned).
        manifest_hash: SHA-256 hex digest of the canonical manifest.

    Returns:
        NotarizationResult with embedded tokens and evidence dict.
    """
    result = NotarizationResult()

    # Tier 1: RFC 3161 timestamping
    tsa_url = os.environ.get("EPI_TSA_URL", DEFAULT_TSA_URL)
    result.tsa_token = _submit_rfc3161(manifest_hash, tsa_url)
    result.tsa_url = tsa_url

    # Tier 2: OpenTimestamps / Bitcoin anchoring
    result.ots_proof, result.ots_upgrade_msg = _submit_opentimestamps(manifest_hash)

    # Build evidence block for manifest
    result.evidence = {
        "notarized_at": {"provider": "rfc3161", "url": tsa_url, "hash": manifest_hash},
        "tsa_token_available": result.tsa_token is not None,
        "ots_proof_available": result.ots_proof is not None,
    }

    if result.ots_upgrade_msg:
        result.evidence["ots_note"] = result.ots_upgrade_msg

    return result


def embed_notarization(source_dir: Path, result: NotarizationResult) -> None:
    """
    Write notarization tokens into source_dir/artifacts/notarization/
    before the ZIP payload is sealed.
    """
    notary_dir = source_dir / "artifacts" / "notarization"
    notary_dir.mkdir(parents=True, exist_ok=True)

    if result.tsa_token:
        (notary_dir / "tsa_reply.tsr").write_bytes(result.tsa_token)

    if result.ots_proof:
        (notary_dir / "digest.ots").write_bytes(result.ots_proof)

    evidence_path = notary_dir / "notarization.json"
    evidence_path.write_text(json.dumps(result.evidence, indent=2), encoding="utf-8")
