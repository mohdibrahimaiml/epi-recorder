# EPI Policy Guide

`epi_policy.json` is the rulebook for an AI workflow.

It tells EPI what the system was supposed to do. The fault analyzer then compares the recorded run against those rules and writes the result into `analysis.json`.

## The Simple Mental Model

- `epi_policy.json` = the rulebook you define before the run
- `policy.json` = the sealed copy of that rulebook inside the `.epi` file
- `analysis.json` = the analyzer's findings about the run

## When EPI Uses `epi_policy.json`

The policy file is used during artifact creation.

Typical sequence:

1. create `epi_policy.json`
2. run the AI workflow with EPI
3. EPI records the trace
4. EPI loads `epi_policy.json`
5. the fault analyzer checks the trace against the policy
6. EPI embeds:
   - `policy.json`
   - `analysis.json`
7. EPI seals the `.epi` artifact

## Where To Store `epi_policy.json`

Store `epi_policy.json` in the same working directory where you run EPI.

Example:

```text
loan-underwriting/
  underwriter.py
  epi_policy.json
```

Run EPI from that directory:

```bash
cd loan-underwriting
epi run underwriter.py
```

That is the current practical rule.

If the file is not in the working directory, EPI will not automatically use it for that run.

## What Happens If The File Is Missing

EPI still records the run and still produces a `.epi` file.

But:

- `policy.json` will not be embedded
- policy-grounded checks will not run
- the analyzer can still produce heuristic findings

So EPI still works without a policy file, but it behaves more like evidence recording plus heuristic analysis.

## What Happens If The File Is Invalid

EPI warns and continues packing.

That means:

- recording does not break
- `policy.json` is not embedded
- policy-grounded checks are skipped for that run

Use:

```bash
epi policy validate
```

before running an important workflow.

## Rule Types

EPI currently supports four policy rule types.

### `constraint_guard`

Use this for hard limits.

Example:

- do not approve above the available balance
- do not exceed a credit limit

Example shape:

```json
{
  "id": "R001",
  "name": "Do Not Exceed Balance",
  "severity": "critical",
  "description": "The agent must not approve an amount above the known balance.",
  "type": "constraint_guard",
  "watch_for": ["balance", "available_balance", "limit"],
  "violation_if": "approved_amount > watched_value"
}
```

### `sequence_guard`

Use this when one action must happen before another.

Example:

- verify identity before refund
- complete risk assessment before final approval

Example shape:

```json
{
  "id": "R002",
  "name": "Verify Identity Before Refund",
  "severity": "high",
  "description": "Identity verification must happen before refund.",
  "type": "sequence_guard",
  "required_before": "refund",
  "must_call": "verify_identity"
}
```

### `threshold_guard`

Use this when crossing a value requires escalation or human approval.

Example:

- amounts above `10000` require human approval

Example shape:

```json
{
  "id": "R003",
  "name": "Human Approval Above 10000",
  "severity": "high",
  "description": "Amounts above 10,000 require human approval.",
  "type": "threshold_guard",
  "threshold_value": 10000,
  "threshold_field": "amount",
  "required_action": "human_approval"
}
```

Notes:

- `threshold_field` is the clearest field name to use
- `watch_for` also works as a fallback for threshold rules

### `prohibition_guard`

Use this for patterns that must never appear in output.

Example:

- never output secrets
- never output token-like strings

Example shape:

```json
{
  "id": "R004",
  "name": "Never Output Secrets",
  "severity": "critical",
  "description": "The system must not expose secret-like tokens in output.",
  "type": "prohibition_guard",
  "prohibited_pattern": "sk-[A-Za-z0-9]+"
}
```

Compatibility note:

- EPI accepts both `prohibited_pattern` and `pattern`
- prefer `prohibited_pattern` in new files

## What The Fault Analyzer Checks

When a policy is present, the analyzer checks the recorded trace for:

- `constraint_violation`
- `sequence_violation`
- `threshold_violation`
- `prohibition_violation`

It also performs heuristic checks such as:

- `error_continuation`
- `context_drop`

So the analyzer can find:

- rule-based faults
- heuristic risk observations

## Why A Policy Fault May Not Always Be The Primary Fault

The analyzer chooses a `primary_fault` for the run.

Sometimes that will be a policy violation.
Sometimes it will be a heuristic observation.

That does not mean the policy file failed to load.

The important checks are:

- was `policy.json` embedded?
- was `analysis.json` embedded?
- does the analysis contain policy-grounded rule IDs or violations?

## How To Create A Policy

### Option 1: start from a built-in profile

```bash
epi policy profiles
epi policy init --profile finance.loan-underwriting
```

### Option 2: create a generic starter file

```bash
epi policy init
```

### Option 3: edit the JSON manually

Advanced teams can manage `epi_policy.json` directly.

## Finance Example

```text
loan-agent/
  loan_agent.py
  epi_policy.json
```

```bash
cd loan-agent
epi policy validate
epi run loan_agent.py
epi view loan_agent.epi
```

What happens:

- EPI records the run
- loads `epi_policy.json`
- embeds `policy.json`
- produces `analysis.json`
- seals the `.epi`

## The Enterprise Reality

Normal employees should not have to write JSON by hand.

In a real organization, the expected model is:

- a risk or platform owner creates the policy once
- EPI applies that policy automatically to runs in that workflow
- employees just use the AI system
- reviewers open `.epi` files and see what went wrong

So `epi_policy.json` should be thought of as the machine-readable form of the company's AI rulebook, not as the main user interface.
