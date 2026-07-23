# Public `.epi` samples

Sealed with the current epi-recorder tree (2026-07-23T16:58:52.246624+00:00).

| File | What it is | Expected `epi verify` |
|------|------------|------------------------|
| `readme-demo.epi` | Refund decision sample (README) | Signature VALID, identity UNKNOWN (WARN) until you pin the key |
| `sample-refund-ord9001.epi` | Same case, stable name | same |
| `sample-hello.epi` | Tiny sealed run | same |

## Try

```bash
epi verify docs/assets/sample-hello.epi -v
epi view docs/assets/sample-hello.epi --extract /tmp/epi-hello
# open viewer.html — plain “Seal looks OK — signer not recognized yet”
epi keys trust docs/assets/sample-hello.epi --name sample-sealer
epi verify docs/assets/sample-hello.epi
```

Hosted: https://epilabs.org/verify (upload the same file).

Do not use old `epi-demo` samples from 2025 as current product truth.
