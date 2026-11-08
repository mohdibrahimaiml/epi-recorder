# Website copy — Part 2 (homepage + /reviewers)

Exact copy for the agent to place. Keep the site's existing components,
classes and section patterns; only the words below are new. Every claim here
must match docs/WEBSITE.md "Claims the site is allowed to make".
Do not name any competitor anywhere.

---

## A. Hero (website/index.html) — one sentence changes

Replace the sub-headline sentence:

> EPI records what your agent saw, what it decided and why, which model
> answered, and who approved it.

with:

> EPI records what your agent saw, what it decided and why, which approved
> version of your logic made the call, and who signed off before it ran.

Everything else in the hero stays.

---

## B. "Six answers" section → "Seven answers"

Heading: **Seven answers in one Decision Record.**

Replace card 06 and add card 07:

**06 · Approval — Who approved it, and when**
A person's approval, signed with their own key. For risky actions, the
approval is signed *before* the action runs, for that exact action, and your
customer's own log shows it came first. If the agent claims an approval
itself, it is labelled as just that.

**07 · Release — Which approved version decided it**
The exact policy, prompts, model and tools your team approved, pinned in a
signed release. The check says whether what ran **matches** it, or names what
**drifted**.

---

## C. "Your customer keeps a copy" — add one paragraph and one card

After the paragraph that starts "If a record is ever rewritten…", add:

> Every sealed record is also numbered. If one is sealed but never reported,
> your customer's log shows the gap: **MISSING #42**.

Add a fourth story card after "At review — The forgery is caught":

**Any day — A record goes missing**
Seal #42 is never reported. Your customer runs `epi witness audit` on their
own log: *"MISSING #42."*

---

## D. NEW section — place directly after "Your customer keeps a copy"

Eyebrow: **What your customer's reviewer will ask**

Heading: **"Immutable" is a promise. *Verifiable* is a check.**

Intro:
> Any vendor can say its audit trail can't be changed. Your customer's
> reviewer will ask four questions that a promise can't answer. EPI answers
> each one with a check they run themselves, on their own machine, against
> their own log.

Four cards (each with a small terminal block showing the output line):

**1 · Can I check it without you?**
Every record is a signed file. It verifies offline with the open-source
verifier: no account, no login, no call to the vendor.
```
$ epi verify decision.epi --policy strict
```

**2 · If you held one back, would I know?**
Records are numbered and reported to your customer's log when sealed. A
signed heartbeat covers the most recent ones.
```
$ epi witness audit received.jsonl
MISSING #42
```

**3 · Was this the version we approved?**
Each decision points to a signed release of your logic. Approvals made
after the decision never count.
```
Release: credit-policy 3.2  MATCHES
Release: credit-policy 3.2  APPROVED AFTER USE
```

**4 · Did a person approve it before it ran?**
The approver signs the exact action on their own machine. Your customer's
log records request, approval and execution in that order. Run first and
approve later, and the check says so.
```
Pre-action: APPROVED BEFORE ACTION (carol@bank.com)
Pre-action: ACTION BEFORE APPROVAL
```

Below the cards, one line + link:
> Read the full argument: [Verifiable, Not Just Immutable →](/blog/posts/verifiable-not-just-immutable.html)

---

## E. "Evidence compared" table — add one column and four rows

Rename the column set to:
**Application Logs · Vendor Observability Dashboard · Vendor "Immutable" Audit Trail · Sealed .epi Artifact**

Intro sentence, replace with:
> The `.epi` column follows from the open file format, its signatures and
> your customer's own log, so anyone can check it without trusting EPI Labs
> or the vendor.

Values for the new column on the EXISTING rows:

| Row | Vendor "Immutable" Audit Trail |
|---|---|
| Independent offline verification | ✗ Inside the vendor's platform |
| A changed record is caught | ⚠ The vendor says so |
| Survives if the vendor disappears | ✗ Lives in the vendor's system |
| Separates Seal vs. Identity vs. Policy | ⚠ Varies |
| Your customer or auditor needs an account | Usually |

NEW rows (all four columns):

| Verification Property | Application Logs | Vendor Observability Dashboard | Vendor "Immutable" Audit Trail | Sealed .epi Artifact |
|---|---|---|---|---|
| A withheld record shows up | ✗ No | ✗ No | ✗ Only the vendor can tell | ✓ Numbered seals, your customer's log |
| Each decision tied to an approved version | ✗ No | ⚠ Sometimes | ⚠ Inside the vendor's platform | ✓ Signed release, checked offline |
| Proves approval came before the action | ✗ No | ✗ No | ⚠ Vendor's own timestamps | ✓ Order on your customer's clock |
| Time from a clock the vendor doesn't control | ✗ No | ✗ No | ✗ No | ✓ Customer witness or timestamp authority |

---

## F. "Honest Trust Boundary" — add two lines

After "The seal proves integrity after sealing, not completeness of capture.":

> Numbered seals reveal records that were sealed and withheld, not decisions
> that were never recorded. Release checks cover only the components EPI
> observes at runtime; anything else is shown as "not observed", never as a
> match.

---

## G. FAQ — add two questions (after "How is this different from LangSmith…")

**How is this different from an "immutable" audit trail in a decision platform?**
An immutable audit trail is kept inside the vendor's platform, so only the
vendor can vouch for it. EPI gives your customer a signed file and their own
log of every seal, so they can check, without you, that nothing was changed,
nothing was held back, the decision came from an approved version, and a
person approved risky actions before they ran.

**Can EPI prove a person approved an action before the AI took it?**
Yes, for actions routed through EPI's approval gate. The approver signs the
exact action, including its arguments, with their own key on their own
machine. The request, the approval and the execution are each reported to
your customer's log, so the order is on their clock, not yours. Actions that
bypass the gate are not covered.

---

## H. /reviewers — new section "What each answer means"

Place after the existing install/verify instructions. Intro:

> From epi-recorder 4.10, three more checks answer the questions a bank or
> insurer asks about an AI vendor. Each runs offline, on your machine,
> against your own witness log.

### 1. Was anything held back?
```
epi witness audit received.jsonl
```
| Answer | Means | Exit |
|---|---|---|
| clean | Every numbered record up to the latest heartbeat was reported. | 0 |
| MISSING #N | Record N was sealed but never reported to you. Ask why. | 1 |
| FORK | Two different records claim the same number. | 1 |
| CHAIN BREAK | A record doesn't link to the one before it. | 1 |
| TAIL GAP | The vendor's heartbeat says more records exist than you received. | 1 |
| APPROVAL REUSED | One approval was used for more than one action. | 1 |
| BURNED #N | The vendor says record N failed while sealing. Not verifiable; worth asking about if it grows. | 0 (1 with `--strict`) |
| NEW CHAIN | A new numbering started for a known key (new machine or reset). | 0 |

### 2. Did an approved version make this decision?
```
epi verify decision.epi --witness-log received.jsonl --release-dir releases/ --require-release --min-approvals 2
```
| Answer | Means |
|---|---|
| MATCHES | Approved release, sealed first, approved before use, and every observed component matches. |
| DRIFT | Something that ran differs from the release. |
| UNDECLARED | Something ran that the release doesn't list (for example a second model). |
| not observed | Declared in the release but EPI couldn't see it at runtime. Never counted as a match. |
| APPROVED AFTER USE | Approvals exist, but were made after this decision. |
| UNAPPROVED RELEASE | Not enough approvals. Your `--min-approvals` wins over the vendor's number. |
| RELEASE SEALED AFTER DECISION | The release was created after the decision. |
| DIRTY RELEASE | Built from uncommitted code. |
| AMBIGUOUS RELEASE | Two release files claim the same id. EPI won't pick one. |

Default: warnings. With `--require-release`: any answer other than MATCHES fails.

### 3. Did a person approve before it ran?
```
epi verify decision.epi --witness-log received.jsonl --require-pre-action-approval
```
| Answer | Means |
|---|---|
| APPROVED BEFORE ACTION | A pinned person signed this exact action, and your log received the approval before the execution. |
| ACTION BEFORE APPROVAL | Your log received the execution first. |
| ACTION WITHOUT APPROVAL | The action needed approval and has none. |
| DENIED BUT EXECUTED | The approver said no; it ran anyway. |
| ARGS CHANGED AFTER APPROVAL | What ran isn't what was approved. |
| APPROVAL EXPIRED / APPROVAL REUSED | Too late, or used twice. |
| SIGNED BY SEALING KEY / UNKNOWN APPROVER | Not independent, or not a key you pinned. |
| AUTO-APPROVED (NOT HUMAN) | A test or dev setting approved it. Never counts as a person. |
| approver key on agent host | Signed, but the key was on the vendor's machine. Not independent. |

Without `--witness-log`, order comes only from the vendor's own record and is
labelled "not independent".

Closing line:
> For an EU bank's DORA review, see [DORA evidence for AI vendors](/dora).
> (Link goes live in Part 3.)
