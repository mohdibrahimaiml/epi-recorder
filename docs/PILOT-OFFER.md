# The witnessed pilot — one page

**Status:** decided 2026-10-30, revised 2026-10-31 to the witnessed pilot. **Revisit:** 2027-01-27 if unproven. **Owner:** founder.

---

## Who this is for

**AI vendors whose agents make decisions for insurers** — underwriting, pricing, claims triage, claims denial.

Not banks. The April 2026 US bank model-risk guidance excludes generative and agentic AI, so banks are a slow, low-urgency buyer. Insurance has a written duty, per decision, already in force.

## The moment we sell into

The insurer's compliance or third-party-risk team asks the vendor:

> "Our regulator expects us to explain the specific data behind this decision, and our contract says you cooperate with their inquiries. Show us the record for this application."

That question is not hypothetical. New York's Insurance Circular Letter No. 7 (11 July 2024) expects insurers to keep documentation of every AI system they use, including vendor-supplied ones, and to make it available to the Department on request (§29); to include **audit rights and cooperation duties** in vendor contracts (§37); and, for an adverse decision, to disclose "details about all information upon which the insurer based any declination, limitation, rate differential" **including the source** (§39). §40 removes the escape hatch: an insurer "may not rely on the proprietary nature of a third-party vendor's algorithmic processes to justify the lack of specificity."

**That last paragraph is the business.** The vendor's secrecy is no longer a defence. Someone has to produce a specific, source-attributed record — and the vendor is the only party that has it.

## What the pilot is

**One workflow, thirty days, fixed price.** We instrument one consequential decision the vendor already makes for an insurer, and every case that flows through it produces a decision file. The insurer keeps its own copy of the proof.

The difference from a signed log: **a signature protects the file, and the vendor holds the key. A witness protects the customer** — the customer's own record of what they were given, so a re-sealed or re-written file is caught even when the vendor's key still signs it.

## What the vendor gets

| Deliverable | What it is |
|---|---|
| A sealed `.epi` per case | What the agent saw, what it decided and why, the rules and data it relied on, the model that answered, and who approved it — hash-chained and signed |
| A readable Decision Record per case | `epi export-summary`: one page a customer, regulator or affected person can read, with the verify instructions on it |
| The customer's witness log | Every case the vendor reported, held by the insurer: case id, goal, and a content digest, appended as each file is sealed |
| The forgery check | `epi verify case.epi --witness-log received.jsonl` — passes on the real file, fails on a re-sealed one that the vendor's key still signs |
| The witness report | `epi witness report` — what the customer's log knows, by case: witnessed, unwitnessed, missing, mismatch |

## What it proves — and what it does not

**Proves:** the record has not changed since sealing; the signature matches the key that sealed it; the file is the one the vendor reported to the customer at the time. One altered byte fails verification, including the embedded viewer.

**Does not prove:** that the run was captured completely, that the signer is who they claim until the key is pinned out of band, that a decision was correct, or that the insurer has met its regulatory duty. This is evidence input, not a certificate, and every report says so.

## Price

**€4,500 fixed.** One workflow, thirty days, one revision included. Paid at the start; the pilot is the deliverable, not a subscription.

No discount tier and no rush tier: the first engagement is the price, and the price is the thing being tested. If the number is wrong, the calls will say so — not a discount.

## Guarantee

Full refund if the pilot's files fail to verify on the customer's machine using the instructions we supply, or if the witness log does not catch a re-sealed file we produced ourselves.

## The three questions that qualify a buyer

Ask these on every call, before quoting:

1. Has an insurer customer ever asked you for the record behind a specific AI decision?
2. What did you send them?
3. Did it delay anything, or cost you anything?

**Decision rule:** if 3 of the first 10 qualified calls answer "yes" to (1), the pain is real and the price stands. If almost nobody does, stop selling and change the buyer — not the code.

## What we need from them

1. One workflow, and the decision inside it that an insurer would question.
2. The name of the insurer or auditor asking, and what they asked for.
3. Permission to quote them anonymously if the insurer accepts the record.

## What we will not do

- Claim admissibility, compliance, or insurability. No insurer requires or accepts EPI today; what the witness gives them is a record they can check without asking the vendor to log in.
- Sign as their custodian — the declaration is theirs to sign; we supply the facts.
- Accept "we'll decide later" as a deadline. No date, no pilot.

---

## Decision record

- **Buyer:** AI vendors selling agents into insurance. One buyer, one site.
- **Trigger:** a documented regulatory duty, not a guessed "stuck deal".
- **Deliverable:** decision files per case, the customer's witness log, and the report over both. No platform, no seats, no SSO.
- **Price:** €4,500 for one workflow over thirty days.
- **Why insurance and not lending:** the April 2026 US bank model-risk guidance excludes generative and agentic AI; the insurance duty is specific, per-decision, and already in force in New York.
- **Kill-switch:** 2027-01-27 — one paid engagement, or one written acceptance from a counterparty. Neither means the buyer is wrong, not the code.
- **Build rule:** nothing unless a signed pilot asks. The one exception is capture-at-decision (gateway, issue #26), because a substitute cannot replicate it.
