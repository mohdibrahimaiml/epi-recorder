"""
Tests for epi_core/aiuc1_mapping.py

Covers: domain mapping (A-F), evidence detection, timestamp monotonicity,
and edge cases.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from epi_core.aiuc1_mapping import (
    AIUC1DomainStatus,
    _check_timestamp_monotonicity,
    _detect_error_steps,
    _detect_redaction_in_steps,
    _has_file_in_manifest,
    aiuc1_summary,
    map_verification_to_aiuc1,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_report(
    *,
    signature_valid: bool = True,
    integrity_ok: bool = True,
    chain_ok: bool = True,
    sequence_ok: bool = True,
    completeness_ok: bool = True,
    scitt_entry_id: str | None = "abc123",
    identity_status: str = "KNOWN",
) -> dict[str, Any]:
    """Build a minimal verification report."""
    return {
        "facts": {
            "signature_valid": signature_valid,
            "integrity_ok": integrity_ok,
            "chain_ok": chain_ok,
            "sequence_ok": sequence_ok,
            "completeness_ok": completeness_ok,
        },
        "identity": {
            "status": identity_status,
            "scitt": {"entry_id": scitt_entry_id} if scitt_entry_id else None,
        },
    }


def _make_manifest(file_manifest: dict[str, str] | None = None) -> Any:
    """Build a mock manifest with the given file_manifest."""
    class MockManifest:
        def __init__(self, files: dict[str, str]) -> None:
            self.file_manifest = files

    return MockManifest(file_manifest or {})


# ---------------------------------------------------------------------------
# Domain mapping — happy path
# ---------------------------------------------------------------------------


def test_all_domains_pass_with_full_evidence() -> None:
    report = _make_report()
    manifest = _make_manifest(
        {
            "review.json": "hash1",
            "policy.json": "hash2",
            "analysis.json": "hash3",
            "environment.json": "hash4",
        }
    )
    steps = [
        {"index": 0, "timestamp": "2026-01-01T00:00:00Z", "kind": "llm.request"},
        {
            "index": 1,
            "timestamp": "2026-01-01T00:00:01Z",
            "kind": "llm.response",
            "content": {"text": "HMAC-SHA256:abc ***REDACTED***"},
        },
        {"index": 2, "timestamp": "2026-01-01T00:00:02Z", "kind": "llm.error"},
    ]

    statuses = map_verification_to_aiuc1(report, manifest, steps)
    summary = aiuc1_summary(statuses)

    assert summary["overall"] == "PASS"
    for domain_id in "ABCDEF":
        assert statuses[domain_id].status == "PASS", f"Domain {domain_id} should PASS"


# ---------------------------------------------------------------------------
# Domain mapping — missing evidence
# ---------------------------------------------------------------------------


def test_domain_a_fails_without_environment() -> None:
    report = _make_report()
    manifest = _make_manifest({})  # no environment.json
    statuses = map_verification_to_aiuc1(report, manifest, [])
    assert statuses["A"].status in ("FAIL", "PARTIAL")
    assert "environment_isolated" in statuses["A"].missing


def test_domain_b_partial_without_scitt() -> None:
    report = _make_report(scitt_entry_id=None)
    manifest = _make_manifest({})
    statuses = map_verification_to_aiuc1(report, manifest, [])
    # signature_valid + integrity_ok + chain_ok are present, scitt is missing
    assert statuses["B"].status == "PARTIAL"
    assert "scitt_receipt_present" in statuses["B"].missing


def test_domain_c_fails_with_broken_chain() -> None:
    report = _make_report(chain_ok=False)
    manifest = _make_manifest({})
    statuses = map_verification_to_aiuc1(report, manifest, [])
    assert statuses["C"].status in ("FAIL", "PARTIAL")
    assert "chain_ok" in statuses["C"].missing


def test_domain_e_fails_without_identity() -> None:
    report = _make_report(identity_status="UNKNOWN")
    manifest = _make_manifest({"review.json": "h", "policy.json": "h"})
    statuses = map_verification_to_aiuc1(report, manifest, [])
    assert statuses["E"].status in ("FAIL", "PARTIAL")
    assert "identity_known" in statuses["E"].missing


def test_domain_f_partial_without_analysis() -> None:
    report = _make_report()
    manifest = _make_manifest({"environment.json": "h"})  # no analysis.json
    statuses = map_verification_to_aiuc1(report, manifest, [])
    assert statuses["F"].status in ("FAIL", "PARTIAL")
    assert "analysis_present" in statuses["F"].missing


# ---------------------------------------------------------------------------
# _check_timestamp_monotonicity
# ---------------------------------------------------------------------------


def test_timestamp_monotonic_empty_steps() -> None:
    assert _check_timestamp_monotonicity([]) is True
    assert _check_timestamp_monotonicity(None) is True


def test_timestamp_monotonic_single_step() -> None:
    step = {"timestamp": "2026-01-01T00:00:00Z"}
    assert _check_timestamp_monotonicity([step]) is True


def test_timestamp_monotonic_iso_strings_ok() -> None:
    steps = [
        {"timestamp": "2026-01-01T00:00:00Z"},
        {"timestamp": "2026-01-01T00:00:01Z"},
        {"timestamp": "2026-01-01T00:00:02Z"},
    ]
    assert _check_timestamp_monotonicity(steps) is True


def test_timestamp_monotonic_iso_strings_out_of_order() -> None:
    steps = [
        {"timestamp": "2026-01-01T00:00:02Z"},
        {"timestamp": "2026-01-01T00:00:01Z"},
        {"timestamp": "2026-01-01T00:00:00Z"},
    ]
    assert _check_timestamp_monotonicity(steps) is False


def test_timestamp_monotonic_timestamp_ns_ok() -> None:
    steps = [
        {"content": {"timestamp_ns": 1_000_000_000}},
        {"content": {"timestamp_ns": 2_000_000_000}},
        {"content": {"timestamp_ns": 3_000_000_000}},
    ]
    assert _check_timestamp_monotonicity(steps) is True


def test_timestamp_monotonic_timestamp_ns_out_of_order() -> None:
    steps = [
        {"content": {"timestamp_ns": 3_000_000_000}},
        {"content": {"timestamp_ns": 2_000_000_000}},
        {"content": {"timestamp_ns": 1_000_000_000}},
    ]
    assert _check_timestamp_monotonicity(steps) is False


def test_timestamp_monotonic_mixed_prefers_ns() -> None:
    """When some steps have timestamp_ns, the function must use ONLY
    timestamp_ns and reject steps that lack it."""
    steps = [
        {"content": {"timestamp_ns": 1_000_000_000}},
        {"timestamp": "2026-01-01T00:00:01Z"},  # missing timestamp_ns
    ]
    assert _check_timestamp_monotonicity(steps) is False


def test_timestamp_monotonic_datetime_objects() -> None:
    t = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    steps = [
        {"timestamp": t},
        {"timestamp": t + timedelta(seconds=1)},
    ]
    assert _check_timestamp_monotonicity(steps) is True


def test_timestamp_monotonic_missing_all_timestamps() -> None:
    """Steps with no timestamp info at all should return False."""
    steps = [
        {"index": 0, "kind": "llm.request"},
        {"index": 1, "kind": "llm.response"},
    ]
    assert _check_timestamp_monotonicity(steps) is False


# ---------------------------------------------------------------------------
# _has_file_in_manifest
# ---------------------------------------------------------------------------


def test_has_file_in_manifest_direct() -> None:
    m = _make_manifest({"review.json": "abc"})
    assert _has_file_in_manifest(m, "review.json") is True
    assert _has_file_in_manifest(m, "policy.json") is False


def test_has_file_in_manifest_nested() -> None:
    m = _make_manifest({"artifacts/review.json": "abc"})
    assert _has_file_in_manifest(m, "review.json") is True


def test_has_file_in_manifest_none() -> None:
    assert _has_file_in_manifest(None, "review.json") is False


# ---------------------------------------------------------------------------
# _detect_redaction_in_steps
# ---------------------------------------------------------------------------


def test_detect_redaction_present() -> None:
    steps = [
        {"content": {"text": "HMAC-SHA256:abc ***REDACTED***"}},
    ]
    assert _detect_redaction_in_steps(steps) is True


def test_detect_redaction_absent() -> None:
    steps = [
        {"content": {"text": "normal text"}},
    ]
    assert _detect_redaction_in_steps(steps) is False


def test_detect_redaction_empty() -> None:
    assert _detect_redaction_in_steps([]) is False
    assert _detect_redaction_in_steps(None) is False


# ---------------------------------------------------------------------------
# _detect_error_steps
# ---------------------------------------------------------------------------


def test_detect_error_steps_present() -> None:
    steps = [
        {"kind": "llm.error", "content": {"message": "oom"}},
    ]
    assert _detect_error_steps(steps) is True


def test_detect_error_steps_absent() -> None:
    steps = [
        {"kind": "llm.request"},
        {"kind": "llm.response"},
    ]
    assert _detect_error_steps(steps) is False


# ---------------------------------------------------------------------------
# aiuc1_summary
# ---------------------------------------------------------------------------


def test_aiuc1_summary_overall_pass() -> None:
    statuses = {
        "A": AIUC1DomainStatus("A", "Data", "PASS"),
        "B": AIUC1DomainStatus("B", "Security", "PASS"),
    }
    summary = aiuc1_summary(statuses)
    assert summary["overall"] == "PASS"
    assert len(summary["domains"]) == 2


def test_aiuc1_summary_overall_fail() -> None:
    statuses = {
        "A": AIUC1DomainStatus("A", "Data", "PASS"),
        "B": AIUC1DomainStatus("B", "Security", "FAIL"),
    }
    summary = aiuc1_summary(statuses)
    assert summary["overall"] == "FAIL"


def test_aiuc1_summary_overall_partial() -> None:
    statuses = {
        "A": AIUC1DomainStatus("A", "Data", "PASS"),
        "B": AIUC1DomainStatus("B", "Security", "PARTIAL"),
    }
    summary = aiuc1_summary(statuses)
    assert summary["overall"] == "PARTIAL"
