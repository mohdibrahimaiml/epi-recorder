"""Tests for EPI CLI local auth storage."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from epi_cli import auth_cmd


def test_save_and_load_auth(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("EPI_HOME", str(tmp_path))
    auth_cmd.save_auth("token_abc", "usr_123", "acme.com")
    data = auth_cmd.load_auth()
    assert data["token"] == "token_abc"
    assert data["user_id"] == "usr_123"
    assert data["org"] == "acme.com"


def test_clear_auth(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("EPI_HOME", str(tmp_path))
    auth_cmd.save_auth("token", "user", "")
    auth_cmd.clear_auth()
    assert auth_cmd.load_auth() is None


def test_load_auth_returns_none_when_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("EPI_HOME", str(tmp_path))
    assert auth_cmd.load_auth() is None


def test_load_auth_returns_none_for_malformed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("EPI_HOME", str(tmp_path))
    path = auth_cmd._auth_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("not json", encoding="utf-8")
    assert auth_cmd.load_auth() is None


def test_base_portal_url_derived_from_telemetry(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("EPI_TELEMETRY_URL", "https://api.example.com/api/telemetry/events")
    assert auth_cmd._base_portal_url() == "https://api.example.com"
