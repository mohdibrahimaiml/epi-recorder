# Evidence alignment proof

**Purpose:** Same `.epi` bytes → same integrity/signature answer across tools.  
This is what makes EPI an *evidence layer*, not a pretty HTML page.

## Golden file

| Item | Value |
|------|--------|
| Path | [`docs/assets/sample-hello.epi`](assets/sample-hello.epi) |
| Also | [`readme-demo.epi`](assets/readme-demo.epi), [`sample-refund-ord9001.epi`](assets/sample-refund-ord9001.epi) |
| Catalog | [`SAMPLES.md`](assets/SAMPLES.md) |

## Expected CLI results (unpinned sealer)

```bash
epi verify docs/assets/sample-hello.epi --json
```

| Fact | Expected |
|------|----------|
| `facts.integrity_ok` | `true` |
| `facts.signature_valid` | `true` |
| `identity.status` | `UNKNOWN` |
| `decision.status` | `WARN` |

Optional pin (then identity becomes known / decision can PASS under standard policy):

```bash
epi keys trust docs/assets/sample-hello.epi --name sample-hello
epi verify docs/assets/sample-hello.epi
```

## Hosted verify (browser)

1. Open https://epilabs.org/verify  
2. Upload `docs/assets/sample-hello.epi`  
3. Expect **integrity + signature OK** (same math as CLI).  
4. Identity may still show unknown — that is correct without a trust list in the browser.

Engine: `website/js/epi-verify-core.js` (canonical; see [`SITE.md`](SITE.md)).  
Smoke (repo maintainers): live `https://epilabs.org/js/epi-verify-core.js` byte-matches `website/js/epi-verify-core.js`.

## Tamper demo (&lt; 5 minutes)

```bash
# From repo root (Windows PowerShell or any shell with Python)
python scripts/check_verify_alignment.py
```

What the script does:

1. Verifies the golden file → must show integrity + signature OK, decision WARN (unknown identity).  
2. Flips one byte in a temp copy → must **not** PASS as clean (typically envelope hash mismatch / FAIL).  
3. Exits non-zero if expectations break.

Manual equivalent:

```bash
cp docs/assets/sample-hello.epi /tmp/tampered.epi
# flip any byte in the file
epi verify /tmp/tampered.epi
# Expect FAIL — do not trust the file
```

Recorded once (illustrative):

| File | Decision | Integrity | Signature |
|------|----------|-----------|-----------|
| golden `sample-hello.epi` | WARN | true | true |
| one-byte flip | FAIL | false / structural fail | n/a or fail |

## Authority (simple)

| Check | Role |
|-------|------|
| Open sealed `viewer.html` | Convenience seal check in the browser |
| `epi verify` | Local full check (teams / CI) |
| https://epilabs.org/verify | Second machine, no install |
| Independent re-verify of bytes | Audit / dispute |

A compromised browser can fake UI. **Re-run `epi verify` on the original bytes for audit.**

## Automation

```bash
python scripts/check_verify_alignment.py
```

Wire into CI when convenient (release-gate or a small workflow). Do not skip when changing verify or container code.
