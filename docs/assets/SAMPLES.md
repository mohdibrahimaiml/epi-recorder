# Public `.epi` samples

**Product version:** 4.6.3. These files were sealed on an older tree (2026-07-23). Re-check with the CLI you actually installed. On a fresh trust store the unpinned identity is a **WARN · UNVERIFIED IDENTITY**; if you have already pinned other keys it is a **FAIL · NOT A KEY YOU TRUST**. Both become PASS after you confirm the sender's fingerprint out of band and `epi keys trust` it.

| File | What it is | Expected `epi verify` |
|------|------------|------------------------|
| `readme-demo.epi` | Refund decision sample (README) | Signature VALID, identity UNKNOWN → WARN/FAIL as above until you pin |
| `sample-refund-ord9001.epi` | Same case, stable name | same |
| `sample-hello.epi` | Tiny sealed run | same |

## Try

```bash
# Dev skim — WARN if sealer not org-pinned (not claim-ready)
epi verify docs/assets/sample-hello.epi -v
# Insurers / claim acceptance — FAIL until pin:
epi verify docs/assets/sample-hello.epi --policy strict
epi view docs/assets/sample-hello.epi --extract /tmp/epi-hello
# Pinning from a .epi needs the fingerprint you confirmed with the sender
# (never skip this — the file under review is not a pin by itself):
epi keys trust docs/assets/sample-hello.epi --name sample-sealer --fingerprint "<confirmed fingerprint>"
epi verify docs/assets/sample-hello.epi --policy strict
```

Hosted: https://epilabs.org/verify (upload the same file).

Do not use old `epi-demo` samples from 2025 as current product truth.
