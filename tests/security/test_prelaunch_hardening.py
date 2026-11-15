"""Regression tests for the pre-launch security audit fixes.

One test per finding, named after the finding id in AUDIT.md. These exist so a
future refactor cannot quietly reintroduce the bug: every one of them fails
against the code as it was before the audit.
"""

from __future__ import annotations

import hashlib
import os
import time

import pytest

pytestmark = pytest.mark.security


# --- 2.7 / 5.2 : OAuth open redirect -----------------------------------------


def test_a_client_with_no_registered_redirect_uri_gets_no_redirect(monkeypatch):
    """2.7. An empty registration list must not mean 'any URI is fine'."""
    monkeypatch.setenv("EPI_OAUTH_SECRET", "x" * 40)
    from epi_mcp import oauth

    oauth.CLIENTS.clear()
    reg = oauth.register_client({"redirect_uris": []})
    assert oauth.redirect_allowed(reg["client_id"], "https://evil.example/cb") is False
    assert oauth.redirect_allowed(reg["client_id"], "") is False


def test_only_the_registered_redirect_uri_is_allowed(monkeypatch):
    """2.7. Exact match against what the client registered.</summary>"""
    monkeypatch.setenv("EPI_OAUTH_SECRET", "x" * 40)
    from epi_mcp import oauth

    oauth.CLIENTS.clear()
    reg = oauth.register_client({"redirect_uris": ["https://ok.example/cb"]})
    assert oauth.redirect_allowed(reg["client_id"], "https://ok.example/cb") is True
    assert oauth.redirect_allowed(reg["client_id"], "https://evil.example/cb") is False
    # Suffix and prefix tricks must not pass either.
    assert oauth.redirect_allowed(reg["client_id"], "https://ok.example/cb.evil.example") is False
    assert oauth.redirect_allowed(reg["client_id"], "https://ok.example/c") is False


# --- 4.3 : retention actually deletes ---------------------------------------


def test_purge_keeps_the_entry_when_the_delete_fails(monkeypatch, tmp_path):
    """4.3.1. A failed unlink must not be forgotten, or the file leaks forever."""
    from epi_mcp import tools

    seal_dir = tmp_path / f"{tools._SEAL_DIR_PREFIX}leak"
    seal_dir.mkdir()
    target = seal_dir / "conversation.epi"
    target.write_bytes(b"secret conversation")

    artifact_id = "b" * 16
    tools.ARTIFACTS[artifact_id] = str(target)
    tools._ARTIFACT_EXPIRY[artifact_id] = 0.0  # long expired
    tools._ARTIFACT_OWNER[artifact_id] = ("owner", 12)

    def refuse(_path, *_args, **_kwargs):
        raise PermissionError("file is locked")

    monkeypatch.setattr("shutil.rmtree", refuse)

    assert tools.purge_expired_artifacts(now=time.time()) == 0
    # Still tracked, so the next sweep tries again instead of orphaning it.
    assert artifact_id in tools._ARTIFACT_EXPIRY
    assert artifact_id in tools.ARTIFACTS

    monkeypatch.undo()
    tools._ARTIFACT_EXPIRY[artifact_id] = 0.0
    assert tools.purge_expired_artifacts(now=time.time()) == 1
    assert not seal_dir.exists()
    assert artifact_id not in tools._ARTIFACT_EXPIRY


def test_purge_removes_a_normal_expired_seal(tmp_path):
    """4.3.1. The happy path still deletes and forgets."""
    from epi_mcp import tools

    seal_dir = tmp_path / f"{tools._SEAL_DIR_PREFIX}ok"
    seal_dir.mkdir()
    target = seal_dir / "conversation.epi"
    target.write_bytes(b"bye")

    artifact_id = "c" * 16
    tools.ARTIFACTS[artifact_id] = str(target)
    tools._ARTIFACT_EXPIRY[artifact_id] = 0.0
    tools._ARTIFACT_OWNER[artifact_id] = ("owner", 3)

    assert tools.purge_expired_artifacts(now=time.time()) == 1
    assert not seal_dir.exists()
    assert artifact_id not in tools.ARTIFACTS
    assert artifact_id not in tools._ARTIFACT_OWNER


def test_orphaned_seal_directories_from_a_previous_process_are_swept(monkeypatch, tmp_path):
    """4.3.2. The registry is in memory, so a restart must not orphan files."""
    from epi_mcp import tools

    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))

    stale = tmp_path / f"{tools._SEAL_DIR_PREFIX}old"
    stale.mkdir()
    old = time.time() - 5 * 24 * 3600
    os.utime(stale, (old, old))

    fresh = tmp_path / f"{tools._SEAL_DIR_PREFIX}new"
    fresh.mkdir()

    assert tools.sweep_orphaned_seals() == 1
    assert not stale.exists()
    assert fresh.exists()  # inside the retention window, left alone


# --- 4.2 : artifact ownership ----------------------------------------------


def test_an_artifact_belonging_to_another_caller_is_not_readable():
    """4.2.1. The id is a content hash, not a capability."""
    from epi_mcp import http, tools

    artifact_id = "d" * 16
    tools._ARTIFACT_OWNER[artifact_id] = (
        hashlib.sha256(b"bob").hexdigest()[:16],
        10,
    )
    token = tools._current_subject.set("alice")
    try:
        assert http._may_read_artifact(artifact_id) is False
    finally:
        tools._current_subject.reset(token)


def test_a_caller_can_read_their_own_artifact_and_a_link_token_still_works():
    """4.2.1. Owner reads, and the download capability is unaffected."""
    from epi_mcp import http, tools

    artifact_id = "e" * 16
    tools._ARTIFACT_OWNER[artifact_id] = (
        hashlib.sha256(b"alice").hexdigest()[:16],
        10,
    )

    token = tools._current_subject.set("alice")
    try:
        assert http._may_read_artifact(artifact_id) is True
    finally:
        tools._current_subject.reset(token)

    link = tools._current_subject.set("download-link")
    try:
        assert http._may_read_artifact(artifact_id) is True
    finally:
        tools._current_subject.reset(link)


def test_an_unmanaged_artifact_stays_readable():
    """4.2.1. Operator-sealed files carry no owner record and must keep working."""
    from epi_mcp import http, tools

    artifact_id = "f" * 16
    tools._ARTIFACT_OWNER.pop(artifact_id, None)
    token = tools._current_subject.set("alice")
    try:
        assert http._may_read_artifact(artifact_id) is True
    finally:
        tools._current_subject.reset(token)


# --- 12.4 : self-serve deletion --------------------------------------------


def _seed_artifact(tmp_path, artifact_id: str, subject: str):
    from epi_mcp import tools

    seal_dir = tmp_path / f"{tools._SEAL_DIR_PREFIX}{artifact_id[:6]}"
    seal_dir.mkdir()
    target = seal_dir / "record.epi"
    target.write_bytes(b"conversation")
    tools.ARTIFACTS[artifact_id] = str(target)
    tools._ARTIFACT_EXPIRY[artifact_id] = time.time() + 3600
    tools._ARTIFACT_OWNER[artifact_id] = (
        hashlib.sha256(subject.encode("utf-8")).hexdigest()[:16],
        target.stat().st_size,
    )
    return seal_dir


def test_a_caller_can_delete_their_own_artifact(tmp_path):
    """12.4. Erasure must not depend on someone answering email."""
    from epi_mcp import tools

    artifact_id = "1" * 16
    seal_dir = _seed_artifact(tmp_path, artifact_id, "alice")
    token = tools._current_subject.set("alice")
    try:
        out = tools.epi_delete_artifact_tool(artifact_id)
    finally:
        tools._current_subject.reset(token)

    assert out["deleted"] is True
    assert not seal_dir.exists()
    assert artifact_id not in tools.ARTIFACTS
    assert artifact_id not in tools._ARTIFACT_EXPIRY
    assert artifact_id not in tools._ARTIFACT_OWNER


def test_another_caller_cannot_delete_it(tmp_path):
    """12.4. Refusal is worded as a miss so the id cannot be probed."""
    from epi_mcp import tools

    artifact_id = "2" * 16
    seal_dir = _seed_artifact(tmp_path, artifact_id, "bob")
    token = tools._current_subject.set("alice")
    try:
        with pytest.raises(ValueError, match="no longer on the server"):
            tools.epi_delete_artifact_tool(artifact_id)
    finally:
        tools._current_subject.reset(token)

    assert seal_dir.exists()
    assert artifact_id in tools.ARTIFACTS


def test_the_operator_can_delete_any_artifact(tmp_path):
    """12.4. Local stdio runs are the operator and may clean up anything."""
    from epi_mcp import tools

    artifact_id = "3" * 16
    seal_dir = _seed_artifact(tmp_path, artifact_id, "bob")
    token = tools._current_subject.set("operator")
    try:
        out = tools.epi_delete_artifact_tool(artifact_id)
    finally:
        tools._current_subject.reset(token)

    assert out["deleted"] is True
    assert not seal_dir.exists()


def test_deleting_an_unknown_artifact_raises():
    from epi_mcp import tools

    token = tools._current_subject.set("alice")
    try:
        with pytest.raises(ValueError, match="no longer on the server"):
            tools.epi_delete_artifact_tool("0123456789abcdef")
    finally:
        tools._current_subject.reset(token)


# --- 2.7 / 5.5 : loopback redirect must be a real loopback ------------------


@pytest.mark.parametrize(
    "uri",
    [
        "http://localhost.evil.example/cb",
        "http://127.0.0.1.evil.example/cb",
        "https://localhost.evil.example/cb",
        "http://localhost.evil.example:8080/cb",
        "javascript:alert(1)",
        "ftp://localhost/cb",
        "//localhost/cb",
    ],
)
def test_lookalike_loopback_redirects_are_refused(uri):
    """5.5. startswith() accepted localhost.evil.example and leaked the token."""
    from verify_portal.auth import is_loopback_redirect

    assert is_loopback_redirect(uri) is False


@pytest.mark.parametrize(
    "uri",
    [
        "http://localhost:8765/cb",
        "http://127.0.0.1:8765/cb",
        "http://[::1]:8765/cb",
        "epi://callback",
    ],
)
def test_real_loopback_redirects_still_work(uri):
    """5.5. The CLI sign-in path must keep working."""
    from verify_portal.auth import is_loopback_redirect

    assert is_loopback_redirect(uri) is True
