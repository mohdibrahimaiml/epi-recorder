# Starter Kit: Insurance Claim Denial

A production-shaped insurance claim denial workflow with full EPI evidence capture.

## The business problem

An AI-assisted claims workflow recommends denying a $1,200 homeowners claim. That is the kind of decision that later gets reviewed by compliance, legal, internal audit, or a regulator. EPI captures the exact checks that ran, the human approval, the denial reason, and the final case record in one portable `.epi` file.

This kit is built for that moment. It gives you a concrete denial flow, a policy pack that matches insurer controls, and a Decision Record export you can hand to another reviewer without rebuilding the story from logs.

## Two demo modes

| Script | When to use |
|:-------|:------------|
| `agent.py` | **Offline / simulated approval.** No gateway needed. Approval is hardcoded. Use for artifact generation, `epi verify`, and Decision Record demos. |
| `agent_live_approval.py` | **Live approval.** Requires a running gateway. Pauses at approval request and waits for a real human to click approve or deny. Use when selling the human-in-the-loop story. |

## What's in this kit

| File | Purpose |
|:-----|:--------|
| `agent.py` | Offline demo — deterministic, no external setup, simulated approval. |
| `agent_live_approval.py` | Live gateway demo — real approval notification and callback. |
| `epi_policy.json` | Insurance claim denial controls: fraud check, coverage check, human approval threshold, denial reason, and PII-safe output. |

## Option 1 — Offline demo (no gateway needed)

```bash
python agent.py
epi view insurance_claim_case.epi
epi verify insurance_claim_case.epi
epi export-summary summary insurance_claim_case.epi
```

Produces `epi-recordings/insurance_claim_case.epi` by default. `epi view`, `epi verify`, and `epi share` accept the bare file name, so you can still run the commands above unchanged. Human approval is simulated inline.

## Option 2 — Live approval demo (requires gateway)

```bash
# Terminal 1: start the gateway
epi gateway serve

# Terminal 2: run the demo
python agent_live_approval.py
```

The script pauses after sending `agent.approval.request` and prints two URLs:

```
APPROVE → http://localhost:8765/api/approve/claim-CLM-48219-xxx/approval-CLM-48219?decision=approve
DENY    → http://localhost:8765/api/approve/claim-CLM-48219-xxx/approval-CLM-48219?decision=deny
```

Open one in your browser. The script continues, seals the case, and exports the Decision Record.

To send a real email or webhook when approval is needed, set these before starting the gateway:

```bash
export EPI_APPROVAL_WEBHOOK_URL=https://hooks.slack.com/...   # or any POST endpoint
export EPI_APPROVAL_BASE_URL=http://localhost:8765
```

## The workflow

1. Load the claim
2. Run a fraud check
3. Check coverage against the policy
4. Request human approval (claim amount exceeds $500 threshold)
5. **Wait for real approval** (live mode) or simulate it (offline mode)
6. Record the denial reason
7. Capture the AI recommendation
8. Record the final denial decision
9. Issue the denial notice

## Why this kit matters

- opens in under 90 seconds
- uses plain business actions instead of generic agent jargon
- proves the denial was reviewed before it went out
- exports a Decision Record a compliance officer can actually read
- live mode demonstrates real human-in-the-loop, not a simulation
