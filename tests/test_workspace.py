import sqlite3
import tempfile

import pytest

from epi_core.storage import EpiStorage
from epi_core.workspace import RecordingWorkspaceError, create_recording_workspace


def test_create_recording_workspace_falls_back_to_cwd(monkeypatch, tmp_path):
    blocked = tmp_path / "blocked-root"
    blocked.write_text("not a directory", encoding="utf-8")

    monkeypatch.setenv("TMP", str(blocked))
    monkeypatch.setenv("TEMP", str(blocked))
    monkeypatch.setenv("TMPDIR", str(blocked))
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(blocked))
    monkeypatch.chdir(tmp_path)

    workspace = create_recording_workspace("epi_record_")
    assert workspace.exists()
    assert tmp_path in workspace.parents


def test_create_recording_workspace_raises_clear_error(monkeypatch):
    monkeypatch.setattr(
        "epi_core.workspace.ensure_workspace_writable",
        lambda path: (_ for _ in ()).throw(RecordingWorkspaceError("blocked")),
    )

    with pytest.raises(RecordingWorkspaceError) as exc:
        create_recording_workspace("epi_record_")

    assert "Set TMP or TEMP to a writable folder" in str(exc.value)


def test_storage_translates_sqlite_error(tmp_path, monkeypatch):
    def _raise(*args, **kwargs):
        raise sqlite3.OperationalError("unable to open database file")

    monkeypatch.setattr(sqlite3, "connect", _raise)

    with pytest.raises(RecordingWorkspaceError) as exc:
        EpiStorage("session", tmp_path / "workspace")

    assert "recording database" in str(exc.value)
