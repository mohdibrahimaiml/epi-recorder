# EPI Recorder: How It Works (Simplified)

Think of **EPI** as a **portable case file for AI execution**. It records what happened during a run, can embed the rulebook used to judge that run, can attach a human review decision, and makes later tampering visible. In `v4.0.1`, the browser experience is now case-first: the viewer leads with the decision, review state, trust state, source system, and supporting evidence instead of making reviewers start from raw logs.

## The Core Concept

When you run an AI workflow with EPI, the goal is not just "collect logs." The goal is to create one artifact that can answer:

- what happened
- why it happened
- what rules or policy evidence were active
- whether a human reviewed it
- whether the evidence is still trustworthy

For imported systems like Microsoft Agent Governance Toolkit (AGT), EPI keeps the same artifact model and adds a transformation audit so a reviewer can see what was preserved raw, translated, derived, or synthesized.

## The 4 Stages of Evidence

Here is the journey of an EPI recording, explained simply:

### 1. The Setup

When you type `epi run my_agent.py` or add `with record(...):` to your code, EPI prepares a capture context before the workflow starts doing real work. The point is to begin with the run itself, not reconstruct it later.

### 2. The Recording

EPI captures meaningful execution steps while the workflow runs.
That may come from:

- explicit `record()` instrumentation
- wrapper clients and integrations
- manual `log_step(...)` calls
- imports from external evidence sources such as AGT bundles

The point is not hidden magic. The point is to create a trustworthy execution timeline and the case metadata needed for later investigation.

### 3. The Safety Net

Computers can crash. Power can go out. If an AI workflow fails halfway through, you do not want to lose the evidence of what led up to the failure.

- The old way: save text logs and hope they are enough.
- The EPI way: persist structured steps and package them into a durable artifact with enough context for another person to inspect the case later.

### 4. The Seal

Once the program finishes, EPI packages the evidence into a single `.epi` artifact.

- The box: execution timeline, environment, viewer, and optional policy, analysis, review, and imported-source artifacts
- The seal: Ed25519 signing plus file-manifest hashing
- The review layer: a later human decision can be appended as `review.json`
- Verification: if someone changes sealed evidence later, EPI can detect it and show the artifact as **tampered**

## What The Viewer Is For

The browser viewer is a local case investigation surface. It is designed to answer, quickly:

- what decision was made
- why that decision happened
- what evidence supports it
- whether someone still needs to act
- whether the artifact can be trusted

The main sections are:

- `Overview`
- `Evidence`
- `Policy`
- `Review`
- `Mapping`
- `Trust`
- `Attachments`

For AGT-imported cases, `Mapping` becomes the transformation audit that explains what EPI copied exactly, translated, derived, synthesized, or preserved raw.

## Technical Summary (For Developers)

For those who want the specifics:

- **Capture**: EPI supports explicit instrumentation, wrappers, integrations, imports, and limited patching paths.
- **Format**: the `.epi` file is a ZIP-based artifact containing timeline data plus optional `policy.json`, `analysis.json`, `review.json`, and imported-source artifacts.
- **Viewer**: the packaged `viewer.html` remains self-contained for offline and extracted review flows.
- **Security**: Ed25519 digital signatures plus integrity verification.
- **Review model**: the original sealed evidence remains intact even when human review is appended later.
