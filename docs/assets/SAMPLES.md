# Public `.epi` samples

**Product version:** 4.6.2. These files were sealed on an older tree (2026-07-23). Re-check with the CLI you actually installed; WARN on unpinned identity is expected until you `epi keys trust`.

| File | What it is | Expected `epi verify` |
|------|------------|------------------------|
| `readme-demo.epi` | Refund decision sample (README) | Signature VALID, identity UNKNOWN → **WARN · UNVERIFIED IDENTITY** until you pin |
| `sample-refund-ord9001.epi` | Same case, stable name | same |
| `sample-hello.epi` | Tiny sealed run | same |

## Try

```bash
# Dev skim — WARN if sealer not org-pinned (not claim-ready)
epi verify docs/assets/sample-hello.epi -v
# Insurers / claim acceptance — FAIL until pin:
epi verify docs/assets/sample-hello.epi --policy strict
epi view docs/assets/sample-hello.epi --extract /tmp/epi-hello
epi keys trust docs/assets/sample-hello.epi --name sample-sealer
epi verify docs/assets/sample-hello.epi --policy strict
```

Hosted: https://epilabs.org/verify (upload the same file).

Do not use old `epi-demo` samples from 2025 as current product truth.
