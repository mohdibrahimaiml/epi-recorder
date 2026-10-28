# Sector demo `.epi` artifacts

Shipped sector demos. The checked-in artifacts were sealed with **mocked LLM
responses** (the script's deterministic fallback when `GROQ_API_KEY` is unset),
so they build reproducibly without external API calls. The seal proves the file
was not altered after sealing, not that a live model produced the text. To
regenerate with a live model, set `GROQ_API_KEY`:

```bash
export GROQ_API_KEY=…   # never commit keys
python scripts/generate_sector_demo_epis.py
```

## Flagship (DM / sales)

| Asset | Path |
|-------|------|
| Sealed case | `docs/assets/demo-finance-loan-underwriter.epi` |

Open it with `epi view docs/assets/demo-finance-loan-underwriter.epi`, or drop the
file on <https://epilabs.org/verify> — no install needed.

All eight checked-in seals use the same demo signing key. Its fingerprint is
`59e3 6c77 0bd9 8524`; confirm it here (this repository) rather than copying it
from the file you are checking.

```bash
# Fresh machine with no pins: WARN · identity NOT_PINNED.
# If you have already pinned other keys: FAIL · NOT A KEY YOU TRUST.
epi verify docs/assets/demo-finance-loan-underwriter.epi
# Pin the demo signer after confirming the fingerprint above:
epi keys trust docs/assets/demo-finance-loan-underwriter.epi \
  --name epi-demo --fingerprint "59e3 6c77 0bd9 8524"
# Claim / insurer path — always use strict (FAIL if sealer not org-pinned):
epi verify docs/assets/demo-finance-loan-underwriter.epi --policy strict
```

## All sector demos

| File | Domain |
|------|--------|
| `demo-finance-loan-underwriter.epi` | Finance — loan underwriting |
| `demo-healthcare-clinical-triage.epi` | Healthcare — clinical triage (not medical advice) |
| `demo-insurance-claim-adjudication.epi` | Insurance — claim adjudication |
| `demo-legal-contract-review.epi` | Legal — MSA review (not legal advice) |
| `demo-banking-aml.epi` | Banking — AML review |
| `demo-hiring-screening.epi` | Hiring — candidate screening |
| `demo-insurance-underwriting.epi` | Insurance — property underwriting |
| `demo-lending-affordability.epi` | Lending — affordability check |

Each of the eight is a single self-contained `.epi`: the `.epi` file is the
evidence and the viewer. Open it with `epi view <file>`, or drop it on
<https://epilabs.org/verify>. There are no separate HTML copies to keep in sync.

Leak-scan every seal: no `gsk_` / `GROQ_API_KEY` in the archive.
