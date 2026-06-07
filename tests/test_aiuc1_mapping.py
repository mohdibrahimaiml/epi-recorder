"""
Tests for epi_core/aiuc1_mapping.py

Covers: domain mapping (A-F), substantive redaction verification,
review binding checks, analysis validation, and edge cases.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from epi_core.aiuc1_mapping import (
    AIUC1DomainStatus,
    _check_analysis_has_findings,
    _check_analysis_passes_complete,
    _check_redaction_completeness,
    _check_redaction_coverage,
    _check_review_binding,
    _check_review_signed,
    _check_timestamp_monotonicity,
    _detect_error_steps,
    _detect_redaction_categories,
    _detect_redaction_in_steps,
    _has_file_in_manifest,
    _validate_redaction_quality,
    _validate_redaction_placeholders,
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
    class MockManifest:
        def __init__(self, files: dict[str, str]) -> None:
            self.file_manifest = files

    return MockManifest(file_manifest or {})


def _make_redaction_placeholder(description: str, value: str) -> str:
    """Create a well-formed redaction placeholder."""
    h = hmac.new(b"test-secret-32-bytes-xxxxxxxxxx", value.encode("utf-8"), hashlib.sha256)
    return f"***REDACTED***:{description}:HMAC-SHA256:{h.hexdigest()}***"


# ---------------------------------------------------------------------------
# Domain A — redaction quality checks
# ---------------------------------------------------------------------------


class TestRedactionQuality:
    def test_valid_redaction_placeholder_passes(self) -> None:
        steps = [
            {
                "index": 0,
                "content": {
                    "text": _make_redaction_placeholder("OpenAI API key", "sk-test-abc123"),
                },
            },
        ]
        assert _validate_redaction_quality(steps) is True

    def test_fake_redaction_without_hmac_fails(self) -> None:
        steps = [
            {"index": 0, "content": {"text": "***REDACTED*** just a string"}},
        ]
        assert _validate_redaction_quality(steps) is False

    def test_redaction_with_wrong_hex_length_fails(self) -> None:
        steps = [
            {
                "index": 0,
                "content": {
                    "text": "***REDACTED***:key:HMAC-SHA256:abc123***",
                },
            },
        ]
        assert _validate_redaction_quality(steps) is False

    def test_empty_steps_fails_quality(self) -> None:
        assert _validate_redaction_quality([]) is False
        assert _validate_redaction_quality(None) is False

    def test_placeholder_format_validation_all_valid(self) -> None:
        steps = [
            {
                "index": 0,
                "content": {
                    "text": _make_redaction_placeholder("key1", "val1") + " " +
                            _make_redaction_placeholder("key2", "val2"),
                },
            },
        ]
        assert _validate_redaction_placeholders(steps) is True

    def test_placeholder_format_validation_mixed(self) -> None:
        steps = [
            {
                "index": 0,
                "content": {
                    "text": _make_redaction_placeholder("key1", "val1") +
                            " ***REDACTED***fake***",
                },
            },
        ]
        assert _validate_redaction_placeholders(steps) is False

    def test_placeholder_format_no_redactions(self) -> None:
        steps = [{"index": 0, "content": {"text": "clean text"}}]
        assert _validate_redaction_placeholders(steps) is False

    def test_redaction_coverage_detects_sensitive(self) -> None:
        # Description "API key" → api_key category → coverage passes
        steps = [
            {
                "index": 0,
                "content": {
                    "text": _make_redaction_placeholder("OpenAI API key", "sk-test"),
                },
            },
        ]
        assert _check_redaction_coverage(steps) is True

    def test_redaction_coverage_fails_without_redaction(self) -> None:
        steps = [
            {"index": 0, "content": {"text": "clean text with no redaction"}},
        ]
        assert _check_redaction_coverage(steps) is False

    def test_redaction_coverage_no_sensitive(self) -> None:
        steps = [{"index": 0, "content": {"text": "Hello world"}}]
        assert _check_redaction_coverage(steps) is False

    def test_redaction_completeness_all_categories_covered(self) -> None:
        # API key description + Email description = api_key + pii = 2 categories
        steps = [
            {
                "index": 0,
                "content": {
                    "text": _make_redaction_placeholder("OpenAI API key", "sk-test123"),
                },
            },
            {
                "index": 1,
                "content": {
                    "text": _make_redaction_placeholder("Email address", "user@example.com"),
                },
            },
        ]
        result = _check_redaction_completeness(steps)
        assert result is True

    def test_redaction_completeness_single_category_fails(self) -> None:
        steps = [
            {
                "index": 0,
                "content": {
                    "text": _make_redaction_placeholder("OpenAI API key", "sk-test123") + " " +
                            _make_redaction_placeholder("GitHub token", "ghp_abc"),
                },
            },
        ]
        # Only api_key category
        assert _check_redaction_completeness(steps) is False

    def test_redaction_completeness_missing_category(self) -> None:
        steps = [
            {
                "index": 0,
                "content": {"text": "user@evil.com"},  # email, NOT redacted
            },
        ]
        assert _check_redaction_completeness(steps) is False


# ---------------------------------------------------------------------------
# Domain mapping — substantive pass with full evidence
# ---------------------------------------------------------------------------


def test_domain_a_passes_with_quality_redaction() -> None:
    report = _make_report()
    manifest = _make_manifest({"environment.json": "env_hash"})
    # Two redaction categories: api_key + pii
    steps = [
        {
            "index": 0,
            "content": {
                "text": _make_redaction_placeholder("OpenAI API key", "sk-test") + " " +
                        _make_redaction_placeholder("Email address", "user@test.com"),
            },
        },
    ]
    statuses = map_verification_to_aiuc1(report, manifest, steps)
    assert statuses["A"].status == "PASS", f"Domain A should PASS, got {statuses['A'].status} — missing: {statuses['A'].missing}"
    assert "redaction_verifiable" in statuses["A"].evidence
    assert "redaction_coverage" in statuses["A"].evidence
    assert "redaction_format_valid" in statuses["A"].evidence


def test_domain_a_fails_without_environment() -> None:
    report = _make_report()
    manifest = _make_manifest({})
    steps = [
        {
            "index": 0,
            "content": {
                "text": _make_redaction_placeholder("key", "sk-test"),
            },
        },
    ]
    statuses = map_verification_to_aiuc1(report, manifest, steps)
    assert statuses["A"].status in ("FAIL", "PARTIAL")
    assert "environment_isolated" in statuses["A"].missing


def test_domain_a_fails_with_fake_redaction() -> None:
    report = _make_report()
    manifest = _make_manifest({"environment.json": "env_hash"})
    steps = [
        {"index": 0, "content": {"text": "***REDACTED*** fake redaction no hmac"}},
    ]
    statuses = map_verification_to_aiuc1(report, manifest, steps)
    assert statuses["A"].status in ("FAIL", "PARTIAL")


# ---------------------------------------------------------------------------
# Domain E — review binding checks
# ---------------------------------------------------------------------------


class TestReviewBinding:
    def test_review_binding_no_epi_path(self) -> None:
        assert _check_review_binding(None, None) is False

    def test_review_signed_no_epi_path(self) -> None:
        assert _check_review_signed(None) is False

    def test_domain_e_requires_review_binding_and_signed(self) -> None:
        report = _make_report()
        manifest = _make_manifest({"policy.json": "pol_hash"})
        statuses = map_verification_to_aiuc1(report, manifest, [], epi_path=None)
        assert statuses["E"].status in ("FAIL", "PARTIAL")
        assert "review_bound_to_artifact" in statuses["E"].missing
        assert "review_signed" in statuses["E"].missing

    def test_domain_e_with_review_bound_to_artifact(self, tmp_path: Path) -> None:
        """End-to-end test: build an .epi, add a review, verify binding."""
        from epi_core.container import EPIContainer
        from epi_core.review import ReviewRecord, add_review_to_artifact
        from epi_core.schemas import ManifestModel
        from epi_core.trust import sign_manifest

        pk = Ed25519PrivateKey.generate()
        manifest = ManifestModel(
            workflow_id=uuid4(),
            created_at=datetime.now(timezone.utc).isoformat(),
            file_manifest={
                "steps.jsonl": "abc",
                "policy.json": "abc",
                "analysis.json": "abc",
                "environment.json": "abc",
            },
        )
        signed = sign_manifest(manifest, pk, "test")

        source = tmp_path / "source"
        source.mkdir()
        (source / "steps.jsonl").write_text('{"index":0}\n')
        (source / "policy.json").write_text('{"system_name":"test","system_version":"1","policy_version":"1","rules":[]}')

        epi = tmp_path / "test.epi"
        EPIContainer.pack(source, signed, epi, container_format="legacy-zip", preserve_generated=True)

        review = ReviewRecord(
            reviewed_by="reviewer@test.com",
            reviews=[{"outcome": "approved", "notes": "LGTM"}],
        )
        add_review_to_artifact(epi, review, private_key=pk)

        report = _make_report()
        statuses = map_verification_to_aiuc1(report, None, [], epi_path=epi)
        assert "review_bound_to_artifact" in statuses["E"].evidence
        assert "review_signed" in statuses["E"].evidence


# ---------------------------------------------------------------------------
# Domain F — analysis checks
# ---------------------------------------------------------------------------


class TestAnalysisChecks:
    def test_analysis_has_findings_with_fault(self) -> None:
        epi = _make_epi_with_analysis({
            "analyzer_version": "1.0",
            "analysis_timestamp": "2026-01-01T00:00:00Z",
            "coverage": {"status": "complete"},
            "fault_detected": True,
            "summary": {"secondary_count": 1},
            "primary_fault": {"step_number": 3, "fault_type": "POLICY_VIOLATION"},
        })
        assert _check_analysis_has_findings(None, epi) is True

    def test_analysis_has_findings_no_fault(self) -> None:
        epi = _make_epi_with_analysis({
            "analyzer_version": "1.0",
            "analysis_timestamp": "2026-01-01T00:00:00Z",
            "coverage": {"status": "complete"},
            "fault_detected": False,
            "summary": {"secondary_count": 0},
            "primary_fault": None,
        })
        assert _check_analysis_has_findings(None, epi) is False

    def test_analysis_passes_complete(self) -> None:
        epi = _make_epi_with_analysis({
            "analyzer_version": "2.0",
            "analysis_timestamp": "2026-01-01T00:00:00Z",
            "coverage": {"status": "complete", "steps_recorded": 10},
            "fault_detected": False,
            "summary": {},
        })
        assert _check_analysis_passes_complete(None, epi) is True

    def test_analysis_passes_incomplete(self) -> None:
        epi = _make_epi_with_analysis({
            "analyzer_version": "2.0",
            "analysis_timestamp": "2026-01-01T00:00:00Z",
            "coverage": {"status": "incomplete"},
            "fault_detected": False,
            "summary": {},
        })
        assert _check_analysis_passes_complete(None, epi) is False

    def test_analysis_passes_missing_fields(self) -> None:
        epi = _make_epi_with_analysis({"fault_detected": False})
        assert _check_analysis_passes_complete(None, epi) is False

    def test_analysis_has_findings_none(self) -> None:
        assert _check_analysis_has_findings(None, None) is False

    def test_analysis_passes_complete_none(self) -> None:
        assert _check_analysis_passes_complete(None, None) is False

    def test_domain_f_requires_substantive_analysis(self) -> None:
        report = _make_report()
        steps = [
            {
                "index": 0,
                "content": {"text": _make_redaction_placeholder("key", "sk-test123")},
            },
        ]
        statuses = map_verification_to_aiuc1(report, None, steps, epi_path=None)
        assert statuses["F"].status in ("FAIL", "PARTIAL")
        assert "analysis_has_findings" in statuses["F"].missing
        assert "analysis_passes_complete" in statuses["F"].missing


def _make_epi_with_analysis(analysis: dict) -> Path:
    """Create a minimal .epi with analysis.json for testing."""
    tmpdir = Path(os.environ.get("TEMP", "/tmp"))
    path = tmpdir / f"test_analysis_{uuid4().hex[:8]}.epi"
    try:
        with zipfile.ZipFile(path, "w") as zf:
            zf.writestr("mimetype", "application/vnd.epi+zip")
            zf.writestr("manifest.json", "{}")
            zf.writestr("analysis.json", json.dumps(analysis))
    except Exception:
        pass
    return path


# ---------------------------------------------------------------------------
# Domain mapping — happy path
# ---------------------------------------------------------------------------


def test_all_domains_pass_with_full_evidence(tmp_path: Path) -> None:
    from epi_core.container import EPIContainer
    from epi_core.review import ReviewRecord, add_review_to_artifact
    from epi_core.schemas import ManifestModel
    from epi_core.trust import sign_manifest
    from epi_core.fault_analyzer import FaultAnalyzer

    pk = Ed25519PrivateKey.generate()
    manifest = ManifestModel(
        workflow_id=uuid4(),
        created_at=datetime.now(timezone.utc).isoformat(),
        file_manifest={"steps.jsonl": "abc", "policy.json": "abc", "analysis.json": "abc", "environment.json": "abc"},
    )
    signed = sign_manifest(manifest, pk, "test")

    # Build steps with real redaction (two categories for completeness)
    steps = []
    steps.append({"index": 0, "timestamp": "2026-01-01T00:00:00Z", "kind": "llm.request",
                   "content": {"messages": [{"role": "user", "content": "test"}]}})
    steps.append({"index": 1, "timestamp": "2026-01-01T00:00:01Z", "kind": "tool.call",
                   "content": {"tool": "verify_identity", "input": {"customer_id": "CUST-001"}}})
    steps.append({"index": 2, "timestamp": "2026-01-01T00:00:02Z", "kind": "tool.response",
                   "content": {"tool": "verify_identity", "output": {"verified": True}}})
    steps.append({"index": 3, "timestamp": "2026-01-01T00:00:03Z", "kind": "llm.response",
                   "content": {"text": (
                       _make_redaction_placeholder("OpenAI API key", "sk-test123") + " " +
                       _make_redaction_placeholder("Email address", "user@example.com")
                   )}})
    steps.append({"index": 4, "timestamp": "2026-01-01T00:00:04Z", "kind": "llm.error",
                   "content": {"error": "RateLimitError"}})
    steps.append({"index": 5, "timestamp": "2026-01-01T00:00:05Z", "kind": "tool.call",
                   "content": {"tool": "lookup_order", "input": {"order_id": "ORD-001"}}})

    source = tmp_path / "source"
    source.mkdir()
    (source / "steps.jsonl").write_text("\n".join(json.dumps(s) for s in steps))
    (source / "environment.json").write_text("{}")
    (source / "policy.json").write_text('{"system_name":"test","system_version":"1","policy_version":"1","rules":[]}')

    # Run analyzer
    analyzer = FaultAnalyzer()
    result = analyzer.analyze((source / "steps.jsonl").read_text())
    (source / "analysis.json").write_text(json.dumps(result.to_dict(), indent=2))

    epi = tmp_path / "test.epi"
    EPIContainer.pack(source, signed, epi, container_format="legacy-zip", preserve_generated=True)

    review = ReviewRecord(
        reviewed_by="reviewer@test.com",
        reviews=[{"outcome": "approved", "notes": "LGTM"}],
    )
    add_review_to_artifact(epi, review, private_key=pk)

    report = _make_report()
    final_manifest = EPIContainer.read_manifest(epi)
    statuses = map_verification_to_aiuc1(report, final_manifest, steps, epi_path=epi)
    summary = aiuc1_summary(statuses)

    # With full evidence, all domains should PASS
    for domain_id in "ABCDEF":
        assert statuses[domain_id].status == "PASS", (
            f"Domain {domain_id} should PASS, got {statuses[domain_id].status} — "
            f"missing: {statuses[domain_id].missing}"
        )


# ---------------------------------------------------------------------------
# Domain mapping — missing evidence
# ---------------------------------------------------------------------------


def test_domain_b_partial_without_scitt() -> None:
    report = _make_report(scitt_entry_id=None)
    manifest = _make_manifest({})
    statuses = map_verification_to_aiuc1(report, manifest, [])
    assert statuses["B"].status == "PARTIAL"
    assert "scitt_receipt_present" in statuses["B"].missing


def test_domain_c_fails_with_broken_chain() -> None:
    report = _make_report(chain_ok=False)
    manifest = _make_manifest({})
    statuses = map_verification_to_aiuc1(report, manifest, [])
    assert statuses["C"].status in ("FAIL", "PARTIAL")
    assert "chain_ok" in statuses["C"].missing


# ---------------------------------------------------------------------------
# _check_timestamp_monotonicity
# ---------------------------------------------------------------------------


def test_timestamp_monotonic_empty_steps() -> None:
    assert _check_timestamp_monotonicity([]) is True
    assert _check_timestamp_monotonicity(None) is True


def test_timestamp_monotonic_iso_strings_ok() -> None:
    steps = [
        {"timestamp": "2026-01-01T00:00:00Z"},
        {"timestamp": "2026-01-01T00:00:01Z"},
    ]
    assert _check_timestamp_monotonicity(steps) is True


def test_timestamp_monotonic_iso_strings_out_of_order() -> None:
    steps = [
        {"timestamp": "2026-01-01T00:00:02Z"},
        {"timestamp": "2026-01-01T00:00:01Z"},
    ]
    assert _check_timestamp_monotonicity(steps) is False


def test_timestamp_monotonic_timestamp_ns_ok() -> None:
    steps = [
        {"content": {"timestamp_ns": 1_000_000_000}},
        {"content": {"timestamp_ns": 2_000_000_000}},
    ]
    assert _check_timestamp_monotonicity(steps) is True


def test_timestamp_monotonic_mixed_prefers_ns() -> None:
    steps = [
        {"content": {"timestamp_ns": 1_000_000_000}},
        {"timestamp": "2026-01-01T00:00:01Z"},
    ]
    assert _check_timestamp_monotonicity(steps) is False


def test_timestamp_monotonic_datetime_objects() -> None:
    t = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    steps = [
        {"timestamp": t},
        {"timestamp": t + timedelta(seconds=1)},
    ]
    assert _check_timestamp_monotonicity(steps) is True


# ---------------------------------------------------------------------------
# _detect_error_steps
# ---------------------------------------------------------------------------


def test_detect_error_steps_present() -> None:
    steps = [{"kind": "llm.error", "content": {"message": "oom"}}]
    assert _detect_error_steps(steps) is True


def test_detect_error_steps_absent() -> None:
    steps = [{"kind": "llm.request"}, {"kind": "llm.response"}]
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
