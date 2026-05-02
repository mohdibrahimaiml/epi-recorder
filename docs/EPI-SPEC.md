# EPI File Format Specification v4.0.2

**Status:** Active  
**Date:** 2026-05-02
**Version:** 4.0.2
**Authors:** EPI Project Team

---

## Abstract

The **Evidence Packaged Infrastructure (EPI)** format provides a standardized, portable, and verifiable container for AI evidence. This specification defines the structure, serialization, and verification mechanisms for `.epi` files as implemented in `epi-recorder` v4.0.1.

---

## 1. Overview

### 1.1 Purpose
EPI files capture complete AI workflows, code, inputs, model interactions, outputs, and environment into a single, cryptographically verifiable container.

### 1.2 Key Features (v4.0.2)
- **Offline-First Viewer:** Embedded HTML/CSS/JS requires no internet connection. As of v4.0.2, the baked-in iewer.html uses the epi-preloaded-cases format so every open path renders the same current decision-ops UI.
- **Binary Envelope Identity:** New artifacts start with `EPI1`, not ZIP magic bytes.
- **External Handler Required for Double-Click:** Operating systems open `.epi`
  through a registered application; they do not execute the embedded viewer
  directly from inside the archive.
- **Ed25519 Signing:** Tamper-evident signatures using standard crypto keys.
- **Content-Addressing:** Artifacts stored by SHA-256 hash to deduplicate storage.
- **Policy-Grounded Analysis:** `analysis.json` and `policy.json` can travel with the artifact.
- **Human Review Addendum:** `review.json` can be appended without replacing the original sealed evidence files.
- **Privacy-Aware:** Automatic regex-based redaction of API keys and secrets.

---

## 2. File Format

### 2.1 Container Structure
`.epi` files are binary envelopes with this current structure:

```text
example.epi
EPI1 header                 # magic, envelope version, payload format, payload length, payload SHA-256
payload.zip                 # embedded signed ZIP evidence payload
  mimetype                  # MUST be first and STORED ("application/vnd.epi+zip")
  steps.jsonl               # Timeline (NDJSON format) when steps were captured
  environment.json          # Environment snapshot when available
  analysis.json             # Sealed analyzer output when analysis runs
  policy.json               # Validated policy embedded at pack time, when present
  policy_evaluation.json    # Structured control outcomes when policy is present
  review.json               # Optional appended human review record
  viewer.html               # Embedded offline viewer
  artifacts/                # Optional captured files
  manifest.json             # Metadata + signatures + file hashes (written last)
```

Older historical docs may mention `env.json`, raw ZIP `.epi` containers, or a `viewer/` directory. In
`v4.0.2`, the canonical layout uses an `EPI1` outer envelope, `environment.json`, and a root
`viewer.html`. The embedded viewer is portable evidence content, but
double-click still requires a registered external handler such as the Windows
installer or `epi associate`.

### 2.2 Envelope Header

- bytes `0..3`: `EPI1`
- byte `4`: envelope version (`1`)
- byte `5`: payload format enum (`0x01` = `zip-v1`)
- bytes `6..7`: reserved, must be zero
- bytes `8..15`: payload length (`uint64`, little-endian)
- bytes `16..47`: raw payload SHA-256
- bytes `48..63`: reserved zero bytes
- bytes `64..end`: payload bytes

All multi-byte integers are little-endian.

Readers must:

1. validate the envelope header
2. validate payload length sanity
3. stream-hash the payload and compare it to the header SHA-256
4. only then open the embedded ZIP payload and continue manifest/integrity verification

### 2.3 Manifest (`manifest.json`)
The source of truth for the package.

```json
{
  "spec_version": "4.0.2",
  "workflow_id": "uuid...",
  "created_at": "iso-8601...",
  "cli_command": "epi run script.py",
  "env_snapshot_hash": "sha256...",
  "file_manifest": {
    "steps.jsonl": "sha256...",
    "environment.json": "sha256...",
    "artifacts/...": "sha256..."
  },
  "public_key": "<hex_public_key>",
  "signature": "ed25519:<hex_signature>"
}
```

### 2.4 Timeline (`steps.jsonl`)
Newline-delimited JSON storage of events.

**Step Types:**
- `shell.command`: CLI interactions.
- `python.call`: Function traces.
- `llm.request` / `llm.response`: Model interactions.
- `agent.decision` / `agent.approval.request` / `agent.approval.response`: structured agent workflow events.
- `file.write`: File creation events.
- `security.redaction`: Documented scrubbing of secrets.
- `agt.audit.*` / `agt.flight.*`: imported AGT fallback event kinds when no native EPI mapping exists.

### 2.5 Policy and Analysis Payloads
Current EPI artifacts may also include:

- `analysis.json` - sealed analyzer output describing heuristic and policy-grounded findings
- `policy.json` - the validated policy rules that were active during execution
- `policy_evaluation.json` - structured control outcomes for richer policy review
- `review.json` - optional human review outcome appended after analysis
- `artifacts/agt/mapping_report.json` - transformation audit for imported AGT evidence
- `artifacts/annex_iv.md` / `artifacts/annex_iv.json` - optional imported Annex IV outputs

These files are included in the file manifest when present so they are covered by integrity verification. `viewer.html` is intentionally excluded from the file manifest because it is a generated presentation layer that embeds artifact data and verification context.

---

## 3. Integrity Model

- Every sealed file listed in `file_manifest` is hashed with SHA-256.
- `manifest.json` carries the public key and Ed25519 signature.
- Integrity verification recalculates hashes and checks the signature.
- `review.json` is additive and does not replace the original sealed evidence files.

---

## 4. Compatibility Notes

- `v4.0.1` is the current documented layout.
- `v4.0.1` preserves the `EPI1` outer envelope introduced in `v4.0.0` while adding opt-in telemetry and onboarding surfaces outside the artifact format.
- `v4.0.0` introduced the `EPI1` outer envelope while preserving the ZIP evidence payload and inner trust model.
- Older artifacts may still contain legacy naming such as `env.json`.
- Legacy ZIP-based `.epi` artifacts remain readable.
- Double-click behavior is an operating-system integration concern, not a property of the archive alone.

---

## 5. Version History

| Version | Date | Status | Notes |
| --- | --- | --- | --- |
| **4.0.1** | 2026-04-12 | **Current** | No artifact wire-format change from `4.0.0`; adds opt-in telemetry, pilot signup, integration scaffolding, and gateway telemetry ingestion. |
| **4.0.0** | 2026-04-08 | Previous | New `EPI1` outer envelope, dual-format compatibility, `.epi` transport identity upgrade, and `epi migrate` support. |
| **3.0.3** | 2026-04-07 | Previous | Current release line with the AGT import front door, transformation-audit documentation, and aligned `v3.0.3` release surfaces. |
| **3.0.2** | 2026-04-04 | Previous | Extracted-viewer offline packaging fix and self-contained `epi view --extract` output. |
| **3.0.1** | 2026-04-02 | Previous | Front-door reliability patch for packaged viewer assets, LangChain callback stability, and policy threshold alignment. |
| **3.0.0** | 2026-04-01 | Previous | Major release line for the current capture, share, gateway, review, and insurance-pilot surfaces. |
| **2.8.10** | 2026-03-24 | Previous | Notebook packaging correction for source releases, sdist audit coverage, and no wire-format change from `2.8.9`. |
| **2.8.9** | 2026-03-24 | Previous | Policy validation diagnostics, OpenAI Agents-style event bridge, viewer auto-expand on control jump, installer regression guard, and release/version consistency hardening. |
| **2.8.7** | 2026-03-24 | Previous | Policy v2 metadata, `tool_permission_guard`, `policy_evaluation.json`, richer control-outcome viewer support, and trust hardening across viewer/installer surfaces. |
| **2.8.6** | 2026-03-22 | Previous | Agent-first recording, reviewer/trust polish, better onboarding, print capture in `epi run`, faster CLI startup, and cleaner release consistency. |
| **2.8.5** | 2026-03-20 | Previous | Guided policy setup, reliable `epi review` CLI behavior, manual-step bootstrap support, and stronger Windows association repair paths. |
| **2.8.4** | 2026-03-18 | Previous | Windows double-click stability fix by preferring a real `epi.exe` launcher when available. |
| **2.8.3** | 2026-03-18 | Viewer consistency fixes, clearer analyzer wording, and dependency caps for cleaner installs. |
| **2.8.2** | 2026-03-18 | Front-door reliability fixes for zero-step artifacts, clearer onboarding behavior, and release consistency cleanup. |
| **2.8.1** | 2026-03-17 | Previous | Viewer trust rendering fix, current viewer embedded in new artifacts, and policy compatibility/documentation cleanup. |
| **2.8.0** | 2026-03-16 | Previous | Policy-grounded fault analysis release. Enforced `threshold_guard` and `prohibition_guard`, sealed `analysis.json`/`policy.json` workflow, and stronger Windows installer/file-opening behavior. |
| **2.7.2** | 2026-03-14 | Previous | Bug fixes: legacy Base64 signature compatibility, CLI exit-code correctness, analytics import safety. No format changes from 2.7.1. |
| **2.7.0** | 2026-03-11 | Previous | Zero-friction file opening, OS-level association work, and Unicode safety fixes. |
