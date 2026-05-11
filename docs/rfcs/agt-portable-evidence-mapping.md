# AGT → EPI Portable Evidence Mapping

- **Status**: Draft
- **Date**: 2026-05-11
- **Author**: Mohd Ibrahim Afridi (mohdibrahim@epilabs.org)
- **Related**: [AGT Discussion #806](https://github.com/microsoft/agent-governance-toolkit/discussions/806)

---

## 1. Summary

AGT produces rich governance evidence during AI agent execution — audit logs, compliance reports, policy evaluations, and EU AI Act technical documentation. Today, this evidence lives in memory or in SQLite databases on the runtime host. When an auditor requests proof of compliance six months later, the evidence is often gone, fragmented, or tied to a deployment environment that no longer exists.

This document specifies how AGT evidence bundles map into `.epi`, a portable, signed evidence envelope shipped as `epi-recorder` v4.0.3 on PyPI. This RFC is published for review by the AGT community and other governance framework maintainers. The mapping is implemented in `epi_recorder/integrations/agt/converter.py` via `export_agt_to_epi()`. The envelope carries AGT artifacts without altering their semantics. `.epi` certifies integrity — that the enclosed files have not changed since sealing — not compliance. Compliance evaluation remains the responsibility of the consumer.

---

## 2. Motivation

The EU AI Act enters into force across phased deadlines through 2027. Article 12 requires providers of high-risk AI systems to maintain logs of operation "appropriate to the system's lifecycle." The article specifies what must be recorded — input data, output data, decisions — but does not specify how that evidence must be packaged for external review. This is the gap.

AGT generates the raw material that Article 12 demands. It captures `AuditEntry` records with Merkle-tree integrity, `ComplianceReport` evaluations, and `AnnexIVDocument` technical documentation. But AGT does not define a portable export format. The evidence stays where it was created.

In AGT discussion #806, Imran Siddique validated this gap and invited a proposal mapping AGT evidence types to a portable format. Musaab Hasan emphasized that any such format must preserve evidence for assessors to verify coverage, not claim compliance on its own. This RFC is that proposal.

The `.epi` envelope exists to close this gap. It packages execution timelines, environment snapshots, policy evaluations, and raw evidence attachments into a single file that can be emailed, archived, or submitted to a regulator. The Ed25519 signature and SHA-256 `file_manifest` in `manifest.json` make tampering detectable without network access.

---

## 3. Design Principles

### 3.1 Raw must remain raw

AGT artifacts are preserved verbatim under `evidence/agt/` inside the envelope. The `ComplianceReport`, audit logs, `PolicyDocument`, and Annex IV materials are written as `compliance_report.json`, `audit_logs.json`, `policy_document.json`, and `annex_iv.json` without field reordering or value normalization. Auditors can diff the raw attachment against the original AGT output.

### 3.2 Derived must be labeled derived

Artifacts synthesized during import — `analysis.json`, `policy_evaluation.json`, `control_map.json` — carry provenance metadata indicating their `source_system` and confidence level. The `MappingReportBuilder` in `epi_recorder/integrations/agt/report.py` records every transformation in `artifacts/agt/mapping_report.json` with version `agt-mapping-report/v1`. Consumers can distinguish between what AGT produced and what the importer inferred.

### 3.3 Reference instead of inline for large artifacts

The envelope uses file paths and SHA-256 hashes in `manifest.json`'s `file_manifest` rather than embedding large artifacts as base64 strings inside JSON. This keeps the manifest small, makes incremental verification possible, and allows streaming extraction of individual files without unpacking the entire container.

### 3.4 Never silently synthesize

Every transformation performed by `normalize_agt_steps()`, `build_control_map()`, or `build_redactions()` is documented in `mapping_report.json` with the `FieldHandlingCategory` classification: `exact`, `translated`, `derived`, `synthesized`, `preserved_raw`, or `dropped`. If the importer cannot map a field, it marks it `dropped` and records why.

### 3.5 Replayability

The `steps.jsonl` timeline contains every `StepModel` needed to reconstruct the agent's execution offline. Each step carries a `prev_hash` forming an immutable chain. An auditor can replay the timeline in the embedded `viewer.html` or parse it programmatically without the original runtime environment.

### 3.6 Offline verification

Trust evaluation requires no network calls. `EPIContainer.verify_integrity()` checks the SHA-256 `file_manifest` against actual file contents. `verify_embedded_manifest_signature()` validates the Ed25519 signature against the public key in `manifest.json`. The `epi verify --strict` CLI command performs both checks and returns a trust level: `HIGH`, `MEDIUM`, `LOW`, `NONE`, `FAIL`, or `INVALID`.

### 3.7 No self-certification of compliance

The envelope certifies integrity — the files are exactly what the signer sealed — not compliance with any regulation. `policy_evaluation.json` contains the policy check results, but the consumer must evaluate whether those results satisfy their own compliance framework. `control_map.json` maps controls to evidence references; it does not assert that the evidence is sufficient.

---

## 4. AGT Evidence Model

AGT is a multi-language toolkit. The Python implementation in `agent-governance-python` defines the canonical evidence types. The following table lists every artifact type that the EPI importer consumes, its source module, output format, and classification.

| AGT Artifact | Source Module | Output Format | Classification |
|---|---|---|---|
| `AuditEntry` | `agentmesh.governance.audit` | Pydantic BaseModel → JSON | Raw evidence |
| `AuditLog` | `agentmesh.governance.audit` | List[`AuditEntry`] | Raw evidence (collection) |
| `MerkleAuditChain` | `agentmesh.governance.audit` | Merkle tree with SHA-256 nodes | Integrity metadata |
| `ComplianceReport` | `agentmesh.governance.compliance` | Pydantic BaseModel → JSON | Derived evidence |
| `ComplianceViolation` | `agentmesh.governance.compliance` | Nested in `ComplianceReport` | Derived evidence |
| `Policy` | `agentmesh.governance.policy` | Pydantic BaseModel → JSON / YAML | Raw evidence |
| `PolicyRule` | `agentmesh.governance.policy` | Nested in `Policy` | Raw evidence |
| `PolicyDecision` | `agentmesh.governance.policy` | Enum / string | Derived evidence |
| `AnnexIVDocument` | `agentmesh.governance.annex_iv` | Pydantic BaseModel → JSON / Markdown | Derived evidence (synthesized) |
| `SLO` | `agent_sre.slo.objectives` | Class with `to_dict()` | Raw evidence |
| `ErrorBudget` | `agent_sre.slo.objectives` | Nested in `SLO` | Derived evidence |
| `AgentSBOM` | `agent_sre.sbom` | SPDX 2.3 or CycloneDX 1.5 JSON | Attestation |
| `SignatureBundle` | `agent_sre.signing` | `dataclass` with hex fields | Integrity metadata |
| `GovernanceAttestation` | `agent_compliance.verify` | `dataclass` with control results | Attestation |
| `RuntimeEvidence` | `agent_compliance.verify` | YAML or JSON, schema `agt-runtime-evidence/v1` | Raw evidence |
| `ApprovalRequest` | `agentmesh.governance.approval` | `dataclass` | Raw evidence |
| `ApprovalDecision` | `agentmesh.governance.approval` | `dataclass` | Raw evidence |

### 4.1 AuditEntry and AuditLog

`AuditEntry` is the atomic unit of governance telemetry. Each entry carries `entry_id`, `timestamp`, `event_type`, `agent_did`, `action`, `resource`, `data`, `outcome`, `policy_decision`, `matched_rule`, `previous_hash`, `entry_hash`, `trace_id`, and `session_id`. The `compute_hash()` method produces a SHA-256 digest over canonical JSON of the entry fields. `AuditLog` is the append-only collection. `MerkleAuditChain` builds a Merkle tree over the log for efficient inclusion proofs.

### 4.2 ComplianceReport and ComplianceViolation

`ComplianceReport` aggregates evaluation results for a framework (`eu_ai_act`, `soc2`, `hipaa`, `gdpr`). It contains `report_id`, `generated_at`, `framework`, `period_start`, `period_end`, `organization_id`, `agents_covered`, `total_controls`, `controls_met`, `controls_partial`, `controls_failed`, `compliance_score`, `violations`, `evidence_items`, and `recommendations`. `ComplianceViolation` records individual findings with `violation_id`, `agent_did`, `action_type`, `control_id`, `framework`, `severity`, `description`, `evidence`, `remediated`, `remediated_at`, and `remediation_notes`.

### 4.3 Policy, PolicyRule, and PolicyDecision

`Policy` is a declarative document with `apiVersion` (`governance.toolkit/v1`), `metadata`, and `rules`. `PolicyRule` defines `name`, `description`, `stage` (`pre_input`, `pre_tool`, `post_tool`, `pre_output`), `condition` (expression string), `action` (`allow`, `deny`, `warn`, `require_approval`, `log`), `limit`, `approvers`, `priority`, and `enabled`. `PolicyDecision` is the runtime outcome: `allowed`, `blocked`, or `error`. The `condition` field contains free-form expression logic that cannot be flattened into JSON without loss of semantics.

**Mapping note:** `allowed` maps to EPI `validation.pass`, `blocked` maps to `validation.fail`, and `error` maps to `validation.corrected` in `steps.jsonl`.

### 4.4 AnnexIVDocument

`AnnexIVDocument` assembles existing governance artifacts into the EU AI Act Annex IV conformity dossier. It contains `title`, `generated_at`, `system_name`, `provider`, `sections` (list of `AnnexIVSection`), and `metadata`. Each `AnnexIVSection` has `number`, `title`, `content`, `placeholder`, and `source_artifacts`. The document is synthesized by `TechnicalDocumentationExporter` from `ComplianceReport`, `Policy`, and `AuditLog` inputs.

### 4.5 SLO and ErrorBudget

`SLO` defines service-level objectives with `name`, `indicators` (SLIs), `error_budget`, `description`, `labels`, and `agent_id`. `ErrorBudget` tracks `total`, `consumed`, `window_seconds`, `burn_rate_alert`, `burn_rate_critical`, `exhaustion_action`, and a bounded `deque` of events (`maxlen=100_000`). The `to_dict()` method exports a snapshot; the full event deque is not serialized by default.

### 4.6 AgentSBOM and SignatureBundle

`AgentSBOM` generates SPDX 2.3 or CycloneDX 1.5 output from `requirements.txt` or `pyproject.toml`. It contains `packages` (list of `SBOMPackage`) and `relationships` (list of `SBOMRelationship`). `SignatureBundle` is the portable verification envelope produced by `ArtifactSigner.sign_artifact()`: `signature` (hex), `public_key` (hex), `artifact_hash` (SHA-256 hex), `timestamp` (ISO-8601), and optional `signer_did`.

### 4.7 GovernanceAttestation and RuntimeEvidence

`GovernanceAttestation` is produced by `agent_compliance.verify` and contains `passed`, `controls` (list of `ControlResult`), `toolkit_version`, `python_version`, `platform_info`, `verified_at`, `attestation_hash`, `controls_passed`, `controls_total`, `mode`, `strict`, `evidence_source`, `evidence_checks`, and `failures`. `RuntimeEvidence` is the deployment-level manifest with `source_path`, `schema` (`agt-runtime-evidence/v1`), `generated_at`, `toolkit_version`, and `deployment`.

### 4.8 ApprovalRequest and ApprovalDecision

`ApprovalRequest` captures `action`, `rule_name`, `policy_name`, `agent_id`, `context`, `approvers`, and `requested_at`. `ApprovalDecision` captures `approved`, `approver`, `reason`, and `decided_at`. These represent human-in-the-loop governance checkpoints.

---

## 5. EPI Container Model

`.epi` is a polyglot file format. It begins with a 128-byte binary envelope-v2 header and continues with a ZIP payload. The envelope header contains: magic (`<!--`), version (1 byte), payload format (1 byte), flags (2 bytes), payload length (8 bytes), artifact UUID (16 bytes), created-at microseconds (8 bytes), payload SHA-256 (32 bytes), and reserved padding (56 bytes). The ZIP payload contains the evidence files, manifest, viewer, and verification guide.

### 5.1 File Layout

A typical `.epi` file contains the following entries:

| Path | Content | Generated By |
|---|---|---|
| `mimetype` | `application/vnd.epi+zip` | `EPIContainer.pack()` |
| `manifest.json` | `ManifestModel` as canonical JSON | `EPIContainer.pack()` |
| `steps.jsonl` | NDJSON stream of `StepModel` records | `normalize_agt_steps()` |
| `policy.json` | `PolicyModel` from AGT `policy_document` | `map_policy_document()` |
| `policy_evaluation.json` | Derived evaluation from `ComplianceReport` | `map_policy_evaluation()` |
| `analysis.json` | Synthesized analysis | `synthesize_analysis()` |
| `environment.json` | Runtime context snapshot | `map_environment()` |
| `review.json` | Human review ledger (optional) | `map_review()` |
| `control_map.json` | Standards-aligned control mapping | `build_control_map()` |
| `redactions.json` | Non-repudiable redaction metadata (optional) | `build_redactions()` |
| `artifacts/agt/mapping_report.json` | Transformation audit | `MappingReportBuilder` |
| `artifacts/agt/bundle.json` | Full raw AGT bundle | `_attach_raw_payloads()` |
| `artifacts/agt/compliance_report.json` | Raw `ComplianceReport` | `_attach_raw_payloads()` |
| `artifacts/agt/audit_logs.json` | Raw `AuditLog` entries | `_attach_raw_payloads()` |
| `artifacts/agt/policy_document.json` | Raw `Policy` | `_attach_raw_payloads()` |
| `viewer.html` | Embedded HTML viewer | `EPIContainer._create_embedded_viewer()` |
| `VERIFY.txt` | Human verification guide | `EPIContainer.pack()` |

### 5.2 manifest.json

`manifest.json` is the cryptographic root of trust. It is an instance of `epi_core.schemas.ManifestModel` with the following fields relevant to AGT imports:

| Field | Type | Description |
|---|---|---|
| `spec_version` | string | EPI specification version (e.g. `"4.0.3"`) |
| `workflow_id` | UUID | Unique artifact identifier |
| `created_at` | ISO-8601 datetime | Sealing timestamp |
| `cli_command` | string | Original command that produced the workflow |
| `env_snapshot_hash` | SHA-256 hex | Hash of `environment.json` |
| `file_manifest` | `dict[str, str]` | Mapping of file paths to SHA-256 hashes |
| `public_key` | hex string | Ed25519 public key (32 bytes raw, hex-encoded) |
| `signature` | string | `ed25519:<key_name>:<hex_signature>` |
| `container_format` | `"legacy-zip"` or `"envelope-v2"` | Physical container format |
| `analysis_status` | `"complete"`, `"skipped"`, or `"error"` | Analysis generation state |
| `source` | `dict[str, str]` | System integration identity |
| `trust` | `dict[str, Any]` | `payload_hash`, `artifact_uuid`, `mimetype`, `envelope_version` |
| `policy` | `PolicyModel` | Formal policy evaluation result |
| `governance` | `dict[str, Any]` | Optional DID identity, trust score, source |

The signature is computed over the canonical JSON hash of the manifest excluding the `signature` field. For spec v2.x+, JSON canonicalization (sorted keys, no whitespace) is used. For spec v1.x, CBOR encoding (RFC 8949) is used instead.

### 5.3 steps.jsonl

`steps.jsonl` is an NDJSON stream where each line is a `StepModel`. Fields include `index`, `timestamp`, `kind`, `content`, `trace_id`, `span_id`, `parent_span_id`, `prev_hash`, and optional `governance`. The `prev_hash` field contains the SHA-256 hash of the canonical JSON of the previous step, forming an immutable chain. Kind values include `shell.command`, `python.call`, `llm.request`, `llm.response`, `file.write`, `security.redaction`, `validation.pass`, `validation.fail`, `validation.corrected`, and `validation.start`.

### 5.4 Review System

Reviews are additive metadata bound to the sealed artifact. `review.json` contains reviewer identity, verdict, notes, and a binding hash that ties the review to the exact `manifest.json` and `steps.jsonl` at the time of review. The review ledger is append-only: new reviews are added as `reviews/<review_id>.json` without rewriting the sealed execution files. Review versions are `1.0.0` (legacy) and `1.1.0` (with artifact binding and ledger chaining).

### 5.5 Cryptographic Integrity and Trust Levels

Verification produces one of six trust levels:

| Level | Condition | Meaning |
|---|---|---|
| `HIGH` | Integrity OK + valid signature + known trusted identity | Cryptographically verified and integrity intact |
| `MEDIUM` | Integrity OK + unsigned | Unsigned but integrity intact |
| `LOW` | Integrity OK + valid signature + unknown identity | Valid signature from unknown identity — verify signer before trusting |
| `NONE` | Integrity compromised | Integrity compromised — do not trust |
| `FAIL` | Identity mismatch | Identity in manifest does not match the verifying key registry |
| `INVALID` | Identity revoked | Signature invalid or identity revoked — do not trust |

The `epi verify --strict` CLI applies `VerificationPolicy.STRICT`, which requires a known trusted identity and full telemetry completeness in addition to integrity and valid signature.

---

## 6. Field-Level Mapping Table

The following table maps every AGT artifact from Section 4 to its destination inside `.epi`, the transformation applied, and what is preserved or lost.

| AGT Evidence Object | AGT Source | `.epi` Destination | Transformation Type | Preservation Level | Notes |
|---|---|---|---|---|---|
| `AuditEntry` | `agentmesh.governance.audit` | `steps.jsonl` (normalized) + `artifacts/agt/audit_logs.json` (raw) | `translated` (normalized) / `preserved_raw` | High | `entry_id` → `StepModel.index`; `data` → `StepModel.content`; Merkle `entry_hash`/`previous_hash` preserved only in raw attachment, not replayed in EPI's `prev_hash` chain |
| `AuditLog` | `agentmesh.governance.audit` | `artifacts/agt/audit_logs.json` | `preserved_raw` | High | Full list of `AuditEntry` objects written verbatim |
| `MerkleAuditChain` | `agentmesh.governance.audit` | `artifacts/agt/audit_logs.json` (embedded in entries) | `preserved_raw` | Medium | Merkle tree structure is lost; only per-entry `entry_hash` and `previous_hash` are preserved. Inclusion proofs cannot be recomputed from `.epi` alone |
| `ComplianceReport` | `agentmesh.governance.compliance` | `artifacts/agt/compliance_report.json` (raw) + `policy_evaluation.json` (derived) | `preserved_raw` + `derived` | High | Raw report preserved verbatim; `policy_evaluation.json` synthesizes `controls_met`/`controls_failed` into `PolicyModel.status` and `rules` |
| `ComplianceViolation` | `agentmesh.governance.compliance` | `policy_evaluation.json` (derived) + `control_map.json` (derived) | `derived` + `synthesized` | Medium | Violation `control_id` mapped to `ControlMapEntryModel.control_id`; `severity` influences `ControlMapEntryModel.status`. Remediation metadata is preserved in raw attachment |
| `Policy` | `agentmesh.governance.policy` | `artifacts/agt/policy_document.json` (raw) + `policy.json` (derived) | `preserved_raw` + `translated` | High | Raw policy preserved verbatim; `policy.json` extracts `policy_id`, `version`, `status`, and `rules` (rule IDs only) |
| `PolicyRule` | `agentmesh.governance.policy` | `policy.json` (`rules[]`) | `translated` | Low | Only `name` (rule ID) is preserved in `PolicyModel.rules`. `condition`, `stage`, `action`, `limit`, `approvers`, and `priority` are dropped from `policy.json` because `PolicyModel.rules` is `List[str]`. Raw `policy_document.json` must be consulted for rule semantics |
| `PolicyDecision` | `agentmesh.governance.policy` | `steps.jsonl` (`kind: validation.*`) | `translated` | Medium | Decisions are mapped to EPI validation steps with `result` (`pass`/`fail`/`corrected`). See Section 4.3 for the AGT-to-EPI outcome mapping |
| `AnnexIVDocument` | `agentmesh.governance.annex_iv` | `artifacts/annex_iv.json` + `artifacts/annex_iv.md` | `preserved_raw` | High | Both JSON and Markdown forms are preserved if present in the AGT bundle |
| `SLO` | `agent_sre.slo.objectives` | `artifacts/slo.json` | `preserved_raw` | High | `SLO.to_dict()` snapshot is written as JSON |
| `ErrorBudget` | `agent_sre.slo.objectives` | `artifacts/slo.json` (nested) | `preserved_raw` | Medium | `total`, `consumed`, `remaining_percent`, `is_exhausted`, `burn_rate`, `exhaustion_action`, and `firing_alerts` are preserved. The bounded event `deque` is not serialized |
| `AgentSBOM` | `agent_sre.sbom` | `artifacts/agt/bundle.json` (nested) | `preserved_raw` | High | Full SPDX 2.3 or CycloneDX 1.5 document preserved inside raw bundle |
| `SignatureBundle` | `agent_sre.signing` | `artifacts/agt/bundle.json` (nested) | `preserved_raw` | High | AGT signatures on raw artifacts are preserved but not replayed into EPI's manifest signature. AGT signs raw artifact bytes; EPI signs canonical manifest JSON hash. These are incompatible domains |
| `GovernanceAttestation` | `agent_compliance.verify` | `artifacts/agt/bundle.json` (nested) | `preserved_raw` | High | Full attestation with `controls`, `evidence_checks`, and `failures` preserved in raw bundle |
| `RuntimeEvidence` | `agent_compliance.verify` | `artifacts/agt/bundle.json` (nested) | `preserved_raw` | High | YAML/JSON evidence file with schema `agt-runtime-evidence/v1` preserved in raw bundle |
| `ApprovalRequest` | `agentmesh.governance.approval` | `steps.jsonl` (`kind: agent.decision` or governance metadata) | `translated` | Medium | Request details mapped to step `governance` metadata or `review.json` if multi-party |
| `ApprovalDecision` | `agentmesh.governance.approval` | `steps.jsonl` + `review.json` | `translated` | Medium | Decision outcome (`approved`, `approver`, `reason`, `decided_at`) mapped to `review.json` entries |

### 6.1 What Is Lost in Normalization

The following transformations inherently lose information. The raw attachment is the only way to recover the original semantics.

**AGT Merkle inclusion proofs.** EPI's `prev_hash` chain in `steps.jsonl` is computed from the canonical JSON of `StepModel` records. It is not compatible with AGT's `MerkleAuditChain`, which hashes `AuditEntry` fields in a different canonical form. The per-entry `entry_hash` and `previous_hash` are preserved in `artifacts/agt/audit_logs.json`, but the Merkle tree structure (parent nodes, root hash, inclusion proofs) is not reconstructed inside `.epi`.

**PolicyRule.condition logic.** `PolicyModel.rules` is `List[str]` — it stores only rule IDs. The `condition` expression string, which may contain dot-notation field access, `and`/`or` boolean logic, comparison operators, and `in` membership tests, is flattened away during import. The full rule semantics remain available only in `artifacts/agt/policy_document.json`.

**ErrorBudget event deque.** `ErrorBudget._events` is a `collections.deque` with `maxlen=100_000`. Only the derived metrics (`consumed`, `remaining_percent`, `burn_rate`) are exported via `to_dict()`. The individual good/bad event records are not preserved.

**Signature domain mismatch.** AGT's `ArtifactSigner` produces `SignatureBundle` objects that sign raw artifact file bytes. EPI's `sign_manifest()` signs the SHA-256 hash of canonical JSON of the `ManifestModel`. An AGT signature on `compliance_report.json` cannot be verified against the same file inside `.epi` using EPI's signature verification logic, because EPI never signs the raw file bytes. Both signatures coexist: AGT signatures in `artifacts/agt/bundle.json`, EPI signature in `manifest.json`.

### 6.2 What Is Synthesized

The importer creates the following artifacts that do not exist in the original AGT bundle:

| Synthesized Artifact | Source AGT Data | Generator Function |
|---|---|---|
| `analysis.json` | `ComplianceReport` + `AuditLog` + `SLO` | `synthesize_analysis()` |
| `policy_evaluation.json` | `ComplianceReport` + `Policy` | `map_policy_evaluation()` |
| `control_map.json` | `ComplianceReport.violations[]` + `AnnexIVDocument` | `build_control_map()` |
| `redactions.json` | `AuditLog[].data` (regex scan) | `build_redactions()` |
| `mapping_report.json` | All of the above | `MappingReportBuilder` |

Each synthesized artifact is labeled with `source_system: "epi-recorder/agt-import"` and a confidence indicator in `mapping_report.json`.

---

## 7. Standards Alignment

The `.epi` envelope is designed to carry standards-native artifacts, not to replace the standards themselves. This section describes the conceptual relationship with five relevant standards.

### 7.1 in-toto

**Conceptual overlap.** in-toto provides supply-chain integrity through signed link metadata that records materials, products, and commands for each step. AGT's `AuditEntry` sequence and EPI's `steps.jsonl` both capture step-level execution traces. The `prev_hash` chain in `steps.jsonl` serves a similar chaining purpose to in-toto's link-to-link binding.

**What `.epi` can borrow.** The `control_map.json` evidence reference type `raw-timeline` explicitly references in-toto Link format concepts. An EPI consumer could embed a genuine in-toto layout in `artifacts/provenance/intoto.json` and reference it from `control_map.json`. The envelope's file manifest and signature provide the same tamper-evidence properties that in-toto link metadata provides.

**What `.epi` must NOT overclaim.** `.epi` is not an in-toto implementation. It does not produce in-toto-compatible link metadata, does not support in-toto layout verification, and does not implement the in-toto supply-chain layout language. The envelope cannot be verified with the in-toto client.

**Compatibility opportunity.** A future exporter could translate `steps.jsonl` into a sequence of in-toto Link files and produce an in-toto Layout that wraps the AGT execution as a supply chain. This would be a Phase B or C extension, not part of the core envelope.

### 7.2 CycloneDX

**Conceptual overlap.** CycloneDX 1.5 defines an evidence model for software components: `metadata.component.evidence` can include identity, occurrence, and callstack evidence. AGT's `AgentSBOM` already supports CycloneDX 1.5 output. EPI's `control_map.json` references CycloneDX evidence paths for component attestations.

**What `.epi` can borrow.** The envelope can carry a complete CycloneDX BOM as `evidence/sbom/cyclonedx.json`. `control_map.json` can reference specific BOM fields (e.g., `metadata.component.evidence[*]`) as standards-native evidence for EU AI Act Article 11 (technical documentation) or Article 13 (transparency).

**What `.epi` must NOT overclaim.** `.epi` does not encode timeline evidence as BOM components. It does not generate CycloneDX files from AGT data; it only preserves CycloneDX files that AGT (or another toolchain) has already produced. The envelope is not a CycloneDX parser or validator.

**Compatibility opportunity.** If AGT's `AgentSBOM` produces CycloneDX with evidence fields populated, the EPI importer can reference those fields directly in `control_map.json`. No translation layer is required.

### 7.3 SLSA

**Conceptual overlap.** SLSA (Supply-chain Levels for Software Artifacts) defines provenance requirements for software builds. SLSA Provenance v1.0 records `buildDefinition`, `runDetails`, and `resolvedDependencies`. AI model training and deployment pipelines share structural similarities with software builds: they consume inputs (data, code), run commands (training scripts), and produce outputs (model weights, predictions).

**What `.epi` can borrow.** EPI's `control_map.json` references `artifacts/provenance/slsa.json` as a standards-native evidence path. The envelope can carry a genuine SLSA Provenance statement. `buildDefinition.externalParameters` is a natural place to record training configuration, and `resolvedDependencies` can list training datasets and model checkpoints.

**What `.epi` must NOT overclaim.** Agent execution is not a software build. EPI does not generate SLSA Provenance from AGT data. It does not assign SLSA build levels (L1–L3). The envelope merely provides a structured home for SLSA statements produced by other tools. A signed `.epi` does not imply SLSA compliance.

**Compatibility opportunity.** A CI/CD pipeline that trains an AI model could produce a SLSA Provenance statement and embed it in `.epi` alongside the AGT governance evidence. The combination gives auditors both supply-chain provenance (SLSA) and runtime governance evidence (AGT) in one envelope.

### 7.4 Sigstore

**Conceptual overlap.** Sigstore provides transparency and keyless signing through Rekor (transparency log), Fulcio (OIDC-based CA), and Cosign (container signing). EPI uses Ed25519 signatures, which are cryptographically similar to the ECDSA signatures used by Sigstore, but with a different trust model: EPI relies on key distribution and identity registries, not OIDC identity providers or transparency logs.

**What `.epi` can borrow.** The envelope's `manifest.json` signature format (`ed25519:<key_name>:<hex_signature>`) could be extended to support Sigstore-style signed attestations as embedded JSON objects. The `governance` field in `ManifestModel` has room for a `rekor_entry_id` or `fulcio_identity`.

**What `.epi` must NOT overclaim.** `.epi` is not a Sigstore bundle. It does not submit entries to Rekor, does not verify Fulcio certificates, and does not support OIDC-based keyless signing. The envelope does not provide the transparency guarantees that Sigstore provides through its public log.

**Compatibility opportunity.** In Phase C (optional transparency anchoring), a signer plugin could submit the manifest hash to Rekor and embed the Rekor entry UUID in `manifest.json`. Verification would then check both the Ed25519 signature and the Rekor inclusion proof. This must degrade gracefully: if Rekor is unreachable, the Ed25519 signature alone still provides integrity.

### 7.5 SCITT

**Conceptual overlap.** SCITT (Supply Chain Integrity, Transparency, and Trust) is an IETF draft that defines a transparency service for software supply chain artifacts. It uses signed statements with COSE headers and Merkle-tree transparency logs. SCITT's conceptual model — signed statements about artifacts, with transparency logging — aligns with EPI's model of signed envelopes carrying attestations.

**What `.epi` can borrow.** SCITT's signed statement format (COSE_Sign1 with payload) could be used as an alternative signing layer for `.epi` in the future. The envelope's 128-byte header already has reserved fields (`reserved_flags`, `reserved_tail`) that could signal SCITT compatibility.

**What `.epi` must NOT overclaim.** `.epi` is not a SCITT transparency service. It does not implement a transparency log, does not produce COSE-signed statements, and does not support SCITT receipt verification. The envelope is a file format, not a network service.

**Compatibility opportunity.** A SCITT-compatible adapter could wrap an `.epi` file as the payload of a SCITT signed statement and register it with a transparency service. This would give the envelope the long-term auditable timestamp that SCITT provides, without changing the envelope format itself.

---

## 8. Threat Model

The following threats are assessed from the perspective of an auditor or regulator evaluating an `.epi` file that claims to contain AGT governance evidence.

### 8.1 Tampering

**Threat.** An attacker modifies files inside `.epi` after sealing — for example, changing `policy_evaluation.json` to hide a violation.

**Mitigation.** The SHA-256 `file_manifest` in `manifest.json` covers every file. `EPIContainer.verify_integrity()` recomputes the hash of each extracted file and reports mismatches. Any modification invalidates the manifest hash, which invalidates the Ed25519 signature. The `epi verify --strict` CLI fails with trust level `NONE` if any file is tampered with.

### 8.2 Replay

**Threat.** An attacker reuses a valid `.epi` from a previous run and presents it as evidence for a different deployment or time period.

**Mitigation.** `manifest.json` contains `workflow_id` (UUID), `created_at` (timestamp), and `env_snapshot_hash`. The `workflow_id` is unique per artifact and cannot be changed without invalidating the signature. Auditors should cross-check `created_at` against the claimed reporting period and verify that `environment.json` contains the expected deployment context. The `VERIFY.txt` file includes the artifact UUID for manual verification.

### 8.3 Signature Spoofing

**Threat.** An attacker confuses the verifier by mixing hex-encoded and base64-encoded signatures, or by stripping the `ed25519:` prefix.

**Mitigation.** EPI v4.0.3 mandates the format `ed25519:<key_name>:<hex_signature>`. The verifier in `epi_core/trust.py` parses this format strictly and rejects signatures that do not match. Legacy base64-encoded signatures from v1.x are detected and handled with explicit backward-compatibility logic. The `epi verify` CLI reports `INVALID` for malformed signatures.

### 8.4 Redaction Abuse

**Threat.** A producer redacts evidence of a policy violation and claims the removal was for PII protection.

**Mitigation.** Every redaction produces both a `redactions.json` ledger entry and a `security.redaction` step in `steps.jsonl`. The step is included in the signed `file_manifest`, making the redaction non-repudiable. Each redaction carries `non_compliance_risk` (`none`, `low`, `medium`, `high`) and `justification`. Auditors should reject artifacts with any `high`-risk redaction and manually verify that the justification matches the data category. The `approved_by` field requires a named authority with a DID or PGP key.

### 8.5 Evidence Loss

**Threat.** Raw AGT attachments are omitted (`attach_raw=False`), causing Merkle proofs, original `PolicyRule` conditions, and SBOM relationships to be lost.

**Mitigation.** The `export_agt_to_epi()` function defaults to `attach_raw=True`. The `MappingReportBuilder` records whether raw attachments were included. Auditors should check `mapping_report.json` for the `preserved_raw` classification count. If it is zero, the artifact is incomplete. The `epi verify --strict` CLI does not currently enforce raw attachment presence, but a future policy could add this check.

### 8.6 Provenance Ambiguity

**Threat.** The `source` field in `manifest.json` is free-form (`dict[str, str]`), allowing producers to claim any origin without validation.

**Mitigation.** The `source` field is informational only. Trust evaluation does not depend on it. The `workflow_id`, `created_at`, and cryptographic signature provide stronger provenance than free-form text. Consumers should treat `source` as a hint, not a claim. Future versions of the spec could require `source` to contain a verifiable DID.

### 8.7 Overclaiming Compliance

**Threat.** A producer or intermediary claims that a signed `.epi` constitutes compliance certification.

**Mitigation.** The envelope certifies integrity, not compliance. This is stated in the design principles, the `VERIFY.txt` file, and the `trust_message` returned by verification. `policy_evaluation.json` contains the producer's own evaluation, which the consumer must independently assess. The `control_map.json` coverage summary explicitly marks controls as `evidence_missing` when evidence is not present. Regulators should train reviewers to distinguish between integrity verification (`epi verify`) and compliance assessment (manual review of evidence).

### 8.8 Ambiguous Mapping

**Threat.** The importer maps AGT fields to EPI fields in ways that obscure semantic differences — for example, mapping `PolicyRule.condition` to a simple rule ID.

**Mitigation.** The `mapping_report.json` records every field mapping with its `FieldHandlingCategory`. Fields that lose semantics are marked `translated` or `dropped`, not `exact`. Auditors can cross-reference the mapping report against the raw attachment to reconstruct the original semantics. The mapping report version is `agt-mapping-report/v1`, which allows tooling to evolve without silent behavior changes.

### 8.9 Format Drift

**Threat.** AGT evolves its schema — for example, adding new fields to `ComplianceReport` or changing `PolicyRule.stage` enum values — and the EPI importer no longer recognizes them.

**Mitigation.** The AGT bundle schema in `epi_recorder/integrations/agt/schema.py` uses `ConfigDict(extra="allow")`, which means unknown fields are preserved in the raw bundle even if the importer does not process them. The `AGTBundleModel` validator requires only that `audit_logs` or `flight_recorder` be present. New AGT fields will be carried in `artifacts/agt/bundle.json` without blocking import. The `MappingReportBuilder` records unknown fields as `unclassified` for later analysis.

### 8.10 Backward Compatibility

**Threat.** An `.epi` file created with v1.x (CBOR manifest encoding) cannot be verified by a v4.x tool (JSON canonicalization).

**Mitigation.** `EPIContainer` supports both `legacy-zip` and `envelope-v2` container formats. The `manifest.json` `spec_version` field indicates the format version. `verify_integrity()` handles both formats transparently. Legacy artifacts are detected by the absence of `container_format` or by the presence of CBOR-encoded manifest data. The CLI warns when verifying legacy artifacts but still performs integrity checks. Producers should use v4.x+ for new artifacts to ensure the strongest verification guarantees.

---

## 9. Open Questions

The following questions are intentionally unresolved. They represent genuine uncertainty about requirements, feasibility, or governance acceptance.

### 9.1 AGT Multi-Language SDK Parity

The EPI importer is tested against the Python AGT SDK (`agent-governance-python`). The .NET, TypeScript, Go, and Rust implementations may produce bundle shapes that differ in field naming, datetime formatting, or enum serialization. Should the importer maintain per-language normalizers, or should AGT define a stricter cross-language JSON export contract?

### 9.2 DID:WEB Resolution Stability for Long-Term Archival

`RedactionApproverModel.identity` supports `did:web` identifiers. A `did:web` document is hosted on an HTTPS endpoint controlled by the issuer. If the domain expires or the endpoint changes, the DID document becomes unresolvable. Should the envelope embed a cached copy of the DID document, or should long-term archival switch to `did:key` (self-certifying but non-rotatable)?

### 9.3 Regulatory Acceptance of Synthesized Analysis

`analysis.json` is synthesized from AGT evidence during import, not produced by a native EPI analyzer. Regulators may question whether synthesized artifacts satisfy EU AI Act Article 12's requirement for "logs of operation." Is a post-hoc synthesis acceptable if the raw audit logs are preserved alongside it? This question has not been tested with a notified body.

### 9.4 Sigstore OIDC Availability in Air-Gapped Enterprise Environments

Phase C proposes optional Sigstore/Rekor transparency anchoring. Sigstore's keyless signing requires OIDC identity providers (GitHub, Google, Microsoft) and network access to Rekor. Many enterprises subject to EU AI Act operate air-gapped environments. Should Phase C include a private Rekor instance option, or is Sigstore integration limited to non-air-gapped deployments?

### 9.5 Merkle Proof Interoperability

AGT's `MerkleAuditChain` provides cryptographic inclusion proofs. EPI's `prev_hash` chain provides a different form of tamper evidence. Is there value in defining a bridge format that allows an auditor to verify AGT Merkle proofs against EPI's extracted raw data, or is raw preservation sufficient?

### 9.6 PolicyRule.condition Expression Standardization

`PolicyRule.condition` uses a custom expression language (dot-notation access, `and`/`or`, comparison operators, `in` membership). This language is not standardized. Should EPI define a mapping to a standard expression format (e.g., CEL, OPA Rego, or JSON Logic) to enable cross-tool policy evaluation, or is raw preservation of the AGT-native expression sufficient?

### 9.7 ErrorBudget Event Retention

`ErrorBudget._events` is a bounded `deque(maxlen=100_000)` that silently evicts old events. For compliance purposes, should EPI require that the full event history be preserved (e.g., by writing the deque to `artifacts/slo_events.jsonl`), or is the derived metrics snapshot sufficient for audit?

### 9.8 Control Map Coverage Thresholds

The test vectors assert `coverage_percentage >= 80%` as a passing threshold. This is an arbitrary heuristic. Should the RFC define formal coverage thresholds per framework (e.g., EU AI Act requires 100% of Articles 9–15), or should coverage assessment remain a consumer-side policy decision?

### 9.9 Review Ledger Forking

The EPI review system supports append-only reviews via `reviews/<review_id>.json`. There is no mechanism to prevent two reviewers from producing contradictory reviews that both appear valid. Should the review system include a conflict-resolution or arbitration mechanism, or is contradictory review presence an acceptable feature (evidence of disagreement)?

### 9.10 AGT Discussion #806 Outcome

This RFC is a response to AGT discussion #806. The AGT maintainers have not yet endorsed or rejected the proposal. Should the RFC be treated as a unilateral specification (EPI-side only), or should it be submitted as a formal AGT proposal with maintainer review? The answer affects whether `.epi` export becomes an official AGT feature or remains an optional adapter.

---

## 10. Future Work

Future work is organized into three phases with no specific timelines. Each phase builds on the previous one.

### Phase A: Harden Current AGT Importer

- Enforce raw attachment in strict mode (currently `attach_raw=True` is the default but not mandatory)
- Ensure `mapping_report.json` is complete for every field in the AGT bundle
- Add importer-level schema validation against published AGT bundle schemas
- Improve `PolicyRule.condition` preservation (e.g., embed raw rule objects in `policy.json` metadata)
- Add coverage threshold configuration per framework
- Harden redaction heuristics against false positives with allowlist support

### Phase B: Standards-Native Attestation Embedding

- Add an in-toto layout export option that translates `steps.jsonl` into a sequence of in-toto Link files with a generated Layout
- Support embedding genuine SLSA Provenance v1.0 statements in `artifacts/provenance/slsa.json`
- Support embedding genuine CycloneDX 1.5 BOMs with evidence fields in `evidence/sbom/cyclonedx.json`
- Add `control_map.json` verification that checks whether referenced standards-native files actually exist inside the envelope
- Add exporter plugins for CI/CD pipelines (GitHub Actions, Azure DevOps) that generate SLSA provenance during model training

### Phase C: Optional Transparency Anchoring

- Add a Sigstore/Rekor signer plugin that submits the manifest hash to a transparency log and embeds the Rekor entry UUID
- Add SCITT adapter that wraps `.epi` as the payload of a SCITT signed statement
- Support private Rekor instances for air-gapped enterprise deployments
- Ensure all transparency features degrade gracefully: if the transparency service is unreachable, the Ed25519 signature and file manifest still provide full offline verification
- Define a key rotation and revocation registry format for long-term archival

---

## 11. Non-Goals

The following are explicitly out of scope for this RFC and for the EPI AGT importer:

- **Does not propose AGT codebase changes.** This RFC specifies the EPI-side adapter only. It does not require modifications to `agent-governance-toolkit` repositories, APIs, or SDKs.
- **Does not propose `.epi` as a replacement for in-toto, SLSA, CycloneDX, or SCITT.** The envelope carries these standards; it does not compete with them.
- **Does not propose `.epi` as compliance certification.** A signed `.epi` certifies integrity. Compliance is evaluated by the consumer against their own policy framework.
- **Does not propose mandatory adoption by any framework.** `.epi` export is optional. AGT users can continue to use SQLite audit logs, Markdown exports, and in-memory evidence without ever producing an `.epi` file.
- **Does not define a new signing algorithm.** The envelope uses Ed25519. It does not introduce new cryptography.
- **Does not require network access for verification.** All trust evaluation must work offline. Network-dependent features (transparency logs, DID resolution) are optional and must degrade gracefully.
- **Does not standardize policy rule semantics.** The importer preserves raw policy documents but does not attempt to normalize `PolicyRule.condition` into a cross-platform expression language.

---

## 12. References

| Reference | URL |
|---|---|
| Agent Governance Toolkit (AGT) | `https://github.com/microsoft/agent-governance-toolkit` |
| AGT Discussion #806 — Portable Evidence Format | `https://github.com/microsoft/agent-governance-toolkit/discussions/806` |
| AGT Annex IV Exporter #782 | `https://github.com/microsoft/agent-governance-toolkit/pull/782` |
| EPI Recorder Repository | `https://github.com/mohdibrahimaiml/epi-recorder` |
| EPI Recorder on PyPI (v4.0.3) | `https://pypi.org/project/epi-recorder/4.0.3/` |
| EPI Specification | `https://github.com/mohdibrahimaiml/epi-spec` |
| in-toto v1.0 Specification | `https://github.com/in-toto/docs/blob/master/in-toto-spec.md` |
| SLSA v1.0 Provenance | `https://slsa.dev/spec/v1.0/provenance` |
| CycloneDX 1.5 Specification | `https://cyclonedx.org/specification/overview/` |
| SCITT IETF Draft | `https://datatracker.ietf.org/doc/draft-ietf-scitt-architecture/` |
| EU AI Act (Regulation 2024/1689), Article 12 | `https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32024R1689` |
| EU AI Act Annex IV — Technical Documentation | Same as above, Annex IV sections |


