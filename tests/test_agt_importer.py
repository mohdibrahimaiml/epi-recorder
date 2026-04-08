import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from epi_core.container import EPIContainer
from epi_core.trust import sign_manifest
from epi_recorder.integrations.agt import coerce_agt_bundle, export_agt_to_epi
from epi_recorder.integrations.agt.mapping import (
    map_audit_logs,
    map_flight_recorder,
    normalize_agt_steps,
)
from epi_recorder.integrations.agt.report import MappingReportBuilder

FIXED_REPORT_TIME = datetime(2026, 4, 7, 12, 0, 0, tzinfo=UTC)
FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "agt"
EXPECTED_DIR = FIXTURE_DIR / "expected"


def _fixture_path(name: str) -> Path:
    return FIXTURE_DIR / f"{name}.json"


def _load_fixture(name: str) -> dict:
    return json.loads(_fixture_path(name).read_text(encoding="utf-8"))


def _snapshot_path(name: str) -> Path:
    return EXPECTED_DIR / f"{name}.mapping_report.json"


def _deterministic_builder() -> MappingReportBuilder:
    return MappingReportBuilder(generated_at=FIXED_REPORT_TIME, importer_version="test-importer")


def _read_zip_json(epi_path: Path, member: str) -> dict:
    payload = EPIContainer.read_member_json(epi_path, member)
    assert isinstance(payload, dict)
    return payload


def _export_fixture(
    name: str,
    tmp_path: Path,
    *,
    signed: bool = False,
    **kwargs,
) -> Path:
    output_path = tmp_path / f"{name}.epi"
    signer = None
    if signed:
        private_key = Ed25519PrivateKey.generate()

        def signer(manifest):
            return sign_manifest(manifest, private_key, "test")

    export_agt_to_epi(
        _load_fixture(name),
        output_path,
        signer_function=signer,
        report_builder=_deterministic_builder(),
        **kwargs,
    )
    return output_path


class TestAGTBundleValidation:
    def test_valid_bundle_with_audit_logs_only(self):
        bundle = coerce_agt_bundle(_load_fixture("audit_only"))
        assert len(bundle.audit_logs) == 2

    def test_valid_bundle_with_flight_recorder_only(self):
        bundle = coerce_agt_bundle(_load_fixture("flight_only"))
        assert len(bundle.flight_recorder) == 2

    def test_invalid_bundle_without_evidence_sections(self):
        with pytest.raises(Exception):
            coerce_agt_bundle({"metadata": {"goal": "missing evidence"}})

    def test_extras_are_preserved(self):
        payload = _load_fixture("audit_only")
        payload["custom_block"] = {"kept": True}
        bundle = coerce_agt_bundle(payload)
        dumped = bundle.model_dump(mode="json")
        assert dumped["custom_block"] == {"kept": True}


class TestAGTMapping:
    def test_tool_events_map_to_native_step_kinds(self):
        steps = map_audit_logs(_load_fixture("audit_only")["audit_logs"])
        assert [step.kind for step in steps] == ["tool.call", "tool.response"]
        assert steps[0].content["source_ref"]["system"] == "AGT"
        assert steps[0].content["source_ref"]["section"] == "audit_logs"

    def test_decision_and_failure_events_map_correctly(self):
        steps = map_flight_recorder(_load_fixture("flight_only")["flight_recorder"])
        assert [step.kind for step in steps] == ["tool.response", "policy.check"]
        assert steps[1].content["source_ref"]["section"] == "flight_recorder"

    def test_unknown_events_are_preserved_and_reported(self):
        builder = _deterministic_builder()
        payload = _load_fixture("audit_only")
        payload["audit_logs"][0]["event_type"] = "custom_event"
        payload["audit_logs"][0].pop("policy_decision", None)
        payload["audit_logs"][0].pop("matched_rule", None)
        builder.observe_bundle(coerce_agt_bundle(payload))
        steps = map_audit_logs(payload["audit_logs"], report_builder=builder)
        report = builder.build(strict=False)
        assert steps[0].kind == "agt.audit.custom_event"
        assert report.event_mapping.unknown[0].source_type == "custom_event"

    def test_dedupe_prefers_audit_events_over_flight_rows(self):
        bundle = coerce_agt_bundle(_load_fixture("combined_clean"))
        steps = normalize_agt_steps(bundle, report_builder=_deterministic_builder())
        assert len(steps) == 3
        assert [step.kind for step in steps] == ["tool.call", "tool.response", "policy.check"]
        assert steps[-1].content["source_ref"]["dedupe_resolution"] == "preferred_audit"

    def test_dedupe_keep_both_preserves_both_candidates(self):
        bundle = coerce_agt_bundle(_load_fixture("combined_clean"))
        steps = normalize_agt_steps(
            bundle,
            report_builder=_deterministic_builder(),
            dedupe_strategy="keep-both",
        )
        assert len(steps) == 4
        assert (
            sum(
                1
                for step in steps
                if step.content["source_ref"]["dedupe_resolution"] == "kept_both"
            )
            == 2
        )


class TestAGTConverter:
    @pytest.mark.parametrize(
        "fixture_name",
        [
            "audit_only",
            "flight_only",
            "combined_clean",
            "combined_conflict",
            "no_violations",
            "heavy_violations",
        ],
    )
    def test_mapping_report_matches_snapshot(self, fixture_name, tmp_path):
        output_path = _export_fixture(fixture_name, tmp_path)
        report = _read_zip_json(output_path, "artifacts/agt/mapping_report.json")
        expected = json.loads(_snapshot_path(fixture_name).read_text(encoding="utf-8"))
        assert report == expected
        assert report["field_handling"]["unclassified"] == []
        assert report["field_handling"]["dropped"] == []

    def test_exported_artifact_contains_imported_files(self, tmp_path):
        output_path = _export_fixture("combined_clean", tmp_path, signed=True)

        names = set(EPIContainer.list_members(output_path))

        assert "steps.jsonl" in names
        assert "policy.json" in names
        assert "policy_evaluation.json" in names
        assert "analysis.json" in names
        assert "environment.json" in names
        assert "artifacts/annex_iv.md" in names
        assert "artifacts/annex_iv.json" in names
        assert "artifacts/slo.json" in names
        assert "artifacts/agt/bundle.json" in names
        assert "artifacts/agt/compliance_report.json" in names
        assert "artifacts/agt/mapping_report.json" in names

    def test_manifest_metadata_and_integrity_are_valid(self, tmp_path):
        bundle = _load_fixture("combined_clean")
        output_path = _export_fixture("combined_clean", tmp_path, signed=True)

        manifest = EPIContainer.read_manifest(output_path)
        integrity_ok, mismatches = EPIContainer.verify_integrity(output_path)

        assert str(manifest.workflow_id) == bundle["metadata"]["workflow_id"]
        assert manifest.goal == bundle["metadata"]["goal"]
        assert manifest.metrics["availability"] == 99.95
        assert manifest.signature is not None
        assert integrity_ok is True
        assert mismatches == {}

    def test_analysis_none_omits_analysis_but_keeps_report(self, tmp_path):
        output_path = _export_fixture("combined_clean", tmp_path, analysis_mode="none")

        names = set(EPIContainer.list_members(output_path))
        report = _read_zip_json(output_path, "artifacts/agt/mapping_report.json")

        assert "analysis.json" not in names
        assert "artifacts/agt/mapping_report.json" in names
        assert report["analysis"]["mode"] == "none"
        assert report["analysis"]["synthesized"] is False

    def test_strict_import_fails_on_unknown_event_type(self, tmp_path):
        payload = _load_fixture("audit_only")
        payload["audit_logs"][0]["event_type"] = "custom_event"
        payload["audit_logs"][0].pop("policy_decision", None)
        payload["audit_logs"][0].pop("matched_rule", None)
        with pytest.raises(ValueError, match="unknown AGT event type"):
            export_agt_to_epi(
                payload,
                tmp_path / "strict_unknown.epi",
                strict=True,
                dedupe_strategy="fail",
                report_builder=_deterministic_builder(),
            )

    def test_strict_import_fails_on_unclassified_field(self, tmp_path):
        payload = _load_fixture("audit_only")
        payload["audit_logs"][0]["custom_extra"] = "surprise"
        with pytest.raises(ValueError, match="unclassified field"):
            export_agt_to_epi(
                payload,
                tmp_path / "strict_unclassified.epi",
                strict=True,
                dedupe_strategy="fail",
                report_builder=_deterministic_builder(),
            )

    def test_strict_import_fails_on_dedupe_conflict(self, tmp_path):
        with pytest.raises(ValueError, match="dedupe conflict"):
            export_agt_to_epi(
                _load_fixture("combined_clean"),
                tmp_path / "strict_conflict.epi",
                strict=True,
                dedupe_strategy="fail",
                report_builder=_deterministic_builder(),
            )

    def test_keep_both_reports_conflict_and_preserves_both(self, tmp_path):
        output_path = _export_fixture(
            "combined_clean",
            tmp_path,
            dedupe_strategy="keep-both",
        )
        report = _read_zip_json(output_path, "artifacts/agt/mapping_report.json")

        steps = EPIContainer.read_steps(output_path)

        assert report["step_transformation"]["kept_both_count"] == 2
        assert len(steps) == 4
        assert all(step["content"]["source_ref"] for step in steps)
