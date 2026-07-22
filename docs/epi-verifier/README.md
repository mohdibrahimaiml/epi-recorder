# EPI Independent Verifier

Zero-dependency verification for [EPI](https://epilabs.org) (.epi) evidence files. Runs in any browser, any JavaScript runtime.

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

## Verification Checks

| Check | Without JSZip | With JSZip |
|-------|--------------|-----------|
| Manifest parsing | Yes | Yes |
| Signature verification | Yes | Yes |
| File integrity | No | Yes |
| Steps chain verification | No | Planned |

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
See `docs/EPI-CANONICAL-HASH.md` for known divergences from full JCS.

## License

Apache 2.0. Contains bundled noble-ed25519 (MIT) for zero-dependency operation.
