"""Shared fixtures for AGT adapter integration tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixture_agt_current() -> dict:
    """Current AGT export bundle with all 6 event types."""
    return json.loads((FIXTURES_DIR / "agt_current.json").read_text())


@pytest.fixture
def fixture_agt_old() -> dict:
    """Older AGT format (v4.0) — missing policy_decision."""
    return json.loads((FIXTURES_DIR / "agt_old.json").read_text())


@pytest.fixture
def fixture_agt_extra() -> dict:
    """AGT export with unknown future fields (forward compat test)."""
    return json.loads((FIXTURES_DIR / "agt_extra.json").read_text())


@pytest.fixture
def fixture_agt_malformed() -> dict:
    """Malformed AGT entry (missing required field)."""
    return json.loads((FIXTURES_DIR / "agt_malformed.json").read_text())


@pytest.fixture
def fixture_agt_fileaudit() -> list[dict]:
    """FileAuditSink JSONL format with HMAC signatures."""
    raw = (FIXTURES_DIR / "agt_fileaudit.jsonl").read_text()
    return [json.loads(line) for line in raw.strip().split("\n") if line.strip()]


@pytest.fixture
def fixture_agt_cloudevents() -> list[dict]:
    """CloudEvents v1.0 envelope from export_cloudevents()."""
    return json.loads((FIXTURES_DIR / "agt_cloudevents.json").read_text())
