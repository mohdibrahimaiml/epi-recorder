# EPI Conformance Test Vectors

## tv-001: Manifest canonical hash (JSON, sort_keys=True, compact, SHA-256, excluding signature/governance/trust)

```json
{
  "id": "tv-001",
  "desc": "Manifest canonical hash (JSON, sort_keys=True, compact, SHA-256, excluding signature/governance/trust)",
  "hash": "be5337ff4f336d73a889e6550a4b75b4a953be81900f54b944b848fc322b42f8"
}
```

## tv-002: File hash verification — SHA-256 over raw bytes matches file_manifest entry

```json
{
  "id": "tv-002",
  "desc": "File hash verification \u2014 SHA-256 over raw bytes matches file_manifest entry",
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

## tv-003: Envelope v2 header — read first 4 bytes of file for magic detection

```json
{
  "id": "tv-003",
  "desc": "Envelope v2 header \u2014 read first 4 bytes of file for magic detection",
  "magic_detection": "If bytes 0-3 are 0x3C 0x21 0x2D 0x2D (ASCII <!--), it is envelope-v2. If 0x45 0x50 0x49 0x31 (EPI1), it is legacy-zip.",
  "header_size": 128,
  "zip_marker": "\\n<!-- EPI_ZIP_PAYLOAD_START -->\\n"
}
```

## tv-004: MIME type constants

```json
{
  "id": "tv-004",
  "desc": "MIME type constants",
  "envelope_v2_mime": "application/vnd.epi",
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
    "TAMPERED"
  ],
  "container_formats": [
    "legacy-zip",
    "envelope-v2"
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

## tv-007: Canonical hash algorithm (normative)

```json
{
  "id": "tv-007",
  "desc": "Canonical hash algorithm (normative)",
  "manifest_hash": {
    "exclude": [
      "signature",
      "governance",
      "trust"
    ],
    "datetime_fmt": "YYYY-MM-DDTHH:MM:SSZ",
    "uuid_fmt": "lowercase canonical",
    "json_order": "sort_keys=True, separators=compact, ensure_ascii=True",
    "hash": "SHA-256"
  },
  "step_hash": {
    "exclude": [
      "source_type"
    ],
    "datetime_fmt": "YYYY-MM-DDTHH:MM:SSZ",
    "uuid_fmt": "lowercase canonical",
    "json_order": "sort_keys=True, separators=compact, ensure_ascii=True",
    "hash": "SHA-256",
    "step_0_prev_hash": "null"
  }
}
```

