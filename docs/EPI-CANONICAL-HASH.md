# EPI Canonical Hash Specification

## Normative Reference

EPI canonical hashes follow **JCS RFC 8785** (JSON Canonicalization Scheme) with the
following clarifications and extensions for EPI-specific types.

**Normative reference:** [RFC 8785 — JSON Canonicalization Scheme (JCS)](https://www.rfc-editor.org/rfc/rfc8785)

## Algorithm

```
canonical_hash(model) = SHA-256(JCS(model_dump_without_excluded_fields))
```

### Step 1: Serialize model to dictionary

Extract all fields from the Pydantic model via `model.model_dump()`. The result is a
flat dictionary. Nested dictionaries and lists are preserved as-is.

**Note:** Pydantic `model_dump()` includes unset optional fields as `null` by default.
These `null` values participate in the canonical hash. Test vectors below reflect the
full model state, not a trimmed subset.

### Step 2: Exclude fields

Exclude the following fields from the dictionary **before** normalization. These
fields are excluded because they are either the signature itself or fields that did
not exist in legacy artifacts:

| Field | Applies to | Reason |
|-------|-----------|--------|
| `signature` | ManifestModel | The signature cannot sign itself |
| `governance` | ManifestModel, StepModel | Optional metadata not present in all artifacts |
| `source_type` | StepModel | Backward compatibility (AUD-AT-01); legacy artifacts do not contain this field |

### Step 3: Normalize types

Convert the following Python types to their canonical string representation:

| Type | Normalization |
|------|--------------|
| `datetime` (naive) | Assume UTC. Strip microseconds. Format as `YYYY-MM-DDTHH:MM:SSZ` |
| `datetime` (timezone-aware) | Convert to UTC. Strip microseconds. Format as `YYYY-MM-DDTHH:MM:SSZ` |
| `UUID` | Convert to canonical lowercase hyphenated form (`550e8400-e29b-41d4-a716-446655440000`) |

The normalization **must** be applied recursively to all nested dictionaries and lists.

### Step 4: JCS RFC 8785 canonicalization

Apply JCS RFC 8785 to the normalized dictionary:

1. Serialize to JSON with:
   - `sort_keys=True` — object keys sorted lexicographically by Unicode code point
   - `separators=(',', ':')` — compact form with no whitespace
   - `ensure_ascii=False` — non-ASCII characters emitted as literal UTF-8 bytes. **This is required by JCS RFC 8785 §3.4**, which mandates that Unicode code points outside the ASCII control range be serialized "as is" (literal UTF-8), not as `\uXXXX` escapes. This also aligns with AlgoVoi's cross-validated conformance corpus.
2. Encode the resulting JSON string as UTF-8 bytes.
3. Compute SHA-256 of the UTF-8 bytes.
4. Return the hex digest (64 lowercase hex characters).

### Step 5: Hash

```
SHA-256(JCS_JSON_bytes) → hex digest
```

## Conformance Test Vectors

### Test Vector 1: ManifestModel (basic)

**Input:**
```json
{
  "spec_version": "v2.0",
  "workflow_id": "550e8400-e29b-41d4-a716-446655440000",
  "created_at": "2025-06-08T12:00:00Z",
  "cli_command": "epi record --out test.epi",
  "file_manifest": {
    "steps.jsonl": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "policy.json": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
  }
}
```

**Expected canonical JSON (JCS):**
```
{"analysis_error":null,"analysis_status":null,"approved_by":null,"cli_command":"epi record --out test.epi","container_format":null,"corrected":null,"created_at":"2025-06-08T12:00:00Z","env_snapshot_hash":null,"failed":null,"file_manifest":{"policy.json":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","steps.jsonl":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"},"goal":null,"governance":null,"metrics":null,"notes":null,"passed":null,"policy":null,"public_key":null,"signature":null,"source":null,"spec_version":"v2.0","tags":null,"total_llm_calls":null,"total_steps":null,"total_validators":null,"trust":null,"viewer_version":null,"workflow_id":"550e8400-e29b-41d4-a716-446655440000"}
```

**Expected hash:** `b132da411e56c8364c7c5e4d5a00b65a03467fe7ce7709ec13a1b81bb2d8e8ec`

To verify independently:
```python
import json, hashlib
data = { ... }  # the normalized dict above
jcs = json.dumps(data, sort_keys=True, separators=(',',':'), ensure_ascii=False).encode('utf-8')
assert hashlib.sha256(jcs).hexdigest() == expected_hash
```

### Test Vector 2: StepModel (with source_type excluded)

**Input:**
```json
{
  "index": 0,
  "timestamp": "2025-06-08T12:00:00Z",
  "kind": "llm.request",
  "content": {"prompt": "Hello"},
  "source_type": "reasoning"
}
```

**After excluding `source_type`:**
```json
{
  "content": {"prompt": "Hello"},
  "governance": null,
  "index": 0,
  "kind": "llm.request",
  "parent_span_id": null,
  "prev_hash": null,
  "span_id": null,
  "timestamp": "2025-06-08T12:00:00Z",
  "trace_id": null
}
```

**Expected canonical JSON (JCS):**
```
{"content":{"prompt":"Hello"},"governance":null,"index":0,"kind":"llm.request","parent_span_id":null,"prev_hash":null,"span_id":null,"timestamp":"2025-06-08T12:00:00Z","trace_id":null}
```

**Expected hash:** `d324120ef801294f0f74e39a4f18c00666e38bcd97852a77e15c915c1ba5538a`

### Test Vector 3: Unicode (literal UTF-8)

**Input:**
```json
{
  "name": "Müller",
  "score": 100
}
```

**Expected canonical JSON (JCS):**
```
{"name":"Müller","score":100}
```

Note: JCS RFC 8785 §3.4 **requires** non-ASCII characters to be serialized as
literal UTF-8 bytes, not as `\uXXXX` escapes. The string `Müller` becomes `Müller`
(2-byte UTF-8) in the canonical form. `\u00fc` escaping (Python's `ensure_ascii=True`)
is **not** JCS-compliant for non-ASCII strings.

## Float Handling

Floats **should not** appear in manifest or step data that requires canonical hashing.
EPI schemas use `int`, `str`, `UUID`, `datetime`, `dict`, and `list` types exclusively
for fields that participate in canonical hashing.

If a float must be included, the producer is responsible for ensuring consistent
serialization across implementations. JSON does not specify float precision, and
different JSON libraries may serialize `1.0` differently from `1.00` or `1e0`.

## Implementation Reference

The canonical reference implementation is at `epi_core/serialize.py` in the
EPI Recorder repository:

- `get_canonical_hash(model, exclude_fields, format)` — main entry point
- `_get_json_canonical_hash(data)` — JCS RFC 8785 canonicalization
- `_get_cbor_canonical_hash(data)` — legacy CBOR canonicalization (v1.0 only)
- `normalize_value(value)` — datetime/UUID normalization

Independent implementations must reproduce the algorithm described above, not
the specific Python code. The conformance test vectors are the source of truth
for cross-implementation compatibility.

## Timestamp Encoding Note

EPI canonical hashes encode `datetime` values as **ISO 8601 strings**
(`YYYY-MM-DDTHH:MM:SSZ`). This is an EPI-specific choice.

Other portable evidence formats (e.g., AlgoVoi's compliance-receipt-v1) encode
timestamps as **epoch millisecond integers** (`timestamp_ms`). That choice is
**not** required by JCS RFC 8785 — it is a format-level convention. The two
preimages hash to different digests and will not cross-validate. EPI consumers
must normalize timestamps to ISO 8601 strings before hashing.

See `EPI-ALGOVOI-INTEROP.md` for the full interoperability boundary.

## Version History

| Version | Date | Change |
|---------|------|--------|
| 2.0 | 2025-06-08 | Initial specification. Incorrectly used `ensure_ascii=True`. Documented `source_type` exclusion. Added conformance test vectors. |
| 2.2 | 2026-06-11 | Fixed `ensure_ascii=True` → `False` to comply with JCS RFC 8785 §3.4 (literal UTF-8 for non-ASCII). Also aligns with AlgoVoi's cross-validated conformance corpus. Updated all conformance vectors and tests. |
