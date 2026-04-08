"""
End-to-end AGT -> EPI converter.
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

from epi_core.container import EPIContainer
from epi_core.schemas import ManifestModel, StepModel
from epi_core.workspace import create_recording_workspace

from .mapping import (
    classify_bundle_fields,
    extract_manifest_metrics,
    map_environment,
    map_policy_document,
    map_policy_evaluation,
    map_review,
    normalize_agt_steps,
    synthesize_analysis,
)
from .report import AnalysisMode, DedupStrategy, MappingReportBuilder
from .schema import AGTBundleModel, coerce_agt_bundle


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _write_text(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, encoding="utf-8")


def _write_steps(path: Path, steps: list[StepModel]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for step in steps:
            handle.write(step.model_dump_json(exclude_none=True))
            handle.write("\n")


def _build_manifest(bundle: AGTBundleModel) -> ManifestModel:
    metadata = bundle.metadata
    manifest_kwargs: dict[str, Any] = {
        "cli_command": metadata.cli_command,
        "goal": metadata.goal or "AGT compliance evidence export",
        "notes": metadata.notes or "Imported from Microsoft Agent Governance Toolkit evidence.",
        "metrics": extract_manifest_metrics(bundle.slo_data),
        "approved_by": metadata.approved_by,
        "tags": sorted(set((metadata.tags or []) + ["agt", "compliance", "import"])),
    }

    if metadata.workflow_id is not None:
        manifest_kwargs["workflow_id"] = metadata.workflow_id
    if metadata.created_at is not None:
        manifest_kwargs["created_at"] = metadata.created_at

    return ManifestModel(**manifest_kwargs)


def _attach_raw_payloads(workspace: Path, bundle: AGTBundleModel) -> None:
    raw_dir = workspace / "artifacts" / "agt"
    raw_dir.mkdir(parents=True, exist_ok=True)

    raw_bundle = bundle.model_dump(mode="json", exclude_none=True)
    _write_json(raw_dir / "bundle.json", raw_bundle)

    known_sections = {
        "audit_logs.json": bundle.audit_logs,
        "flight_recorder.json": bundle.flight_recorder,
        "compliance_report.json": bundle.compliance_report,
        "policy_document.json": bundle.policy_document,
        "runtime_context.json": bundle.runtime_context,
        "slo_data.json": bundle.slo_data,
        "review.json": bundle.review,
    }
    for filename, payload in known_sections.items():
        if payload not in (None, [], {}):
            _write_json(raw_dir / filename, payload)


def export_agt_to_epi(
    bundle: AGTBundleModel | dict[str, Any] | str | bytes | Path,
    output_path: Path,
    *,
    signer_function: Callable[[ManifestModel], ManifestModel] | None = None,
    attach_raw: bool = True,
    strict: bool = False,
    dedupe_strategy: DedupStrategy = "prefer-audit",
    analysis_mode: AnalysisMode = "synthesized",
    report_builder: MappingReportBuilder | None = None,
) -> Path:
    """Convert an AGT evidence bundle into a sealed .epi artifact."""

    model = coerce_agt_bundle(bundle)
    output_path = Path(output_path)
    if output_path.suffix.lower() != ".epi":
        output_path = output_path.with_suffix(".epi")

    if strict and dedupe_strategy != "fail":
        raise ValueError("Strict AGT import requires --dedupe fail")

    report_builder = report_builder or MappingReportBuilder()
    report_builder.observe_bundle(model)

    steps = normalize_agt_steps(
        model,
        report_builder=report_builder,
        strict=strict,
        dedupe_strategy=dedupe_strategy,
    )
    if not steps:
        raise ValueError("AGT bundle did not produce any steps for import")

    classify_bundle_fields(
        model,
        report_builder,
        attach_raw=attach_raw,
        analysis_mode=analysis_mode,
    )

    workspace = create_recording_workspace("epi_agt_import_")
    try:
        _write_steps(workspace / "steps.jsonl", steps)

        if model.policy_document:
            _write_json(workspace / "policy.json", map_policy_document(model.policy_document))

        policy_evaluation = None
        if model.compliance_report:
            policy_evaluation = map_policy_evaluation(
                model.compliance_report,
                steps,
                policy_document=model.policy_document,
            )
            _write_json(workspace / "policy_evaluation.json", policy_evaluation)

        if analysis_mode == "synthesized":
            analysis = synthesize_analysis(model, steps, policy_evaluation=policy_evaluation)
            _write_json(workspace / "analysis.json", analysis)
            report_builder.record_analysis(
                mode="agt_import",
                synthesized=True,
                confidence="derived",
                warning="Synthesized from AGT evidence; not native EPI analysis.",
                source_artifacts=["compliance_report", "steps.jsonl"],
            )
        else:
            report_builder.record_analysis(
                mode="none",
                synthesized=False,
                confidence="n/a",
                warning="analysis.json omitted because analysis_mode=none",
                source_artifacts=[],
            )
            report_builder.add_warning("analysis.json omitted because analysis_mode=none")

        if model.runtime_context:
            _write_json(workspace / "environment.json", map_environment(model.runtime_context))

        if model.review:
            _write_json(workspace / "review.json", map_review(model.review))

        if model.slo_data:
            _write_json(workspace / "artifacts" / "slo.json", model.slo_data)

        if model.annex_markdown:
            _write_text(workspace / "artifacts" / "annex_iv.md", model.annex_markdown)

        if model.annex_json is not None:
            _write_json(workspace / "artifacts" / "annex_iv.json", model.annex_json)

        if attach_raw:
            _attach_raw_payloads(workspace, model)

        mapping_report = report_builder.build(strict=strict)
        _write_json(
            workspace / "artifacts" / "agt" / "mapping_report.json",
            mapping_report.model_dump(mode="json"),
        )

        manifest = _build_manifest(model)
        EPIContainer.pack(
            workspace,
            manifest,
            output_path,
            signer_function=signer_function,
            preserve_generated=True,
            generate_analysis=False,
        )
    finally:
        shutil.rmtree(workspace, ignore_errors=True)

    return output_path
