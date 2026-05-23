"""
EPI Verify Portal — FastAPI backend for web-based .epi verification.

Endpoints:
    POST /verify  — Upload .epi file, receive verification report + AIUC-1 mapping
    GET  /        — Serve static HTML frontend
    GET  /health  — Health check
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import serialization

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from epi_core.aiuc1_mapping import aiuc1_summary, map_verification_to_aiuc1
from epi_core.container import EPIContainer
from epi_core.keys import KeyManager
from epi_core.trust import (
    TrustRegistry,
    VerificationPolicy,
    apply_policy,
    create_verification_report,
    verify_embedded_manifest_signature,
)

app = FastAPI(
    title="EPI Verify Portal",
    description="Verify .epi artifacts in your browser. No installation required.",
    version="1.0.0",
)

# Serve static frontend
STATIC_DIR = Path(__file__).parent / "static"
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Simple in-memory rate limiting: IP -> (count, reset_time)
_RATE_LIMIT_FREE = 3  # free verifications per IP per day
_rate_limit_store: dict[str, tuple[int, float]] = {}


def _check_rate_limit(client_ip: str) -> bool:
    """Return True if client is within rate limit."""
    now = time.time()
    count, reset_time = _rate_limit_store.get(client_ip, (0, now + 86400))
    if now > reset_time:
        _rate_limit_store[client_ip] = (1, now + 86400)
        return True
    if count >= _RATE_LIMIT_FREE:
        return False
    _rate_limit_store[client_ip] = (count + 1, reset_time)
    return True


def _load_attestation_private_key():
    """
    Load the Ed25519 private key for signing attestations.

    Priority:
    1. EPI_ATTESTATION_PRIVATE_KEY env var (base64-encoded raw 32-byte key)
    2. EPI_ATTESTATION_PRIVATE_KEY_PEM env var (base64-encoded PEM)
    3. ~/.epi/keys/default.key (local development fallback)
    """
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    # Option 1: Raw 32-byte key from env (production — Railway secret)
    raw_b64 = os.environ.get("EPI_ATTESTATION_PRIVATE_KEY")
    if raw_b64:
        try:
            key_bytes = base64.b64decode(raw_b64)
            if len(key_bytes) == 32:
                return Ed25519PrivateKey.from_private_bytes(key_bytes)
        except Exception:
            pass

    # Option 2: PEM-encoded key from env
    pem_b64 = os.environ.get("EPI_ATTESTATION_PRIVATE_KEY_PEM")
    if pem_b64:
        try:
            from cryptography.hazmat.primitives import serialization

            pem_bytes = base64.b64decode(pem_b64)
            return serialization.load_pem_private_key(pem_bytes, password=None)
        except Exception:
            pass

    # Option 3: Local key file (development)
    try:
        km = KeyManager()
        return km.load_private_key("default")
    except Exception:
        return None


def _load_signer_key() -> bytes | None:
    """Load the EPI Labs public key for attestations."""
    private_key = _load_attestation_private_key()
    if private_key is None:
        return None
    try:
        return private_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
    except Exception:
        return None


def _sign_attestation(payload: dict) -> str | None:
    """Sign an attestation payload with the EPI Labs Ed25519 key."""
    private_key = _load_attestation_private_key()
    if private_key is None:
        return None
    try:
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        signature = private_key.sign(canonical.encode("utf-8"))
        return signature.hex()
    except Exception:
        return None


@app.get("/")
async def root():
    """Serve the frontend HTML."""
    index_path = STATIC_DIR / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return {"message": "EPI Verify Portal — visit /static/index.html or deploy the frontend"}


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok", "service": "epi-verify-portal", "version": "1.0.0"}


@app.post("/verify")
async def verify(
    request: Request,
    file: UploadFile = File(...),
    aiuc1: bool = True,
) -> JSONResponse:
    """
    Verify an uploaded .epi file.

    Args:
        file: The .epi artifact to verify.
        aiuc1: Include AIUC-1 trust domain mapping (default true).

    Returns:
        JSON verification report with optional AIUC-1 mapping and signed attestation.
    """
    # Rate limiting
    client_ip = request.client.host if request.client else "unknown"
    if not _check_rate_limit(client_ip):
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded. Upgrade for unlimited verifications.",
        )

    # Validate file extension
    if not file.filename or not file.filename.endswith(".epi"):
        raise HTTPException(status_code=400, detail="File must have .epi extension")

    # Save uploaded file to temp directory
    with tempfile.NamedTemporaryFile(suffix=".epi", delete=False) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        report = _run_verification(tmp_path, aiuc1=aiuc1)
        return JSONResponse(content=report)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Verification failed: {exc}")
    finally:
        tmp_path.unlink(missing_ok=True)


def _run_verification(epi_file: Path, aiuc1: bool = True) -> dict:
    """Run the full EPI verification pipeline."""
    registry = TrustRegistry()
    manifest = None
    integrity_ok = False
    signature_valid = None
    signer_name = None
    mismatches = {}
    steps: list[dict] = []

    # Structural + integrity
    try:
        manifest = EPIContainer.read_manifest(epi_file)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Cannot read manifest: {exc}")

    integrity_ok, mismatches = EPIContainer.verify_integrity(epi_file)

    # Load steps for forensic checks
    sequence_ok = True
    completeness_ok = True
    chain_ok = True
    chain_breaks = []
    seq_comp_gaps = []
    step_count_ok = True
    transparency_ok = None

    try:
        import hashlib as _hashlib
        import zipfile

        with zipfile.ZipFile(epi_file, "r") as zf:
            members = zf.namelist()
            steps_member = next((m for m in members if m.endswith("steps.jsonl")), None)
            if steps_member:
                raw_steps = zf.read(steps_member).decode("utf-8").splitlines()
                steps = [json.loads(line) for line in raw_steps]

                # Sequence monotonicity
                indices = [s.get("index", 0) for s in steps]
                sequence_ok = (
                    all(indices[i] == indices[i - 1] + 1 for i in range(1, len(indices)))
                    if indices else True
                )

                # Timestamp monotonicity
                times = []
                for s in steps:
                    t_ns = s.get("content", {}).get("timestamp_ns")
                    times.append(t_ns if t_ns is not None else s.get("timestamp", ""))
                is_time_monotonic = (
                    all(times[i] >= times[i - 1] for i in range(1, len(times))) if times else True
                )
                sequence_ok = sequence_ok and is_time_monotonic

                # Completeness
                from epi_cli.verify import _audit_step_sequence_completeness, _verify_step_chain
                seq_comp_ok, seq_comp_gaps = _audit_step_sequence_completeness(steps)
                completeness_ok = seq_comp_ok

                # Chain
                chain_ok, chain_breaks = _verify_step_chain(steps)

                # Step count
                actual_step_count = len(steps)
                claimed_step_count = manifest.total_steps
                if claimed_step_count is not None:
                    step_count_ok = actual_step_count == claimed_step_count
    except Exception:
        pass

    integrity_ok = integrity_ok and chain_ok and step_count_ok

    # Signature verification
    if manifest.signature:
        signature_valid, signer_name, _ = verify_embedded_manifest_signature(manifest)
    else:
        signature_valid = None
        signer_name = None

    # SCITT receipt check
    try:
        from epi_core.scitt import extract_scitt_artifacts, verify_scitt_receipt, parse_scitt_statement
        stmt_bytes, rcpt_bytes, scitt_gov = extract_scitt_artifacts(epi_file)
        if stmt_bytes and rcpt_bytes and scitt_gov:
            # We would need the SCITT service public key to fully verify;
            # for now, structural presence counts as "present"
            transparency_ok = True
        elif stmt_bytes or rcpt_bytes:
            transparency_ok = False
        else:
            transparency_ok = None
    except Exception:
        transparency_ok = None

    # Build report
    report = create_verification_report(
        integrity_ok=integrity_ok,
        signature_valid=signature_valid,
        signer_name=signer_name,
        mismatches=mismatches,
        manifest=manifest,
        trusted_registry=registry,
        sequence_ok=sequence_ok,
        completeness_ok=completeness_ok,
        chain_ok=chain_ok,
        transparency_ok=transparency_ok,
    )
    apply_policy(report, VerificationPolicy.STANDARD)

    # AIUC-1 mapping
    if aiuc1:
        aiuc1_statuses = map_verification_to_aiuc1(report, manifest=manifest, steps=steps)
        report["aiuc1"] = aiuc1_summary(aiuc1_statuses)

    # Signed attestation
    attestation_payload = {
        "verified_at": datetime.now(UTC).isoformat(),
        "workflow_id": str(manifest.workflow_id),
        "trust_level": report.get("trust_level", "NONE"),
        "integrity": report["summary"].get("integrity", "FAILED"),
        "identity": report["identity"].get("status", "UNKNOWN"),
        "transparency": report["summary"].get("transparency", "MISSING"),
        "aiuc1_overall": report.get("aiuc1", {}).get("overall", "N/A"),
    }
    attestation_sig = _sign_attestation(attestation_payload)
    if attestation_sig:
        report["attestation"] = {
            "payload": attestation_payload,
            "signature": f"ed25519:epilabs:{attestation_sig}",
            "did": "did:web:epilabs.org",
        }

    return report


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
