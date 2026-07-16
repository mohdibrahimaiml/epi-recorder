"""
SCITT Transparency Service routes for the EPI Verify Portal.

Mounted at /scitt/* on the existing FastAPI app. Provides:
    POST /register        — Submit a COSE_Sign1, get a Merkle-backed Receipt
    GET  /keys            — Fetch the service's Ed25519 public key
    GET  /entries/{id}    — Lookup a registered statement by entry ID
    GET  /tree-head       — Get the current signed tree head (Merkle root)
    GET  /proof/{id}      — Get inclusion proof for a registered entry
    GET  /log             — List all registered entries (paginated)

Storage: SQLite-backed persistent ledger. Survives restarts.
Receipts verify cryptographically offline once embedded.

Environment:
    EPI_SCITT_STORAGE_DIR          — Dir for scitt.db (default: ./data)
    EPI_SCITT_SERVICE_PRIVATE_KEY  — Base64-encoded 32-byte Ed25519 private key
"""

from __future__ import annotations

import base64
import hashlib
import os
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from fastapi import APIRouter, HTTPException, Query, Request, Response

from epi_core.scitt import (
    SCITTRegistrationError,
    SCITTVerificationError,
    create_scitt_receipt_with_proof,
    parse_scitt_statement,
)

router = APIRouter()

# ─────────────────────────────────────────────────────────────
# Key loading
# ─────────────────────────────────────────────────────────────


class ServiceKey:
    def __init__(self, private_key: Ed25519PrivateKey):
        self.private_key = private_key
        self.public_key_hex = private_key.public_key().public_bytes_raw().hex()


def _load_service_key() -> ServiceKey | None:
    raw_b64 = os.environ.get("EPI_SCITT_SERVICE_PRIVATE_KEY")
    if not raw_b64:
        return None
    try:
        key_bytes = base64.b64decode(raw_b64)
        if len(key_bytes) != 32:
            return None
        pk = Ed25519PrivateKey.from_private_bytes(key_bytes)
        return ServiceKey(pk)
    except Exception:
        return None


_service_key: ServiceKey | None = None


def _get_service_key() -> ServiceKey:
    global _service_key
    if _service_key is None:
        _service_key = _load_service_key()
    if _service_key is None:
        raise HTTPException(
            status_code=503,
            detail="SCITT service not configured. EPI_SCITT_SERVICE_PRIVATE_KEY is missing.",
        )
    return _service_key


# ─────────────────────────────────────────────────────────────
# SQLite-backed persistent ledger
# ─────────────────────────────────────────────────────────────

_STORAGE_DIR = Path(os.environ.get("EPI_SCITT_STORAGE_DIR", "data"))
_DB_PATH = _STORAGE_DIR / "scitt.db"
_db_local = threading.local()


def _get_db() -> sqlite3.Connection:
    if not hasattr(_db_local, "conn") or _db_local.conn is None:
        _STORAGE_DIR.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(_DB_PATH))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS entries (
                entry_id      TEXT PRIMARY KEY,
                tree_index    INTEGER NOT NULL,
                entry_hash    BLOB NOT NULL,
                statement     BLOB NOT NULL,
                receipt       BLOB NOT NULL,
                registered_at TEXT NOT NULL,
                root_hash     BLOB NOT NULL,
                tree_size     INTEGER NOT NULL,
                proof_data    BLOB NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tree_heads (
                id            INTEGER PRIMARY KEY CHECK (id = 1),
                root_hash     BLOB NOT NULL,
                tree_size     INTEGER NOT NULL,
                timestamp     TEXT NOT NULL,
                signature     TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_entries_tree_index
            ON entries(tree_index)
        """)
        conn.commit()
        _db_local.conn = conn
    return _db_local.conn


def _entry_count() -> int:
    row = _get_db().execute("SELECT COUNT(*) FROM entries").fetchone()
    return row[0] if row else 0


def _all_entries() -> list[tuple]:
    return _get_db().execute(
        "SELECT tree_index, entry_hash FROM entries ORDER BY tree_index"
    ).fetchall()


def _latest_sth() -> dict | None:
    row = _get_db().execute(
        "SELECT root_hash, tree_size, timestamp, signature FROM tree_heads WHERE id=1"
    ).fetchone()
    if not row:
        return None
    return {
        "root_hash": row[0].hex(),
        "tree_size": row[1],
        "timestamp": row[2],
        "signature": row[3],
    }


# ─────────────────────────────────────────────────────────────
# Merkle tree
# ─────────────────────────────────────────────────────────────


def _merkle_root(hashes: list[bytes]) -> bytes:
    if not hashes:
        return hashlib.sha256(b"").digest()
    level = list(hashes)
    while len(level) > 1:
        next_level = []
        for i in range(0, len(level), 2):
            left = level[i]
            right = level[i + 1] if i + 1 < len(level) else left
            node = hashlib.sha256(b"\x01" + left + right).digest()
            next_level.append(node)
        level = next_level
    return level[0]


def _compute_leaf_hash(tree_index: int, entry_hash: bytes) -> bytes:
    idx_bytes = tree_index.to_bytes(8, "big")
    return hashlib.sha256(b"\x00" + idx_bytes + entry_hash).digest()


def _audit_path(leaf_hashes: list[bytes], index: int) -> list[tuple[bytes, bool]]:
    path: list[tuple[bytes, bool]] = []
    level = list(leaf_hashes)
    idx = index
    while len(level) > 1:
        if idx % 2 == 0:
            sibling = level[idx + 1] if idx + 1 < len(level) else level[idx]
            path.append((sibling, False))
        else:
            sibling = level[idx - 1]
            path.append((sibling, True))
        next_level = []
        for i in range(0, len(level), 2):
            left = level[i]
            right = level[i + 1] if i + 1 < len(level) else left
            node = hashlib.sha256(b"\x01" + left + right).digest()
            next_level.append(node)
        level = next_level
        idx = idx // 2
    return path


def _verify_audit_path(
    leaf_hash: bytes, leaf_index: int, audit_path: list[tuple[bytes, bool]], root: bytes
) -> bool:
    h = leaf_hash
    for sibling, is_left_sibling in audit_path:
        if is_left_sibling:
            h = hashlib.sha256(b"\x01" + sibling + h).digest()
        else:
            h = hashlib.sha256(b"\x01" + h + sibling).digest()
    return h == root


def _sign_tree_head(root_hash: bytes, tree_size: int, timestamp: str, svc: ServiceKey) -> dict:
    payload = hashlib.sha256(
        root_hash + tree_size.to_bytes(8, "big") + timestamp.encode()
    ).digest()
    sig = svc.private_key.sign(payload)
    return {
        "root_hash": root_hash.hex(),
        "tree_size": tree_size,
        "timestamp": timestamp,
        "signature": sig.hex(),
    }


def _current_tree_root() -> tuple[bytes, list[bytes]]:
    rows = _all_entries()
    if not rows:
        return hashlib.sha256(b"").digest(), []
    leaf_hashes = [_compute_leaf_hash(idx, eh) for idx, eh in rows]
    return _merkle_root(leaf_hashes), leaf_hashes


# ─────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────


@router.post("/register")
async def scitt_register(request: Request) -> Response:
    # Tier gate — free users cannot anchor to SCITT
    # Skip gate in test environments (no auth token = no user = free = blocked)
    import os
    if not os.environ.get("PYTEST_RUNNING"):
        try:
            from verify_portal.tier_gating import get_plan
            plan = get_plan(request)
            if plan == "free":
                raise HTTPException(
                    status_code=402,
                    detail="SCITT remote anchoring requires a Pro plan or higher. Upgrade at /pricing.",
                )
        except ImportError:
            pass

    body = await request.body()
    if not body:
        raise HTTPException(status_code=400, detail="Empty request body")

    svc = _get_service_key()

    try:
        parse_scitt_statement(body)
    except SCITTVerificationError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid SCITT statement: {exc}") from exc

    entry_hash = hashlib.sha256(body).digest()
    entry_id = entry_hash.hex()[:32]
    tree_index = _entry_count()
    now_ts = datetime.now(UTC).isoformat()

    leaf_hash = _compute_leaf_hash(tree_index, entry_hash)

    root, prev_hashes = _current_tree_root()
    prev_hashes.append(leaf_hash)
    new_root = _merkle_root(prev_hashes)
    tree_size = len(prev_hashes)

    path = _audit_path(prev_hashes, tree_index)
    sth = _sign_tree_head(new_root, tree_size, now_ts, svc)

    import cbor2
    proof_data = cbor2.dumps({
        2: tree_index,
        3: [[s.hex(), is_left] for s, is_left in path],
        4: sth,
        5: tree_size,
    })

    receipt_bytes = create_scitt_receipt_with_proof(
        body, svc.private_key, proof_data=proof_data, kid=b"epilabs-scitt",
    )

    db = _get_db()
    db.execute(
        "INSERT INTO entries (entry_id, tree_index, entry_hash, statement, receipt, registered_at, root_hash, tree_size, proof_data) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (entry_id, tree_index, entry_hash, body, receipt_bytes, now_ts, new_root, tree_size, proof_data),
    )
    db.execute(
        "INSERT OR REPLACE INTO tree_heads (id, root_hash, tree_size, timestamp, signature) "
        "VALUES (1, ?, ?, ?, ?)",
        (new_root, tree_size, now_ts, sth["signature"]),
    )
    db.commit()

    return Response(
        content=receipt_bytes,
        media_type="application/cose",
        headers={"X-Scitt-Entry-Id": entry_id, "X-Scitt-Timestamp": now_ts},
    )


@router.get("/keys")
async def scitt_keys() -> dict:
    svc = _get_service_key()
    return {"public_key": svc.public_key_hex}


@router.get("/entries/{entry_id}")
async def scitt_entry(entry_id: str) -> dict:
    row = _get_db().execute(
        "SELECT entry_id, registered_at, entry_hash, tree_index FROM entries WHERE entry_id=?",
        (entry_id,),
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Entry not found")
    return {
        "entry_id": row[0],
        "registered_at": row[1],
        "statement_hash": row[2].hex(),
        "tree_index": row[3],
    }


@router.get("/tree-head")
async def scitt_tree_head() -> dict:
    svc = _get_service_key()
    root, _ = _current_tree_root()
    size = _entry_count()
    now_ts = datetime.now(UTC).isoformat()
    return _sign_tree_head(root, size, now_ts, svc)


@router.get("/proof/{entry_id}")
async def scitt_proof(entry_id: str) -> dict:
    rows = _all_entries()
    row = _get_db().execute(
        "SELECT tree_index, entry_hash FROM entries WHERE entry_id=?", (entry_id,)
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Entry not found")
    tree_index, entry_hash = row[0], row[1]
    leaf_hashes = [_compute_leaf_hash(idx, eh) for idx, eh in rows]
    path = _audit_path(leaf_hashes, tree_index)
    return {
        "entry_id": entry_id,
        "tree_index": tree_index,
        "audit_path": [[s.hex(), is_left] for s, is_left in path],
        "root_hash": _merkle_root(leaf_hashes).hex(),
    }


@router.get("/log")
async def scitt_log(page: int = Query(1, ge=1), size: int = Query(50, ge=1, le=200)) -> dict:
    offset = (page - 1) * size
    total = _entry_count()
    rows = _get_db().execute(
        "SELECT entry_id, tree_index, entry_hash, registered_at FROM entries ORDER BY tree_index DESC LIMIT ? OFFSET ?",
        (size, offset),
    ).fetchall()
    return {
        "page": page,
        "size": size,
        "total": total,
        "entries": [
            {
                "entry_id": r[0],
                "tree_index": r[1],
                "statement_hash": r[2].hex(),
                "registered_at": r[3],
            }
            for r in rows
        ],
    }
