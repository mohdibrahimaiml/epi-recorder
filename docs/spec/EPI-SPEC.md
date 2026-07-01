# EPI File Format Specification v4.2.0

**Status:** Active  
**Date:** 2026-06-29  
**Version:** 4.2.0  
**Category:** Standards Track

---

### EU AI Act Annex IV Technical Documentation

EPI provides structured JSON schemas for all 9 sections of EU AI Act Annex IV.
See [schemas/annex-iv.schema.json](schemas/annex-iv.schema.json) for the full JSON Schema.
The `epi annex` CLI subsystem generates, signs, and verifies Annex IV artifacts.

## Abstract

The EPI (Evidence Portable Infrastructure) format defines a portable,
self-contained, cryptographically sealed container for AI agent execution
evidence. A `.epi` file is a polyglot — valid HTML for browser-based
inspection AND a binary envelope carrying a ZIP payload — enabling
zero-install verification by regulators, auditors, and compliance reviewers.

This specification defines:
- The container structure (envelope-v2 and legacy-zip)
- The manifest schema and cryptographic signing protocol
- The step timeline format and hash-chain integrity
- The verification procedure and trust model
- Conformance requirements for implementers

It is the authoritative reference for independent implementations. The
reference implementation is available under the MIT license at
https://github.com/mohdibrahimaiml/epi-recorder.

---

## 1. Conventions

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT",
"SHOULD", "SHOULD NOT", "RECOMMENDED", "MAY", and "OPTIONAL" in this
document are to be interpreted as described in RFC 2119.

- All hash values are SHA-256, represented as 64-character lowercase hex strings.
- All signatures are Ed25519 (RFC 8032), represented as 64-character lowercase hex strings.
- All timestamps are UTC ISO 8601 with second precision (`YYYY-MM-DDTHH:MM:SSZ`).
- All UUIDs are lowercase RFC 4122 variant 4 (random).
- "MUST be zero" fields that contain non-zero values cause verification to fail with an
  incorrect-format error.

---

## 2. Container Format

### 2.1 Envelope v2 (Polyglot)

A `.epi` file using envelope-v2 begins with a 128-byte binary header followed
by an HTML viewer and a ZIP payload. The polyglot structure allows any browser
to open the file directly for forensic inspection.

#### 2.1.1 Envelope Header

| Offset | Size | Field | Description |
|--------|------|-------|-------------|
| 0 | 4 | `magic` | `0x3C 0x21 0x2D 0x2D` (ASCII `<!--`) |
| 4 | 1 | `version` | Envelope format version. Value: `0x02` |
| 5 | 1 | `flags` | Reserved. MUST be `0x00` |
| 6 | 2 | `reserved` | Reserved. MUST be `0x0000` |
| 8 | 8 | `payload_length` | ZIP payload length in bytes (little-endian uint64) |
| 16 | 16 | `payload_uuid` | UUID v4 (16 raw bytes) |
| 32 | 8 | `created_at` | Unix epoch timestamp in microseconds (little-endian uint64) |
| 40 | 32 | `payload_sha256` | SHA-256 hash of the ZIP payload bytes (32 raw bytes) |
| 72 | 56 | `reserved` | Reserved. MUST be zero |

Total header size: **128 bytes**.

Implementers MUST reject files shorter than 128 bytes. Implementers MUST reject
files where `payload_length` is zero or where the file size is less than
`128 + payload_length`.

#### 2.1.2 ZIP Payload Marker

Following the 128-byte header, a viewer HTML payload MAY be present. The start
of the ZIP payload is marked by the exact byte sequence:

```
0x0A 3C 21 2D 2D 20 45 50 49 5F 5A 49 50 5F 50 41
59 4C 4F 41 44 5F 53 54 41 52 54 20 2D 2D 3E 0A
```

ASCII representation: `
<!-- EPI_ZIP_PAYLOAD_START -->
`

All bytes between the 128-byte header and this marker constitute the embedded
viewer. All bytes after this marker constitute the ZIP payload.

#### 2.1.3 MIME Type

The container's MIME type is `application/vnd.epi`.

### 2.2 Legacy ZIP

Prior to v4.0.0, `.epi` files used a non-polyglot binary header with magic
bytes `EPI1` (0x45 0x50 0x49 0x31). The ZIP payload followed immediately.

Implementers SHOULD support reading legacy `EPI1` containers but SHOULD NOT
produce them.

The legacy MIME type is `application/vnd.epi+zip`.

### 2.3 Container Auto-detection

Implementers MUST detect the container format as follows:
1. Read first 4 bytes of the file.
2. If `0x3C 0x21 0x2D 0x2D` → envelope-v2.
3. If `0x45 0x50 0x49 0x31` → legacy-zip.
4. Otherwise → not a valid `.epi` file.

---

## 3. Internal ZIP Payload

### 3.1 Required Files

| File | Purpose | Schema |
|------|---------|--------|
| `mimetype` | MUST contain exactly `application/vnd.epi+zip` (uncompressed, first ZIP entry) | Plain text |
| `manifest.json` | Signed manifest — the root of trust | `schemas/manifest.schema.json` |
| `steps.jsonl` | Ordered, immutable execution timeline (NDJSON) | `schemas/step.schema.json` |
| `environment.json` | Runtime environment snapshot | `schemas/environment.schema.json` |
| `analysis.json` | Deterministic fault analysis output | `schemas/analysis.schema.json` |
| `policy.json` | Governance rulebook applied during execution | `schemas/policy.schema.json` |
| `viewer.html` | Self-contained HTML forensic viewer | N/A (visual) |
| `VERIFY.txt` | Human-readable offline verification instructions | Plain text |

`mimetype` MUST be the first entry in the ZIP and MUST be stored (Method 0,
uncompressed). This convention follows the Open Document Format and EPUB
standards.

### 3.2 Optional Files

| File | Purpose |
|------|---------|
| `review.json` | Human review addendum (mutable, appended post-sealing, NOT in file_manifest) |
| `review_index.json` | Index for multi-reviewer review records |
| `policy_evaluation.json` | Structured evaluation of each policy rule against execution steps |
| `stdout.log` | Captured standard output |
| `stderr.log` | Captured standard error |
| `artifacts/scitt/statement.cbor` | SCITT COSE_Sign1 signed statement |
| `artifacts/scitt/receipt.cbor` | SCITT transparency receipt with Merkle proof |
| `artifacts/sbom/` | CycloneDX SBOM artifacts |
| `artifacts/agt_export.json` | AGT compliance export |

### 3.3 Reserved Root Names

The names `mimetype`, `manifest.json`, `viewer.html`, and `VERIFY.txt` are
reserved. User artifacts MUST NOT use these names. Implementers SHOULD place
user-generated files under `artifacts/`.

---

## 4. Manifest Schema (`manifest.json`)

The manifest is the root of trust for the entire `.epi` file. Every required
and optional file's SHA-256 hash is recorded in `file_manifest`. If the
manifest is signed (Ed25519), the signature covers the canonical hash of the
manifest object itself.

### 4.1 Required Fields

| Field | Type | Description |
|-------|------|-------------|
| `spec_version` | string | EPI specification version (e.g., `"4.2.0"`) |
| `workflow_id` | UUID (string) | Unique identifier for this workflow execution |
| `created_at` | datetime (string) | UTC ISO 8601 timestamp when the container was created |
| `file_manifest` | object (string→string) | Mapping of ZIP-relative file paths to SHA-256 hex hashes |

### 4.2 Optional Fields

| Field | Type | Description |
|-------|------|-------------|
| `cli_command` | string | Command-line invocation that produced this workflow |
| `env_snapshot_hash` | string | SHA-256 hex hash of `environment.json` |
| `public_key` | string | 64-character hex-encoded Ed25519 public key (32 raw bytes) |
| `signature` | string | Ed25519 signature: `ed25519:<key_id>:<sig_hex>` (see §5.2) |
| `container_format` | string | `"legacy-zip"` or `"envelope-v2"` |
| `analysis_status` | string | `"complete"`, `"skipped"`, or `"error"` |
| `analysis_error` | string | Non-sensitive error message when `analysis_status` is `"error"` |
| `goal` | string | Human-readable workflow goal |
| `notes` | string | Free-form notes |
| `metrics` | object | Key-value metrics (values: number or string) |
| `source` | object | Integration metadata: `integration`, `framework`, `agent` |
| `total_steps` | integer | Total number of steps recorded |
| `approved_by` | string | Identity of approving reviewer |
| `tags` | array of string | Categorization tags |
| `viewer_version` | string | Preferred viewer shell version |
| `governance` | object | Governance metadata (DID identity, SCITT registration, trust score) |
| `trust` | object | Immediate cryptographic verification state |
| `policy` | object | Policy evaluation outcome (`policy_id`, `version`, `status`, `rules`) |
| `prev_hash` | string | SHA-256 of the previous container's manifest (for chaining) |

### 4.3 Complete JSON Schema

See `schemas/manifest.schema.json` for the formal JSON Schema definition.

---

## 5. Cryptographic Protocol

### 5.1 Canonical Hashing

The canonical hash of a manifest or step is computed as follows:

1. Convert the model to a dictionary.
2. Remove excluded fields (typically `signature` and `governance` for
   manifests; `source_type` for steps).
3. Normalize UUID values to lowercase canonical string form.
4. Normalize datetime values to UTC ISO 8601 with second precision
   (`YYYY-MM-DDTHH:MM:SSZ`).
5. Serialize to JSON with:
   - `sort_keys=True` (keys sorted alphabetically)
   - `separators=(",", ":")` (no whitespace)
   - `ensure_ascii=True`
6. Encode to UTF-8 bytes.
7. Compute SHA-256.
8. Return as 64-character lowercase hex string.

**Conformance requirement:** Two implementations computing the canonical hash
of identical data MUST produce the same hex string. The test vectors in
`test-vectors/` provide known input/output pairs to verify this.

### 5.2 Manifest Signing

1. Compute the canonical hash of the manifest, excluding the `signature`,
   `governance`, and `trust` fields.
2. Convert the 64-character hex hash to 32 raw bytes.
3. Sign with an Ed25519 private key (RFC 8032). This produces 64 raw signature bytes.
4. Encode the signature as 128-character lowercase hex.
5. Derive the key ID: SHA-256 the 64-character hex-encoded public key,
   take the first 16 characters of the resulting hex digest.
6. Format the signature string as: `ed25519:<key_id>:<signature_hex>`
7. Set `manifest.signature` to this value.

**Example signature string:**
```
ed25519:a1b2c3d4e5f67890:5f3a2b1c...<128 hex chars>
```

The key ID is cryptographically bound to the public key. This prevents an
attacker from substituting a different public key while keeping the same key
ID.

### 5.3 Manifest Verification

1. Parse the signature string by splitting on `:` into three parts.
2. Reject if the algorithm is not `ed25519`.
3. Verify the key ID matches the SHA-256 prefix of the hex-encoded public key.
4. Decode the 128-character hex signature to 64 raw bytes.
5. Compute the canonical hash of the manifest (excluding `signature`,
   `governance`, and `trust`).
6. Import the Ed25519 public key (32 raw bytes from hex).
7. Verify the signature over the canonical hash bytes.
8. Return `(True, "Valid")` or `(False, "Invalid - tampered")`.

### 5.4 File Integrity

For each entry in `manifest.file_manifest`:
1. Read the file from the ZIP payload.
2. Compute SHA-256 over the raw file bytes.
3. Compare to the stored hex hash.
4. Any mismatch is an integrity failure.

Implementers MUST also check that no extra files exist in the ZIP
that are not listed in `file_manifest` (except `review.json` and
`review_index.json`, which are mutable addendums excluded from
file_manifest).

### 5.5 Step Hash Chain

Each step in `steps.jsonl` contains a `prev_hash` field:

1. Step 0 has `prev_hash: null`.
2. For step N (N > 0), `prev_hash` is the SHA-256 hex digest of the
   canonical JSON hash of step N-1.
3. The step's own hash (stored separately, e.g., in the viewer or as
   a computed value) is the SHA-256 of its own canonical JSON bytes.
4. Verifying the chain: for each step N, compute its canonical hash,
   then verify that step N+1's `prev_hash` matches.

This creates an append-only, hash-linked timeline. Any insertion,
deletion, or reorder of steps breaks the chain.

---

## 6. Steps Format (`steps.jsonl`)

`steps.jsonl` uses Newline-Delimited JSON (NDJSON): one JSON object per line,
terminated by `
`. No trailing newline is required after the last line.

### 6.1 Step Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `index` | integer | Yes | Sequential step number (0-indexed, monotonically increasing) |
| `kind` | string | Yes | Step type identifier (see §6.2) |
| `timestamp` | datetime | Yes | UTC ISO 8601 timestamp |
| `content` | object | Yes | Step-specific payload |
| `prev_hash` | string or null | Yes | SHA-256 hex of previous step's canonical hash (null for step 0) |
| `trace_id` | string | No | W3C trace identifier |
| `span_id` | string | No | W3C span identifier |
| `parent_span_id` | string | No | W3C parent span identifier |
| `governance` | object | No | Step-level governance metadata |
| `source_type` | string | No | Actor type: `"user"`, `"tool"`, `"reasoning"`, `"system"` |

The `source_type` field is excluded from canonical hash computation to
maintain backward compatibility with artifacts sealed before this field was
added.

### 6.2 Standard Step Kinds

| Kind | Description |
|------|-------------|
| `session.start` | Recording session started |
| `session.end` | Recording session ended |
| `llm.request` | LLM API request (model, messages, parameters) |
| `llm.response` | LLM API response (completion, tokens, latency) |
| `tool.call` | Tool invocation (name, input) |
| `tool.output` | Tool result |
| `agent.decision` | Agent decision point |
| `agent.handoff` | Agent delegation |
| `agent.message` | Agent communication |
| `agent.approval.request` | Human approval request |
| `agent.approval.response` | Human approval response |
| `agent.run.start` | Agent run started |
| `agent.run.end` | Agent run ended |
| `agent.run.error` | Agent error |
| `user.input` | User-provided input |
| `human.approval` | Human approval recorded |
| `file.write` | File written to disk |
| `shell.command` | Shell command executed |
| `python.call` | Python function call |
| `validation.pass` | Validation passed |
| `validation.fail` | Validation failed |
| `validation.corrected` | Validation auto-corrected |
| `security.redaction` | Sensitive content redacted |
| `agent.step` | Generic agent step |
| `calculation` | Computation result |
| `summary` | Workflow summary |
| `stdout.print` | Standard output captured |

Custom step kinds are permitted but SHOULD use a namespace prefix
(e.g., `integration.mykind`).

### 6.3 Complete JSON Schema

See `schemas/step.schema.json` for the formal JSON Schema definition.

---

## 7. Environment Format (`environment.json`)

Describes the runtime environment at capture time.

| Field | Type | Description |
|-------|------|-------------|
| `python_version` | string | Python interpreter version |
| `platform` | string | Operating system identifier |
| `epi_version` | string | EPI package version |
| `hostname` | string | Machine hostname (may be redacted) |
| `packages` | object | Installed package names and versions |
| `environment_variables` | object | Environment variable names (values redacted) |

See `schemas/environment.schema.json` for the formal definition.

---

## 8. Analysis Format (`analysis.json`)

Contains the output of the 9-pass deterministic fault analysis.

| Field | Type | Description |
|-------|------|-------------|
| `fault_detected` | boolean | Whether any fault was found |
| `verdict_short` | string | Summary verdict |
| `primary_fault` | object | Primary fault details |
| `secondary_flags` | array | Secondary fault details |
| `coverage` | object | Analysis coverage statistics |
| `mode` | string | `"policy"` or `"heuristic_only"` |
| `analysis_version` | string | Fault analyzer version |

See `schemas/analysis.schema.json` for the formal definition.

---

## 9. Policy Format (`policy.json`)

Governance rulebook applied during execution.

| Field | Type | Description |
|-------|------|-------------|
| `policy_id` | string | Unique policy identifier |
| `policy_version` | string | Policy version |
| `rules` | array | Policy rules (see below) |
| `description` | string | Human-readable policy description |
| `metadata` | object | Additional metadata |

Each rule in `rules`:

| Field | Type | Description |
|-------|------|-------------|
| `rule_id` | string | Unique rule identifier |
| `rule_name` | string | Human-readable rule name |
| `severity` | string | `"critical"`, `"high"`, `"medium"`, or `"low"` |
| `mode` | string | `"detect"`, `"block"`, or `"warn"` |
| `conditions` | array | Rule conditions |
| `action` | string | Action to take |
| `description` | string | Rule description |

See `schemas/policy.schema.json` for the formal definition.

---

## 10. Verification Procedure

A conformant verifier MUST perform checks in this order:

### Pass 1: Structural Validation
- File is at least 128 bytes.
- Valid envelope header or legacy `EPI1` magic.
- ZIP payload is extractable.
- Required files (`manifest.json`, `steps.jsonl`, `mimetype`, `viewer.html`)
  are present.

### Pass 2: File Integrity
- Every entry in `manifest.file_manifest` has a matching file in the ZIP.
- No extra files exist in the ZIP (except `review.json`, `review_index.json`).
- Computed SHA-256 matches stored hash for every file.

### Pass 3: Signature Verification
- If `manifest.signature` is present, verify per §5.3.
- If absent, report as `UNSIGNED`.

### Pass 4: Step Chain Integrity
- `steps.jsonl` is valid NDJSON.
- Step indices are monotonically increasing starting from 0.
- Step timestamps are in non-decreasing order.
- For each step N > 0, `prev_hash` matches the canonical hash of step N-1.

### Pass 5: Completeness
- `manifest.total_steps` matches the number of lines in `steps.jsonl`.

### Pass 6: MIME Type
- `mimetype` file contains exactly `application/vnd.epi+zip`.

### Pass 7: SCITT Transparency (Optional)
- If `artifacts/scitt/statement.cbor` and `artifacts/scitt/receipt.cbor` exist:
  - Parse the COSE_Sign1 statement.
  - Verify the statement signature.
  - Verify the receipt's Merkle inclusion proof.

---

## 11. Trust Model

| Level | Integrity | Signature | Identity | Meaning |
|-------|-----------|-----------|----------|---------|
| **HIGH** | Pass | Valid | Known | Signer identity verified in trust registry |
| **MEDIUM** | Pass | Valid | Unknown | SCITT-anchored (transparency verified) |
| **LOW** | Pass | Valid | Unknown | Valid signature, identity not verified |
| **NONE** | Pass | None | — | Unsigned artifact |
| **TAMPERED** | Fail | Invalid | — | File has been modified or corrupted |

---

## 12. Security Considerations

### Threats Mitigated

| Threat | Mitigation |
|--------|------------|
| Post-seal tampering | SHA-256 file manifest + Ed25519 signature |
| Evidence replay | Unique `workflow_id` + `created_at` timestamp |
| Secret leakage | HMAC-SHA256 redaction of API keys, tokens, PII |
| Signature spoofing | Key ID cryptographically bound to public key |
| Step manipulation | `prev_hash` chain breaks on insert/remove/reorder |
| File injection | Integrity check rejects extra files |
| Visual deception | `viewer.html` hash in `file_manifest` |
| Key compromise | Key revocation files in trust registry |

### Threats Not Mitigated

- EPI is a post-execution evidence system. It does not prevent unauthorized
  AI access at runtime. For runtime enforcement, use `EPI_ENFORCE=1`.
- Encryption of .epi files is not specified by this format. Implementations
  MAY layer transport encryption (TLS) or file-level encryption (GPG,
  age) on top.
- The manifest signature covers file hashes, not file contents directly.
  Implementations MUST verify both signature AND individual file hashes.

---

## 13. Conformance

An implementation is conformant if it:

1. Produces `.epi` files that pass the verification procedure (§10) using
   a conformant verifier.
2. Produces correct canonical hashes (§5.1) matching the test vectors in
   `test-vectors/`.
3. Produces valid Ed25519 signatures (§5.2) that verify correctly.
4. Parses and validates `steps.jsonl` hash chains (§5.5) correctly.

An implementation MAY support only envelope-v2 (not legacy-zip) and still be
conformant. An implementation that does not sign manifests but otherwise
produces valid files is partially conformant.

---

## 14. Version History

| Version | Date | Changes |
|---------|------|---------|
| 4.2.0 | 2026-06-29 | Gateway fail-closed, key encryption, EPI_ENFORCE, formal schemas |
| 4.1.0 | 2026-05-14 | SCITT, AGT adapter, AIUC-1 mapping |
| 4.0.3 | 2026-05-03 | Viewer redesign, DID:WEB |
| 4.0.0 | 2026-04-08 | Envelope v2 (polyglot HTML+ZIP) |
| 1.0.0 | 2025-12-15 | Initial release |

---

*This specification is an open standard. Contributions and errata are welcome
via GitHub Issues at https://github.com/mohdibrahimaiml/epi-recorder.*
