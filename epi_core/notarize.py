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


def _build_rfc3161_query(digest_bytes: bytes) -> bytes:
    """Build a DER-encoded RFC 3161 TimeStampReq (pure Python, no OpenSSL CLI needed).

    Structure (no nonce, no certReq):
      TimeStampReq ::= SEQUENCE {
          version         INTEGER { v1(1) },
          messageImprint  MessageImprint,
      }
    """
    # SHA-256 OID = 2.16.840.1.101.3.4.2.1
    sha256_oid = bytes.fromhex("0609608648016503040201")
    null_param = bytes.fromhex("0500")
    # AlgorithmIdentifier = SEQUENCE { algorithm OID, parameters NULL }
    # content bytes: 11 (oid) + 2 (null) = 13 bytes = 0x0D
    alg_id = bytes([0x30, 0x0D]) + sha256_oid + null_param  # 15 bytes total

    # OCTET STRING wrapping 32-byte digest
    octet_str = bytes([0x04, 0x20]) + digest_bytes  # 34 bytes total

    # MessageImprint = SEQUENCE { hashAlgorithm AlgorithmIdentifier, hashedMessage OCTET STRING }
    # content: algId(15) + octetStr(34) = 49 bytes = 0x31
    msg_imprint = bytes([0x30, 0x31]) + alg_id + octet_str  # 51 bytes total

    # INTEGER version = 1
    version = bytes.fromhex("020101")  # 3 bytes

    # TimeStampReq = SEQUENCE { version, messageImprint }
    # content: version(3) + msgImprint(51) = 54 bytes = 0x36
    return bytes([0x30, 0x36]) + version + msg_imprint  # 56 bytes total


def _parse_tsr_gen_time(token: bytes | None) -> str | None:
    """Best-effort parse of TSTInfo.genTime from a RFC 3161 TimeStampResp.

    Handles GeneralizedTime (0x18) and UTCTime (0x17), fractional seconds,
    and trailing Z / ±HHMM / ±HH:MM offsets. Returns UTC ISO-8601
    (YYYY-MM-DDTHH:MM:SSZ) or None when unparseable.
    """
    if not token:
        return None
    import re
    from datetime import datetime, timedelta, timezone

    # UTCTime: YYMMDDHHMMSSZ (13) with optional fractions/TZ; GeneralizedTime:
    # YYYYMMDDHHMMSS with optional fractions/TZ (15+).
    patterns = [
        # GeneralizedTime with fractions + TZ
        r"(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})(?:\.(\d+))?(Z|[+-]\d{2}:?\d{2})?",
        # UTCTime with fractions + TZ
        r"(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})(?:\.(\d+))?(Z|[+-]\d{2}:?\d{2})?",
    ]
    i = 0
    while i < len(token) - 2:
        tag = token[i]
        if tag in (0x17, 0x18):
            length = token[i + 1]
            # Long-form length (rare in TSRs but handle it)
            hdr = 2
            if length & 0x80:
                n = length & 0x7F
                if n == 0 or n > 2 or i + 2 + n > len(token):
                    i += 1
                    continue
                length = int.from_bytes(token[i + 2 : i + 2 + n], "big")
                hdr = 2 + n
            if 11 <= length <= 32 and i + hdr + length <= len(token):
                try:
                    text = token[i + hdr : i + hdr + length].decode("ascii")
                except UnicodeDecodeError:
                    i += 1
                    continue
                text = text.strip()
                m = re.fullmatch(patterns[0], text) if tag == 0x18 else re.fullmatch(patterns[1], text)
                if m:
                    try:
                        if tag == 0x18:
                            y, mo, d, h, mi, s, _frac, tz = m.groups()
                            dt = datetime(int(y), int(mo), int(d), int(h), int(mi), int(s))
                        else:
                            yy, mo, d, h, mi, s, _frac, tz = m.groups()
                            year = int(yy)
                            year += 2000 if year < 50 else 1900
                            dt = datetime(year, int(mo), int(d), int(h), int(mi), int(s))
                        if tz and tz != "Z":
                            sign = 1 if tz[0] == "+" else -1
                            digits = tz[1:].replace(":", "")
                            off_h = int(digits[:2])
                            off_m = int(digits[2:4]) if len(digits) >= 4 else 0
                            dt = dt - sign * timedelta(hours=off_h, minutes=off_m)
                        dt = dt.replace(tzinfo=timezone.utc)
                        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
                    except ValueError:
                        pass
        i += 1
    return None


def _submit_rfc3161(digest_hex: str, tsa_url: str = DEFAULT_TSA_URL) -> Optional[bytes]:
    """
    Submit a SHA-256 digest to a Time Stamp Authority and return the .tsr token.

    Pure Python implementation — builds the DER-encoded TimeStampReq directly.
    No external CLI dependency.
    Returns None if timestamping is unavailable.
    """
    try:
        digest_bytes = bytes.fromhex(digest_hex)
        if len(digest_bytes) != 32:
            raise ValueError("SHA-256 digest must be 32 bytes")
    except (ValueError, TypeError):
        return None

    # Build the RFC 3161 TimeStampReq query
    query_bytes = _build_rfc3161_query(digest_bytes)

    # POST query to TSA, get reply
    try:
        resp = httpx.post(
            tsa_url,
            content=query_bytes,
            headers={"Content-Type": "application/timestamp-query"},
            timeout=30.0,
        )
        resp.raise_for_status()
    except (httpx.HTTPError, OSError):
        return None

    # Basic sanity: response should be DER-encoded PKCS#7 SignedData
    token = resp.content
    if len(token) < 10 or token[0] != 0x30:
        return None

    return token


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
            digest_path = Path(td) / "digest"

            # Write digest bytes to file for ots stamp
            digest_path.write_bytes(digest_bytes)

            # Create timestamp
            subprocess.run(
                ["ots", "stamp", str(digest_path)],
                check=True,
                capture_output=True,
                timeout=30,
            )

            ots_path = digest_path.with_suffix(".ots")

            # Upgrade the proof — this contacts Bitcoin calendars
            subprocess.run(
                ["ots", "upgrade", str(ots_path)],
                check=True,
                capture_output=True,
                timeout=60,
            )

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
        "tsa_genTime": _parse_tsr_gen_time(result.tsa_token),
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
