# The Decision Record

**Every AI decision needs a Decision Record.** One readable record per decision:
what the model saw, what it decided and why, which model answered, who approved
it, and what happened next.

A Decision Record is not a log, a trace, or a governance dashboard. Those answer
questions for engineers and risk teams. A Decision Record answers the question a
customer, auditor or insurer asks:

> "Why was this case decided this way, and who approved it?"

Live page: <https://epilabs.org/decision-record>  
Download the checklist: <https://epilabs.org/assets/decision-record-checklist.md>  
See real output: <https://epilabs.org/assets/demo/decision-record-example.html>

## What is inside

| Field | What it answers |
|---|---|
| Goal and case | What the agent was asked to do, for whom |
| Steps | What the model saw, which tools it called, what came back |
| Decision | The outcome, in plain language |
| Reasons | Why that outcome was chosen |
| Rules | The policy, limit or eligibility rule that applied |
| Model | Which model and version answered, and when |
| Approval | Who signed off, with which key — or that none was required |
| Outcome | The action taken or the customer result |

## Why not a log

| What you have | Who it serves | The question it answers | What it cannot do |
|---|---|---|---|
| Logs | Engineers | What did the system do? | Explain one decision to a customer |
| Traces | Engineers | Where did time and tokens go? | Show reasons and approval per case |
| Governance dashboards | Risk and compliance | Do we have the policy and inventory? | Produce the record of a specific decision |
| **Decision Record** | **Customer, reviewer, auditor** | **Why was this case decided this way, and who approved it?** | Replace your observability stack |

## The ten-question completeness checklist

Score one point per question you can answer **from the record itself**, without
asking the vendor to log in or search another system.

1. What was decided, in plain language?
2. What outcome was recorded, and when?
3. What inputs and data did the model rely on?
4. Which model and version answered?
5. What rules, policy or limit applied?
6. What reasons were recorded for the decision?
7. Who or what approved it, and when?
8. If a human approval was required, is it attached to this record?
9. What happened next — the action taken or the customer outcome?
10. Can the customer or reviewer read this record without the vendor's system?

**9–10:** a Decision Record. **6–8:** close, but reasons, approval or outcome are
incomplete. **3–5:** observability data. **0–2:** logs.

## How EPI produces it

- **Capture without re-platforming:** the gateway, runtime wrappers, or the SDK;
  OpenAI, Anthropic, LangChain, LangGraph, LiteLLM, OpenTelemetry, Guardrails.
- **Approval as data:** approver registry, single-use approval links, review
  records, role bindings.
- **Policy at decision time:** the runtime policy engine and interceptor can
  pause or block before the action.
- **Reviewer output:** `epi export-summary` writes the one-page record;
  `epi view` opens it in a browser; `epi oversight report` aggregates a period.
- **Gap detection:** `epi_core.evidence_profile` and `fault_analyzer` show what a
  reviewer would find missing.

Technical details — sealing, keys, the customer witness and offline verification
— are on the [trust model](https://epilabs.org/trust) page and in
[VERIFICATION_CONTRACT.md](./VERIFICATION_CONTRACT.md). They are proof mechanics,
not the category.

## Where this fits commercially

If a customer is asking for the record behind a decision, that is the
[AI vendor review engagement](https://epilabs.org/plans): one workflow, thirty
days, a Decision Record per case, and a review pack. The recorder and verifier
remain free and open source.
