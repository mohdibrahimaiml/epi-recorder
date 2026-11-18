"""Tests for privacy-safe identity signal extraction."""

from __future__ import annotations

import json
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


def test_org_signals_can_be_opted_out(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("EPI_TELEMETRY_ORG_SIGNALS", "0")
    monkeypatch.setattr(
        identity_signals,
        "get_identity_signals",
        lambda: {"email_domain": "example.com", "github_org": "acme"},
    )
    monkeypatch.setattr(identity_signals, "_get_auth_identity", lambda: {"user_id": "usr_123"})
    result = identity_signals.attach_identity_signals({"command": "test"})
    assert result == {"command": "test", "user_id": "usr_123"}


def test_account_fields_need_the_pilot_opt_in(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EPI_HOME", str(tmp_path))
    # The legacy login file must never be enough on its own.
    (tmp_path / "auth.json").write_text(
        json.dumps({"token": "t", "user_id": "usr_1", "org": "org_1"}), encoding="utf-8"
    )
    (tmp_path / "cloud.json").write_text(
        json.dumps({"org_id": "org_2", "api_key": "epik_x"}), encoding="utf-8"
    )
    assert identity_signals._get_auth_identity() == {}
    assert "user_id" not in identity_signals.attach_identity_signals({})


def test_account_fields_come_from_cloud_json_after_opt_in(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EPI_HOME", str(tmp_path))
    (tmp_path / "pilot_signup.json").write_text(
        json.dumps({"link_telemetry": True}), encoding="utf-8"
    )
    (tmp_path / "auth.json").write_text(
        json.dumps({"token": "t", "user_id": "usr_legacy", "org": "org_legacy"}), encoding="utf-8"
    )
    (tmp_path / "cloud.json").write_text(
        json.dumps({"org_id": "org_cloud", "api_key": "epik_x"}), encoding="utf-8"
    )
    identity = identity_signals._get_auth_identity()
    assert identity == {"org_id": "org_cloud"}


def test_attach_sends_no_account_fields_without_opt_in(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EPI_HOME", str(tmp_path))
    (tmp_path / "auth.json").write_text(
        json.dumps({"token": "t", "user_id": "usr_1", "org": "org_1"}), encoding="utf-8"
    )
    monkeypatch.setattr(identity_signals, "get_identity_signals", lambda: {})
    assert identity_signals.attach_identity_signals({"command": "test"}) == {"command": "test"}
