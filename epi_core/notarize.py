"""
Tier 1+2 notarization: RFC 3161 timestamping + OpenTimestamps Bitcoin anchoring.

At seal time, the recomputable seal imprint (epi-tsa-imprint/v1: workflow id,
creation time, sealing key, payload file hashes) is submitted to two
independent public Time Stamp Authorities (FreeTSA.org, DigiCert) for RFC 3161
countersignature, and the manifest hash to OpenTimestamps for public Bitcoin
blockchain anchoring.

The returned tokens (.tsr for TSA, .ots for OpenTimestamps) are embedded into
the .epi archive under artifacts/notarization/ and referenced in the manifest.
`epi verify` checks every token offline against pinned TSA roots.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

import httpx

# FreeTSA.org — public, free RFC 3161 Time Stamp Authority
DEFAULT_TSA_URL = os.environ.get("EPI_TSA_URL", "https://freetsa.org/tsr")

# Seal time stamps with two independent TSAs (no single third party).
# EPI_TSA_URLS (comma-separated) overrides the pair; EPI_TSA_URL still works
# as a single-URL override. Checkpoints use the first URL with fallback.
_BUILTIN_TSA_URLS = ("https://freetsa.org/tsr", "http://timestamp.digicert.com")


def _tsa_urls() -> list[str]:
    multi = (os.environ.get("EPI_TSA_URLS") or "").strip()
    if multi:
        return [u.strip() for u in multi.split(",") if u.strip()]
    single = (os.environ.get("EPI_TSA_URL") or "").strip()
    if single:
        return [single]
    return list(_BUILTIN_TSA_URLS)

# OpenTimestamps calendars (public, free)
DEFAULT_OTS_CALENDARS = [
    "https://a.pool.opentimestamps.org",
    "https://b.pool.opentimestamps.org",
    "https://c.pool.opentimestamps.org",
]


class NotarizationResult:
    """Result of notarizing a hash at seal time."""

    def __init__(self) -> None:
        self.tsa_urls_tried: list[str] = []
        self.tsa_token: Optional[bytes] = None
        self.tsa_url: str = ""
        # Additional TSA tokens beyond the first: (member_name, token_bytes).
        self.additional_tsa_tokens: list[tuple[str, bytes]] = []
        # Evidence entries for every token: {"url": ..., "member": ...}.
        self.tsa_tokens: list[dict] = []
        # Seal-imprint binding (epi-tsa-imprint/v1); None when the caller
        # stamped a raw manifest hash (pre-imprint behaviour).
        self.imprint_scheme: Optional[str] = None
        self.imprinted_digest: Optional[str] = None
        self.imprinted_public_key: Optional[str] = None
        self.ots_proof: Optional[bytes] = None
        self.ots_upgrade_msg: str = ""
        self.evidence: dict = {}


# ---------------------------------------------------------------------------
# Seal imprint (epi-tsa-imprint/v1)
#
# The seal-time TSA digest must be recomputable from the FINAL artifact,
# otherwise no verifier can ever check the token. The digest submitted to the
# TSA is therefore NOT the canonical manifest hash (which is computed before
# notarization/VERIFY.txt/viewer.html are added and the manifest re-signed)
# but a hash over the stable core: workflow id, creation time, sealing key,
# and the payload file hashes minus display/notarization members.
# container.py computes this at the notarization point, when file_manifest
# holds exactly the payload files the verifier will filter down to.
# ---------------------------------------------------------------------------

IMPRINT_SCHEME = "epi-tsa-imprint/v1"
_IMPRINT_EXCLUDED_EXACT = {"viewer.html", "VERIFY.txt", "manifest.json", "mimetype"}
_IMPRINT_EXCLUDED_PREFIXES = (
    "artifacts/notarization/",
    "artifacts/scitt/",
    "artifacts/transparency/",
)


def filter_imprint_files(file_manifest: dict) -> dict[str, str]:
    """Payload file hashes covered by the seal imprint (both seal and verify sides use this)."""
    return {
        name: digest
        for name, digest in dict(file_manifest or {}).items()
        if name not in _IMPRINT_EXCLUDED_EXACT
        and not any(str(name).startswith(p) for p in _IMPRINT_EXCLUDED_PREFIXES)
    }


def normalize_imprint_time(value) -> str:
    """One canonical creation-time string for seal and verify sides.

    Seal passes a datetime, verify passes the stored JSON string; both flow
    through fromisoformat/isoformat so the imprint input is identical.
    """
    if isinstance(value, datetime):
        return value.isoformat()
    return datetime.fromisoformat(str(value)).isoformat()


def compute_seal_imprint(
    workflow_id: str,
    created_at_iso: str,
    public_key_hex: str | None,
    file_manifest: dict,
) -> str:
    """SHA-256 hex over JCS({scheme, workflow_id, created_at, public_key, files}).

    ``public_key_hex`` is None when the first pack seals before signing (the
    normal record() flow signs on repack); the value used is stored in
    notarization.json as ``imprinted_public_key`` so the verifier recomputes
    with the identical input.
    """
    import rfc8785

    payload = {
        "scheme": IMPRINT_SCHEME,
        "workflow_id": str(workflow_id),
        "created_at": normalize_imprint_time(created_at_iso),
        "public_key": public_key_hex,
        "files": filter_imprint_files(file_manifest),
    }
    return hashlib.sha256(rfc8785.dumps(payload)).hexdigest()


def _build_rfc3161_request(digest_bytes: bytes, *, nonce: int | None = None) -> tuple[bytes, int]:
    """Build a DER TimeStampReq with message imprint, random nonce and certReq.

    cert_req=True means the TSA returns its certificate chain inside the
    token, which offline validation needs. Returns (query_bytes, nonce).
    """
    from asn1crypto import tsp as _tsp

    digest_bytes = bytes(digest_bytes)
    if len(digest_bytes) != 32:
        raise ValueError("SHA-256 digest must be 32 bytes")
    if nonce is None:
        nonce = int.from_bytes(secrets.token_bytes(8), "big")
    req = _tsp.TimeStampReq(
        {
            "version": 1,
            "message_imprint": {
                "hash_algorithm": {"algorithm": "sha256"},
                "hashed_message": digest_bytes,
            },
            "nonce": nonce,
            "cert_req": True,
        }
    )
    return req.dump(), nonce


def _build_rfc3161_query(digest_bytes: bytes) -> bytes:
    """Thin wrapper kept for checkpoints.py: returns the DER query bytes."""
    query, _nonce = _build_rfc3161_request(digest_bytes)
    return query


def _parse_tsr_gen_time(token: bytes | None) -> str | None:
    """Parsed TSTInfo.genTime from a RFC 3161 TimeStampResp (real ASN.1, not byte scanning).

    Returns UTC ISO-8601 (YYYY-MM-DDTHH:MM:SSZ) or None when unparseable.
    Never raises.
    """
    if not token:
        return None
    try:
        from epi_core.tsa_verify import validate_tsr

        validation = validate_tsr(token, b"")
        # Any status still carries the parsed genTime when the token parses;
        # imprint_mismatch is expected here (empty expected digest).
        return validation.gen_time
    except Exception:
        return None


def _response_nonce(token: bytes) -> int | None:
    """Nonce echoed inside a TimeStampResp, or None when unreadable/absent."""
    try:
        from asn1crypto import tsp as _tsp

        tst = _tsp.TimeStampResp.load(token)["time_stamp_token"]["content"][
            "encap_content_info"
        ]["content"].parsed
        nonce = tst["nonce"]
        return int(nonce.native) if nonce is not None else None
    except Exception:
        return None


def _tsa_timeout() -> httpx.Timeout:
    """How long to wait for the time-stamp service. EPI_TSA_TIMEOUT (seconds) overrides the 10 s default;
    the hosted evidence server sets a few seconds so a slow public service can never hold a seal hostage.
    All configured TSAs are asked in parallel, so this is also the worst-case added seal time."""
    try:
        total = float(os.environ.get("EPI_TSA_TIMEOUT") or 10.0)
    except ValueError:
        total = 10.0
    total = max(0.5, total)
    return httpx.Timeout(total, connect=min(total, 5.0))


def _submit_rfc3161(digest_hex: str, tsa_url: str = DEFAULT_TSA_URL) -> Optional[bytes]:
    """
    Submit a SHA-256 digest to a Time Stamp Authority and return the .tsr token.

    Builds the TimeStampReq with a random nonce and certReq, then checks the
    response echoes the sent nonce (a mismatch returns None, recorded as a
    gap exactly like an outage). Returns None if timestamping is unavailable.
    """
    try:
        digest_bytes = bytes.fromhex(digest_hex)
        if len(digest_bytes) != 32:
            raise ValueError("SHA-256 digest must be 32 bytes")
    except (ValueError, TypeError):
        return None

    # Build the RFC 3161 TimeStampReq query (nonce + certReq inside).
    try:
        query_bytes, sent_nonce = _build_rfc3161_request(digest_bytes)
    except (ValueError, TypeError):
        return None

    # POST query to TSA, get reply
    try:
        resp = httpx.post(
            tsa_url,
            content=query_bytes,
            headers={"Content-Type": "application/timestamp-query"},
            timeout=_tsa_timeout(),
        )
        resp.raise_for_status()
    except (httpx.HTTPError, OSError):
        return None

    # Basic sanity: response should be DER-encoded PKCS#7 SignedData
    token = resp.content
    if len(token) < 10 or token[0] != 0x30:
        return None

    # The TSA must echo our nonce; otherwise the reply is not bound to our
    # request. An absent echo is accepted (some TSAs omit it) because the
    # token's imprint and signature are still fully validated offline later.
    echoed = _response_nonce(token)
    if echoed is not None and echoed != sent_nonce:
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


def notarize_manifest(
    manifest_json: str,
    manifest_hash: str,
    *,
    stamp_digest: str | None = None,
    imprinted_public_key: str | None = None,
) -> NotarizationResult:
    """
    Notarize a manifest at seal time.

    Args:
        manifest_json: The canonical JSON string of the manifest (unsigned).
        manifest_hash: SHA-256 hex digest of the canonical manifest.
        stamp_digest: The digest actually submitted to the TSAs. container.py
            passes the recomputable seal imprint (epi-tsa-imprint/v1); when
            omitted the manifest hash is stamped (pre-imprint behaviour, kept
            for compatibility).
        imprinted_public_key: The sealing key recorded in the imprint (None
            when the first pack seals before signing).

    Returns:
        NotarizationResult with embedded tokens and evidence dict.
    """
    result = NotarizationResult()

    # The digest the timestamp binds. The imprint (not the canonical manifest
    # hash) is what a verifier can recompute from the final artifact.
    stamp = stamp_digest or manifest_hash

    # Tier 1: RFC 3161 timestamping — every configured TSA, first success kept
    # at the legacy member name for backward compatibility.
    urls = _tsa_urls()
    stamped: list[tuple[str, bytes]] = []

    def _one(url: str) -> Optional[bytes]:
        try:
            return _submit_rfc3161(stamp, url)
        except Exception:
            return None

    # Ask every TSA at once: a silently dropped connection costs one timeout,
    # not one per TSA. Order of `urls` is kept for member naming.
    if len(urls) > 1:
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=len(urls)) as pool:
            tokens = list(pool.map(_one, urls))
    else:
        tokens = [_one(u) for u in urls]
    for url, token in zip(urls, tokens):
        if token:
            stamped.append((url, token))
    result.tsa_urls_tried = list(urls)
    if stamped:
        result.tsa_token = stamped[0][1]
        result.tsa_url = stamped[0][0]
        result.tsa_tokens = [
            {
                "url": url,
                "member": (
                    "artifacts/notarization/tsa_reply.tsr"
                    if i == 0
                    else f"artifacts/notarization/tsa_reply_{i}.tsr"
                ),
            }
            for i, (url, _tok) in enumerate(stamped)
        ]
        result.additional_tsa_tokens = [
            (entry["member"], tok) for entry, (_url, tok) in zip(result.tsa_tokens[1:], stamped[1:])
        ]
    if stamp_digest is not None:
        result.imprint_scheme = IMPRINT_SCHEME
        result.imprinted_digest = stamp
        result.imprinted_public_key = imprinted_public_key

    # Tier 2: OpenTimestamps / Bitcoin anchoring
    result.ots_proof, result.ots_upgrade_msg = _submit_opentimestamps(manifest_hash)

    # Build evidence block for manifest
    result.evidence = {
        "notarized_at": {"provider": "rfc3161", "url": result.tsa_url, "hash": stamp},
        "tsa_token_available": result.tsa_token is not None,
        "tsa_genTime": _parse_tsr_gen_time(result.tsa_token),
        "tsa_tokens": result.tsa_tokens,
        "ots_proof_available": result.ots_proof is not None,
    }
    if result.imprint_scheme is not None:
        result.evidence["imprint_scheme"] = result.imprint_scheme
        result.evidence["imprinted_digest"] = result.imprinted_digest
        result.evidence["imprinted_public_key"] = result.imprinted_public_key

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
    for member_name, token_bytes in result.additional_tsa_tokens:
        (notary_dir / Path(member_name).name).write_bytes(token_bytes)

    if result.ots_proof:
        (notary_dir / "digest.ots").write_bytes(result.ots_proof)

    evidence_path = notary_dir / "notarization.json"
    evidence_path.write_text(json.dumps(result.evidence, indent=2), encoding="utf-8")
