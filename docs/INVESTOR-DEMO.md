# EPI 3-Minute Live Investor Demo

This is the fastest reliable live screenshare demo for EPI `v2.8.3`.

The one takeaway to drive home is:

**EPI shows where the AI went wrong, proves it with portable evidence, and makes tampering obvious.**

---

## Opening Line

Start with this exact sentence:

> EPI doesn't just log AI behavior. It shows where the AI likely went wrong and preserves tamper-evident proof of that run.

Then immediately open the reviewed `.epi` artifact in the viewer. Do not start with code, install steps, or CLI help.

---

## Demo Order

Use this order and do not add extra detours unless asked:

1. Open the reviewed investor artifact
2. Show the trust state, primary fault, why it matters, and human review
3. Scroll briefly to policy, analysis, and the timeline
4. Switch to the tampered artifact
5. Show tamper detection
6. End with the one-line product close

---

## Exact Talk Track

### 0:00-0:20 - Hook

Say:

> EPI doesn't just log AI behavior. It shows where the AI likely went wrong and preserves tamper-evident proof of that run.

### 0:20-1:10 - Primary Fault

Open the reviewed finance artifact and focus only on:

- trust state
- primary fault
- why it matters
- human review

Say:

> This AI-assisted financial workflow violated policy.
>
> EPI identifies the primary fault, links it to the rule, and preserves the human review outcome.

### 1:10-1:50 - Evidence Drill-Down

Scroll just enough to show:

- embedded policy
- embedded analysis
- execution timeline

Say:

> This file contains the trace, the rules active at run time, the analyzer's conclusion, and the review.
>
> It is a portable case file, not just a dashboard entry.

### 1:50-2:25 - Tamper Proof

Switch to the tampered artifact and show:

- `epi verify` result or viewer trust state
- tampered status
- integrity failure

Say:

> If someone changes the evidence after the run, EPI makes that visible immediately.
>
> That is the difference between logs and sealed evidence.

### 2:25-3:00 - Product Close

Say:

> For high-risk AI systems, EPI gives teams three things: what happened, what went wrong, and whether the evidence is still trustworthy.

Then stop.

---

## Assets To Use

Primary assets:

- reviewed investor `.epi` artifact for the main story
- tampered investor `.epi` artifact for the trust moment

Backup asset:

- the Colab demo notebook using PyPI `2.8.3`

The notebook is a backup only. Do not lead with it in a live investor call.

---

## What To Avoid

Do not start with:

- CLI help
- package install
- policy JSON authoring
- long timeline scrolling
- framework integration code

Do not say:

- fully enterprise-ready
- works for every AI workflow automatically
- employees just use it today with zero setup
- this can never fail

---

## If Asked

### If asked about policy UX

Say:

> Today, policy is machine-readable and admin-defined.
>
> The product direction is profile-driven setup so normal employees don't deal with JSON.

### If asked why not logs

Say:

- logs are fragmented
- rules are usually external to the log stream
- logs do not preserve a sealed reviewable artifact
- tampering is much harder to prove with logs alone

---

## Pre-Demo Checklist

Run these checks before every live session:

1. Open the reviewed artifact and confirm the viewer shows the `v2.8.3` viewer
2. Confirm the primary fault renders at the top
3. Confirm the review section is present
4. Run verification on the tampered artifact and confirm it shows tampered
5. Confirm browser opening works on the intended machine
6. Keep the Colab notebook ready only as fallback

---

## Positioning

For investors, describe EPI like this:

**EPI records real AI execution, identifies where the run violated rules or behaved unsafely, and seals that evidence into a portable artifact whose trust can be verified later.**
