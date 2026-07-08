"""EPI Team Dashboard — run history, review queue, team key management."""
import json
import os
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse

router = APIRouter()
STORAGE_DIR = Path(os.getenv("EPI_STORAGE_DIR", "./data"))


def _dashboard_db():
    p = STORAGE_DIR / "dashboard.db"
    p.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(p))
    c.row_factory = sqlite3.Row
    c.executescript("""
        CREATE TABLE IF NOT EXISTS team_runs (
            run_id TEXT PRIMARY KEY, user_id TEXT, workflow TEXT, filename TEXT,
            share_id TEXT, trust_level TEXT, review_status TEXT DEFAULT 'pending',
            fault_count INTEGER DEFAULT 0, created_at TEXT, sha256 TEXT
        );
        CREATE TABLE IF NOT EXISTS team_reviews (
            review_id TEXT PRIMARY KEY, run_id TEXT, reviewer TEXT,
            outcome TEXT, notes TEXT, created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS team_keys (
            key_id TEXT PRIMARY KEY, team_id TEXT, name TEXT,
            public_key_hex TEXT, created_at TEXT
        );
    """)
    c.commit()
    return c


def _auth_user(request: Request) -> dict:
    tok = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    if not tok:
        raise HTTPException(401, "Bearer token required")
    from verify_portal import auth as am
    u = am.verify_token(STORAGE_DIR, tok)
    if not u:
        raise HTTPException(401, "Invalid token")
    return dict(u)


@router.get("/api/dashboard/runs")
async def runs(request: Request, workflow: str = Query(None), status: str = Query(None),
               limit: int = Query(50, le=200), offset: int = Query(0)):
    u = _auth_user(request)
    db = _dashboard_db()
    q = "SELECT * FROM team_runs WHERE user_id = ?"
    params = [u["id"]]
    if workflow:
        q += " AND workflow = ?"
        params.append(workflow)
    if status:
        q += " AND review_status = ?"
        params.append(status)
    q += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    rows = db.execute(q, params).fetchall()
    db.close()
    return {"runs": [dict(r) for r in rows], "limit": limit, "offset": offset}


@router.get("/api/dashboard/workflows")
async def workflows(request: Request):
    u = _auth_user(request)
    db = _dashboard_db()
    rows = db.execute(
        "SELECT DISTINCT workflow, COUNT(*) as c FROM team_runs WHERE user_id=? GROUP BY workflow ORDER BY c DESC",
        (u["id"],),
    ).fetchall()
    db.close()
    return {"workflows": [{"name": r["workflow"], "count": r["c"]} for r in rows]}


@router.get("/api/dashboard/reviews")
async def reviews(request: Request, limit: int = Query(20, le=100)):
    u = _auth_user(request)
    db = _dashboard_db()
    rows = db.execute(
        "SELECT * FROM team_runs WHERE user_id=? AND review_status='pending' ORDER BY created_at DESC LIMIT ?",
        (u["id"], limit),
    ).fetchall()
    db.close()
    return {"reviews": [dict(r) for r in rows]}


@router.post("/api/dashboard/reviews/{run_id}")
async def submit_review(run_id: str, request: Request):
    u = _auth_user(request)
    body = await request.json()
    outcome = body.get("outcome", "dismissed")
    notes = body.get("notes", "")
    reviewer = body.get("reviewer", u.get("login", "unknown"))
    if outcome not in ("confirmed_fault", "dismissed", "skipped"):
        raise HTTPException(400, "Invalid outcome")
    db = _dashboard_db()
    rid = f"rev_{run_id[:8]}_{int(time.time())}"
    now = datetime.now(timezone.utc).isoformat()
    db.execute(
        "INSERT INTO team_reviews (review_id,run_id,reviewer,outcome,notes,created_at) VALUES (?,?,?,?,?,?)",
        (rid, run_id, reviewer, outcome, notes, now),
    )
    new_st = "reviewed" if outcome != "skipped" else "pending"
    db.execute("UPDATE team_runs SET review_status=? WHERE run_id=?", (new_st, run_id))
    db.commit()
    db.close()
    return {"review_id": rid, "run_id": run_id, "status": new_st, "reviewer": reviewer}


@router.get("/api/dashboard/keys")
async def list_keys(request: Request):
    u = _auth_user(request)
    db = _dashboard_db()
    team = u.get("org", u["id"])
    rows = db.execute(
        "SELECT key_id,team_id,name,created_at FROM team_keys WHERE team_id=? ORDER BY created_at DESC",
        (team,),
    ).fetchall()
    db.close()
    return {"keys": [dict(r) for r in rows]}


@router.post("/api/dashboard/keys")
async def create_key(request: Request):
    u = _auth_user(request)
    body = await request.json()
    name = body.get("name", "team-default")
    team = u.get("org", u["id"])
    from epi_core.keys import KeyManager
    km = KeyManager()
    km.generate_keypair(name)
    pub_bytes = km.load_public_key(name)
    pub = pub_bytes.hex()
    db = _dashboard_db()
    kid = f"tk_{int(time.time())}_{name}"
    db.execute(
        "INSERT INTO team_keys (key_id,team_id,name,public_key_hex,created_at) VALUES (?,?,?,?,?)",
        (kid, team, name, pub, datetime.now(timezone.utc).isoformat()),
    )
    db.commit()
    db.close()
    return {"key_id": kid, "name": name, "public_key": pub, "note": f"Key {name} created."}
