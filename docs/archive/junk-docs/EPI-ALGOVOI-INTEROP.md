# EPI ↔ AlgoVoi Interoperability Boundary

This document defines the interoperability boundary between EPI Recorder and AlgoVoi's canonicalisation substrate. It is based on empirical cross-testing, not standards assertions.

## References

- **AlgoVoi JCS Conformance Vectors:** https://github.com/chopmob-cloud/algovoi-jcs-conformance-vectors
- **AlgoVoi Canonicalisation Substrate:** https://docs.algovoi.co.uk/canonicalisation-substrate
- **AlgoVoi Authorship and Provenance:** https://docs.algovoi.co.uk/substrate-authorship-provenance
- **RFC 8785 — JSON Canonicalization Scheme (JCS):** https://www.rfc-editor.org/rfc/rfc8785
- **EPI Canonical Hash Specification:** `./EPI-CANONICAL-HASH.md`

---

## Verified Matches (tested corpus only)

EPI Recorder was cross-tested against AlgoVoi's published JCS conformance corpus. After aligning `ensure_ascii` behaviour, the following properties produce **identical canonical bytes** for the tested vectors:

| Property | EPI Behaviour | AlgoVoi Behaviour | Match |
|----------|--------------|-------------------|-------|
| Key ordering | Lexicographic by Unicode code point | Lexicographic by Unicode code point | ✅ (tested) |
| Whitespace | `separators=(',', ':')` — no spaces | Compact form, no whitespace | ✅ (tested) |
| Non-ASCII strings | Literal UTF-8 bytes (`ensure_ascii=False`) | Literal UTF-8 bytes | ✅ (tested) |
| Hash algorithm | SHA-256 over canonical preimage | SHA-256 over canonical preimage | ✅ (tested) |
| Digest encoding | Lowercase hex (64 characters) | Lowercase hex (64 characters) | ✅ (tested) |

**Scope limit:** These matches are verified for the 69-vector AlgoVoi corpus and EPI's own 3-vector golden fixture. They are *not* proven for all possible JSON objects.

### Test Methodology

1. Clone EPI Recorder at commit `5f3ae63` (or later).
2. Run `python -m pytest tests/compatibility/test_canonical_hash.py -v`.
3. The test `test_golden_vectors_match_reference_implementation` asserts EPI hashes against `tests/compatibility/golden/canonical_hash_vectors.json`.
4. Independent verification: apply the same JCS parameters (`sort_keys=True`, `separators=(',', ':')`, `ensure_ascii=False`) and SHA-256 to the normalized dictionaries in the fixture.

---

## Documented Divergences (different preimages → different hashes)

The following differences are **explicit interoperability boundaries**. A manifest hash computed by EPI will not match a frame_id computed by AlgoVoi if these fields differ.

### 1. Timestamps

| Format | EPI | AlgoVoi |
|--------|-----|---------|
| Example | `"2025-06-08T12:00:00Z"` | `1749640800000` |
| Type | ISO 8601 string | Epoch millisecond integer |
| Spec reference | EPI convention | `compliance-receipt-v1`, AlgoVoi docs |

**Impact:** Different bytes in the canonical preimage → different SHA-256 digests. This is the most common silent divergence between the two formats.

**Conversion:** EPI → AlgoVoi requires `datetime.isoformat()` → `int(dt.timestamp() * 1000)`.

### 2. Signature Envelope

| Aspect | EPI | AlgoVoi |
|--------|-----|---------|
| Format | Raw Ed25519 signature as hex string in `signature` field | JWKS/JWS envelope |
| Key distribution | `public_key` hex field in manifest | JWKS key set URL, key rotation supported |
| Verification | Requires `public_key` field + Ed25519 verify | Stateless JWS verify against published JWKS |
| Spec reference | EPI convention | `draft-hopley-x402-compliance-receipt` |

**Impact:** The signature structure, verification path, and key rotation model are completely different. An EPI signature cannot be verified with AlgoVoi tooling, and vice versa, without transformation.

**Conversion:** EPI → AlgoVoi requires wrapping raw Ed25519 bytes in a JWS envelope and publishing the corresponding JWKS.

### 3. Verdict / Claim Enums

| Aspect | EPI | AlgoVoi |
|--------|-----|---------|
| Validation result | Free-text / open schema (`pass`, `fail`, `corrected`, or custom) | Closed enum (`COMPLIANT`, `NON_COMPLIANT`, `PENDING_REVIEW`) |
| Policy status | `Literal["compliant", "violation", "warning"]` | Fixed categorical values |
| Extensibility | Producer-defined values | Machine-comparable across providers |
| Spec reference | EPI `PolicyModel`, `ValidationPayload` | `compliance-receipt-v1` |

**Impact:** Verdicts are not machine-comparable across implementations without a mapping layer.

### 4. Schema Structure

| Field | EPI | AlgoVoi |
|-------|-----|---------|
| Version marker | `spec_version` (e.g., `"v2.0"`) | `receipt_spec_version` (compliance-receipt-v1) |
| Workflow identity | `workflow_id` (UUID v4) | `frame_id` (derived from canonical hash) |
| Step chain | `prev_hash` chain in `StepModel` | Part of settlement attestation |
| Container | `.epi` ZIP envelope | JSON/CBOR receipt document |

---

## Conversion Path (not yet implemented)

EPI artifacts can be transformed into AlgoVoi compliance-receipt-v1 format, but this requires explicit conversion:

```text
EPI Manifest
    ├── Normalize timestamps: ISO 8601 → epoch milliseconds
    ├── Wrap signature: raw Ed25519 → JWS envelope
    ├── Map verdicts: EPI values → closed enum
    └── Emit: compliance-receipt-v1 JSON/CBOR
```

No automatic converter exists today. Building one is deferred until:
- This interop document is reviewed by both parties
- The shared conformance fixture is seeded and agreed
- Remaining divergences (JWKS/JWS, enums) are settled

---

## Shared Conformance Fixture

EPI contributes the following vectors to the shared fixture:

- `ManifestModel_basic` — full manifest with null fields, file manifest, UUID
- `StepModel_source_type_excluded` — step with `source_type` excluded from hash (AUD-AT-01)
- `Unicode_literal_utf8` — non-ASCII string (`Müller`) serialized as literal UTF-8

Location: `tests/compatibility/golden/canonical_hash_vectors.json`

AlgoVoi's corpus: https://github.com/chopmob-cloud/algovoi-jcs-conformance-vectors

---

## Version History

| Date | Change |
|------|--------|
| 2026-06-11 | Initial boundary document. Documented matches (tested corpus), divergences, and conversion path. |

---

## Disclaimer

This document describes observed interoperability behaviour between two independent implementations. It does not claim either implementation is fully "RFC 8785 compliant" — only that the tested canonicalization behaviours produce matching bytes for the shared corpus. Standards compliance is a broader claim requiring audit of number serialization, float handling, and edge cases not covered by the current fixture.
