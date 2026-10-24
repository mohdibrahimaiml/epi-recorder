"""Durable storage for contact / waitlist submissions.

Uses the same backend as auth (`verify_portal.db`): Turso/libSQL when
TURSO_DATABASE_URL + TURSO_AUTH_TOKEN are configured, otherwise local SQLite
under EPI_STORAGE_DIR. On Render the free plan has an ephemeral disk, so a
local-only write is lost on restart; Turso keeps the lead.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from verify_portal.db import connect_auth

log = logging.getLogger("epi.contact")

DDL = (
    "CREATE TABLE IF NOT EXISTS contact_submissions ("
    "id INTEGER PRIMARY KEY AUTOINCREMENT,"
    "created_at TEXT NOT NULL,"
    "name TEXT NOT NULL,"
    "email TEXT NOT NULL,"
    "company TEXT DEFAULT '',"
    "tier TEXT DEFAULT '',"
    "use_case TEXT DEFAULT ''"
    ")"
)


def init_contact_table() -> None:
    conn = connect_auth()
    try:
        conn.executescript(DDL)
        conn.commit()
    finally:
        conn.close()


def save_submission(submission) -> None:
    """Insert one submission; raises on failure so the caller can fall back."""
    conn = connect_auth()
    try:
        conn.execute(
            "INSERT INTO contact_submissions "
            "(created_at, name, email, company, tier, use_case) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                datetime.now(UTC).isoformat(),
                submission.name,
                submission.email,
                submission.company,
                submission.tier,
                submission.use_case,
            ),
        )
        conn.commit()
    finally:
        conn.close()
