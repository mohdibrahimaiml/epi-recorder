# EPI Conformance Test Vectors

These vectors are normative for the current specification line (4.6.2). The tv-001 example names **4.6.3 (release pending)**; its canonicalization is unchanged from 4.6.2. `test-vectors.json` is the machine-readable copy.

## tv-001: Manifest canonical hash (JCS/RFC 8785, excluding signature only)

```json
{
  "id": "tv-001",
  "desc": "Manifest canonical hash (JCS/RFC 8785, excluding signature only)",
  "input": {
    "workflow_id": "00000000-0000-4000-8000-000000000001",
    "spec_version": "4.6.3",
    "created_at": "2026-10-23T00:00:00Z",
    "goal": "test-vector"
  },
  "canonicalization": "jcs",
  "exclude": [
    "signature"
  ],
  "hash": "00e931af4939c8a6c3a1214cbf626511a784398b7759f615463286a59cf665ec"
}
```

## tv-002: File hash verification — SHA-256 over raw bytes matches file_manifest entry

```json
{
  "id": "tv-002",
  "desc": "File hash verification — SHA-256 over raw bytes matches file_manifest entry",
  "manifest_files": {
    "analysis.json": "60d2887b82260d53c82ba4a7092db6c70a146bad5d4019c01b1e39b7cdcf2f34",
    "environment.json": "4d4edb57ccd35612cf66dbae0c537b96e6d3c21ca32aa622f001adbb84021036",
    "policy.json": "4f5d022abc23e8896409622b98e5c0fb147dbdc7200380724078c6a851dbc6a6",
    "policy_evaluation.json": "54a1fe24ada8960a3ae6ce86ee80fade4faeb44aa557a5a2271fe5336c5eb173",
    "steps.jsonl": "69af9d0e83f74393107246aa890d438ee6f548154da9296b5b33466a7d935e7e"
  },
  "computed_hashes": {
    "analysis.json": "60d2887b82260d53c82ba4a7092db6c70a146bad5d4019c01b1e39b7cdcf2f34",
    "environment.json": "4d4edb57ccd35612cf66dbae0c537b96e6d3c21ca32aa622f001adbb84021036",
    "policy.json": "4f5d022abc23e8896409622b98e5c0fb147dbdc7200380724078c6a851dbc6a6",
    "policy_evaluation.json": "54a1fe24ada8960a3ae6ce86ee80fade4faeb44aa557a5a2271fe5336c5eb173",
    "steps.jsonl": "69af9d0e83f74393107246aa890d438ee6f548154da9296b5b33466a7d935e7e"
  },
  "all_match": true,
  "note_excluded": "review.json and review_index.json are mutable addendums NOT in file_manifest"
}
```

## tv-003: Container auto-detection (envelope-v2, legacy EPI1, bare ZIP)

```json
{
  "id": "tv-003",
  "desc": "Container auto-detection (envelope-v2, legacy EPI1, bare ZIP)",
  "magic_detection": "Read bytes 0-3. 0x3C 0x21 0x2D 0x2D (<!--) = envelope-v2. 0x45 0x50 0x49 0x31 (EPI1) = legacy EPI1 container; probe the first 64 bytes for PK\\x03\\x04. 0x50 0x4B 0x03 0x04 (PK\\x03\\x04) = bare ZIP (legacy-zip pipeline). Anything else is not a valid .epi file.",
  "header_size": 128,
  "zip_marker": "\n<!-- EPI_ZIP_PAYLOAD_START -->\n"
}
```

## tv-004: MIME type constants

```json
{
  "id": "tv-004",
  "desc": "MIME type constants",
  "envelope_v2_mime": "application/vnd.epi+zip",
  "legacy_zip_mime": "application/vnd.epi+zip",
  "scitt_payload_mime": "application/vnd.epi.manifest+hash",
  "mimetype_file": "application/vnd.epi+zip"
}
```

## tv-005: Ed25519 signature format: ed25519:<key_id>:<sig_hex>

```json
{
  "id": "tv-005",
  "desc": "Ed25519 signature format: ed25519:<key_id>:<sig_hex>",
  "algorithm": "ed25519",
  "key_id": "SHA-256(hex_public_key)[:16]",
  "sig_hex_len": 128,
  "sig_raw_len": 64
}
```

## tv-006: Valid enumeration values

```json
{
  "id": "tv-006",
  "desc": "Valid enumeration values",
  "severity": [
    "critical",
    "high",
    "medium",
    "low"
  ],
  "policy_mode": [
    "detect",
    "block",
    "warn"
  ],
  "trust_levels": [
    "HIGH",
    "MEDIUM",
    "LOW",
    "NONE",
    "FAIL",
    "INVALID"
  ],
  "container_formats": [
    "envelope-v2",
    "EPI1",
    "legacy-zip"
  ],
  "analysis_status": [
    "complete",
    "skipped",
    "error"
  ],
  "source_type": [
    "user",
    "tool",
    "reasoning",
    "system"
  ]
}
```

## tv-007: Canonical hash algorithm (normative, current spec versions)

```json
{
  "id": "tv-007",
  "desc": "Canonical hash algorithm (normative, current spec versions)",
  "manifest_hash": {
    "canonicalization": "JCS (RFC 8785)",
    "exclude": [
      "signature"
    ],
    "omit_when_null": [
      "content_truncated",
      "policy_load_status",
      "producer_version"
    ],
    "datetime_fmt": "YYYY-MM-DDTHH:MM:SSZ",
    "uuid_fmt": "lowercase canonical",
    "hash": "SHA-256"
  },
  "step_hash": {
    "canonicalization": "JCS (RFC 8785)",
    "exclude": [
      "source_type",
      "verification_class"
    ],
    "omit_when_null": [
      "content_truncated",
      "policy_load_status",
      "producer_version"
    ],
    "datetime_fmt": "YYYY-MM-DDTHH:MM:SSZ",
    "uuid_fmt": "lowercase canonical",
    "hash": "SHA-256",
    "step_0_prev_hash": "CHAIN_START or null"
  },
  "legacy_dispatch": "Verifiers select canonicalization from the manifest spec_version: 1.x = CBOR; 2.x through pre-4.4.1 = legacy JSON (sort_keys, compact, ensure_ascii=False); 4.4.1+ = JCS. Current sealers always use JCS for steps."
}
```

Legacy artifacts are still verified: the canonicalization is selected from the manifest `spec_version` (see tv-007 `legacy_dispatch`).
