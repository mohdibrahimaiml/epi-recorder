# EPI Specification v1.0

**Status:** Normative. This document defines the EPI (Evidence Packaged Infrastructure) format for portable, verifiable AI compliance evidence.

**Cross-validated:** AlgoVoi JCS conformance corpus (3 independent RFC 8785 implementations).

**Reference implementation:** EPI Recorder v4.2.0 (Python, Apache 2.0)

**Independent verifier:** epi-labs/epi-verifier (JavaScript, Apache 2.0)

---

## 1. File Format

An .epi file is a polyglot container -- a valid ZIP archive that is also a valid HTML document. This enables browser-based verification with zero server infrastructure.

### 1.1 Container Formats

| Format | Description |
|--------|------------|
| **legacy-zip** | Standard ZIP archive. Viewer embedded as viewer.html at root. |
| **envelope-v2** | Binary envelope header (EPIEnvelope) prepended to ZIP payload. |

### 1.2 Required Members

| Member | Format | Description |
|--------|--------|------------|
| mimetype | text | Must be first, uncompressed. Value: application/vnd.epi+zip |
| manifest.json | JSON | Manifest (see Section 2) |
| steps.jsonl | NDJSON | Execution steps, one per line (see Section 3) |

### 1.3 Optional Members

| Member | Format | Description |
|--------|--------|------------|
| policy.json | JSON | Policy evaluation result |
| analysis.json | JSON | Fault analysis report |
| environment.json | JSON | Environment snapshot |
| review.json | JSON | Human review record (see Section 6) |
| viewer.html | HTML | Embedded forensic viewer |
| artifacts/* | Various | Additional evidence artifacts |

### 1.4 MIME Type

application/vnd.epi+zip

---

## 2. Manifest

The manifest is the global header -- analogous to a PDF catalog. It contains metadata, file integrity hashes, and a cryptographic signature.

### 2.1 Required Fields

| Field | Type | Description |
|-------|------|------------|
| spec_version | string | EPI specification version (e.g. v2.0) |
| workflow_id | UUID | Unique identifier, UUID v4, lowercase hyphenated |
| created_at | datetime | Creation timestamp, ISO 8601, UTC, no microseconds |

### 2.2 Optional Fields

| Field | Type | Description |
|-------|------|------------|
| cli_command | string | Command-line invocation |
| env_snapshot_hash | string | SHA-256 of environment.json |
| file_manifest | dict | File path to SHA-256 hash mapping |
| public_key | string | Hex-encoded Ed25519 public key, 64 hex characters |
| signature | string | Ed25519 signature: ed25519:{derived_key_name}:{hex_sig} |
| container_format | string | legacy-zip or envelope-v2 |
| goal | string | Workflow objective |
| notes | string | Additional context |
| metrics | dict | Key-value metrics |
| total_steps | int | Total step count |
| total_validators | int | Total validator count |
| total_llm_calls | int | Total LLM call count |
| passed, failed, corrected | int | Validation result counts |
| approved_by | string | Approver identity |
| tags | list | Categorization tags |
| governance | dict | Governance metadata (DID, SCITT, trust score) |
| policy | PolicyModel | Policy evaluation result |
| analysis_status | string | complete, skipped, or error |
| analysis_error | string | Analysis failure reason (when status is error) |

---

## 3. Steps

Each step is an immutable record in steps.jsonl (NDJSON format). Steps form a cryptographically chained timeline via prev_hash.

### 3.1 Step Fields

| Field | Type | Required | Description |
|-------|------|----------|------------|
| index | int | Yes | Sequential step number, 0-indexed |
| timestamp | datetime | Yes | UTC, ISO 8601, no microseconds |
| kind | string | Yes | Step type identifier |
| content | dict | Yes | Step-specific data |
| prev_hash | string | No | Canonical hash of previous step (SHA-256 hex, 64 chars) |
| trace_id | string | No | W3C execution trace identifier |
| span_id | string | No | W3C execution span identifier |
| parent_span_id | string | No | Parent W3C execution span identifier |
| source_type | string | No | Source actor: user, tool, reasoning, or system |
| governance | dict | No | Step-level governance metadata |

### 3.2 Standard Step Kinds

| Kind | Description |
|------|------------|
| llm.request | LLM API request (prompt, model, messages) |
| llm.response | LLM API response (output, tokens, choices) |
| tool.call | Tool invocation (name, input parameters) |
| tool.response | Tool result (output, errors) |
| agent.decision | Agent decision (verdict, rationale) |
| agent.approval.request | Human approval requested |
| agent.approval.response | Human approval response |
| agent.run.start | Agent run started |
| agent.run.end | Agent run ended |
| agent.handoff | Agent handoff event |
| validation.pass | Validator passed |
| validation.fail | Validator failed |
| validation.corrected | Validator auto-corrected |
| validation.start | Validation run started |
| policy.check | Policy rule evaluated |
| session.start | Recording session started |
| session.end | Recording session ended |
| environment.captured | Environment snapshot captured |
| security.redaction | Secret redacted from step content |
| file.write | File written during execution |

### 3.3 Source Type Auto-population

When source_type is not explicitly set, it is derived from kind:

- tool.response -> tool
- agent.approval.response -> user
- agent.message with role=user -> user, role=system -> system, otherwise -> reasoning
- agent.run.start -> user
- llm.request, llm.response, agent.decision, agent.handoff, agent.run.end, tool.call, agent.approval.request -> reasoning
- validation.*, security.redaction, shell.command, file.write, python.call -> system

### 3.4 Validation Payload

When kind is validation.pass, validation.fail, or validation.corrected, the content object MAY include:

| Field | Type | Description |
|-------|------|------------|
| validator | string | Validator name (e.g. guardrails, pydantic) |
| result | string | pass, fail, or corrected |
| input_ref | int | Reference to input step index |
| output_ref | int | Reference to output step index (corrected outcomes) |
| score | float | Confidence/severity score (0.0-1.0) |
| details | dict | Validator-specific details |

---

## 4. Canonical Hash

### 4.1 Algorithm

```
canonical_hash(model) = SHA-256(JCS(model_dump - excluded_fields))
```

### 4.2 Step 1: Serialize

Extract all fields from the model. Null values participate in the hash.

### 4.3 Step 2: Exclude

| Field | Applies to | Reason |
|-------|-----------|--------|
| signature | Manifest | The signature cannot sign itself |
| governance | Manifest, Step | Optional metadata not present in all artifacts |
| source_type | Step | Backward compatibility (AUD-AT-01); legacy artifacts do not contain this field |

### 4.4 Step 3: Normalize

| Type | Normalization |
|------|--------------|
| datetime (naive) | Assume UTC. Strip microseconds. Format as YYYY-MM-DDTHH:MM:SSZ |
| datetime (timezone-aware) | Convert to UTC. Strip microseconds. Format as YYYY-MM-DDTHH:MM:SSZ |
| UUID | Lowercase hyphenated form (e.g. 550e8400-e29b-41d4-a716-446655440000) |

Apply normalization recursively to nested dictionaries and lists.

### 4.5 Step 4: JCS RFC 8785 Canonicalization

1. Serialize to JSON with:
   - sort_keys=True -- object keys sorted lexicographically by Unicode code point
   - separators=(',', ':') -- compact form with no whitespace
   - ensure_ascii=False -- non-ASCII characters emitted as literal UTF-8 bytes. Required by JCS RFC 8785 Section 3.4.
2. Encode the resulting JSON string as UTF-8 bytes.
3. Compute SHA-256 of the UTF-8 bytes.
4. Return the hex digest (64 lowercase hex characters).

### 4.6 Step 5: Hash

```
SHA-256(JCS_JSON_bytes) -> hex digest
```

### 4.7 StepModel Format Selection

StepModel has no spec_version field. The reference implementation uses JSON canonicalization (format="json"). Legacy v1.0 artifacts used CBOR canonicalization; v2+ uses JSON. Implementations MUST provide a means to select JSON canonicalization for StepModel.

### 4.8 Float Handling

Floats SHOULD NOT appear in manifest or step data that requires canonical hashing. EPI schemas use int, str, UUID, datetime, dict, and list types exclusively for fields participating in canonical hashing.

---

## 5. Signature

### 5.1 Format

```
ed25519:{derived_key_name}:{hex_signature}
```

Where:
- derived_key_name = SHA-256(public_key_hex)[:16] -- cryptographically bound to the public key
- hex_signature = Ed25519 signature over SHA-256(canonical hash of manifest excluding signature field)

### 5.2 Key Storage

Public keys are stored as hex-encoded raw Ed25519 key bytes (64 hex characters) in the manifest's public_key field. Private keys are stored in PEM format on the signer's filesystem.

### 5.3 Verification Procedure

1. Parse signature string by splitting on ':' (three components expected)
2. Verify first component is "ed25519"
3. Verify derived_key_name equals SHA-256(public_key)[:16]
4. Decode hex_signature to bytes (supports both hex and legacy base64)
5. Compute canonical hash of manifest (excluding signature field)
6. Compute SHA-256 of the canonical hash
7. Verify Ed25519 signature against SHA-256 hash bytes using public key

---

## 6. Verification Report

### 6.1 Trust Levels

| Level | Conditions |
|-------|-----------|
| HIGH | Integrity valid + signature valid + identity KNOWN |
| MEDIUM | Integrity valid + unsigned (or signed with SCITT valid) |
| LOW | Integrity valid + signature valid + identity UNKNOWN |
| INVALID | Identity REVOKED |
| FAIL | Identity MISMATCH (possible impersonation attack) |
| NONE | Integrity compromised |

### 6.2 Identity Status

| Status | Meaning |
|--------|---------|
| KNOWN | Public key found in trusted registry or DID:WEB resolution matches |
| UNKNOWN | Signature valid but identity not in any trusted registry |
| MISMATCH | DID:WEB resolved but public key does not match |
| REVOKED | Key explicitly revoked |

### 6.3 Policy Evaluation

| Policy | Acceptance criteria |
|--------|-------------------|
| PERMISSIVE | Integrity only |
| STANDARD | Integrity + not revoked + not mismatched. Unknown identity = WARN |
| STRICT | Integrity + known identity + completeness |

---

## 7. Interoperability Boundaries

### 7.1 Timestamps

EPI uses ISO 8601 strings (YYYY-MM-DDTHH:MM:SSZ). Other formats (e.g., AlgoVoi compliance-receipt-v1) use epoch millisecond integers. The two preimages hash to different digests. This is an explicit format boundary -- each format chooses its timestamp encoding independently.

### 7.2 Signature Envelope

EPI uses raw Ed25519 hex signatures and embedded public keys. Other formats (e.g., AlgoVoi) use JWKS/JWS envelopes with published key sets. Cross-verification requires format translation.

### 7.3 Verdict Enums

EPI uses open-schema validation results. Other formats (e.g., AlgoVoi) use closed categorical enums (COMPLIANT, NON_COMPLIANT, PENDING_REVIEW). Machine comparability across implementations requires a mapping layer.

Full boundary documentation: docs/EPI-ALGOVOI-INTEROP.md

---

## 8. Human Review

### 8.1 Review Record

Human reviewers can append a review.json to an existing .epi file without invalidating the original manifest signature. Review records are stored outside the file_manifest.

| Field | Type | Description |
|-------|------|------------|
| reviewed_by | string | Reviewer identity |
| reviewed_at | datetime | Review timestamp |
| status | string | approved, rejected, or escalated |
| notes | string | Review rationale and findings |

### 8.2 Review Signing

Reviews may be cryptographically signed. The review signature binds the reviewer's attestation to the artifact's workflow_id without modifying the original evidence.

---

## 9. Conformance Vectors

### 9.1 Location

Machine-readable conformance vectors are published at:

tests/compatibility/golden/canonical_hash_vectors.json

### 9.2 Format

Each vector contains:

| Field | Description |
|-------|------------|
| name | Human-readable identifier |
| input | Normalized dictionary (post step 2 & 3) |
| canonical_json | JCS RFC 8785 canonical JSON string |
| expected_hash | SHA-256 hex digest of canonical_json |

### 9.3 Validation

All vectors satisfy: SHA-256(canonical_json) = expected_hash

Cross-validated by AlgoVoi across 3 independent RFC 8785 implementations (rfc8785/Python, canonicalize/JS, gowebpki-jcs/Go), in addition to EPI Recorder's reference implementation.

### 9.4 Timestamp Encoding Note

The conformance vectors use ISO 8601 timestamp encoding. This is the EPI canonical format. Implementations using epoch millisecond integers will produce different frame_ids and will not cross-validate against these vectors without explicit normalization.

---

## 10. References

| Reference | Link |
|-----------|------|
| JCS RFC 8785 | https://www.rfc-editor.org/rfc/rfc8785 |
| EPI Canonical Hash Specification | docs/EPI-CANONICAL-HASH.md |
| EPI-AlgoVoi Interoperability | docs/EPI-ALGOVOI-INTEROP.md |
| AlgoVoi JCS Conformance Corpus | https://github.com/chopmob-cloud/algovoi-jcs-conformance-vectors |
| EPI Reference Implementation | https://github.com/mohdibrahimaiml/epi-recorder |
| EPI Independent Verifier | https://github.com/epi-labs/epi-verifier |

---

*Version 1.0 -- 2026-06-13*
*EPI is an open format under the Apache 2.0 license. The specification is freely implementable, distributable, and modifiable.*
