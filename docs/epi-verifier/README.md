# EPI Independent Verifier

**JavaScript helper in this folder — not the `epi` CLI and not a complete verifier.** Product version 4.6.2. Canonical check: `epi verify` ([../VERIFICATION_CONTRACT.md](../VERIFICATION_CONTRACT.md)).

Zero-dependency **partial** verification for [EPI](https://epilabs.org) `.epi` files. Runs in a browser or Node. File-integrity hashing needs JSZip. Step-chain verification is **not implemented** (marked planned in the table below).

## Usage

### Browser
```html
<script type="module">
  import { verifyEpi } from './verify.js';
  const file = document.querySelector('input[type=file]').files[0];
  const bytes = await file.arrayBuffer();
  const report = await verifyEpi(bytes);
  console.log(report);
</script>
```

### Node.js
```js
import { verifyEpi } from './verify.js';
import { readFileSync } from 'fs';
const bytes = readFileSync('evidence.epi');
const report = await verifyEpi(bytes);
```

### With JSZip (recommended for full verification)
```bash
npm install jszip
```

## Verification Checks (`verifyEpi`, end-to-end)

| Check | Without JSZip | With JSZip |
|-------|--------------|-----------|
| Envelope location (polyglot marker / legacy ZIP) | Yes | Yes |
| Manifest parsing | No (ZIP parsing needs JSZip) | Yes |
| Signature verification | No (needs the manifest) — standalone `verifyManifestSignature(manifestObj)` works on a manifest you supply | Yes — verified against real 4.6.2 and legacy-zip seals |
| File integrity | No | Yes |
| Step-chain verification | No | Planned |

Notes: v1.x CBOR-sealed manifests are refused with directions, not a tamper
verdict (no CBOR canonicalizer here — use `epi verify`). Step-chain checking
is not implemented. Canonical check is always `epi verify`
([VERIFICATION_CONTRACT](../VERIFICATION_CONTRACT.md)).

## API

### verifyEpi(bytes)
Returns `{ integrity, signature, trust_level, files_checked, mismatches }`

### verifyManifestSignature(manifest)
Returns `{ valid, reason }`

### canonicalJson(obj)
JCS-compatible (RFC 8785-style) canonical JSON serialization — sorted keys, compact
separators, literal UTF-8. Same algorithm as `epi_core/serialize.py` (not a claim of
full RFC 8785 library conformance).

## Conformance

EPI golden vectors require: SHA-256(canonical_json) = expected_hash under the EPI
normalization rules. Cross-checked against AlgoVoi interop fixtures where shared.
Divergence cases live with the vectors: `tests/compatibility/test_canonical_hash.py`
and `tests/compatibility/golden/canonical_hash_vectors.json`.

## License

Apache 2.0. Contains bundled noble-ed25519 (MIT) for zero-dependency operation.
