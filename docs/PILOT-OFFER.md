# The pilot offer — one page

**Status:** decided 2026-10-30. Revisit 2027-01-27 if unproven.
**Owner:** founder. **Scope:** one buyer, one price, one deliverable.

---

## Who this is for

**AI vendors selling agents into insurance or lending**, at the moment a customer's
security, risk or third-party team asks them to prove what an agent did in a
specific run.

Not for: banks buying directly, compliance teams buying tooling, or anyone who has
not been asked the question yet.

## The moment we sell into

> "The deal is agreed. Their security review asked us to prove the agent's decision
> in the CL-77 case. We sent a screenshot and an export. They said that proves
> nothing."

That is the only moment this gets paid for. Everything else is a conversation.

## What they send us

One of:

1. A **step log** — `.jsonl`, `.ndjson`, a JSON array, `.csv` or `.tsv`. Each record
   needs a `kind`; `timestamp` is optional (if missing, import time is used and
   declared inside the artifact).
2. An **AGT bundle** — Microsoft Agent Governance Toolkit directory, bundle, or manifest.
3. An **EPI run** — an existing `.epi` recorded with `epi-recorder`.

Anything else is a schema mapping, quoted separately after we see one sample file.

## What they get, in five business days

| Deliverable | What it is |
|---|---|
| `case.epi` | The sealed record: hash-chained steps, Ed25519 signature, declared capture path and gaps |
| `verification-report.txt` | Integrity, signature, chain and identity status, in plain language |
| `how-to-verify.txt` | The recipient's instructions — CLI, browser, or the standalone verifier |
| `epi-verify` | Single-file verifier build with its published SHA-256 (unsigned) |

## What it proves — and what it does not

**Proves:** the record has not changed since sealing, and the signature matches the
key that sealed it. One altered byte fails verification, including in the embedded
viewer.

**Does not prove:** that the run was captured completely (the artifact declares its
own gaps), that the signer is who they claim until their key is pinned out of band,
or that any regulation is satisfied. This is evidence input, not a certificate.

## Price

**€4,500 fixed.** Five business days from receipt of a usable export.
**72-hour rush: €6,750.** One revision included; further revisions €750 each.

First engagement for a new buyer may be discounted to €2,500 — once, in exchange for
a written statement we can quote if the artifact is accepted.

## Guarantee

If the artifact fails to verify on the recipient's machine using the instructions we
supply, we refund in full. That is the only guarantee we can honestly make, because
it is the only claim we can prove.

## What we need from them

1. One sample record (redacted is fine) and the schema if it is not one of the three above.
2. The name of the party who must be convinced, and what they asked for.
3. Permission to quote them anonymously if the artifact is accepted.

## What we will not do

- Claim admissibility, compliance, or insurability.
- Sign as their custodian. The declaration is theirs to sign; we supply the facts.
- Accept "we'll decide later" as a deadline. No date, no pack.

---

## Decision record

- **Buyer:** AI vendors selling into insurance and lending. One buyer, one site.
- **Deliverable:** the four files above. No platform, no seats, no SSO.
- **Price:** €4,500 anchor; €2,500 first engagement; €6,750 rush.
- **Why this and not compliance:** no regulation requires a `.epi`, and the AI Act
  high-risk logging obligations apply from 2 Dec 2027 / 2 Aug 2028. The forcing
  function is a deal, not a deadline.
- **Kill-switch:** by 2027-01-27, either one paid engagement **or** one written
  acceptance from a counterparty. Neither means the buyer is wrong, not the code.
- **Build rule:** nothing gets built unless a signed pilot asks for it. The single
  exception is capture-at-decision (gateway), because that is the only form of this
  that a substitute cannot replicate.
