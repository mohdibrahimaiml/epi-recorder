# EPI Enterprise Demo Script

**Audience:** Head of AI Governance, CISO, Chief Risk Officer, VP Engineering
**Duration:** 12-15 minutes
**Setup:** Terminal open with EPI installed, browser open to epilabs.org

---

## Minute 0-2: The Problem

**Say:** "What happens when a regulator asks what your AI agent did six months ago?"

**Show:** Open a folder of raw text logs. Scroll through them.

**Say:** "These logs prove nothing. They're mutable. They're system-local. They can't be handed to an auditor. And if your AI makes a consequential decision — a loan, a diagnosis, a hiring call — logs aren't evidence."

**Say:** "EPI solves this. It captures every decision, cryptographically seals it, and lets anyone verify it — offline, forever. One file."

---

## Minute 2-5: The EPI Difference

**Show terminal:**

```bash
$ pip install epi-recorder
$ cat agent.py
```

**Say:** "Three lines of code. That's the integration surface."

**Show the code:**

```python
from epi_recorder import record

with record("loan-decision.epi", goal="Loan decision pipeline"):
    response = client.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": "Assess loan applicant #421"}]
    )
```

**Run it, then say:** "One file. Everything inside — the LLM call, response, tools used, timestamps, environmental context."

---

## Minute 5-8: Verification

```bash
$ epi verify loan-decision.epi --verbose
  [1/5] Structure  ........ PASS  (valid polyglot ZIP+HTML)
  [2/5] Manifest   ...... PASS  (SHA-256: d4e2f1a8b3c7...)
  [3/5] Integrity  ..... PASS  (11 files, all hashes match)
  [4/5] Hash Chain ..... PASS  (42 steps, chain intact)
  [5/5] Signature  .... PASS  (Ed25519: valid)
  DECISION: PASS
```

**Say:** "Five cryptographic checks. All pass. This file proves itself."

**Switch to browser at epilabs.org/verify, drag-and-drop the .epi file.**

**Say:** "Same file. Same checks. No server. No upload. Browser runs verification entirely client-side using Web Crypto. This is what an auditor would see."

---

## Minute 8-12: Annex IV — Enterprise Hook

```bash
$ epi annex init
$ epi annex sign all
$ epi annex pack
$ epi verify annex-iv-compliance.epi --verbose
  DECISION: PASS
$ epi annex report --format pdf
  PDF Report: annex-iv-compliance-report.pdf
```

**Say:** "Nine sections, Ed25519-signed. Declaration of Conformity. Governance Model. SCITT receipt. Multi-signer chain. And this PDF is what you hand to the notified body."

---

## Minute 12-15: Q&A

| Objection | Response |
|-----------|----------|
| "We already have logging" | "Logs are mutable. Any DBA can edit them. A .epi file proves itself — the hash chain and Ed25519 signature make any modification cryptographically detectable." |
| "We don't do high-risk AI" | "Regulation is expanding. California, New York, UK, Canada, Brazil — all writing AI accountability laws. EPI future-proofs your evidence infrastructure." |
| "This looks complex" | "pip install and three lines of code. The complexity is the cryptography underneath — and that's the part you want to be complex." |
| "What about our existing tools?" | "EPI integrates with OpenAI, Anthropic, LangChain, LangGraph, LiteLLM, Guardrails, pytest, and OpenTelemetry. If you call an LLM, EPI can record it." |
| "Can we self-host?" | "Everything runs locally. The CLI, viewer, verification — zero external dependencies. Only the optional SCITT transparency service is hosted." |

**Close:** "I'd like to set up a 14-day pilot. No credit card, no commitment. Full Enterprise, onboarding call, test against your actual pipeline."

---

## Technical Demo Notes

### Pre-flight Checklist
- pip install epi-recorder (latest)
- Generate signing key: epi keys generate
- Simple LLM script ready
- Browser open to epilabs.org/verify
- Clean terminal, large font (14pt+)
- Close all other apps

### What to Emphasize
- "One file"
- "No server, no upload, no calling home"
- "Three lines of code"
- "The auditor opens it without installing anything"
- "pip install + 3 lines = evidence"

### What NOT to Show
- Don't read code line by line — they can see it
- Don't explain Ed25519 or SCITT unless asked
- Don't apologize for bugs — pivot to "this is why evidence matters"

---

## Post-Demo Follow-up Email

> Subject: EPI Pilot — Next Steps
>
> Thanks for your time today. Here's what a 14-day pilot looks like:
>
> 1. 30-minute onboarding call
> 2. Full Enterprise access (RBAC, PDF reports, SCITT, support)
> 3. Test EPI against your actual AI pipeline
> 4. Day 14: decide next steps — no commitment
>
> To get started: pip install epi-recorder && epi demo
>
> Best,
> Mohd Ibrahim Afridi, EPI Labs
