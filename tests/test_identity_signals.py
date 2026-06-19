"""Tests for privacy-safe identity signal extraction."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from epi_core import identity_signals


@pytest.fixture(autouse=True)
def _reset_cache(monkeypatch: pytest.MonkeyPatch):
    """Clear the module-level signal cache before each test."""
    monkeypatch.setattr(identity_signals, "_signals", None)


def test_extract_email_domain():
    assert identity_signals._extract_domain("John Doe <john@example.com>") == "example.com"
    assert identity_signals._extract_domain("  Jane@Company.org ") == "company.org"
    assert identity_signals._extract_domain("not-an-email") is None


def test_extract_github_org_from_ssh():
    assert identity_signals._extract_github_org("git@github.com:openai/project.git") == "openai"
    assert identity_signals._extract_github_org("git@github.com:microsoft/vscode") == "microsoft"


def test_extract_github_org_from_https():
    assert identity_signals._extract_github_org("https://github.com/anthropic/claude-code.git") == "anthropic"
    assert identity_signals._extract_github_org("http://github.com/epi-recorder/epi-recorder") == "epi-recorder"


def test_collect_signals_from_git_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(tmp_path)
    subprocess.run(["git", "init"], check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "dev@acme.com"], check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Dev"], check=True, capture_output=True)
    subprocess.run(["git", "remote", "add", "origin", "git@github.com:acme-corp/product.git"], check=True, capture_output=True)

    signals = identity_signals.get_identity_signals()
    assert signals == {"email_domain": "acme.com", "github_org": "acme-corp"}


def test_signals_are_cached(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(tmp_path)
    subprocess.run(["git", "init"], check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "dev@acme.com"], check=True, capture_output=True)

    first = identity_signals.get_identity_signals()
    # Even if cwd changes, cached result should be returned.
    monkeypatch.setattr(identity_signals, "_collect_signals", lambda: {"github_org": "spoof"})
    second = identity_signals.get_identity_signals()
    assert second == first


def test_attach_identity_signals_merges_values():
    monkeypatch = pytest.MonkeyPatch()
    with monkeypatch.context() as m:
        m.setattr(identity_signals, "get_identity_signals", lambda: {"email_domain": "example.com"})
        m.setattr(
            identity_signals,
            "_get_auth_identity",
            lambda: {"user_id": "usr_123", "org_id": "example.com"},
        )
        result = identity_signals.attach_identity_signals({"command": "test"})
        assert result["command"] == "test"
        assert result["email_domain"] == "example.com"
        assert result["user_id"] == "usr_123"
        assert result["org_id"] == "example.com"
