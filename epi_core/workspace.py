"""
Shared recording workspace helpers.

These utilities centralize temp/workspace creation so recording flows can
survive restrictive Windows temp environments and fail clearly when no
usable workspace is available.
"""

from __future__ import annotations

import os
import shutil
import tempfile
import uuid
from pathlib import Path


class RecordingWorkspaceError(RuntimeError):
    """Raised when EPI cannot allocate a usable recording workspace."""


def ensure_workspace_writable(path: Path) -> Path:
    """
    Ensure a workspace directory is writable for JSON and SQLite files.

    Creates the directory, writes a probe file, and touches a SQLite-style
    temp file to confirm the location is actually usable.
    """
    path = Path(path)
    try:
        path.mkdir(parents=True, exist_ok=True)

        probe = path / ".epi_write_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)

        sqlite_probe = path / ".epi_sqlite_probe.db"
        sqlite_probe.write_bytes(b"")
        sqlite_probe.unlink(missing_ok=True)
    except Exception as exc:
        raise RecordingWorkspaceError(
            f"EPI could not prepare a writable recording workspace at '{path}'. "
            "This usually means the temp directory is blocked or not writable. "
            "Try setting TMP/TEMP to a writable folder and rerun."
        ) from exc

    return path


def create_recording_workspace(prefix: str) -> Path:
    """
    Create a writable workspace directory using a fallback chain.

    Order:
    1. Explicit TMP/TEMP/TMPDIR values
    2. tempfile.gettempdir()
    3. current working directory fallback
    4. user home fallback
    """
    attempted: list[str] = []
    candidate_roots: list[Path] = []

    for env_name in ("TMP", "TEMP", "TMPDIR"):
        value = os.environ.get(env_name)
        if value:
            candidate_roots.append(Path(value))

    try:
        candidate_roots.append(Path(tempfile.gettempdir()))
    except Exception:
        pass

    candidate_roots.append(Path.cwd() / ".epi-temp")
    candidate_roots.append(Path.home() / ".epi-temp")

    seen: set[str] = set()
    unique_roots: list[Path] = []
    for root in candidate_roots:
        root_str = str(root)
        if root_str not in seen:
            seen.add(root_str)
            unique_roots.append(root)

    for root in unique_roots:
        workspace = root / f"{prefix}{uuid.uuid4().hex}"
        attempted.append(str(workspace))
        try:
            return ensure_workspace_writable(workspace)
        except RecordingWorkspaceError:
            shutil.rmtree(workspace, ignore_errors=True)
            continue

    attempted_text = "\n".join(f"  - {path}" for path in attempted) or "  - <none>"
    raise RecordingWorkspaceError(
        "EPI could not find any usable recording workspace.\n"
        "Attempted locations:\n"
        f"{attempted_text}\n"
        "Set TMP or TEMP to a writable folder and rerun."
    )
