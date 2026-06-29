# EPI DOC v3.0.3

Author: Codex  
Date: 2026-04-07  
Repo analyzed: `C:\Users\dell\epi-recorder`  
Release line observed in source: `v3.0.3`

---

## 1. What EPI is

EPI is an evidence system for AI workflows.

Its core job is simple:

- capture what happened
- seal it into one portable `.epi` case file
- let reviewers reopen it later
- let anyone verify that the artifact was not changed after sealing

The product center is the artifact itself, not a hosted dashboard.

That is why the most important surfaces in this repo are:

- capture APIs
- artifact packing
- trust verification
- browser review
- policy and review outputs

If you remember one sentence, remember this:

**EPI turns an AI workflow into a sealed, reviewable case file.**

---

## 2. What `v3.0.3` means

`v3.0.3` is a release-polish line for the current product surface.

The most important change is not a new subsystem. It is a better front door for users coming from exported governance evidence, especially the Microsoft Agent Governance Toolkit path.

In practical terms, `v3.0.3` makes three things clearer:

- the `AGT -> EPI` flow is now a first-class public quickstart
- imported artifacts carry an explicit transformation audit at `artifacts/agt/mapping_report.json`
- the active docs, installer metadata, and current release references now agree on the same release line

---

## 3. The four main starting paths

### Developer repro path

Use this when you want to capture a run directly from Python:

```bash
pip install epi-recorder
epi demo
epi view <artifact>
epi verify <artifact>
```

### AGT import path

Use this when you already have exported Microsoft Agent Governance Toolkit evidence:

```bash
epi import agt examples/agt/sample_bundle.json --out sample.epi
epi verify sample.epi
epi view sample.epi
```

This is the cleanest path from governance evidence to a portable case artifact.

### Governed workflow path

Use this when you own the workflow and want policy-grounded review:

1. create `epi_policy.json`
2. run the workflow with EPI capture
3. inspect `analysis.json` and `policy_evaluation.json`
4. review or export the resulting case

### Shared review path

Use this when a team needs a local/shared review workspace:

1. start `epi connect open`
2. review cases in the browser
3. export reviewed cases back to `.epi`

---

## 4. What a `.epi` file contains

The normal artifact contains:

- `manifest.json` for metadata, hashes, and signatures
- `steps.jsonl` for the execution trace
- `environment.json` for environment context
- `analysis.json` for analyzer findings when present
- `policy.json` and `policy_evaluation.json` for control evidence when present
- `review.json` for additive human review
- `viewer.html` for the embedded offline browser review surface

Imported AGT artifacts may also include:

- `artifacts/agt/mapping_report.json`
- raw AGT payloads under `artifacts/agt/`
- imported Annex IV attachments under `artifacts/`

That is the important distinction:

- EPI is not only a viewer
- EPI is a portable case format with a built-in trust model

---

## 5. Why the AGT path matters

The AGT integration story is strong because the two systems solve adjacent problems:

- AGT is the governance/control-plane side
- EPI is the portable evidence/case-file side

AGT already produces valuable evidence fragments such as audit logs, compliance outputs, policy documents, and Annex IV materials.

EPI’s job is to package that evidence into one artifact that can be:

- opened later
- verified later
- reviewed later
- handed to another engineer, operator, or auditor

`mapping_report.json` matters because it makes the conversion auditable instead of opaque.

That means an imported artifact can answer both:

- "Is this case file intact?"
- "How was the imported evidence transformed?"

---

## 6. The current product shape

The product is best understood as five layers:

```text
Capture -> Artifact -> Trust -> Review -> Sharing
```

In repo terms:

- `epi_recorder/` handles capture APIs and integrations
- `epi_core/` owns schemas, packing, trust, policy, and review data
- `epi_cli/` is the main human-facing terminal surface
- `web_viewer/` is the browser review surface
- `epi_gateway/` supports shared capture and shared review workflows

The moat is not only that EPI records data.

The moat is that EPI produces a durable artifact that still makes sense later.

---

## 7. What is most credible today

As of the `v3.0.3` source line, EPI is strongest where someone may later ask:

- what happened
- which controls applied
- who reviewed it
- whether the artifact was altered

That is why EPI fits especially well in:

- approvals
- denials
- escalations
- workflow audits
- AI bug-report artifacts
- compliance evidence handoff

The right mental model is:

**portable AI case files with built-in trust and review**

---

## 8. Related Docs

- [AGT Import Quickstart](AGT-IMPORT-QUICKSTART.md)
- [CLI Reference](CLI.md)
- [Policy Guide](POLICY.md)
- [Self-Hosted Runbook](SELF-HOSTED-RUNBOOK.md)
- [EPI Specification](EPI-SPEC.md)
- [Changelog](../CHANGELOG.md)

---

## 9. Final plain-language summary

EPI is infrastructure for portable AI case files.

`v3.0.3` does not change that core idea. It makes the current product easier to discover and easier to trust, especially for users starting from exported AGT evidence instead of instrumented Python code.

That leaves the product with one cleaner front door:

- import or capture once
- verify once
- review once
- hand off one artifact
