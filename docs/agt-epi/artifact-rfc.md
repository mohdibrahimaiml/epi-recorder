# RFC: AGT -> EPI Portable Artifact Layer

## Problem

AGT currently lacks a **single portable, sealed, independently verifiable case artifact**.

Today, its compliance evidence is spread across in-memory structures, SQLite audit logs, and Annex IV Markdown/JSON exports. Those outputs are useful, but they are not one portable object a reviewer, auditor, or regulator can reopen later with full trust.

Before:
- in-memory structures
- SQLite audit logs
- Annex IV Markdown/JSON exports

After:
- one `.epi` file with trace, policy, trust, and source evidence

## Proposal

Introduce `.epi` as an **optional output layer** of the AGT Annex IV exporter.

This would package:
- execution trace
- policy and evaluation outputs
- runtime context
- source evidence
- integrity and signature metadata

This is an extension, not a replacement.

## Architecture

```text
AGT Runtime
   ->
Annex IV Exporter
   ->
EPI Adapter
   ->
.epi artifact
```

The AGT runtime stays unchanged. The Annex IV exporter remains the producer. The EPI adapter adds a portable artifact layer on top.

## Evidence Mapping

| AGT Evidence | EPI Output |
| --- | --- |
| `ComplianceReport` | `policy_evaluation.json` plus analysis/decision context |
| `PolicyDocument` | `policy.json` |
| `audit_logs` | `steps.jsonl` |
| `flight_recorder` | `steps.jsonl` |
| `runtime_context` | `environment.json` |
| `slo_data` | `artifacts/slo.json` |
| `annex_markdown` | `artifacts/annex_iv.md` |
| `annex_json` | `artifacts/annex_iv.json` |
| raw AGT payloads | `artifacts/agt/` |
| mapping metadata | `artifacts/agt/mapping_report.json` |

## Standards Alignment

EPI is a container layer, not a competing standard.

It can align conceptually with:
- `SLSA` for provenance
- `Sigstore` for signing and verification interoperability
- optional `CycloneDX` exports where component evidence is relevant

The goal is not to replace those standards. The goal is to package AGT evidence into one portable case artifact that can carry or reference them.

## Minimal Flow

Current working proof:

```bash
epi import agt examples/agt-epi-demo/sample_annex_bundle.json --out case.epi
epi verify case.epi
epi view case.epi
```

Future AGT-side target:
- the Annex IV exporter emits this bundle shape directly
- or the Annex IV exporter calls an equivalent EPI adapter

## Why This Matters

- portable compliance evidence
- verifiable audit handoff
- local investigation
- regulator- and reviewer-readable case artifact

![AGT evidence reopened as one portable case file with policy, evidence, trust, and transformation audit.](../assets/agt-epi-demo-case-view.png)
