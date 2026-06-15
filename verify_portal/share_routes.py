import json, uuid, logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from fastapi import APIRouter, Query, Request
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
async def share_epi_file(request: Request, expires_days: int = Query(30, ge=1, le=30)):
    body = await request.body()
    filename = request.headers.get("X-EPI-Filename", "untitled.epi")
    if len(body) > 5 * 1024 * 1024:
        raise HTTPException(413, "File too large. Max 5 MB")
    sid = uuid.uuid4().hex[:12]
    Path("shared_cases").mkdir(exist_ok=True)
    Path(f"shared_cases/{sid}.epi").write_bytes(body)
    meta = {
        "share_id": sid, "filename": filename, "size": len(body),
        "created_at": datetime.now(UTC).isoformat(),
        "expires_at": (datetime.now(UTC) + timedelta(days=expires_days)).isoformat(),
        "downloads": 0,
    }
    Path(f"shared_cases/{sid}.json").write_text(json.dumps(meta, indent=2))
    logger.info(f"SHARE {sid} {filename} {len(body)}")
    return {"share_id": sid, "url": f"https://epilabs.org/cases/?id={sid}", "expires_in_days": expires_days}


@router.get("/api/share/{share_id}")
async def get_share(share_id: str):
    p = Path(f"shared_cases/{share_id}.epi")
    if not p.exists():
        raise HTTPException(404, "Share not found")
    return FileResponse(p, media_type="application/vnd.epi+zip", filename=f"{share_id}.epi",
        headers={"Content-Disposition": f"attachment; filename={share_id}.epi"})


@router.post("/api/contact")
async def submit_contact(submission: ContactSubmission):
    Path("contact_submissions").mkdir(exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    safe_name = submission.name.replace(" ", "_")
    p = Path(f"contact_submissions/{ts}_{safe_name}.json")
    p.write_text(submission.model_dump_json(indent=2), encoding="utf-8")
    logger.info(f"CONTACT {submission.name} {submission.email}")
    return {"status": "ok", "message": "Thank you!"}
