---
title: Verifiable, Not Just Immutable
date: November 2026
description: Why "our audit trail is immutable" is a promise, not evidence, and what evidence about AI decisions has to look like when someone else needs to rely on it.
excerpt: "Immutable" tells you what a vendor promises about its own system. "Verifiable" means you can check it without trusting them.
---

# Verifiable, Not Just Immutable

Almost every AI decisioning product now has a page that says something like *"decision history that cannot be tampered with or altered, by anyone."*

It's a reasonable thing to want. But read it as an auditor would and ask one question: **who can check that?**

If the answer is "the vendor's own system says so", what you have is a promise, not evidence. That is fine while the vendor's interests and yours line up. It stops being fine the moment they don't.

## When "immutable" is enough, and when it isn't

Inside one company, a well-run log with access controls and a SOC 2 report is usually enough. The team relying on the log also controls it, or trusts whoever does.

The trouble starts when evidence **crosses a boundary**: one party produces it and a different party, with different interests, has to rely on it.

- An AI vendor tells a bank its model followed the approved policy. The bank's third-party risk team has to rely on the vendor's logs.
- A lender denies an application and the applicant disputes it. The lender's records are now evidence in a dispute against the lender.
- An insurer rejects a claim using an AI agent. An ombudsman asks what the agent saw and why it decided.
- A regulator asks whether the logic that ran last March was the logic that was approved.

In each case, the party holding the records has a reason to prefer one version of events. "Our system says it wasn't changed" asks the other side to trust the very party whose conduct is in question.

## Three things "immutable" doesn't answer

Even an honest, genuinely append-only log leaves three questions open for an outsider.

**1. Was anything left out?**
Immutability protects records that exist. It says nothing about records that were never written, or written and never shared. If a vendor sealed 100 decisions and shows you 97, every one of those 97 can be perfectly intact.

**2. Is this the logic that was approved?**
A record of what was decided isn't a record of *which version of the rules, prompts and models* decided it, or whether that version was approved before it was used.

**3. When did things actually happen?**
Timestamps written by the system under review come from that system's clock. Backdating an approval after a decision has been challenged is the oldest trick in the book.

## What verifiable evidence needs

Evidence is verifiable when a third party can check it **without access to the producer's systems and without trusting the producer**. In practice that takes five properties:

1. **Portable.** The record travels as a file that can be handed to an auditor, a court or a customer. It doesn't live behind someone's login.
2. **Signed.** Integrity is checked with public-key cryptography, offline, by anyone. Not by asking the vendor's API.
3. **Witnessed.** At the moment of sealing, a small hash-only receipt goes to a system **the other party** controls. The producer can't edit that copy afterwards.
4. **Gap-evident.** Records are numbered, so a missing one shows up as a hole, not as silence.
5. **Bound to an approved release.** Each decision points to a signed release of its logic, and the check confirms that what ran matches what was approved, and that the approval came first.

## What this looks like in EPI

[EPI](https://github.com/mohdibrahimaiml/epi-recorder) is an open-core recorder that produces signed `.epi` evidence files. Here is how each property maps to commands you can run today.

### Gaps show up as numbers

Every seal made with a signing key carries a sequence number and a link to the previous seal, inside the signed manifest. The same numbers go to the customer's witness. The customer audits their own log:

```bash
epi witness audit received.jsonl
```

If seal #2 was never reported, the audit says `MISSING #2` and exits with code 1. It also reports **forks** (two different seals claiming the same number), **chain breaks**, and **tail gaps** (fewer seals reported than the vendor's signed heartbeat says exist):

```bash
epi witness heartbeat
```

Numbers the vendor declares as "burned" (a seal that started and never finished) are shown as their own finding. They never quietly count as clean, because "it was burned" is exactly what you'd say about a seal you wanted to hide.

### Decisions are tied to an approved release

A release pins the exact policy file, prompt templates, model identifiers, tool schemas and code commit:

```bash
epi release create --name credit-policy --version 3.2 \
  --policy credit=policies/credit.yaml --prompt system=prompts/system.txt \
  --model anthropic:claude-x --git-commit auto --require-approvals 2 \
  --out releases/credit-policy-3.2.epi
```

Approvers sign it with their own keys (run this once per approver), and each approval is reported to the witness when it happens:

```bash
epi release approve releases/credit-policy-3.2.epi --as alice@bank.com
```

Then anyone can check a decision against it:

```bash
epi verify decision.epi --release-dir releases/ --witness-log received.jsonl --require-release
```

You get one of a small set of plain answers:

- `MATCHES`: the release is approved, was sealed before the decision, and every component EPI observed at runtime matches what was pinned.
- `APPROVED AFTER USE`: the approvals exist but were made after the decision. Retroactive sign-off never looks clean.
- `DRIFT`: something that ran differs from the release, for example a prompt changed mid-run.
- `UNDECLARED`: something ran that the release never mentioned, such as a second model.
- `AMBIGUOUS RELEASE`: two different release files claim the same id, so EPI refuses to pick one.

The verifier sets the bar, not the vendor: `--min-approvals 2` requires two approvals even if the release itself only asked for one.

### Time comes from someone other than the producer

When EPI decides whether a release or approval came *before* a decision, it uses the most independent clock available and tells you which one:

1. an RFC 3161 timestamp from a timestamp authority,
2. the time **the customer's witness** received the report,
3. the seal sequence on the same ledger,
4. the producer's own clock, labelled "not independent".

## What this does not prove

Overclaiming is the fastest way to lose an auditor's trust, so here are the limits.

- **A decision that was never recorded at all is invisible.** Sequence numbers reveal seals that were withheld, not decisions that never went through the recorder. Capture at a chokepoint (such as EPI's gateway) narrows that gap; it doesn't close it.
- **Tail gaps need heartbeats.** A vendor that never sends heartbeats can hide its most recent seals.
- **EPI compares only what it observes.** Code that runs outside the instrumented path can differ from the release without EPI seeing it. The release check reports unobserved components as "not observed", never as a match.
- **A signature proves a record wasn't altered, not that the decision was right.**

## The question to ask

Next time a product page says its audit trail is immutable, ask it the outsider's questions:

- Can I verify a record **without your system** and without trusting you?
- If you withheld one record, **how would I know**?
- Can I prove which **approved version** made this decision, and that it was approved **before** it ran?
- Whose **clock** says when?

If the answers all point back to the vendor, the trail may well be immutable. It just isn't evidence yet.
