"""Durable DB connections for the verify portal.

Backends (automatic):
1. **Turso / libSQL remote** when TURSO_DATABASE_URL + TURSO_AUTH_TOKEN are set
   (or LIBSQL_URL + LIBSQL_AUTH_TOKEN). Free tier — survives Render redeploys.
2. **Local SQLite** under EPI_STORAGE_DIR (default ./data/auth.db).

No paid disk required if Turso free is configured.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from pathlib import Path
from typing import Any, Iterable, Sequence

import httpx

_lock = threading.RLock()


def turso_configured() -> bool:
    return bool(_turso_url() and _turso_token())


def _turso_url() -> str:
    return (
        os.getenv("TURSO_DATABASE_URL", "").strip()
        or os.getenv("LIBSQL_URL", "").strip()
        or os.getenv("LIBSQL_DATABASE_URL", "").strip()
    )


def _turso_token() -> str:
    return (
        os.getenv("TURSO_AUTH_TOKEN", "").strip()
        or os.getenv("LIBSQL_AUTH_TOKEN", "").strip()
    )


def storage_dir() -> Path:
    raw = os.getenv("EPI_STORAGE_DIR", "./data")
    path = Path(raw)
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError:
        path = Path("./data")
        path.mkdir(parents=True, exist_ok=True)
    return path


def auth_db_path(storage_dir_path: Path | str | None = None) -> Path:
    base = Path(storage_dir_path) if storage_dir_path is not None else storage_dir()
    return base / "auth.db"


def backend_name() -> str:
    return "turso" if turso_configured() else "sqlite"


# ── Row helper ────────────────────────────────────────────

class Row(dict):
    """dict that also supports row['col'] and row[0]-style access lightly."""

    def __getitem__(self, key: Any) -> Any:  # type: ignore[override]
        if isinstance(key, int):
            return list(self.values())[key]
        return super().__getitem__(key)

    def keys(self):  # type: ignore[override]
        return super().keys()


# ── Local SQLite ──────────────────────────────────────────

class _SqliteConn:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path), timeout=30, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        try:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
        except sqlite3.Error:
            pass

    def execute(self, sql: str, params: Sequence[Any] | None = None):
        cur = self._conn.execute(sql, tuple(params or ()))
        return _SqliteCursor(cur)

    def executescript(self, sql: str):
        self._conn.executescript(sql)
        return self

    def commit(self):
        self._conn.commit()

    def close(self):
        self._conn.close()


class _SqliteCursor:
    def __init__(self, cur: sqlite3.Cursor):
        self._cur = cur

    def fetchone(self) -> Row | None:
        row = self._cur.fetchone()
        if row is None:
            return None
        return Row({k: row[k] for k in row.keys()})

    def fetchall(self) -> list[Row]:
        rows = self._cur.fetchall()
        return [Row({k: r[k] for k in r.keys()}) for r in rows]

    @property
    def lastrowid(self) -> Any:
        return self._cur.lastrowid

    @property
    def rowcount(self) -> int:
        return self._cur.rowcount


# ── Turso HTTP (Hrana pipeline v2) ────────────────────────

def _encode_arg(value: Any) -> dict[str, Any]:
    if value is None:
        return {"type": "null"}
    if isinstance(value, bool):
        return {"type": "integer", "value": "1" if value else "0"}
    if isinstance(value, int):
        return {"type": "integer", "value": str(value)}
    if isinstance(value, float):
        return {"type": "float", "value": value}
    if isinstance(value, (bytes, bytearray)):
        import base64
        return {"type": "blob", "base64": base64.b64encode(value).decode("ascii")}
    return {"type": "text", "value": str(value)}


def _pipeline_url(db_url: str) -> str:
    # libsql://xxx.turso.io  →  https://xxx.turso.io/v2/pipeline
    u = db_url.strip()
    if u.startswith("libsql://"):
        u = "https://" + u[len("libsql://") :]
    if u.startswith("https://") and not u.endswith("/v2/pipeline"):
        u = u.rstrip("/") + "/v2/pipeline"
    return u


class _TursoConn:
    """Minimal sqlite3-like wrapper over Turso HTTP pipeline API."""

    def __init__(self, db_url: str, auth_token: str):
        self._url = _pipeline_url(db_url)
        self._token = auth_token
        self._baton: str | None = None
        self._client = httpx.Client(
            timeout=30.0,
            headers={
                "Authorization": f"Bearer {auth_token}",
                "Content-Type": "application/json",
            },
        )

    def _request(self, requests: list[dict[str, Any]]) -> dict[str, Any]:
        payload: dict[str, Any] = {"requests": requests}
        if self._baton:
            payload["baton"] = self._baton
        resp = self._client.post(self._url, content=json.dumps(payload))
        resp.raise_for_status()
        data = resp.json()
        if data.get("baton"):
            self._baton = data["baton"]
        # surface first error
        for item in data.get("results") or []:
            if item.get("type") == "error":
                err = item.get("error") or {}
                raise RuntimeError(err.get("message") or str(err) or "Turso query error")
        return data

    def execute(self, sql: str, params: Sequence[Any] | None = None):
        stmt: dict[str, Any] = {"sql": sql}
        if params:
            stmt["args"] = [_encode_arg(p) for p in params]
        data = self._request([{"type": "execute", "stmt": stmt}])
        results = data.get("results") or []
        exec_result = None
        for item in results:
            if item.get("type") == "ok":
                response = item.get("response") or {}
                if response.get("type") == "execute":
                    exec_result = response.get("result") or {}
                    break
        return _TursoCursor(exec_result or {})

    def executescript(self, sql: str):
        # Split on semicolons carefully enough for our schema scripts
        parts = [p.strip() for p in sql.split(";") if p.strip()]
        reqs = [{"type": "execute", "stmt": {"sql": p}} for p in parts]
        if reqs:
            self._request(reqs)
        return self

    def commit(self):
        # each pipeline execute is auto-committed on remote
        return None

    def close(self):
        try:
            if self._baton:
                self._request([{"type": "close"}])
        except Exception:
            pass
        self._client.close()


class _TursoCursor:
    def __init__(self, result: dict[str, Any]):
        self._result = result
        cols = result.get("cols") or []
        self._colnames = [c.get("name", f"c{i}") for i, c in enumerate(cols)]
        self._rows_raw = result.get("rows") or []
        self._affected = int(result.get("affected_row_count") or 0)
        self.lastrowid = result.get("last_insert_rowid")
        self.rowcount = self._affected

    def _decode_cell(self, cell: Any) -> Any:
        if cell is None:
            return None
        if isinstance(cell, dict):
            t = cell.get("type")
            if t == "null":
                return None
            if t in ("text", "float", "integer", "blob"):
                if t == "integer":
                    try:
                        return int(cell.get("value"))
                    except Exception:
                        return cell.get("value")
                if t == "float":
                    return cell.get("value")
                if t == "blob":
                    return cell.get("base64")
                return cell.get("value")
            # newer shapes
            if "value" in cell:
                return cell["value"]
        return cell

    def _row_at(self, raw_row: Any) -> Row:
        # raw_row is list of cell objects
        values: list[Any]
        if isinstance(raw_row, list):
            values = [self._decode_cell(c) for c in raw_row]
        else:
            values = [raw_row]
        data = {}
        for i, name in enumerate(self._colnames):
            data[name] = values[i] if i < len(values) else None
        return Row(data)

    def fetchone(self) -> Row | None:
        if not self._rows_raw:
            return None
        raw = self._rows_raw.pop(0)
        return self._row_at(raw)

    def fetchall(self) -> list[Row]:
        rows = [self._row_at(r) for r in self._rows_raw]
        self._rows_raw = []
        return rows


# ── Public API ────────────────────────────────────────────

def connect_auth(storage_dir_path: Path | str | None = None):
    """Open the auth database (Turso if configured, else local SQLite)."""
    with _lock:
        if turso_configured():
            return _TursoConn(_turso_url(), _turso_token())
        path = auth_db_path(storage_dir_path)
        return _SqliteConn(path)


def db_status() -> dict[str, Any]:
    return {
        "backend": backend_name(),
        "turso_configured": turso_configured(),
        "local_path": str(auth_db_path()),
        "durable": turso_configured(),
    }
