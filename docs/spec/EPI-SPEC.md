# EPI File Format Specification v4.6.2

**Status:** Active  
**Date:** 2026-10-23  
**Version:** 4.6.2. **4.6.3 (release pending).**  
**Category:** Standards Track

---

### EU AI Act Annex IV Technical Documentation

EPI provides structured JSON schemas for all 9 sections of EU AI Act Annex IV.
See [schemas/annex-iv.schema.json](schemas/annex-iv.schema.json) for the full JSON Schema.
The `epi annex` CLI generates, signs, and verifies Annex IV **templates you fill in**. That is not a certificate.

## Abstract

The EPI (Evidence Packaged Infrastructure) format defines a portable,
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
- All signatures are Ed25519 (RFC 8032), represented as 128-character lowercase hex strings (64 bytes).
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
| 5 | 1 | `format` | Payload format. Value: `0x01` (ZIP v1) |
| 6 | 2 | `flags` | Reserved. MUST be `0x0000` |
| 8 | 8 | `payload_length` | ZIP payload length in bytes, excluding the HTML gap (little-endian uint64) |
| 16 | 16 | `payload_uuid` | UUID v4 (16 raw bytes); MUST equal `manifest.workflow_id` |
| 32 | 8 | `created_at` | Unix epoch timestamp in microseconds (little-endian uint64) |
| 40 | 32 | `payload_sha256` | SHA-256 hash of the ZIP payload bytes only, excluding the HTML gap (32 raw bytes) |
| 72 | 32 | `viewer_sha256` | SHA-256 of the outer viewer HTML bytes (UTF-8, without the ` -->\n` prefix or ZIP marker). All-zero means a legacy artifact whose display layer is not integrity-covered |
| 104 | 24 | `reserved` | Reserved. MUST be zero |

Total header size: **128 bytes**.

Implementers MUST reject files shorter than 128 bytes. Implementers MUST reject
files where `payload_length` is zero. Because a viewer HTML gap sits between
the header and the ZIP, implementers MUST NOT assume the ZIP starts at
`128 + payload_length` from the front nor find it by searching for the ZIP
local-file-header signature (`PK\x03\x04`) — viewer HTML may contain those
bytes. The ZIP starts immediately after the marker in §2.1.2; its length MUST
equal `payload_length` and its SHA-256 MUST equal `payload_sha256`.

#### 2.1.2 ZIP Payload Marker

Following the 128-byte header, a viewer HTML payload MAY be present. The start
of the ZIP payload is marked by the exact byte sequence:

```
0x0A 3C 21 2D 2D 20 45 50 49 5F 5A 49 50 5F 50 41
59 4C 4F 41 44 5F 53 54 41 52 54 20 2D 2D 3E 0A
```

ASCII representation: `<!-- EPI_ZIP_PAYLOAD_START -->`

All bytes between the 128-byte header and this marker constitute the embedded
viewer. All bytes after this marker constitute the ZIP payload.

#### 2.1.3 MIME Type

The envelope is a polyglot (valid HTML comment + ZIP) and has no single
MIME type. The canonical evidence identifier is `application/vnd.epi+zip`,
carried in the `mimetype` ZIP member (§3.1) and in `manifest.trust.mimetype`.

### 2.2 Legacy containers (`EPI1` and bare ZIP)

Prior to v4.0.0, `.epi` files used a non-polyglot binary header with magic
bytes `EPI1` (0x45 0x50 0x49 0x31). The ZIP payload followed immediately.

Implementers SHOULD support reading legacy `EPI1` containers. New artifacts
SHOULD use envelope-v2; a **bare ZIP payload** (same member layout as §3, no
envelope header and no outer viewer) remains supported for compatibility
pipelines and is what `epi migrate --legacy-zip` writes. Because historical
writers varied in header length, readers MUST NOT assume a fixed legacy
header size: after matching `EPI1` magic,
probe a bounded window (at least the first 64 bytes) for the ZIP
local-file-header signature (`PK\x03\x04`) and treat everything before it as
header. If no signature is found, the file is not a valid legacy container.

Both forms use the legacy MIME type `application/vnd.epi+zip` and verify
exactly like a payload without a viewer.

### 2.3 Container Auto-detection

Implementers MUST detect the container format as follows:
1. Read the first 4 bytes of the file.
2. If `0x3C 0x21 0x2D 0x2D` (`<!--`) → **envelope-v2**.
3. If `0x45 0x50 0x49 0x31` (`EPI1`) → **legacy `EPI1`**; probe for
   `PK\x03\x04` as described in §2.2.
4. If `0x50 0x4B 0x03 0x04` (`PK\x03\x04`) → **bare ZIP** (legacy-zip pipeline).
5. Otherwise → not a valid `.epi` file.

The ZIP payload inside envelope-v2 also starts with `PK\x03\x04`, but it is
located via the `EPI_ZIP_PAYLOAD_START` marker (§2.1.2), never by scanning
from byte 0.

---

## 3. Internal ZIP Payload

### 3.1 Required Files

| File | Purpose | Schema |
|------|---------|--------|
| `mimetype` | MUST contain exactly `application/vnd.epi+zip` (uncompressed, first ZIP entry) | Plain text |
| `manifest.json` | Signed manifest — the root of trust | `schemas/manifest.schema.json` |
| `steps.jsonl` | Ordered, tamper-evident execution timeline (NDJSON) | `schemas/step.schema.json` |
| `viewer.html` | Self-contained HTML forensic viewer | N/A (visual) |
| `VERIFY.txt` | Human-readable offline verification instructions (always written by current packers; readers MUST accept older artifacts where it is absent) | Plain text |

### 3.1b Conditional Files (present only when that run happened)

| File | Purpose | Schema |
|------|---------|--------|
| `environment.json` | Runtime environment snapshot (written by the recorder; readers tolerate absence, legacy `env.json` accepted) | `schemas/environment.schema.json` |
| `analysis.json` | Deterministic fault analysis output | `schemas/analysis.schema.json` |
| `policy.json` | Governance rulebook applied during execution | `schemas/policy.schema.json` |
| `policy_evaluation.json` | Sealed per-rule evaluation results | N/A (no standalone schema file) |

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
| `artifacts/notarization/tsa_reply.tsr` | First successful RFC 3161 `TimeStampResp` (DER) |
| `artifacts/notarization/tsa_reply_<n>.tsr` | Additional TSA tokens (one per extra TSA) |
| `artifacts/notarization/notarization.json` | Notarization evidence (see below) |
| `artifacts/notarization/digest.ots` | OpenTimestamps proof (when available) |
| `artifacts/sbom/` | CycloneDX SBOM artifacts |
| `artifacts/agt_export.json` | AGT compliance export |

### 3.3 Reserved Root Names

The names `mimetype`, `manifest.json`, `viewer.html`, and `VERIFY.txt` are
reserved. User artifacts MUST NOT use these names. Implementers SHOULD place
user-generated files under `artifacts/`.

---

## 4. Manifest Schema (`manifest.json`)

The manifest is the root of trust for the entire `.epi` file. Every sealed
file's SHA-256 hash is recorded in `file_manifest`, except:
`manifest.json` itself (covered by the Ed25519 signature instead),
`mimetype` (fixed 23-byte magic string), mutable review files
(`review.json`, `review_index.json`, `reviews/*`, added post-sealing), and
`artifacts/scitt/*` (verified cryptographically via receipt, not by file
hash). If the manifest is signed (Ed25519), the signature covers the
canonical hash of the manifest object itself.

### 4.1 Required Fields

| Field | Type | Description |
|-------|------|-------------|
| `spec_version` | string | EPI specification version (e.g., `"4.3.0"`) |
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

### 4.3 Complete JSON Schema

See `schemas/manifest.schema.json` for the formal JSON Schema definition.

---

## 5. Cryptographic Protocol

### 5.1 Canonical Hashing

Three canonicalizations exist, selected by `spec_version` — sign and verify
MUST use the same selection (one dispatch function, no trial):

| `spec_version` | Canonicalization |
|---|---|
| `1.x` | CBOR (RFC 8949, canonical encoding) |
| `2.x` through pre-`4.4.1` | Legacy JSON: `sort_keys=True`, separators `(",", ":")`, `ensure_ascii=False` |
| `4.4.1` and later | JCS (RFC 8785). Integers verbatim; non-integral numbers use ECMAScript number-to-string (`900.0` hashes as `"900"`); non-ASCII emitted as raw UTF-8 |
| missing, empty, unparseable, or major version `0` | CBOR (matches what signing has always produced for such inputs) |

`StepModel` records always use JCS: steps are stored and distributed as JSON
and carry no `spec_version` field.

The canonical hash of a manifest or step is computed as follows:

1. Convert the model to a dictionary.
2. Drop `source_type` and `verification_class` for steps (backward
   compatibility with artifacts sealed before those fields existed).
3. Drop `content_truncated`, `policy_load_status`, and `producer_version`
   when null (fields added after existing artifacts were sealed).
4. Remove excluded fields (see §5.2: `signature` for manifests).
5. Normalize UUID values to canonical string form.
6. Normalize datetime values to UTC ISO 8601 with second precision
   (`YYYY-MM-DDTHH:MM:SSZ`); naive datetimes are assumed UTC.
7. Serialize with the selected canonicalization above.
8. Encode to UTF-8 bytes.
9. Compute SHA-256.
10. Return as 64-character lowercase hex string.

**Conformance requirement:** Two implementations computing the canonical hash
of identical data MUST produce the same hex string. The test vectors in
`test-vectors/` provide known input/output pairs to verify this.

### 5.2 Manifest Signing

1. Compute the canonical hash of the manifest, excluding the `signature`
   field only. `governance` and `trust` are part of the signed preimage —
   a signature over a manifest with altered governance or trust does not verify.
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
5. Compute the canonical hash of the manifest (excluding `signature` only,
   per §5.2).
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
that are not listed in `file_manifest`, except:
`mimetype` and `manifest.json` (reserved names, covered by fixed content and
by the Ed25519 signature respectively);
`review.json`, `review_index.json`, and `reviews/*` (mutable addendums
verified via the review ledger instead); and `artifacts/scitt/*` (verified
cryptographically via receipt instead).
`VERIFY.txt` is normally listed in `file_manifest`; readers SHOULD accept
older artifacts where it is absent.

Two different hashes share the name "payload hash" — do not compare them:
the header's `payload_sha256` is the SHA-256 of the ZIP payload bytes, while
`manifest.trust.payload_hash` is the SHA-256 of the sorted `file_manifest`
JSON (a hash-of-hashes fingerprint for display).

### 5.5 Step Hash Chain

Each step in `steps.jsonl` contains a `prev_hash` field:

1. Step 0 carries the genesis marker: `prev_hash` is `null` or the string
   `"CHAIN_START"` (sealers write `"CHAIN_START"`). There is no previous
   step to link to, so nothing is checked for step 0 beyond this.
2. For step N (N > 0), `prev_hash` is **exactly** the 64-character
   lowercase SHA-256 hex digest that is the canonical hash of step N-1 — not
   a second SHA-256 over that digest string. Canonical hashing follows §5.1:
   current sealers (specification `4.4.1` and later) always encode steps with
   JCS, and verifiers select the canonicalization from the manifest's
   `spec_version` so that pre-`4.4.1` artifacts remain readable with the
   legacy JSON form. A genesis marker at N > 0 means the chain was restarted
   (possible truncation) and MUST be reported as a break.
3. The step's own canonical hash is the SHA-256 of its canonical JSON bytes
   (the same value the next step stores in `prev_hash`).
4. Verifying the chain: for each step N, compute its canonical hash,
   then verify that step N+1's `prev_hash` matches.

This creates an append-only, hash-linked timeline. Any insertion,
deletion, or reorder of steps breaks the chain.

### 5.6 Seal Timestamp Imprint (`epi-tsa-imprint/v1`)

Seal-time RFC 3161 tokens bind a recomputable digest, not the canonical
manifest hash (which is computed before the notarization members,
`VERIFY.txt` and `viewer.html` are added, so no verifier could recompute it).

To compute the imprint (seal and verify sides MUST agree byte for byte):

1. Take `manifest.file_manifest` (archive member name → SHA-256 hex).
2. Remove exact names `viewer.html`, `VERIFY.txt`, `manifest.json`,
   `mimetype`, and every name starting with `artifacts/notarization/`,
   `artifacts/scitt/` or `artifacts/transparency/`.
3. Build the JSON object (keys in this order; encoding is JCS per §5.1):
   `{"scheme": "epi-tsa-imprint/v1", "workflow_id": "<str>",
   "created_at": "<manifest.created_at in ISO-8601>",
   "public_key": "<hex or null>", "files": <filtered map>}`.
   `public_key` is `manifest.public_key` at seal time (`null` on unsigned
   first packs; the value used is stored in `notarization.json` as
   `imprinted_public_key` so verifiers recompute with identical input).
   `created_at` MUST round-trip through ISO-8601 parse/format identically on
   both sides.
4. `imprinted_digest` is the SHA-256 hex of the JCS bytes.

The TSA request imprints this digest with SHA-256. The verifier recomputes it
from the final manifest and requires the token's `messageImprint` to match
byte for byte; any difference is `imprint_mismatch`.

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
| `prev_hash` | string or null | Yes | SHA-256 hex of previous step's canonical hash (`null` or `"CHAIN_START"` for step 0, see §5.5) |
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
| `tool.response` | Tool result (what the verifier pairs with `tool.call`) |
| `tool.output` | Legacy alias for a tool result; readers accept it |
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
| `policy_format_version` | string | Format version (currently `"1.0"`) |
| `policy_id` | string | Unique policy identifier |
| `system_name` | string | System/workflow the policy governs |
| `system_version` | string | System version |
| `policy_version` | string | Policy version |
| `profile_id` | string | Optional profile identifier |
| `scope` | object | Optional scope (intervention point, approval) |
| `authorized_by` | string | Optional authorizing party |
| `governance_url` | string | Optional governance URL |
| `approval_policies` | array | Approval policy definitions (`approval_id`, …) |
| `context_tracking` | object | Optional `identity_fields` / `exempt_fields` for context-drop detection |
| `rules` | array | Policy rules (see below) |

Each rule in `rules` (implemented by `epi_core.policy.PolicyRule`):

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique rule identifier (e.g. `R001`) |
| `name` | string | Human-readable rule name |
| `severity` | string | `"critical"`, `"high"`, `"medium"`, or `"low"` |
| `description` | string | Rule description |
| `type` | string | `constraint_guard`, `sequence_guard`, `threshold_guard`, `prohibition_guard`, `approval_guard`, or `tool_permission_guard` |
| `mode` | string | Optional `"detect"`, `"block"`, or `"warn"` |
| `applies_at` | string or array | Optional intervention point(s) |
| `rationale`, `domain` | string | Optional metadata |
| `watch_for`, `violation_if` | array/string | `constraint_guard` fields |
| `required_before`, `must_call` | string | `sequence_guard` fields |
| `threshold_value`, `threshold_field`, `required_action` | number/string | `threshold_guard` fields |
| `prohibited_pattern` | string | `prohibition_guard` pattern (`pattern` is accepted as an alias) |
| `approval_action`, `approved_by`, `approval_policy_ref` | string | `approval_guard` fields (`action` is accepted as an alias) |
| `allowed_tools`, `denied_tools` | array | `tool_permission_guard` fields |

See `epi_core/policy.py` and `docs/POLICY.md` for the normative implementation.

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
- No extra files exist in the ZIP (except `review.json`, `review_index.json`,
  `reviews/*`, and `artifacts/scitt/*` — see §5.4 for the full exemption list).
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

### Pass 8: Timestamp Validation (Optional)
- If `artifacts/notarization/notarization.json` exists:
  - Read `imprint_scheme`, `imprinted_digest`, `imprinted_public_key` and
    `tsa_tokens[]` (`{url, member}`). Absent `imprint_scheme` means a legacy
    token: report presence only, never fail.
  - Recompute the §5.6 imprint from the final manifest; require equality with
    `imprinted_digest`.
  - For each token: parse `TimeStampResp` (or bare token), require granted
    status, require SHA-256/384/512 `messageImprint` equal to the digest,
    locate the single SignerInfo's certificate, check the `message-digest`
    attribute and ESS binding, verify the CMS signature (RSA PKCS#1 v1.5,
    RSA-PSS or ECDSA), require critical `id-kp-timeStamping` EKU and
    `genTime` within the signer validity, and chain to a pinned root —
    fully offline, no revocation check.
  - `imprint_mismatch` / `bad_signature` / `cert_invalid` MUST fail
    verification in every policy. `untrusted`, `legacy`, `absent`,
    `malformed` and `not_granted` MUST NOT change the decision (unless
    `--require-timestamp` is set, which requires at least one `valid`
    seal-time token).

`notarization.json` fields: `notarized_at` (`provider`, `url`, `hash`),
`tsa_token_available`, `tsa_genTime`, `tsa_tokens[]`, and — only on new
seals — `imprint_scheme`, `imprinted_digest`, `imprinted_public_key`.
All are optional; verifiers MUST accept files without them.

---

## 11. Trust Model

| Level | Integrity | Signature | Identity | Meaning |
|-------|-----------|-----------|----------|---------|
| **HIGH** | Pass | Valid | Known (org-pinned) | Signer key was pinned out of band |
| **MEDIUM** | Pass | Valid | Local | Sealer key is on this machine, not an org pin |
| **MEDIUM** | Pass | Valid | Unknown | SCITT-anchored (transparency verified) |
| **LOW** | Pass | Valid | Unknown | Valid signature, identity not verified |
| **LOW** | Pass | None | - | Unsigned artifact: integrity only, no authenticity |
| **NONE** | Fail | - | - | Integrity or signature verification failed; do not trust |
| **FAIL** | Pass | Valid | Mismatch | Claimed identity does not match the signing key |
| **INVALID** | Pass | Valid | Revoked | The signing key has been revoked |

A `KNOWN` identity resolved only from the signer's own `did:web` document is
still `KNOWN` for policy purposes but is described as
`SIGNER SELF-ASSERTED (DID)`, never as `IDENTITY PINNED`. See
[`docs/VERIFICATION_CONTRACT.md`](../VERIFICATION_CONTRACT.md).

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
| 4.6.3 (release pending) | 2026-10-23 | `epi verify` binds the outer display layer to the signed `file_manifest["viewer.html"]` hash; viewer fail-closed on baked envelope failures; DID-only identities reported as self-asserted with `pin_source`; decompression-bomb guards; context-aware PII redaction and `allowlist_fields` |
| 4.6.2 | 2026-10-22 | Viewer fail-closed on envelope tamper (#141/#143); Cloud login/dashboard, evidence pack, key registry, customer-owned storage; witness wording fixes |
| 4.6.1 | 2026-10-13 | Remote trust registry informational only; first-party Cloud fixes |
| 4.6.0 | 2026-10-12 | RFC 3161 offline validation (`epi-tsa-imprint/v1`, pinned TSA roots, `report.timestamps`); dual-TSA seal stamping; `--tsa-root`, `--require-timestamp` |
| 4.5.0 | 2026-10-04 | Policy/governance and verification-contract updates; see `CHANGELOG.md` |
| 4.4.1 | 2026-08-29 | JCS (RFC 8785) canonicalization for manifests and steps |
| 4.3.0 | 2026-06-29 | Gateway fail-closed, key encryption, EPI_ENFORCE, formal schemas |
| 4.1.0 | 2026-05-14 | SCITT, AGT adapter, AIUC-1 mapping |
| 4.0.3 | 2026-05-03 | Viewer redesign, DID:WEB |
| 4.0.0 | 2026-04-08 | Envelope v2 (polyglot HTML+ZIP) |
| 1.0.0 | 2025-12-15 | Initial release |

---

*This specification is an open standard. Contributions and errata are welcome
via GitHub Issues at https://github.com/mohdibrahimaiml/epi-recorder.*
