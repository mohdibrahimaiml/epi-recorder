# EPI Review Trust Protocol v1

This document defines the v1.1 review trust protocol for `.epi` artifacts.
It is a compatibility upgrade: legacy `review.json` files remain readable, while
new reviews are bound to the exact sealed evidence they reviewed.

## Canonical Review Hashing

Review hashes and signatures use canonical JSON:

- UTF-8 encoding.
- Object keys sorted lexicographically by Unicode code point.
- No insignificant whitespace.
- Strings encoded with standard JSON escaping.
- Booleans encoded as `true` or `false`.
- Null encoded as `null`.
- Integers are allowed.
- Floats are not allowed in signed review payloads.
- Timestamps are RFC3339/ISO-8601 strings and are informational only.

The `review_hash` is the SHA-256 hex digest of the canonical review payload
after removing `review_hash` and `review_signature`.

The `review_signature` signs the bytes represented by `review_hash` with
Ed25519 and is encoded as:

```text
ed25519:<public_key_hex>:<signature_hex>
```

## Artifact Binding

New reviews use `review_version: "1.1.0"` and include an `artifact_binding`
object:

```json
{
  "binding_version": "1.0.0",
  "binding_type": "epi_artifact",
  "workflow_id": "...",
  "manifest_sha256": "...",
  "manifest_signature": "...",
  "manifest_public_key": "...",
  "sealed_evidence_sha256": "...",
  "container_format": "envelope-v2"
}
```

`manifest_sha256` is the SHA-256 of the exact `manifest.json` bytes in the
artifact.

`sealed_evidence_sha256` is a deterministic SHA-256 over the actual files listed
in `manifest.file_manifest`, after any redaction has already occurred. Redacted
artifacts seal the redacted evidence, not unavailable raw secrets.

Review files are intentionally mutable metadata and are not part of sealed
evidence: `review.json`, `review_index.json`, `reviews/*`, `viewer.html`, and
`mimetype` are excluded from the review binding hash.

Verification can only protect files listed in `manifest.file_manifest`. All
execution-semantics evidence that needs protection must be listed there.

## Append-Only Review History

Each new review is stored at:

```text
reviews/<review_id>.json
```

`review.json` remains a compatibility pointer to the latest review.
`review_index.json` is for navigation only and is not a source of trust.

Verification MUST ignore `review_index.json` and recompute review order, hashes,
binding, and chain validity from `reviews/*.json`.

`previous_review_hash` links each v1.1 review to the previous v1.1 review in the
artifact. Legacy v1.0 reviews are readable but are not part of the v1.1 chain.

`epi verify --review --strict` requires at least one valid signed,
artifact-bound v1.1 review. Preserved gateway case-level reviews remain visible
as unbound warnings after a bound review is added; they are not upgraded or
silently treated as artifact-time approvals.

## Identity and Time

`reviewer_identity.verified` is always `false` in v1. This protocol proves
cryptographic authorship by a key, not organizational trust in that key.

`reviewed_at` and entry timestamps are self-declared and informational. They are
not trusted time unless a future trusted timestamp authority is added.
