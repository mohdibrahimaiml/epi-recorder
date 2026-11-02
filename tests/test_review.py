"""Tests for epi_core.review — human review record for fault analysis."""

import json
import zipfile
from pathlib import Path

import pytest

from epi_cli.review import _analysis_has_fault
from epi_core.container import EPI_CONTAINER_FORMAT_ENVELOPE, EPIContainer
from epi_core.review import (
    ReviewRecord,
    add_review_to_artifact,
    make_review_entry,
    read_review,
)

# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_minimal_epi(tmp_path: Path, with_analysis: bool = True) -> Path:
    """Create a minimal valid .epi file for testing."""
    epi_path = tmp_path / "test.epi"
    with zipfile.ZipFile(epi_path, "w") as zf:
        zf.writestr("mimetype", "application/vnd.epi+zip",
                    compress_type=zipfile.ZIP_STORED)
        zf.writestr("steps.jsonl",
                    '{"index": 0, "kind": "session.start", "content": {}}')
        zf.writestr("manifest.json",
                    json.dumps({"file_manifest": {}, "spec_version": "2.7.2"}))
        if with_analysis:
            zf.writestr("analysis.json", json.dumps({
                "fault_detected": True,
                "primary_fault": {
                    "step_index": 1,
                    "step_number": 2,
                    "fault_type": "POLICY_VIOLATION",
                    "rule_id": "R001",
                    "rule_name": "Balance Check",
                    "severity": "critical",
                    "plain_english": "Balance was exceeded.",
                    "fault_chain": [],
                },
                "secondary_flags": [],
                "human_review": {"status": "pending", "reviewed_by": None,
                                 "reviewed_at": None, "outcome": None, "notes": None},
                "disclaimer": "This analysis is probabilistic.",
            }))
    return epi_path


def _make_review_record() -> ReviewRecord:
    return ReviewRecord(
        reviewed_by="alice@example.com",
        reviews=[
            make_review_entry(
                fault={"step_number": 2, "rule_id": "R001", "fault_type": "POLICY_VIOLATION"},
                outcome="confirmed_fault",
                notes="Confirmed. Balance check bypassed.",
                reviewer="alice@example.com",
            )
        ],
    )


# ── Test: ReviewRecord ─────────────────────────────────────────────────────────

class TestReviewRecord:
    def test_content_hash_is_deterministic(self):
        r = _make_review_record()
        h1 = r.content_hash()
        h2 = r.content_hash()
        assert h1 == h2
        assert len(h1) == 64  # SHA-256 hex

    def test_to_dict_has_required_keys(self):
        r = _make_review_record()
        d = r.to_dict()
        for key in ("review_version", "reviewed_by", "reviewed_at", "reviews"):
            assert key in d

    def test_to_json_is_valid(self):
        r = _make_review_record()
        parsed = json.loads(r.to_json())
        assert parsed["reviewed_by"] == "alice@example.com"

    def test_from_dict_round_trips(self):
        r = _make_review_record()
        d = r.to_dict()
        r2 = ReviewRecord.from_dict(d)
        assert r2.reviewed_by == r.reviewed_by
        assert len(r2.reviews) == len(r.reviews)

    def test_review_signature_is_none_before_signing(self):
        r = _make_review_record()
        assert r.review_signature is None


# ── Test: make_review_entry ────────────────────────────────────────────────────

class TestMakeReviewEntry:
    def test_outcome_confirmed_fault(self):
        fault = {"step_number": 3, "rule_id": "R002", "fault_type": "POLICY_VIOLATION"}
        entry = make_review_entry(fault, "confirmed_fault", "Real bug", "bob@co.com")
        assert entry["outcome"] == "confirmed_fault"
        assert entry["rule_id"] == "R002"
        assert entry["reviewer"] == "bob@co.com"
        assert entry["notes"] == "Real bug"

    def test_outcome_dismissed(self):
        fault = {"step_number": 1, "rule_id": None, "fault_type": "HEURISTIC_OBSERVATION"}
        entry = make_review_entry(fault, "dismissed", "", "carol@co.com")
        assert entry["outcome"] == "dismissed"

    def test_entry_has_timestamp(self):
        fault = {"step_number": 1, "rule_id": None, "fault_type": "HEURISTIC_OBSERVATION"}
        entry = make_review_entry(fault, "skipped", "", "dave@co.com")
        assert "timestamp" in entry
        assert entry["timestamp"]  # non-empty string


# ── Test: add_review_to_artifact / read_review ────────────────────────────────

class TestArtifactReview:
    def test_adds_review_json_to_artifact(self, tmp_path):
        epi_path = _make_minimal_epi(tmp_path)
        record = _make_review_record()
        add_review_to_artifact(epi_path, record)

        with zipfile.ZipFile(epi_path, "r") as zf:
            assert "review.json" in zf.namelist()

    def test_original_files_unchanged_after_review(self, tmp_path):
        epi_path = _make_minimal_epi(tmp_path)

        # Hash original steps.jsonl and analysis.json before review
        with zipfile.ZipFile(epi_path, "r") as zf:
            original_steps = zf.read("steps.jsonl")
            original_analysis = zf.read("analysis.json")

        record = _make_review_record()
        add_review_to_artifact(epi_path, record)

        with zipfile.ZipFile(epi_path, "r") as zf:
            assert zf.read("steps.jsonl") == original_steps
            assert zf.read("analysis.json") == original_analysis

    def test_read_review_returns_none_when_absent(self, tmp_path):
        epi_path = _make_minimal_epi(tmp_path, with_analysis=False)
        result = read_review(epi_path)
        assert result is None

    def test_read_review_returns_record_after_add(self, tmp_path):
        epi_path = _make_minimal_epi(tmp_path)
        record = _make_review_record()
        add_review_to_artifact(epi_path, record)

        loaded = read_review(epi_path)
        assert loaded is not None
        assert loaded.reviewed_by == "alice@example.com"
        assert len(loaded.reviews) == 1
        assert loaded.reviews[0]["outcome"] == "confirmed_fault"

    def test_second_review_replaces_existing_review_entry_in_zip(self, tmp_path):
        epi_path = _make_minimal_epi(tmp_path)
        first = _make_review_record()
        second = ReviewRecord(
            reviewed_by="bob@example.com",
            reviews=[
                make_review_entry(
                    fault={"step_number": 2, "rule_id": "R009", "fault_type": "POLICY_VIOLATION"},
                    outcome="dismissed",
                    notes="Expected in this case.",
                    reviewer="bob@example.com",
                )
            ],
        )

        add_review_to_artifact(epi_path, first)
        add_review_to_artifact(epi_path, second)

        with zipfile.ZipFile(epi_path, "r") as zf:
            review_entries = [name for name in zf.namelist() if name == "review.json"]
            ledger_entries = [name for name in zf.namelist() if name.startswith("reviews/") and name.endswith(".json")]
            assert len(review_entries) == 1
            assert len(ledger_entries) == 2
            assert "review_index.json" in zf.namelist()

        loaded = read_review(epi_path)
        assert loaded is not None
        assert loaded.reviewed_by == "bob@example.com"
        assert loaded.reviews[0]["outcome"] == "dismissed"

    def test_add_review_raises_on_missing_file(self, tmp_path):
        record = _make_review_record()
        with pytest.raises(FileNotFoundError):
            add_review_to_artifact(tmp_path / "nonexistent.epi", record)

    def test_add_review_raises_on_non_zip(self, tmp_path):
        bad_file = tmp_path / "bad.epi"
        bad_file.write_text("not a zip")
        record = _make_review_record()
        with pytest.raises(ValueError):
            add_review_to_artifact(bad_file, record)

    def test_read_review_returns_none_on_missing_file(self, tmp_path):
        result = read_review(tmp_path / "ghost.epi")
        assert result is None

    def test_add_review_preserves_envelope_format(self, tmp_path):
        legacy_path = _make_minimal_epi(tmp_path)
        envelope_path = tmp_path / "enveloped.epi"
        EPIContainer.migrate(
            legacy_path, envelope_path, container_format=EPI_CONTAINER_FORMAT_ENVELOPE
        )

        record = _make_review_record()
        add_review_to_artifact(envelope_path, record)

        assert EPIContainer.detect_container_format(envelope_path) == EPI_CONTAINER_FORMAT_ENVELOPE
        loaded = read_review(envelope_path)
        assert loaded is not None
        assert loaded.reviewed_by == "alice@example.com"


class TestReviewCliHelpers:
    def test_primary_fault_counts_as_fault_even_if_flag_is_false(self):
        analysis = {
            "fault_detected": False,
            "primary_fault": {"fault_type": "POLICY_VIOLATION", "step_number": 2},
        }
        assert _analysis_has_fault(analysis) is True
