# EPI File Format Specification v1.0-Keystone

**Status:** Draft  
**Date:** 2025-01-29  
**Authors:** EPI Project Team

---

## Abstract

The Executable Package for AI (EPI) format provides a standardized, portable, and verifiable container for AI workflows. This specification defines the structure, serialization, and verification mechanisms for `.epi` files.

## 1. Overview

### 1.1 Purpose

EPI files capture complete AI workflows—including code, inputs, model interactions, outputs, and execution environment—into a single, cryptographically verifiable ZIP-based container.

### 1.2 Design Goals

- **Portability:** Single-file distribution across platforms
- **Verifiability:** Cryptographic integrity and authenticity
- **Reproducibility:** Deterministic replay of workflows
- **Transparency:** Human-readable evidence timeline
- **Security:** Automatic secret redaction and sandboxed viewing

### 1.3 Core Value Proposition

**"See what your AI did. Prove it's real."**

---

## 2. File Format

### 2.1 Container Structure

`.epi` files are ZIP archives with the following structure:

```
example.epi (ZIP archive)
├── mimetype                    # MUST be first, uncompressed
├── manifest.json               # Metadata + signatures + hashes
├── steps.jsonl                 # Timeline (NDJSON format)
├── env.json                    # Environment snapshot
├── artifacts/                  # Content-addressed outputs
│   ├── sha256_<hash1>
│   └── sha256_<hash2>
├── cache/                      # Cached API/LLM responses
│   ├── openai/
│   └── ollama/
├── checks.json                 # Verification rules (optional)
├── viewer/                     # Embedded static HTML viewer
│   ├── index.html
│   └── app.js
└── signatures/                 # Detached signatures (optional)
    └── default.sig
```

### 2.2 Mimetype

**File:** `mimetype`  
**Format:** Plain text, UTF-8  
**Content:** `application/epi+zip`  
**Compression:** MUST be stored uncompressed (ZIP_STORED)  
**Position:** MUST be the first file in the ZIP archive

Per ZIP Application Note, the mimetype file enables MIME type detection.

### 2.3 Manifest

**File:** `manifest.json`  
**Format:** JSON, UTF-8  
**Position:** MUST be written last (after all files are hashed)

#### Schema

```json
{
  "spec_version": "1.0-keystone",
  "workflow_id": "550e8400-e29b-41d4-a716-446655440000",
  "created_at": "2025-01-15T10:30:00Z",
  "cli_command": "epi record --out demo.epi -- python train.py",
  "env_snapshot_hash": "a3c5f7b2...",
  "file_manifest": {
    "steps.jsonl": "b4d6e8f3...",
    "env.json": "a3c5f7b2...",
    "artifacts/sha256_c7f8a9b4": "c7f8a9b4..."
  },
  "signature": "ed25519:3a4b5c6d..."
}
```

#### Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `spec_version` | string | Yes | EPI specification version |
| `workflow_id` | UUID | Yes | Unique workflow identifier |
| `created_at` | ISO 8601 datetime | Yes | Creation timestamp (UTC) |
| `cli_command` | string | No | Command that created this .epi |
| `env_snapshot_hash` | string | No | SHA-256 of env.json |
| `file_manifest` | object | Yes | Map of filenames to SHA-256 hashes |
| `signature` | string | No | Ed25519 signature (see §4) |

### 2.4 Steps Timeline

**File:** `steps.jsonl`  
**Format:** NDJSON (Newline-Delimited JSON)  
**Encoding:** UTF-8

Each line is a JSON object representing one step:

```json
{"index": 0, "timestamp": "2025-01-15T10:30:00Z", "kind": "llm.request", "content": {...}}
{"index": 1, "timestamp": "2025-01-15T10:30:02Z", "kind": "llm.response", "content": {...}}
```

#### Step Schema

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `index` | integer | Yes | Sequential step number (0-indexed) |
| `timestamp` | ISO 8601 datetime | Yes | When step occurred (UTC) |
| `kind` | string | Yes | Step type (see §2.4.1) |
| `content` | object | Yes | Step-specific data |

#### 2.4.1 Step Types

| Kind | Description | Content Fields |
|------|-------------|----------------|
| `shell.command` | Shell command execution | `command`, `stdout`, `stderr`, `exit_code`, `duration` |
| `python.call` | Python function call | `function`, `args`, `kwargs`, `return_value` |
| `llm.request` | LLM API request | `provider`, `model`, `prompt`, `parameters` |
| `llm.response` | LLM API response | `provider`, `model`, `response`, `tokens`, `latency` |
| `file.write` | File write operation | `path`, `size`, `hash` |
| `security.redaction` | Secret redaction event | `count`, `fields_redacted` |

### 2.5 Environment Snapshot

**File:** `env.json`  
**Format:** JSON, UTF-8

```json
{
  "os": "Windows",
  "os_version": "10.0.26100",
  "python_version": "3.11.5",
  "dependencies": {
    "openai": "1.12.0",
    "pydantic": "2.5.3"
  },
  "environment_variables": {
    "PATH": "/usr/local/bin:/usr/bin",
    "PYTHONPATH": "/home/user/project"
  }
}
```

---

## 3. Serialization

### 3.1 Canonical CBOR Hashing

EPI uses **Canonical CBOR** (RFC 8949) for deterministic hashing.

#### Algorithm

1. Convert Pydantic model to dict using `model.model_dump(mode="json")`
2. Exclude specified fields (e.g., `signature`)
3. Encode to CBOR with `canonical=True`:
   - Keys sorted lexicographically
   - Minimal encoding
   - Deterministic datetime/UUID encoding
4. Compute SHA-256 of CBOR bytes

#### Custom Encoders

- **datetime:** Encode as ISO 8601 string with microseconds removed, UTC timezone (`YYYY-MM-DDTHH:MM:SSZ`)
- **UUID:** Encode as canonical string representation

#### Python Implementation

```python
import hashlib
from datetime import datetime
from uuid import UUID
import cbor2

def _cbor_default_encoder(encoder, value):
    if isinstance(value, datetime):
        utc_dt = value.replace(microsecond=0)
        encoder.encode(utc_dt.isoformat() + "Z")
    elif isinstance(value, UUID):
        encoder.encode(str(value))
    else:
        raise ValueError(f"Cannot encode type {type(value)}")

def get_canonical_hash(model, exclude_fields=None):
    model_dict = model.model_dump(mode="json")
    if exclude_fields:
        for field in exclude_fields:
            model_dict.pop(field, None)
    cbor_bytes = cbor2.dumps(model_dict, canonical=True, default=_cbor_default_encoder)
    return hashlib.sha256(cbor_bytes).hexdigest()
```

### 3.2 Hash Stability Guarantees

- ✅ **Platform-independent:** Same hash on Windows, macOS, Linux
- ✅ **Time-independent:** Same data produces same hash across time
- ✅ **Order-independent:** Field order doesn't affect hash
- ✅ **Version-stable:** Compatible across Python 3.11+

---

## 4. Cryptographic Signatures

### 4.1 Signature Algorithm

**Algorithm:** Ed25519 (RFC 8032)  
**Key Size:** 256 bits  
**Signature Size:** 64 bytes (512 bits)

### 4.2 Signing Process

1. Compute canonical CBOR hash of manifest (excluding `signature` field)
2. Sign the hash with Ed25519 private key
3. Encode signature as base64
4. Store in manifest: `"signature": "ed25519:<base64>"`

### 4.3 Verification Process

1. Read manifest from .epi file
2. Extract signature field
3. Recompute canonical CBOR hash (excluding `signature`)
4. Verify signature using Ed25519 public key

### 4.4 Key Management

**Location:** `~/.epi/keys/`  
**Default Key:** `default` (auto-generated on first use)  
**Permissions:** 
- Private keys: `0600` (owner read/write only)
- Public keys: `0644` (owner write, all read)

---

## 5. Integrity Verification

### 5.1 Verification Levels

| Level | Checks Performed | Trust Level |
|-------|------------------|-------------|
| **Structural** | ZIP format, mimetype, manifest schema | Low |
| **Integrity** | File hashes match manifest | Medium |
| **Authenticity** | Ed25519 signature valid | High |

### 5.2 Verification Report

```json
{
  "integrity_ok": true,
  "checks_passed": 23,
  "checks_total": 23,
  "reproducibility_score": 0.97,
  "signature_valid": true,
  "signer": "default",
  "mismatches": []
}
```

---

## 6. Security Considerations

### 6.1 Threat Model

| Threat | Mitigation |
|--------|------------|
| Content tampering | SHA-256 file hashes + Ed25519 signatures |
| Secret leakage | Automatic redaction with regex rules |
| Malicious viewer | Static HTML only, no code execution |
| Replay attacks | Sandboxed execution environment |
| Oversized files | Artifact chunking + size caps |

### 6.2 Redaction

**Patterns:**
- API keys: `sk-[a-zA-Z0-9]{48}`
- Tokens: `Bearer\s+[^\s]+`
- Environment variables: `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`

**Replacement:** `***REDACTED***`

**Logging:** Each redaction creates a `security.redaction` step

---

## 7. Viewer Specification

### 7.1 Embedded Viewer

**Files:** `viewer/index.html`, `viewer/app.js`  
**Technology:** Static HTML + Vanilla JavaScript  
**Security:** Content Security Policy (CSP), no `eval()`

### 7.2 Data Injection

Viewer data is injected at pack time:

```html
<script id="epi-data" type="application/json">
{
  "manifest": {...},
  "steps": [...]
}
</script>
```

### 7.3 Viewer Features

- Manifest summary (author, date, signature status)
- Timeline of steps (filterable, searchable)
- LLM prompt/response rendering (chat bubbles)
- Artifact previews (images, text, CSV)
- Verification badge (✅/⚠️/❌)

---

## 8. Compliance

### 8.1 Compatibility

- **ZIP:** PKWARE ZIP Application Note 6.3.9
- **CBOR:** RFC 8949 (Canonical CBOR)
- **Ed25519:** RFC 8032
- **JSON:** RFC 8259
- **NDJSON:** RFC 7464

### 8.2 Reserved Fields

Future specification versions MAY add fields. Implementations MUST ignore unknown fields.

---

## 9. Example Workflow

```bash
# 1. Record
$ epi record --out demo.epi -- python train.py
✅ Recorded: demo.epi (42 MB)

# 2. Verify
$ epi verify demo.epi
✅ Integrity: OK
✅ Signature: Valid (default)
✅ Checks: 23/23 passed

# 3. View
$ epi view demo.epi
# Opens browser with interactive timeline
```

---

## 10. Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0-keystone | 2025-01-29 | Initial specification |

---

**End of Specification**

