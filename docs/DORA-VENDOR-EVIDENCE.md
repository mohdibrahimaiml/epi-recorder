# DORA evidence for AI vendors serving EU banks

**Product version:** 4.10.0. Related: [WITNESS.md](./WITNESS.md),
[RELEASES.md](./RELEASES.md), [HUMAN-APPROVAL.md](./HUMAN-APPROVAL.md),
[OVERSIGHT.md](./OVERSIGHT.md), [KNOWN_LIMITATIONS.md](./KNOWN_LIMITATIONS.md).

> **Not legal advice and not a compliance claim.** DORA obligations fall on
> the financial entity (the bank) and, for designated critical providers, on
> the provider. EPI does not make anyone "DORA compliant". This page shows
> which pieces of evidence an AI vendor can hand a bank so that the bank's
> own DORA work is easier to do and easier to check. Article references are
> to Regulation (EU) 2022/2554 (DORA), applicable since 17 January 2025.
> Check the current text and the related technical standards with counsel
> before relying on any mapping here.

---

## Who this is for

You sell an AI service (credit decisioning, KYC/KYB review, fraud triage,
claims handling, AML alert review) to a bank, insurer or other financial
entity in the EU.

Under DORA you are an **ICT third-party service provider**. If your service
supports one of the customer's **critical or important functions** (credit
decisioning usually does), the customer must put specific terms in your
contract (Art. 30(3)) and keep monitoring you under their ICT third-party
risk framework (Art. 28).

In practice that means their third-party risk team will ask you, in some
form:

1. What exactly does your system do with our data, and can we check it?
2. When you change the system, how do we find out?
3. Can our auditors, or our supervisor, inspect what happened without
   depending on you?
4. If something goes wrong, what records will you give us, and can we trust
   them?
5. If we leave you, or you go out of business, what do we keep?

This guide answers each question with evidence the bank can verify itself.

---

## The core idea: evidence the bank can check without trusting you

Most vendors answer the questions above with access to their dashboard and a
SOC 2 report. That leaves the bank relying on the vendor's own systems to
show what the vendor did.

EPI produces evidence that works the other way round:

| Property | What it means for the bank | How |
|---|---|---|
| **Portable** | Each decision is a file the bank keeps. | Signed `.epi` Decision Records |
| **Signed** | The bank checks integrity offline, without calling you. | Ed25519 over a canonical manifest; open-source verifier |
| **Witnessed** | The bank holds its own receipt of every seal, on its own system, on its own clock. | Customer witness ([WITNESS.md](./WITNESS.md)) |
| **Gap-evident** | A record you didn't report shows up as a missing number. | Seal sequence numbers, heartbeats, `epi witness audit` |
| **Release-bound** | Each decision names the approved version of your logic that made it. | Release records ([RELEASES.md](./RELEASES.md)) |
| **Pre-action approval** | Where a person must approve an action first, the bank can verify they did, before it ran. | Signed pre-action approvals ([HUMAN-APPROVAL.md](./HUMAN-APPROVAL.md)) |

---

## Mapping to DORA

Each row names the DORA provision, what the bank needs from you, and the
EPI evidence that supports it. "Supports" means it gives the bank something
to check, not that it satisfies the provision.

### Contractual provisions for all ICT services (Art. 30(2))

| DORA | What the bank needs | EPI evidence |
|---|---|---|
| **30(2)(a)** Clear description of the functions and services, including subcontracting | To know what your system does and which subcontractors (including model providers) take part | Release records pin the policy, prompts, **model identifiers** and tools for each version. `UNDECLARED` in `epi verify` flags a model or component that ran but wasn't in the approved release, for example a switch to a different model provider. |
| **30(2)(b)** Locations where data is processed | Where processing happens | Not covered by EPI. State it in the contract. |
| **30(2)(c)** Availability, authenticity, **integrity** and confidentiality of data | Assurance that decision data wasn't altered | Signed records verified offline; customer witness detects re-sealed or withheld records (`DIFFERENT VERSION`, `MISSING #N`, `FORK`). |
| **30(2)(d)** Access, recovery and return of data, in an easily accessible format, on termination or insolvency | Evidence that stays usable after the relationship ends | `.epi` is a self-contained file with an open format and an open-source verifier. The bank's copies keep verifying after your service, your servers or your company are gone. |
| **30(2)(f)** Assistance in ICT incidents | Records to reconstruct what happened | Decision Records with full step history; `epi oversight report` for the incident period; the witness log shows which records were reported when. |
| **30(2)(g)** Cooperation with competent authorities | Evidence the supervisor can inspect | The same files and verifier, handed over directly. No vendor login needed. |

### Additional provisions for critical or important functions (Art. 30(3))

| DORA | What the bank needs | EPI evidence |
|---|---|---|
| **30(3)(a)** Service levels with precise quantitative and qualitative targets | Measurable performance | Decision Records carry outcomes, model, timing and release; `epi oversight report` summarises a period. EPI does not measure availability or define your SLA. |
| **30(3)(b)** Notice periods and reporting obligations, including notification of developments that may materially affect the service | To learn about changes **before** they affect decisions | Every new release is sealed, approved by named people and reported to the bank's witness as `epi.release` when it is created. `APPROVED AFTER USE` and `RELEASE SEALED AFTER DECISION` show changes that reached production first. |
| **30(3)(f)** Unrestricted rights of access, inspection and audit by the bank, an appointed third party and the competent authority | Auditors who can check evidence independently | Any auditor verifies the files offline with the open-source verifier, using the bank's own witness log. The vendor can't edit the bank's copies. |
| **30(3)(g)** Exit strategies | Continuity of evidence after exit | Same as 30(2)(d): portable, self-verifying files in an open format. |
| **30(3)(c), (d), (e)** Business contingency plans, ICT security measures, participation in threat-led penetration testing | Your resilience and security programme | Not covered by EPI. |

### ICT third-party risk management (Art. 28) and incidents (Art. 17–19)

| DORA | What the bank needs | EPI evidence |
|---|---|---|
| **Art. 28(1)–(2)** Managing ICT third-party risk as part of the ICT risk framework | Ongoing monitoring of you, not a one-off review | Periodic `epi witness audit` and `epi oversight report` on the bank's own log: gaps, forks, burned numbers, unreported cases. |
| **Art. 28(3)** Register of information on all ICT contractual arrangements | The register itself | Not covered by EPI. |
| **Art. 17–19** ICT incident management, classification and reporting (obligations on the bank) | Facts about affected decisions, quickly | Decision Records for the affected period; gaps and heartbeats show whether records are missing; release records show which version was live. |

---

## What the bank's reviewer runs

The bank needs no account with you and no network access to your systems.

**1. Receive your seal reports on their own infrastructure** (once):

```bash
EPI_WITNESS_SECRET=SHARED_SECRET epi witness serve --port 8099 --out received.jsonl
```

**2. Check that nothing was withheld:**

```bash
epi witness audit received.jsonl
```

Exit code 1 means a missing, forked or broken record, a tail gap against
your heartbeat, or a reused approval. Burned sequence numbers are listed
separately and are worth asking you about if they grow.

**3. Check a decision against the release that should have made it:**

```bash
epi verify decision.epi --witness-log received.jsonl --release-dir releases/ --require-release --min-approvals 2
```

**4. Where policy requires a person to approve an action first:**

```bash
epi verify decision.epi --witness-log received.jsonl --require-pre-action-approval
```

**5. Summarise a period for the risk committee or the supervisor:**

```bash
epi oversight report --cases ./received --log received.jsonl --since 2026-07-01 --until 2026-09-30 --expect cases.csv --out oversight-2026-Q3.html
```

---

## Draft evidence schedule for the contract

A starting point you can propose as a schedule to the Art. 30 agreement.
**Have counsel on both sides review it.** Numbers in brackets are examples.

> **Schedule [X]: Decision evidence**
>
> 1. **Records.** The Provider shall produce a signed EPI Decision Record for
>    every decision made by the Service for the Customer, and deliver it to
>    the Customer [within 24 hours / on request / via the agreed storage].
> 2. **Witness.** At the moment each record is sealed, the Provider shall send
>    a hash-only seal report to a witness endpoint controlled by the
>    Customer. The Provider shall send a signed heartbeat at least
>    [hourly].
> 3. **Gaps.** The Provider shall explain in writing, within [5] business
>    days, any missing, forked or burned sequence number identified by the
>    Customer's audit of its witness log.
> 4. **Releases.** Before any change to the decision logic (policy, prompts,
>    models, tools or code) is used for the Customer's decisions, the
>    Provider shall seal a release record, report it to the Customer's
>    witness, and obtain approval from at least [2] Provider approvers whose
>    keys are pinned by the Customer. [For material changes: and from [1]
>    Customer approver.]
> 5. **Pre-action approval.** For the actions listed in Annex [Y], the
>    Service shall not execute the action until a pinned approver has signed
>    an approval of that exact action, and the execution shall be reported to
>    the Customer's witness.
> 6. **Keys.** Approver keys shall not be stored on hosts that run the
>    Service.
> 7. **Verification.** The Customer, its auditors and competent authorities
>    may verify any record with the open-source EPI verifier without the
>    Provider's involvement.
> 8. **Exit.** On termination, the Provider shall deliver all Decision
>    Records and release records not previously delivered. Records remain
>    verifiable after termination without any Provider system.

---

## What this does not cover

Be clear about these with the bank. Overclaiming costs more trust than it
wins.

- **Not a compliance determination.** EPI provides evidence. Whether the
  bank's arrangement with you meets DORA is the bank's and its
  supervisor's call.
- **Decisions that were never recorded are invisible.** Sequence numbers
  reveal records that were sealed and withheld, not decisions that never
  went through the recorder. Route decisions through a chokepoint (the EPI
  gateway or the SDK on the decision path) to narrow this.
- **Tail gaps need heartbeats.** Without regular heartbeats, the most recent
  records can be withheld unnoticed.
- **Release checks only cover what EPI observes.** Code that runs outside
  the instrumented path can differ from the release without detection.
- **Times are only independent when they come from the bank's witness or a
  timestamp authority.** Otherwise `epi verify` labels them as the vendor's
  clock.
- **Not covered at all:** the register of information, data location,
  business continuity and disaster recovery, ICT security measures,
  penetration testing, concentration risk, and the oversight framework for
  designated critical ICT third-party providers.
