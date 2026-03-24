# EPI Recorder: How It Works (Simplified)

Think of **EPI** as a **portable case file for AI execution**. It records what happened during a run, can embed the rulebook used to judge that run, can attach a human review decision, and makes later tampering visible. In `v2.8.9`, this also includes richer policy-control outcomes, clearer reviewer links from controls to steps, stronger policy validation diagnostics, and stronger trust verification across both the Python and desktop viewer flows.

## The Core Concept

When you run an AI workflow with EPI, the goal is not just “collect logs.” The goal is to create one artifact that can answer:

- what happened
- what rules were active
- what went wrong
- whether a human reviewed it
- whether the evidence is still trustworthy

## The 4 Stages of Evidence

Here is the journey of an EPI recording, explained simply:

### 1. The Setup (Injection)
When you type `epi run my_agent.py`, EPI creates a secure environment for your script. Before your code even runs its first line, EPI is already there, waiting. It's like putting a dashcam in a car before starting the engine.

### 2. The Recording
EPI captures meaningful execution steps while the workflow runs.
That may come from:
*   explicit `record()` instrumentation
*   wrapper clients and integrations
*   manual `log_step(...)` calls

The point is not hidden magic. The point is to create a trustworthy execution timeline.

### 3. The Safety Net (Atomic Storage)
Computers can crash. Power can go out. If your AI agent crashes halfway through, you don't want to lose the evidence of what led up to the crash.
*   **The Old Way:** Saving to a text file. If the program crashes, the file might get cut off or corrupted.
*   **The EPI Way:** We use a tiny, high-speed database engine (SQLite) that writes every single step to the hard drive instantly. It's like writing in a notebook in permanent ink immediately after every event, rather than trying to remember it all and write it down at the end.

### 4. The Seal (Cryptographic Signing)
Once the program finishes, EPI packages the evidence into a single `.epi` artifact.
*   **The Box:** execution timeline, environment, viewer, and optional policy/analysis
*   **The Seal:** Ed25519 signing plus file-manifest hashing
*   **The Review Layer:** a later human decision can be appended as `review.json`
*   **Verification:** if someone changes sealed evidence later, EPI can detect it and show the artifact as **tampered**

---

## Technical Summary (For Developers)

For those who want the specifics:

*   **Capture**: EPI supports explicit instrumentation, wrappers, integrations, and limited patching paths.
*   **Storage**: `sqlite3` in WAL (Write-Ahead Log) mode for atomic, crash-safe writes.
*   **Format**: The `.epi` file is a ZIP-based artifact containing timeline data plus optional `policy.json`, `analysis.json`, and `review.json`.
*   **Security**: Ed25519 digital signatures plus integrity verification.
*   **Review model**: the original sealed evidence remains intact even when human review is appended later.
