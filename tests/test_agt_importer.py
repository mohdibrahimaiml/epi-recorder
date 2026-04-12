import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from epi_core.container import EPIContainer
from epi_core.trust import sign_manifest
from epi_recorder.integrations.agt import (
    AGTInputError,
    coerce_agt_bundle,
    export_agt_to_epi,
    load_agt_input,
)
from epi_recorder.integrations.agt.mapping import (
    map_audit_logs,
    map_flight_recorder,
    normalize_agt_steps,
)
from epi_recorder.integrations.agt.report import MappingReportBuilder

FIXED_REPORT_TIME = datetime(2026, 4, 7, 12, 0, 0, tzinfo=UTC)
FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "agt"
EXPECTED_DIR = FIXTURE_DIR / "expected"
REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_AGT_DIR = REPO_ROOT / "examples" / "agt"
EXAMPLE_EVIDENCE_DIR = EXAMPLE_AGT_DIR / "evidence-dir"
EXAMPLE_MANIFEST = EXAMPLE_AGT_DIR / "manifest-input" / "agt_import_manifest.json"


def _fixture_path(name: str) -> Path:
    return FIXTURE_DIR / f"{name}.json"


def _load_fixture(name: str) -> dict:
    return json.loads(_fixture_path(name).read_text(encoding="utf-8"))


def _snapshot_path(name: str) -> Path:
    return EXPECTED_DIR / f"{name}.mapping_report.json"


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


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


class TestAGTInputLoader:
    def test_load_bundle_file_still_works(self):
        bundle = load_agt_input(_fixture_path("combined_clean"))
        assert len(bundle.audit_logs) == 3
        assert bundle.metadata.goal == "Combined clean fixture"

    def test_load_directory_by_convention(self):
        bundle = load_agt_input(EXAMPLE_EVIDENCE_DIR)
        assert len(bundle.audit_logs) == 3
        assert len(bundle.flight_recorder) == 1
        assert bundle.metadata.system_name == "Claims Triage Agent"
        assert bundle.metadata.provider == "Acme Insurance"

    def test_load_manifest_file_and_metadata_fallback(self):
        bundle = load_agt_input(EXAMPLE_MANIFEST)
        assert len(bundle.audit_logs) == 3
        assert bundle.metadata.goal == "Import AGT evidence from a raw output directory via manifest."
        assert bundle.metadata.system_name == "Claims Triage Agent"
        assert bundle.metadata.provider == "Acme Insurance"

    def test_manifest_overrides_directory_conventions(self, tmp_path):
        evidence_dir = tmp_path / "evidence-dir"
        evidence_dir.mkdir()

        default_audit = [_load_fixture("audit_only")["audit_logs"][0]]
        override_audit = _load_fixture("audit_only")["audit_logs"]

        _write_json(evidence_dir / "audit_logs.json", default_audit)
        _write_json(evidence_dir / "custom_audit.json", override_audit)
        _write_json(
            evidence_dir / "annex_iv.json",
            {"system_name": "Claims Triage Agent", "provider": "Acme Insurance"},
        )
        _write_json(
            evidence_dir / "agt_import_manifest.json",
            {
                "files": {
                    "audit_logs": "custom_audit.json",
                }
            },
        )

        bundle = load_agt_input(evidence_dir)
        assert len(bundle.audit_logs) == 2
        assert bundle.audit_logs[0]["entry_id"] == override_audit[0]["entry_id"]

    def test_missing_execution_evidence_fails_with_clear_error(self, tmp_path):
        evidence_dir = tmp_path / "missing-evidence"
        evidence_dir.mkdir()
        _write_json(evidence_dir / "annex_iv.json", {"system_name": "Claims Triage Agent"})

        with pytest.raises(AGTInputError, match="missing execution evidence"):
            load_agt_input(evidence_dir)

    def test_empty_directory_explains_expected_files(self, tmp_path):
        evidence_dir = tmp_path / "empty-dir"
        evidence_dir.mkdir()

        with pytest.raises(AGTInputError) as exc:
            load_agt_input(evidence_dir)

        message = str(exc.value)
        assert "No recognized AGT files were found in directory" in message
        assert "audit_logs.json" in message
        assert "flight_recorder.json" in message
        assert "agt_import_manifest.json" in message

    def test_missing_manifest_targets_are_reported(self, tmp_path):
        evidence_dir = tmp_path / "missing-manifest-targets"
        evidence_dir.mkdir()
        _write_json(
            evidence_dir / "agt_import_manifest.json",
            {
                "files": {
                    "audit_logs": "missing_audit.json",
                    "annex_json": "missing_annex.json",
                }
            },
        )

        with pytest.raises(AGTInputError) as exc:
            load_agt_input(evidence_dir)

        message = str(exc.value)
        assert "AGT import manifest references missing file(s)" in message
        assert "audit_logs" in message
        assert "annex_json" in message

    def test_malformed_optional_json_reports_section_name(self, tmp_path):
        evidence_dir = tmp_path / "malformed-json"
        evidence_dir.mkdir()
        _write_json(evidence_dir / "audit_logs.json", _load_fixture("audit_only")["audit_logs"])
        (evidence_dir / "compliance_report.json").write_text("{bad json", encoding="utf-8")

        with pytest.raises(AGTInputError) as exc:
            load_agt_input(evidence_dir)

        message = str(exc.value)
        assert "Invalid JSON in AGT section 'compliance_report'" in message
        assert "compliance_report.json" in message

    def test_non_bundle_json_explains_supported_shapes(self, tmp_path):
        weird_json = tmp_path / "weird.json"
        _write_json(weird_json, {"hello": "world"})

        with pytest.raises(AGTInputError) as exc:
            load_agt_input(weird_json)

        message = str(exc.value)
        assert "neutral AGT bundle" in message
        assert "top-level 'files' mapping" in message

    def test_single_section_json_suggests_passing_directory(self, tmp_path):
        single_section = tmp_path / "audit_logs.json"
        _write_json(single_section, _load_fixture("audit_only")["audit_logs"])

        with pytest.raises(AGTInputError) as exc:
            load_agt_input(single_section)

        message = str(exc.value)
        assert "single AGT section file" in message
        assert "Pass the directory" in message
        assert "agt_import_manifest.json" in message


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

    def test_export_uses_recording_workspace_helper_and_cleans_up(self, tmp_path, monkeypatch):
        from epi_recorder.integrations.agt import converter

        workspace = tmp_path / "agt_workspace"
        created_prefixes: list[str] = []

        def fake_create_recording_workspace(prefix: str) -> Path:
            created_prefixes.append(prefix)
            workspace.mkdir(parents=True, exist_ok=True)
            return workspace

        monkeypatch.setattr(converter, "create_recording_workspace", fake_create_recording_workspace)

        output_path = tmp_path / "workspace_helper.epi"
        export_agt_to_epi(
            _load_fixture("combined_clean"),
            output_path,
            report_builder=_deterministic_builder(),
        )

        assert created_prefixes == ["epi_agt_import_"]
        assert output_path.exists()
        assert not workspace.exists()
