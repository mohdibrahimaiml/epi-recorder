# EPI File Format Specification v2.1.2

**Status:** Active / Stable  
**Date:** 2025-12-20  
**Version:** 2.1.2  
**Authors:** EPI Project Team

---

## Abstract

The **Executable Package for AI (EPI)** format provides a standardized, portable, and verifiable container for AI evidence. This specification defines the structure, serialization, and verification mechanisms for `.epi` files as implemented in `epi-recorder` v2.1.2.

---

## 1. Overview

### 1.1 Purpose
EPI files capture complete AI workflows—code, inputs, model interactions, outputs, and environment—into a single, cryptographically verifiable ZIP-based container.

### 1.2 Key Features (v2.1.2)
- **Offline-First Viewer:** Embedded HTML/CSS/JS requires no internet connection.
- **Ed25519 Signing:** Tamper-proof signatures using standard crypto keys.
- **Content-Addressing:** Artifacts stored by SHA-256 hash to deduplicate storage.
- **Privacy-Aware:** Automatic regex-based redaction of API keys and secrets.

---

## 2. File Format

### 2.1 Container Structure
`.epi` files are ZIP archives (STORED/No Compression for Hash Stability) with this structure:

```text
example.epi (ZIP archive)
├── mimetype                    # MUST be first ("application/epi+zip")
├── manifest.json               # Metadata + signatures + hashes
├── steps.jsonl                 # Timeline (NDJSON format)
├── env.json                    # Environment snapshot
├── artifacts/                  # Content-addressed outputs
│   ├── sha256_<hash1>
│   └── ...
├── viewer/                     # Embedded Offline Viewer
│   ├── index.html
│   └── viewer_lite.css         # Inlined CSS (v2.1.1 change)
└── signatures/                 # (Optional) Detached signatures
```

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
    "env.json": "sha256...",
    "artifacts/...": "sha256..."
  },
  "signature": "ed25519:<base64_signature>"
}
```

### 2.3 Timeline (`steps.jsonl`)
Newline-Delimited JSON storage of events.

**Step Types (v2.1.1):**
- `shell.command`: CLI interactions.
- `python.call`: Function traces.
- `llm.request` / `llm.response`: Model interactions.
- `file.write`: File creation events.
- `security.redaction`: Documented scrubbing of secrets.

---

## 3. Verification

### 3.1 Algorithm
1. **Structural Check:** Unzip and validate manifest existence.
2. **Integrity Check:** Re-hash all files in `file_manifest` and compare with stored hashes.
3. **Authenticity Check:**
    - Extract `signature` from manifest.
    - Compute **Canonical CBOR Hash** of the manifest (excluding signature).
    - Verify signature using public key.

---

## 4. Version History

| Version | Date | Status | Changes |
|:---|:---|:---|:---|
| **2.1.2** | 2025-01-17 | **Current** | Critical security fix (Client-side Verification), Spec v1.1-json. |
| **2.1.1** | 2025-12-20 | Previous | Version alignment, stability fixes. |
| **2.1.0** | 2025-12-15 | Previous | Offline viewer (no CDN), Windows paths fix, Interactive Mode. |
| **2.0.0** | 2025-12-01 | MVP | Production release, CLI polish. |
| **1.0.0** | 2025-01-29 | Legacy | "Keystone" draft spec. |

---
**End of Specification**
