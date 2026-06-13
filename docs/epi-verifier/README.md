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
JCS RFC 8785 canonical JSON serialization.

## Conformance

Cross-validated against AlgoVoi's JCS conformance corpus across 3 independent RFC 8785 implementations. All 8 EPI golden vectors satisfy: SHA-256(canonical_json) = expected_hash.

## License

Apache 2.0. Contains bundled noble-ed25519 (MIT) for zero-dependency operation.
