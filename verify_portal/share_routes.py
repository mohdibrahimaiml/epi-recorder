import json, uuid, logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from fastapi import APIRouter, Query, UploadFile, File
from fastapi.exceptions import HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

logger = logging.getLogger("epi.share")
router = APIRouter()


class ContactSubmission(BaseModel):
    name: str
    email: str
    company: str = ""
    tier: str = ""
    use_case: str = ""


@router.post("/api/share")
async def share_epi_file(
    file: UploadFile = File(...),
    expires_days: int = Query(30, ge=1, le=30),
):
    content = await file.read()
    filename = file.filename or "untitled.epi"
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(413, "File too large. Max 5 MB")
    sid = uuid.uuid4().hex[:12]
    Path("shared_cases").mkdir(exist_ok=True)
    Path(f"shared_cases/{sid}.epi").write_bytes(content)
    meta = {
        "share_id": sid,
        "filename": filename,
        "size": len(content),
        "created_at": datetime.now(UTC).isoformat(),
        "expires_at": (datetime.now(UTC) + timedelta(days=expires_days)).isoformat(),
        "downloads": 0,
    }
    Path(f"shared_cases/{sid}.json").write_text(json.dumps(meta, indent=2))
    logger.info(f"SHARE {sid} {filename} {len(content)}")
    try:
        import zipfile, hashlib as hl, json as j
        zpath = Path(f"shared_cases/{sid}.epi")
        if zpath.exists():
            with zipfile.ZipFile(zpath, "r") as zf:
                m = j.loads(zf.read("manifest.json"))
            from verify_portal.dashboard import _dashboard_db
            db = _dashboard_db()
            db.execute(
                "INSERT OR REPLACE INTO team_runs (run_id, user_id, workflow, filename, share_id, trust_level, review_status, fault_count, created_at, sha256) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (sid, "shared", m.get("workflow_name", m.get("system_name","unknown")), filename, sid, "MEDIUM", "pending", 0, datetime.now(UTC).isoformat(), hl.sha256(content).hexdigest()),
            )
            db.commit(); db.close()
    except Exception:
        pass
    return {
        "share_id": sid,
        "url": f"https://epilabs.org/cases/?id={sid}",
        "expires_in_days": expires_days,
    }


@router.get("/api/share/{share_id}")
async def get_share(share_id: str):
    p = Path(f"shared_cases/{share_id}.epi")
    if not p.exists():
        raise HTTPException(404, "Share not found")
    return FileResponse(
        p,
        media_type="application/vnd.epi+zip",
        filename=f"{share_id}.epi",
        headers={"Content-Disposition": f"attachment; filename={share_id}.epi"},
    )


@router.post("/api/contact")
async def submit_contact(submission: ContactSubmission):
    Path("contact_submissions").mkdir(exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    safe = submission.name.replace(" ", "_")
    p = Path(f"contact_submissions/{ts}_{safe}.json")
    p.write_text(submission.model_dump_json(indent=2), encoding="utf-8")
    logger.info(f"CONTACT {submission.name}")
    return {"status": "ok", "message": "Thank you!"}
