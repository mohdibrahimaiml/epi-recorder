# EPI File Format Specification v4.2.0

**Status:** Active  
**Date:** 2026-06-01  
**Version:** 4.2.0  
**Repository:** https://github.com/mohdibrahimaiml/epi-recorder  

---

## Abstract

The Evidence Packaged Infrastructure (EPI) format defines a portable, self-contained, cryptographically signed container for AI agent execution evidence. A `.epi` file is a polyglot — valid HTML for browser-based inspection AND a binary envelope carrying a ZIP payload — enabling zero-install verification by regulators, auditors, and compliance reviewers.

This specification defines the container structure, manifest schema, cryptographic protocol, internal file layout, verification procedure, and trust model as implemented in `epi-recorder` v4.2.0. It is the authoritative reference for independent implementations.

---

## 1. Conventions

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in RFC 2119.

All hashes are SHA-256 unless otherwise stated. All signatures are Ed25519 unless otherwise stated.

---

## 2. Container Format

### 2.1 Envelope Header

A `.epi` file begins with a 128-byte binary header immediately following the 4-byte magic string.

| Offset | Size | Field | Description |
|--------|------|-------|-------------|
| 0 | 4 | `magic` | Magic bytes: `<!--` (HTML comment start, making the file valid HTML) |
| 4 | 1 | `version` | Envelope format version. Current: `2` |
| 5 | 1 | `flags` | Reserved flags. MUST be `0` |
| 6 | 2 | `reserved` | Reserved. MUST be `0` |
| 8 | 8 | `payload_length` | Total length of the ZIP payload in bytes (little-endian uint64) |
| 16 | 16 | `payload_uuid` | UUID v4 identifying this specific payload |
| 32 | 8 | `created_at` | Unix epoch timestamp when container was created (little-endian uint64) |
| 40 | 32 | `payload_sha256` | SHA-256 hash of the ZIP payload bytes |
| 72 | 56 | `reserved` | Reserved for future use. MUST be zero |

**Reference:** `epi_core/container.py`, class `EPIEnvelopeHeader` (line 61), `EPI_ENVELOPE_HEADER_SIZE = 128` (line 57).

### 2.2 Polyglot Structure

After the 128-byte header, the file MAY contain an embedded HTML viewer. This viewer is valid HTML that, when opened in a browser, provides an interactive forensic interface. The viewer HTML continues until the ZIP payload marker:

```
EPI_ZIP_MARKER = b"\n<!-- EPI_ZIP_PAYLOAD_START -->\n"
```

**Reference:** `epi_core/container.py`, `EPI_ZIP_MARKER` (line 58).

Following the ZIP marker, the remaining bytes form a standard ZIP archive containing the evidence payload.

### 2.3 Legacy Format

Prior to v4.0.0, `.epi` files used the magic bytes `EPI1` (binary, not polyglot). Implementations SHOULD support reading legacy `EPI1` containers but SHOULD NOT produce them.

---

## 3. Internal ZIP Payload

### 3.1 Required Files

| File | Purpose |
|------|---------|
| `mimetype` | MUST contain exactly `application/vnd.epi+zip` (uncompressed, first entry) |
| `manifest.json` | Signed manifest — the root of trust |
| `steps.jsonl` | Line-delimited JSON: ordered, immutable execution timeline |
| `environment.json` | Full runtime environment snapshot |
| `analysis.json` | Deterministic fault analysis output |
| `policy.json` | Rulebook applied during execution |
| `viewer.html` | Self-contained HTML forensic viewer |
| `VERIFY.txt` | Human-readable offline verification instructions |

### 3.2 Optional Files

| File | Purpose |
|------|---------|
| `review.json` | Human review addendum (mutable, appended post-sealing) |
| `policy_evaluation.json` | Structured evaluation of each policy rule against the execution |
| `artifacts/agt_export.json` | AGT (Agent Governance Toolkit) compliance export |
| `artifacts/scitt/statement.cbor` | SCITT COSE_Sign1 signed statement |
| `artifacts/scitt/receipt.cbor` | SCITT transparency receipt |

**Reference:** `epi_core/container.py`, `_RESERVED_ROOT_ARCHIVE_NAMES` (line 141).

---

## 4. Manifest Schema

The `manifest.json` is a JSON object with these fields:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `spec_version` | string | Yes | EPI specification version |
| `workflow_id` | UUID | Yes | Unique identifier for this workflow execution |
| `created_at` | datetime | Yes | Timestamp when .epi was created (UTC, ISO 8601) |
| `cli_command` | string | No | Command-line invocation that produced this workflow |
| `env_snapshot_hash` | string | No | SHA-256 hex of `environment.json` |
| `file_manifest` | object | Yes | Mapping of file paths to SHA-256 hex hashes |
| `public_key` | string | No | 32-byte Ed25519 public key as hex |
| `signature` | string | No | Ed25519 signature (see Section 5.2) |
| `container_format` | string | No | `"legacy-zip"` or `"envelope-v2"` |
| `analysis_status` | string | No | `"complete"`, `"skipped"`, or `"error"` |
| `total_steps` | integer | No | Total number of recorded execution steps |
| `goal` | string | No | Human-readable goal of this execution |
| `notes` | string | No | Free-form notes |
| `metrics` | object | No | Arbitrary key-value metrics |
| `approved_by` | string | No | Identity of approving reviewer |
| `governance` | object | No | Governance metadata including SCITT registration |

**Reference:** `epi_core/schemas.py`, `ManifestModel` (line 27).

---

## 5. Cryptographic Protocol

### 5.1 Canonical Hashing

1. Serialize model to dictionary
2. Sort all keys alphabetically
3. Convert UUID values to canonical string representation
4. Serialize to JSON with `sort_keys=True`, `separators=(",", ":")`, `ensure_ascii=True`
5. Compute SHA-256 over UTF-8 bytes
6. Return 64-character hex string

**Reference:** `epi_core/serialize.py`, `get_canonical_hash()` (line 41).

### 5.2 Manifest Signing

1. Compute canonical hash of manifest, excluding `signature` and `governance` fields
2. Convert hex hash to 32 raw bytes
3. Sign with Ed25519 private key
4. Encode signature as hex (64 characters)
5. Format as: `ed25519:{key_name}:{signature_hex}`
6. Set `manifest.signature` to this string

**Reference:** `epi_core/trust.py`, `sign_manifest()` (line 41).

### 5.3 Manifest Verification

1. Parse signature string: split on `:` to extract algorithm, key name, signature hex
2. Reject if algorithm is not `ed25519`
3. Decode 64-char hex signature to 32 raw bytes
4. Compute canonical hash of manifest (excluding `signature` and `governance`)
5. Import Ed25519 public key from manifest's `public_key` field or trusted registry
6. Call `Ed25519PublicKey.verify(signature_bytes, hash_bytes)`
7. Return `(True, "Valid")` or `(False, "Invalid - tampered")`

**Reference:** `epi_core/trust.py`, `verify_signature()` (line 68).

### 5.4 File Integrity

Each file in `file_manifest` MUST have a SHA-256 matching the stored hash. Verification iterates every entry and recomputes actual hashes.

**Reference:** `epi_core/container.py`, `verify_integrity()` (line 1183).

### 5.5 Step Chain (`prev_hash`)

Each step in `steps.jsonl` contains a `prev_hash` field: SHA-256 of the preceding step's canonical representation. Creates an append-only, hash-linked timeline.

**Reference:** `epi_core/schemas.py`, `StepModel` (line 181).

### 5.6 SCITT Transparency (Optional)

Mode B: SCITT Producer. COSE_Sign1 statement signed by issuer. Receipt signed by transparency service. Embedded at `artifacts/scitt/`.

**COSE parameters:** Algorithm `-8` (EdDSA/Ed25519), Content type `application/vnd.epi.manifest+hash`.

**Reference:** `epi_core/scitt.py`.

---

## 6. Steps Format (`steps.jsonl`)

Newline-delimited JSON. Each line is one step with:

- `index` (integer, monotonically increasing)
- `kind` (string: `session.start`, `llm.request`, `llm.response`, `tool.call`, `agent.decision`, etc.)
- `timestamp` (ISO 8601 with microsecond precision)
- `content` (object: step-specific payload)
- `prev_hash` (string: SHA-256 hex of previous step's canonical bytes)
- `trace_id` (UUID)
- `decision_id` (UUID)
- `case_id` (UUID)

**Reference:** `epi_core/schemas.py`, `StepModel` (line 181); `epi_core/capture.py`, `CaptureEventModel` (line 76).

---

## 7. Environment Format (`environment.json`)

Captures Python version, platform, EPI version, installed packages, and environment variables (with sensitive values redacted).

**Reference:** `epi_recorder/environment.py`.

---

## 8. Analysis Format (`analysis.json`)

9-pass deterministic fault analysis: error continuation, constraint violation, sequence, threshold, prohibition, approval gap, context drop, tool permission, iteration.

**Reference:** `epi_core/fault_analyzer.py`, class `FaultAnalyzer` (line 797).

---

## 9. Policy Format (`policy.json`)

Rulebook containing approval policies, threshold rules, constraint rules, and tool permission guards.

**Reference:** `epi_core/policy.py`, class `EPIPolicy` (line 178).

---

## 10. Review Format (`review.json`)

Mutable addendum appended post-sealing. NOT included in cryptographic `file_manifest`. Contains reviewer identity, verdict, findings, and comments.

**Reference:** `epi_core/review.py`, class `ReviewRecord` (line 146).

---

## 11. Verification Procedure

7 independent checks:

1. **Structural** — Valid envelope, extractable ZIP, required files present
2. **Integrity** — Every `file_manifest` entry matches computed SHA-256
3. **Signature** — Ed25519 signature valid against manifest hash
4. **Chain** — `prev_hash` links intact, monotonic indices, monotonic timestamps
5. **Sequence** — No missing indices, chronological order
6. **Count** — `manifest.total_steps` matches actual `steps.jsonl` line count
7. **SCITT** (optional) — Statement + receipt structurally valid, signature correct

**Reference:** `epi_cli/verify.py`; `epi_core/container.py`.

---

## 12. Trust Model

| Level | Conditions |
|-------|-----------|
| **HIGH** | Integrity PASS + Signature VALID + Identity KNOWN |
| **MEDIUM** | Integrity PASS + Signature VALID + SCITT transparency |
| **LOW** | Integrity PASS + Signature VALID (unknown identity) |
| **NONE** | No signature |
| **TAMPERED** | Integrity FAIL or Signature INVALID |

Trust registry at `epilabs.org/.well-known/epi-trust-registry.json`. DID:WEB at `did:web:epilabs.org`.

**Reference:** `epi_core/trust.py`, class `TrustRegistry` (line 251); `epi_core/did_web.py`.

---

## 13. Browser-Based Verifier

Every `.epi` contains an embedded `viewer.html`:
- Zero-install, opens via `file://`
- Pure JavaScript (no server, no API)
- `@noble/ed25519` for signature verification
- JSZip for ZIP extraction
- Fully offline

**Reference:** `epi_viewer_static/crypto.js`, `epi_viewer_static/app.js`.

---

## 14. Compliance Mappings

### 14.1 AIUC-1

All 6 trust domains mapped: Security, Privacy, Safety, Reliability, Accountability, Societal Impact.

**Reference:** `docs/standards/aiuc-1-evidence.md`; `epi_core/aiuc1_mapping.py`.

### 14.2 EU AI Act

Addresses Article 12 (Record-keeping), Article 14 (Human Oversight), and Article 19 (Transparency).

---

## 15. Security Considerations

- **Key encryption:** Set `EPI_KEY_PASSWORD` env var. Stores keys as PKCS#8 encrypted PEM via `BestAvailableEncryption()`. **Reference:** `epi_core/keys.py` (line 98-101).
- **Enforcement mode:** Set `EPI_ENFORCE=1` to block LLM calls outside `record()` context. Raises `RuntimeError`. **Reference:** `epi_recorder/wrappers/base.py` (line 29).
- **Gateway fail-closed:** Worker health pre-checked before relaying upstream. Returns 502 if worker not ready. **Reference:** `epi_gateway/main.py` (line 1178).
- **Redaction:** Sensitive data scrubbed from `steps.jsonl` before storage. **Reference:** `epi_core/redactor.py`.

### Threats Not Mitigated

- EPI does not prevent pre-execution unauthorized LLM access (post-execution evidence system)
- Encryption is opt-in via `EPI_KEY_PASSWORD`
- Enforcement is opt-in via `EPI_ENFORCE=1`

---

## 16. IANA Considerations

| Media Type | Description |
|-----------|-------------|
| `application/vnd.epi` | EPI evidence container (current) |
| `application/vnd.epi+zip` | EPI evidence container (legacy ZIP) |
| `application/vnd.epi.manifest+hash` | SCITT statement payload |

**File extension:** `.epi`

---

## 17. Version History

| Version | Date | Changes |
|---------|------|---------|
| 4.2.0 | 2026-06-01 | Gateway fail-closed, key encryption, EPI_ENFORCE, portal |
| 4.1.0 | 2026-05-14 | SCITT, AGT adapter, AIUC-1 mapping |
| 4.0.3 | 2026-05-03 | Viewer redesign, DID:WEB |
| 4.0.0 | 2026-04-08 | Envelope v2 (polyglot) |
| 1.0.0 | 2025-12-15 | Initial release |

---

## 18. Reference Implementation

- **PyPI:** https://pypi.org/project/epi-recorder/
- **GitHub:** https://github.com/mohdibrahimaiml/epi-recorder
- **Website:** https://epilabs.org/

---

*This specification is maintained by EPI Labs. Contributions and errata are welcome via GitHub Issues.*
