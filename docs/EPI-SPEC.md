# EPI File Format Specification v2.8.2

**Status:** Active  
**Date:** 2026-03-17  
**Version:** 2.8.2  
**Authors:** EPI Project Team

---

## Abstract

The **Executable Package for AI (EPI)** format provides a standardized, portable, and verifiable container for AI evidence. This specification defines the structure, serialization, and verification mechanisms for `.epi` files as implemented in `epi-recorder` v2.8.2.

---

## 1. Overview

### 1.1 Purpose
EPI files capture complete AI workflows, code, inputs, model interactions, outputs, and environment into a single, cryptographically verifiable ZIP-based container.

### 1.2 Key Features (v2.8.2)
- **Offline-First Viewer:** Embedded HTML/CSS/JS requires no internet connection.
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
`.epi` files are ZIP archives (STORED/No Compression for Hash Stability) with this current structure:

```text
example.epi (ZIP archive)
mimetype                    # MUST be first ("application/epi+zip")
manifest.json               # Metadata + signatures + hashes
steps.jsonl                 # Timeline (NDJSON format)
environment.json            # Environment snapshot
analysis.json               # Sealed analyzer output when analysis runs
policy.json                 # Validated policy embedded at pack time, when present
review.json                 # Optional appended human review record
viewer.html                 # Embedded offline viewer
artifacts/                  # Content-addressed outputs
  sha256_<hash1>
  ...
signatures/                 # Optional detached signatures
```

Older historical docs may mention `env.json` or a `viewer/` directory. In
`v2.8.2`, the canonical layout uses `environment.json` and a root
`viewer.html`. The embedded viewer is portable evidence content, but
double-click still requires a registered external handler such as the Windows
installer or `epi associate`.

### 2.2 Manifest (`manifest.json`)
The source of truth for the package.

```json
{
  "spec_version": "1.1-json",
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

### 2.3 Timeline (`steps.jsonl`)
Newline-delimited JSON storage of events.

**Step Types:**
- `shell.command`: CLI interactions.
- `python.call`: Function traces.
- `llm.request` / `llm.response`: Model interactions.
- `file.write`: File creation events.
- `security.redaction`: Documented scrubbing of secrets.

### 2.4 Policy and Analysis Payloads
Current EPI artifacts may also include:

- `analysis.json` - sealed analyzer output describing heuristic and policy-grounded findings
- `policy.json` - the validated policy rules that were active during execution
- `review.json` - optional human review outcome appended after analysis

These files are included in the file manifest when present so they are covered by integrity verification.

---

## 3. Integrity Model

- Every sealed file listed in `file_manifest` is hashed with SHA-256.
- `manifest.json` carries the public key and Ed25519 signature.
- Integrity verification recalculates hashes and checks the signature.
- `review.json` is additive and does not replace the original sealed evidence files.

---

## 4. Compatibility Notes

- `v2.8.2` is the current documented layout.
- Older artifacts may still contain legacy naming such as `env.json`.
- Double-click behavior is an operating-system integration concern, not a property of the archive alone.

---

## 5. Version History

| Version | Date | Status | Notes |
| --- | --- | --- | --- |
| **2.8.2** | 2026-03-18 | **Current** | Front-door reliability fixes for zero-step artifacts, clearer onboarding behavior, and release consistency cleanup. |
| **2.8.1** | 2026-03-17 | Previous | Viewer trust rendering fix, current viewer embedded in new artifacts, and policy compatibility/documentation cleanup. |
| **2.8.0** | 2026-03-16 | Previous | Policy-grounded fault analysis release. Enforced `threshold_guard` and `prohibition_guard`, sealed `analysis.json`/`policy.json` workflow, and stronger Windows installer/file-opening behavior. |
| **2.7.2** | 2026-03-14 | Previous | Bug fixes: legacy Base64 signature compatibility, CLI exit-code correctness, analytics import safety. No format changes from 2.7.1. |
| **2.7.0** | 2026-03-11 | Previous | Zero-friction file opening, OS-level association work, and Unicode safety fixes. |
