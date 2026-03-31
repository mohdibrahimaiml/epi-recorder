# Starter Kit: Refund Approval Agent

A production-shaped example of an AI refund decision agent with full EPI evidence capture.

## The business problem

A customer requests a $900 refund. Your AI agent looks up the order, consults an LLM, requests human approval (because the amount exceeds $500), and executes the refund. Every step — the tool calls, the LLM reasoning, the human sign-off, and the final decision — is captured in a single signed `.epi` case file.

Six months later, a dispute lands. You open the case file and show exactly what happened: who approved it, what the AI reasoned, what data it had. No reconstructions. No guessing.

## What's in this kit

| File | Purpose |
|:-----|:--------|
| `workflow.py` | The refund agent. Works with or without an API key. |
| `epi_policy.json` | Four control rules: high-value approval, return window, confidence threshold, order lookup gate. |

## Run it

```bash
# Works without any API key (uses built-in mock LLM)
python workflow.py

# With real OpenAI (set key first)
export OPENAI_API_KEY=sk-...
python workflow.py
```

## Inspect the case file

```bash
epi view refund_case.epi      # opens offline browser viewer
epi verify refund_case.epi    # cryptographic integrity check
epi review refund_case.epi    # add human review notes
epi analyze refund_case.epi   # fault analysis against policy
```

## The workflow

```
agent.run.start
  └── tool.call          lookup_order
  └── tool.response      order: $900, gold customer, 12 days
  └── llm.request        model: gpt-4o-mini
  └── llm.response       "APPROVE. Gold customer, within return window. Risk: low."
  └── agent.approval.request   → manager@company.com (required by refund-001: amount > $500)
  └── agent.approval.response  → approved by manager
  └── agent.decision     APPROVE, confidence: 0.94
  └── tool.call          execute_refund
  └── tool.response      refund_id: REF-ORD-9001-001, 3 days
agent.run.end
```

## Policy rules (epi_policy.json)

| Rule | What it checks | Enforcement |
|:-----|:---------------|:------------|
| `refund-001` | Amounts > $500 require human approval | BLOCK |
| `refund-002` | Days since purchase > 30 → flag for escalation | FLAG |
| `refund-003` | LLM confidence < 0.80 → flag for manual check | FLAG |
| `refund-004` | Decision must follow a successful order lookup | BLOCK |

## Adapting to your workflow

- **Different order source**: replace the `order = {...}` block with a real DB or API call inside `tool.call` / `tool.response` steps
- **Real human approval**: replace the simulated `agent.approval.response` with a webhook, Slack bot, or ticketing system callback
- **Different LLM**: swap `gpt-4o-mini` for any model supported by `wrap_openai()` or LiteLLM
- **Tighter policy**: edit `epi_policy.json` — add rules, lower thresholds, or change enforcement from `flag` to `block`

## What audit reviewers see

When a regulator or compliance team requests evidence:

1. Hand them `refund_case.epi`
2. They drag it to `verify.epilabs.org` (no login, no install) — or run `epi verify refund_case.epi`
3. They see: `Signed ✓` — the file has not been altered since it was created
4. They open `epi view refund_case.epi` to read the full decision timeline

The `.epi` file is self-contained. It includes an offline viewer. It works forever, even if EPI Labs stops existing.
