# Investor Demo: 3-Minute Live Screenshare

This demo is the fastest practical way to show EPI as AI Evidence Infrastructure, not just another clever AI tool.

The buyer story is simple: an AI-supported workflow made a consequential decision, and a governance, risk, or compliance team now needs the case file.

The one takeaway is:

**EPI gives enterprises a tamper-evident case file for AI decisions that may later face audit, incident review, or model-risk review.**

It demonstrates:

- sealed `.epi` evidence artifact creation
- embedded `policy.json`
- embedded `analysis.json`
- policy-grounded violations
- heuristic observations
- human review workflow via `epi review`
- visible trust break when an artifact is tampered with

## What this demo triggers

The demo intentionally creates:

- `constraint_guard` violation
- `sequence_guard` violation
- `threshold_guard` violation
- `prohibition_guard` violation
- `error_continuation` heuristic observation
- `context_drop` heuristic observation

## Files

- `epi_policy.json` - the active policy used during the run
- `investor_fault_demo.py` - scripted workflow that produces a realistic faulty trace

## Demo Assets

Use these assets in this order:

1. reviewed investor artifact for the main story
2. tampered artifact for the trust moment
3. [`EPI NEXUA VENTURES.ipynb`](../../EPI%20NEXUA%20VENTURES.ipynb) as the branded Colab backup
4. [`colab_demo.ipynb`](../../colab_demo.ipynb) as the technical backup

The branded Nexua notebook is the canonical investor demo. The generic Colab notebook exists as a simpler fallback when you want less presentation framing and more raw product flow.

## How to Produce the Main Artifact

Open a terminal in this directory:

```bash
cd examples/investor_demo
```

### 1. Validate the policy

```bash
epi policy validate
```

Expected:

- EPI confirms the policy is valid
- all four rule types are listed

### 2. Produce the evidence artifact

```bash
python investor_fault_demo.py
```

Expected:

- `investor_fault_demo.epi` is created
- the artifact is sealed with the active policy and analysis

If you want the same flow through the CLI:

```bash
epi run investor_fault_demo.py
```

For the investor walkthrough, the direct Python run is usually easier because the script writes a stable file name.

### 3. Open the artifact

```bash
epi view investor_fault_demo.epi
```

Expected viewer story:

- the artifact opens like a document
- the viewer shows verification state
- the viewer shows a primary fault at the top
- the viewer shows why it matters
- the viewer shows human review if appended

### 4. Review the faults

```bash
epi review investor_fault_demo.epi
```

Expected:

- a reviewer can confirm or dismiss the findings
- the decision is appended as `review.json`
- the original evidence remains intact

### 5. Show the stored review

```bash
epi review show investor_fault_demo.epi
```

## Recommended Live Flow

For a live investor call:

1. Open the reviewed artifact first, not the code
2. Focus on trust state, primary fault, why it matters, and human review
3. Scroll briefly to policy, analysis, and the timeline
4. Switch to the tampered artifact and show trust failure
5. End with the product close, then stop

Use this exact close:

> When AI affects money, access, safety, or compliance, EPI is the case file teams bring to audit, incident review, and AI governance.

## What Not to Lead With

Avoid starting with:

- CLI help
- package install
- raw policy JSON authoring
- long timeline scrolling
- framework integration code

## Why this is practical

A normal organization would use this for consequential approval workflows such as:

- loan approvals
- refunds and claims
- customer-support automations
- internal AI control testing
- audit and compliance review
