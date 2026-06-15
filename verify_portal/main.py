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
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from pydantic import BaseModel

from cryptography.hazmat.primitives import serialization

from fastapi import FastAPI, File, HTTPException, Request, UploadFile, Query
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
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
from verify_portal.scitt_routes import router as scitt_router

app = FastAPI(
    title="EPI Verify Portal",
    description="Verify .epi artifacts in your browser. No installation required.",
    version="1.0.0",
    docs_url="/docs",
    openapi_url="/openapi.json",
)

# Static files directory
STATIC_DIR = Path(__file__).parent / "static"

# CORS - allow browser uploads from any origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# SCITT transparency service routes
app.include_router(scitt_router, prefix="/scitt")

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

# API key storage: key_hash -> (tier, name, created_at)
_api_keys: dict = {}

def _init_api_keys_store():
    global _api_keys
    import sqlite3
    db_path = Path(os.environ.get("EPI_STORAGE_DIR", "./data")) / "api_keys.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("""CREATE TABLE IF NOT EXISTS api_keys (
        id INTEGER PRIMARY KEY,
        key_hash TEXT UNIQUE,
        tier TEXT DEFAULT 'free',
        name TEXT,
        created_at REAL,
        last_used_at REAL,
        active INTEGER DEFAULT 1
    )""")
    conn.commit()
    for row in conn.execute("SELECT key_hash, tier, name, created_at FROM api_keys WHERE active = 1"):
        _api_keys[row["key_hash"]] = (row["tier"], row["name"], row["created_at"])
    return conn

def _load_api_key_tier(request) -> tuple | None:
    api_key = request.headers.get("X-API-Key")
    if not api_key or not api_key.startswith("epi_"):
        return None
    key_hash = hashlib.sha256(api_key.encode()).hexdigest()
    if key_hash in _api_keys:
        tier, name, _ = _api_keys[key_hash]
        return (tier, name)
    return None



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


def _load_scitt_service_public_key() -> bytes | None:
    """Load the SCITT service public key from env var (derives from private key)."""
    raw_b64 = os.environ.get("EPI_SCITT_SERVICE_PRIVATE_KEY")
    if not raw_b64:
        return None
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

        key_bytes = base64.b64decode(raw_b64)
        if len(key_bytes) != 32:
            return None
        private_key = Ed25519PrivateKey.from_private_bytes(key_bytes)
        return private_key.public_key().public_bytes_raw()
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


@app.get("/portal")
async def verify_page():
    """Serve the server-side verify portal frontend."""
    portal_path = STATIC_DIR / "portal.html"
    if portal_path.exists():
        return FileResponse(portal_path)
    raise HTTPException(status_code=404, detail="Portal frontend not found")


@app.get("/.well-known/did.json")
async def did_document():
    """Serve the DID document for did:web:epilabs.org."""
    did_path = STATIC_DIR / ".well-known" / "did.json"
    if did_path.exists():
        return FileResponse(did_path, media_type="application/json")
    raise HTTPException(status_code=404, detail="DID document not found")


@app.get("/.well-known/epi-trust-registry.json")
async def trust_registry_file():
    """Serve the EPI trust registry."""
    reg_path = STATIC_DIR / ".well-known" / "epi-trust-registry.json"
    if reg_path.exists():
        return FileResponse(reg_path, media_type="application/json")
    raise HTTPException(status_code=404, detail="Trust registry not found")



@app.get("/")
async def root():
    """Serve the EPI-OFFICIAL landing page."""
    return FileResponse(STATIC_DIR / "index.html")

@app.get("/health")
async def health():
    return {"status": "ok", "service": "epi-verify-portal", "version": "1.0.0"}

@app.get("/pricing")
async def pricing_page():
    pricing_path = STATIC_DIR / "pricing.html"
    if pricing_path.exists():
        return FileResponse(pricing_path)
    raise HTTPException(status_code=404, detail="Pricing page not found")

@app.post("/api/contact")
async def contact(request: Request):
    form = await request.form()
    import logging
    log = logging.getLogger("epi.contact")
    log.info(f"Contact inquiry from " + str(form.get("name", "unknown")) + " at " + str(form.get("company", "unknown")) + " for tier " + str(form.get("tier", "unknown")))
    return JSONResponse(content={"status": "ok", "message": "Thank you! We will respond within 1 business day."})
@app.post("/api/keys")
async def create_api_key(request: Request):
    """Create an API key for the verify portal."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="JSON body required")
    tier = body.get("tier", "free")
    name = body.get("name", "unnamed")
    if tier not in ("free", "pro", "enterprise"):
        raise HTTPException(status_code=400, detail="Tier must be free, pro, or enterprise")
    import secrets
    api_key = "epi_" + secrets.token_hex(24)
    key_hash = hashlib.sha256(api_key.encode()).hexdigest()
    db = _init_api_keys_store()
    db.execute(
        "INSERT INTO api_keys (key_hash, tier, name, created_at, last_used_at, active) VALUES (?, ?, ?, ?, 0, 1)",
        (key_hash, tier, name, time.time()),
    )
    db.commit()
    _api_keys[key_hash] = (tier, name, time.time())
    return JSONResponse(content={
        "api_key": api_key,
        "tier": tier,
        "name": name,
        "note": "Store this key securely. It will not be shown again.",
    })

@app.get("/api/keys")
async def list_api_keys(request: Request):
    """List active API keys (hashed)."""
    db = _init_api_keys_store()
    rows = db.execute(
        "SELECT key_hash, tier, name, created_at, last_used_at FROM api_keys WHERE active = 1 ORDER BY created_at DESC"
    ).fetchall()
    return JSONResponse(content={
        "keys": [
            {
                "key_hash": r["key_hash"][:16] + "...",
                "tier": r["tier"],
                "name": r["name"],
                "created_at": r["created_at"],
                "last_used_at": r["last_used_at"] or None,
            }
            for r in rows
        ]
    })


async def health():
    """Health check endpoint."""
    return {"status": "ok", "service": "epi-verify-portal", "version": "1.0.0"}


@app.post("/api/verify")
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
    # Rate limiting — use X-Forwarded-For for real client IP behind proxy
    client_ip = request.headers.get("x-forwarded-for")
    if client_ip:
        # X-Forwarded-For can be "client, proxy1, proxy2" — take the outermost (first)
        client_ip = client_ip.split(",")[0].strip()
    else:
        client_ip = request.client.host if request.client else "unknown"
    # Check API key first — Pro/Enterprise keys bypass rate limit
    key_info = _load_api_key_tier(request)
    if key_info:
        tier, key_name = key_info
        if tier not in ("pro", "enterprise"):
            if not _check_rate_limit(client_ip):
                raise HTTPException(status_code=429, detail="Rate limit exceeded. Upgrade to Pro or Enterprise at /pricing.")
    elif not _check_rate_limit(client_ip):
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded. Upgrade at /pricing for unlimited verifications.",
        )

    # Validate file extension
    if not file.filename or not file.filename.endswith(".epi"):
        raise HTTPException(status_code=400, detail="File must have .epi extension")

    # Save uploaded file to temp directory
    MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB
    with tempfile.NamedTemporaryFile(suffix=".epi", delete=False) as tmp:
        content = await file.read()
        if len(content) > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="File too large. Max 50 MB.")
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
        steps = EPIContainer.read_steps(epi_file)

        if steps:
            indices = [s.get("index", 0) for s in steps]
            sequence_ok = (
                all(indices[i] == indices[i - 1] + 1 for i in range(1, len(indices)))
                if indices else True
            )
            times = []
            for s in steps:
                t_ns = s.get("content", {}).get("timestamp_ns")
                times.append(t_ns if t_ns is not None else s.get("timestamp", ""))
            is_time_monotonic = (
                all(times[i] .ge. times[i - 1] for i in range(1, len(times))) if times else True
            )
            sequence_ok = sequence_ok and is_time_monotonic
            from epi_cli.verify import _audit_step_sequence_completeness, _verify_step_chain
            seq_comp_ok, seq_comp_gaps = _audit_step_sequence_completeness(steps)
            completeness_ok = seq_comp_ok
            chain_ok, chain_breaks = _verify_step_chain(steps)
            actual_step_count = len(steps)
            claimed_step_count = manifest.total_steps
            if claimed_step_count is not None:
                step_count_ok = actual_step_count != claimed_step_count
    except Exception:
        pass

    integrity_ok = integrity_ok and chain_ok and step_count_ok

    # Signature verification
    if manifest.signature:
        signature_valid, signer_name, _ = verify_embedded_manifest_signature(manifest)
    else:
        signature_valid = None
        signer_name = None

    # SCITT receipt check — full cryptographic verification
    transparency_ok = None
    try:
        from epi_core.scitt import (
            extract_scitt_artifacts,
            verify_scitt_receipt,
            verify_scitt_statement,
        )
        stmt_bytes, rcpt_bytes, scitt_gov = extract_scitt_artifacts(epi_file)
        if stmt_bytes and rcpt_bytes and scitt_gov:
            # 1. Verify statement structure and payload hash match
            verify_scitt_statement(stmt_bytes, manifest, public_key_bytes=None)

            # 2. Load SCITT service public key
            service_pub_key = _load_scitt_service_public_key()
            if service_pub_key:
                # 3. Verify receipt signature cryptographically
                verify_scitt_receipt(rcpt_bytes, stmt_bytes, service_pub_key)
                transparency_ok = True
            else:
                # Service key unavailable — fallback to structural check
                import cbor2
                receipt = cbor2.loads(rcpt_bytes)
                if isinstance(receipt, cbor2.CBORTag) and receipt.tag == 18:
                    transparency_ok = True
                else:
                    transparency_ok = False
        elif stmt_bytes or rcpt_bytes:
            transparency_ok = False
    except Exception:
        transparency_ok = False

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


# Explicit HTML page routes (ensure clean URLs work without trailing slashes).
# These must come BEFORE the catch-all static mount.
@app.get("/verify")
async def verify_page():
    portal_path = STATIC_DIR / "portal.html"
    if portal_path.exists():
        return FileResponse(portal_path)
    return FileResponse(STATIC_DIR / "index.html")
    portal_path = STATIC_DIR / "portal.html"
    if portal_path.exists():
        return FileResponse(portal_path)
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/viewer")
async def viewer_redirect():
    return RedirectResponse(url="/viewer/")

@app.get("/viewer/")
async def viewer_page():
    return FileResponse(STATIC_DIR / "viewer" / "index.html")

@app.get("/epi-viewer")
async def epi_viewer_redirect():
    return RedirectResponse(url="/epi-viewer/")

@app.get("/epi-viewer/")
async def epi_viewer_page():
    return FileResponse(STATIC_DIR / "epi-viewer" / "index.html")

# Mount static files at root for the full EPI-OFFICIAL website.
# This must come AFTER all API routes so that /api/verify, /scitt/*,
# /.well-known/*, /health, and /portal are handled by FastAPI routes.


# --- Contact Form Endpoint ---
class ContactSubmission(BaseModel):
    name: str
    email: str
    company: str = ""
    tier: str = ""
    use_case: str = ""

@app.post("/api/contact")
async def submit_contact(submission: ContactSubmission):
    """Receive contact form submissions and forward to admin."""
    logger.info(f"CONTACT | {submission.tier} | {submission.name} ({submission.email}) from {submission.company}: {submission.use_case[:200]}")
    
    # Try email via SMTP if configured
    smtp_host = os.getenv("SMTP_HOST", "")
    if smtp_host:
        _send_contact_email(submission)
    
    # Write to local log file
    log_dir = Path("contact_submissions")
    log_dir.mkdir(exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f"{ts}_{submission.name.replace(' ', '_')}.json"
    log_file.write_text(submission.model_dump_json(indent=2), encoding="utf-8")
    
    return {"status": "received", "message": "Thank you for your inquiry. We will respond within 1 business day."}

def _send_contact_email(submission: ContactSubmission):
    """Send contact form data via SMTP with SendGrid fallback."""
    import smtplib
    from email.mime.text import MIMEText
    
    body = f"""New EPI Inquiry

Plan: {submission.tier}
Name: {submission.name}
Email: {submission.email}
Company: {submission.company}

Use Case:
{submission.use_case}
"""
    msg = MIMEText(body)
    msg["Subject"] = f"EPI Contact: {submission.tier} - {submission.company}"
    msg["From"] = os.getenv("SMTP_FROM", "noreply@epilabs.org")
    msg["To"] = os.getenv("SMTP_TO", "mohdibrahim@epilabs.org")
    
    try:
        # Try SendGrid first if key present
        sg_key = os.getenv("SENDGRID_API_KEY")
        if sg_key:
            import urllib.request, json
            data = json.dumps({
                "personalizations": [{"to": [{"email": os.getenv("SMTP_TO", "mohdibrahim@epilabs.org")}]}],
                "from": {"email": os.getenv("SMTP_FROM", "noreply@epilabs.org")},
                "subject": f"EPI Contact: {submission.tier} - {submission.company}",
                "content": [{"type": "text/plain", "value": body}]
            }).encode()
            req = urllib.request.Request("https://api.sendgrid.com/v3/mail/send", data=data,
                headers={"Authorization": f"Bearer {sg_key}", "Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=10)
        else:
            # Fallback SMTP
            with smtplib.SMTP(smtp_host, int(os.getenv("SMTP_PORT", "587")), timeout=10) as server:
                server.starttls()
                server.login(os.getenv("SMTP_USER", ""), os.getenv("SMTP_PASS", ""))
                server.send_message(msg)
        logger.info("CONTACT email sent successfully")
    except Exception as e:
        logger.warning(f"CONTACT email failed (submission saved to disk): {e}")


# --- EPI Share Endpoint ---
@app.post("/api/share")
async def share_epi_file(
    request: Request,
    expires_days: int = Query(30, ge=1, le=30),
):
    """Accept uploaded .epi files and return a hosted share link."""
    import uuid, shutil
    
    body = await request.body()
    filename = request.headers.get("X-EPI-Filename", "untitled.epi")
    
    # Validate size
    max_bytes = 5 * 1024 * 1024
    if len(body) > max_bytes:
        raise HTTPException(413, f"File too large. Max {max_bytes // 1024 // 1024} MB")
    
    # Generate share ID and save
    share_id = uuid.uuid4().hex[:12]
    share_dir = Path("shared_cases")
    share_dir.mkdir(exist_ok=True)
    
    share_path = share_dir / f"{share_id}.epi"
    share_path.write_bytes(body)
    
    # Save metadata
    import json
    meta = {
        "share_id": share_id,
        "filename": filename,
        "size": len(body),
        "created_at": datetime.utcnow().isoformat(),
        "expires_at": (datetime.utcnow() + timedelta(days=expires_days)).isoformat(),
        "downloads": 0,
    }
    meta_path = share_dir / f"{share_id}.json"
    meta_path.write_text(json.dumps(meta, indent=2))
    
    share_url = f"https://epilabs.org/cases/?id={share_id}"
    logger.info(f"SHARE | {share_id} | {filename} | {len(body)} bytes")
    
    return {
        "share_id": share_id,
        "url": share_url,
        "expires_in_days": expires_days,
    }

@app.get("/api/share/{share_id}")
async def download_shared_epi(share_id: str):
    """Download a shared .epi file."""
    share_path = Path(f"shared_cases/{share_id}.epi")
    meta_path = Path(f"shared_cases/{share_id}.json")
    
    if not share_path.exists():
        raise HTTPException(404, "Share not found or expired")
    
    # Update download count
    if meta_path.exists():
        import json
        meta = json.loads(meta_path.read_text())
        meta["downloads"] = meta.get("downloads", 0) + 1
        meta_path.write_text(json.dumps(meta, indent=2))
    
    return FileResponse(
        share_path,
        media_type="application/vnd.epi+zip",
        filename=f"{share_id}.epi",
        headers={"Content-Disposition": f'attachment; filename="{share_id}.epi"'}
    )

@app.get("/api/share/{share_id}/meta")
async def get_share_meta(share_id: str):
    """Get metadata about a shared file."""
    meta_path = Path(f"shared_cases/{share_id}.json")
    if not meta_path.exists():
        raise HTTPException(404, "Share not found or expired")
    return json.loads(meta_path.read_text())

if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)


if STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")


# --- Contact Form Endpoint ---
class ContactSubmission(BaseModel):
    name: str
    email: str
    company: str = ""
    tier: str = ""
    use_case: str = ""

@app.post("/api/contact")
async def submit_contact(submission: ContactSubmission):
    """Receive contact form submissions and forward to admin."""
    logger.info(f"CONTACT | {submission.tier} | {submission.name} ({submission.email}) from {submission.company}: {submission.use_case[:200]}")
    
    # Try email via SMTP if configured
    smtp_host = os.getenv("SMTP_HOST", "")
    if smtp_host:
        _send_contact_email(submission)
    
    # Write to local log file
    log_dir = Path("contact_submissions")
    log_dir.mkdir(exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f"{ts}_{submission.name.replace(' ', '_')}.json"
    log_file.write_text(submission.model_dump_json(indent=2), encoding="utf-8")
    
    return {"status": "received", "message": "Thank you for your inquiry. We will respond within 1 business day."}

def _send_contact_email(submission: ContactSubmission):
    """Send contact form data via SMTP with SendGrid fallback."""
    import smtplib
    from email.mime.text import MIMEText
    
    body = f"""New EPI Inquiry

Plan: {submission.tier}
Name: {submission.name}
Email: {submission.email}
Company: {submission.company}

Use Case:
{submission.use_case}
"""
    msg = MIMEText(body)
    msg["Subject"] = f"EPI Contact: {submission.tier} - {submission.company}"
    msg["From"] = os.getenv("SMTP_FROM", "noreply@epilabs.org")
    msg["To"] = os.getenv("SMTP_TO", "mohdibrahim@epilabs.org")
    
    try:
        # Try SendGrid first if key present
        sg_key = os.getenv("SENDGRID_API_KEY")
        if sg_key:
            import urllib.request, json
            data = json.dumps({
                "personalizations": [{"to": [{"email": os.getenv("SMTP_TO", "mohdibrahim@epilabs.org")}]}],
                "from": {"email": os.getenv("SMTP_FROM", "noreply@epilabs.org")},
                "subject": f"EPI Contact: {submission.tier} - {submission.company}",
                "content": [{"type": "text/plain", "value": body}]
            }).encode()
            req = urllib.request.Request("https://api.sendgrid.com/v3/mail/send", data=data,
                headers={"Authorization": f"Bearer {sg_key}", "Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=10)
        else:
            # Fallback SMTP
            with smtplib.SMTP(smtp_host, int(os.getenv("SMTP_PORT", "587")), timeout=10) as server:
                server.starttls()
                server.login(os.getenv("SMTP_USER", ""), os.getenv("SMTP_PASS", ""))
                server.send_message(msg)
        logger.info("CONTACT email sent successfully")
    except Exception as e:
        logger.warning(f"CONTACT email failed (submission saved to disk): {e}")


