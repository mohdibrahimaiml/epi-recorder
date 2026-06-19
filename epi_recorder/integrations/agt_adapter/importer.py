"""Import AGT evidence artifacts into EPI format.

Raw AGT evidence is preserved verbatim as an attachment.
AuditEntry fields are mapped to EPI steps where applicable.
Every transformation is recorded in the mapping report.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from epi_core.schemas import StepModel, ManifestModel

from .detect import detect_file_format, AGTArtifactType, detect_agt_version
from .errors import AGTArtifactError
from .mapping_report import create_report, finalize_report, add_exact, add_dropped
from .transforms import (
    map_event_type, map_action, map_outcome, map_agent_did, build_step_content
)
from .schemas import AGTExportEntry, AGTFileAuditEntry, MappingReport, FieldMapping


def import_agt(
    source: str | Path,
    output_dir: str | Path = "epi-recordings",
    key_name: str = "default",
    workflow_name: str = "",
    tags: list[str] | None = None,
) -> tuple[Path, MappingReport]:
    """Import an AGT evidence artifact into an EPI .epi file.

    Args:
        source: Path to AGT artifact (.json, .jsonl, or .epi)
        output_dir: Where to write the .epi file
        key_name: EPI signing key name
        workflow_name: Override workflow name (auto-detected from entries if empty)
        tags: Additional tags for the EPI artifact

    Returns:
        (epi_file_path, mapping_report)
    """
    source = Path(source)

    # Step 1: Detect format and load entries
    artifact_type, raw_entries = detect_file_format(source)

    # Step 2: Parse entries into typed models (preserves unknown fields via extra="allow")
    entries = []
    for raw in raw_entries:
        try:
            if "signature" in raw or "content_hash" in raw:
                entries.append(AGTFileAuditEntry(**raw))
            else:
                entries.append(AGTExportEntry(**raw))
        except Exception as exc:
            raise AGTArtifactError(f"Malformed AGT entry: {exc}") from exc

    # Step 3: Detect AGT version
    agt_version = detect_agt_version(raw_entries)

    # Step 4: Initialize mapping report
    report = create_report(agt_version)
    report.total_source_fields = sum(len(e.model_dump()) for e in entries)

    # Step 5: Build EPI steps from entries
    steps = []
    for idx, entry in enumerate(entries):
        step = _entry_to_step(idx, entry, report)
        steps.append(step)

    # Step 6: Auto-detect workflow name from first entry if not provided
    if not workflow_name and entries:
        workflow_name = map_agent_did(entries[0].agent_did, report)

    # Step 7: Build EPI artifact with raw AGT evidence
    raw_agt_bytes = source.read_bytes()

    epi_path = _build_epi_artifact(
        steps=steps,
        raw_agt_bytes=raw_agt_bytes,
        report=report,
        output_dir=Path(output_dir),
        key_name=key_name,
        workflow_name=workflow_name,
        tags=tags or ["agt-import"],
    )

    finalize_report(report)
    return epi_path, report


def _entry_to_step(
    idx: int,
    entry: AGTExportEntry | AGTFileAuditEntry,
    report: MappingReport,
) -> dict:
    """Convert a single AGT AuditEntry to an EPI step dict."""
    entry_dict = entry.model_dump()

    step = {
        "index": idx,
        "timestamp": entry.timestamp.isoformat(),
        "kind": map_event_type(entry.event_type, report),
        "content": build_step_content(entry_dict, report),
        "trace_id": entry.trace_id or "",
        "span_id": "",
        "parent_span_id": "",
        "governance": {
            "action": map_action(entry.action, report),
            "outcome": map_outcome(entry.outcome, report),
            "agent_did": entry.agent_did,  # Preserved verbatim
        },
    }

    # Map agent name
    step["content"]["agent_name"] = map_agent_did(entry.agent_did, report)

    # Extract matched_rule from data.policy_name if not at top level
    data = entry_dict.get("data", {}) or {}
    matched_rule = entry_dict.get("matched_rule") or data.get("policy_name") or ""
    if matched_rule:
        step["content"]["matched_rule"] = matched_rule
        step["governance"]["policy_name"] = matched_rule

    # Map entry_id → step trace reference
    add_exact(report, "entry_id", "governance.agt_entry_id", entry.entry_id)
    step["content"]["agt_entry_id"] = entry.entry_id

    # Preserve unknown fields (extra="allow" caught these)
    known_fields = {
        "entry_id", "timestamp", "event_type", "agent_did", "action",
        "resource", "data", "outcome", "policy_decision", "trace_id",
        "entry_hash", "content_hash", "previous_hash", "signature",
    }
    unknown = {k: v for k, v in entry_dict.items() if k not in known_fields}
    if unknown:
        step["content"]["agt_unknown_fields"] = unknown
        report.unknown_fields_preserved.extend(unknown.keys())
        report.field_mappings.append(
            FieldMapping(
                source_field=str(list(unknown.keys())),
                target_field="content.agt_unknown_fields",
                mapping_type="preserved_raw",
                notes=f"Preserved {len(unknown)} unknown AGT fields",
            )
        )

    return step


def _build_epi_artifact(
    steps: list[dict],
    raw_agt_bytes: bytes,
    report: MappingReport,
    output_dir: Path,
    key_name: str,
    workflow_name: str,
    tags: list[str],
) -> Path:
    """Build and sign the EPI artifact with raw AGT evidence embedded."""
    from epi_core.container import EPIContainer

    # Create source directory with steps and raw evidence
    source_dir = output_dir / f".agt_import_{workflow_name}"
    source_dir.mkdir(parents=True, exist_ok=True)

    # Write steps as JSONL
    steps_file = source_dir / "steps.jsonl"
    with open(steps_file, "w", encoding="utf-8") as f:
        for step in steps:
            f.write(json.dumps(step, default=str) + "\n")

    # Write raw AGT evidence as attachment
    raw_file = source_dir / "agt_evidence_raw.json"
    raw_file.write_bytes(raw_agt_bytes)

    # Write mapping report
    report_file = source_dir / "mapping_report.json"
    report_file.write_text(report.model_dump_json(indent=2), encoding="utf-8")

    # Package into .epi (raw AGT evidence is auto-included via file_manifest)
    from epi_core.keys import KeyManager
    from epi_core.trust import sign_manifest
    km = KeyManager()
    if key_name not in [k["name"] for k in km.list_keys()]:
        km.generate_keypair(key_name)

    priv_key = km.load_private_key(key_name)

    manifest = ManifestModel(
        cli_command=f"agt-adapter import {workflow_name}",
        goal=f"AGT evidence import: {workflow_name}",
        tags=tags,
    )

    def signer_function(m: ManifestModel) -> ManifestModel:
        return sign_manifest(m, priv_key, key_name)

    epi_path = output_dir / f"{workflow_name}.epi"
    EPIContainer.pack(
        source_dir=source_dir,
        manifest=manifest,
        output_path=epi_path,
        signer_function=signer_function,
        preserve_generated=True,
        generate_analysis=False,
    )

    # Cleanup temp source dir
    import shutil
    shutil.rmtree(source_dir, ignore_errors=True)

    return epi_path
