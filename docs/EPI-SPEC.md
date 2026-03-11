# EPI File Format Specification v2.7.0

**Status:** Draft  
**Date:** 2026-03-11  
**Version:** 2.7.0  
**Authors:** EPI Project Team

---

## Abstract

The **Executable Package for AI (EPI)** format provides a standardized, portable, and verifiable container for AI evidence. This specification defines the structure, serialization, and verification mechanisms for `.epi` files as implemented in `epi-recorder` v2.7.0.

---

## 1. Overview

### 1.1 Purpose
EPI files capture complete AI workflows—code, inputs, model interactions, outputs, and environment—into a single, cryptographically verifiable ZIP-based container.

### 1.2 Key Features (v2.2.0)
- **Offline-First Viewer:** Embedded HTML/CSS/JS requires no internet connection.
- **Ed25519 Signing:** Tamper-proof signatures using standard crypto keys.
- **Content-Addressing:** Artifacts stored by SHA-256 hash to deduplicate storage.
- **Gemini Native:** Automatic interception of `google.generativeai` calls (v2.1.3).
- **Thread-Safe Recording:** Using `contextvars` for concurrent agent support (v2.2.0).
- **SQLite Storage:** Atomic, crash-safe storage replacing JSONL (v2.2.0).
- **Mistake Detection:** `epi debug` command for automatic bug detection (v2.2.0).
- **Async API:** Native `async/await` support for modern frameworks (v2.2.0).
- **MIT License:** More permissive licensing for commercial adoption (v2.2.0).
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
| **2.7.0** | 2026-03-11 | **Current** | Zero-friction file opening (OS-level association), double-click to view, Unicode safety fixes. |
| **2.6.0** | 2026-02-20 | Previous | Framework integrations (LiteLLM, LangChain, OTel), CI verification (GitHub Action, pytest), streaming, global install. |
| **2.5.0** | 2026-02-13 | Previous | Anthropic Claude wrapper, path resolution fix, enhanced parameter tracking. |
| **2.4.0** | 2026-02-12 | Previous | Agent Analytics Engine, Async/Await support, LangGraph integration, Ollama local LLM support. |
| **2.3.0** | 2026-02-06 | Previous | Explicit evidence capture, wrapper clients, monkey patching removal. |
| **2.2.0** | 2026-01-30 | Legacy | Thread-safe recording, SQLite storage, `epi debug` command, Async API, MIT license. |
| **2.1.3** | 2026-01-24 | Previous | Gemini Native Support (Patcher + Chat). |
| **2.1.2** | 2025-01-17 | Previous    | Critical security fix (Client-side Verification), Spec v1.1-json. |
| **2.1.1** | 2025-12-20 | Previous | Version alignment, stability fixes. |
| **2.1.0** | 2025-12-15 | Previous | Offline viewer (no CDN), Windows paths fix, Interactive Mode. |
| **2.0.0** | 2025-12-01 | MVP | Production release, CLI polish. |
| **1.0.0** | 2025-01-29 | Legacy | "Keystone" draft spec. |

---
**End of Specification**


 