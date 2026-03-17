# Investor Demo: Policy, Fault Analysis, and Review

This demo is the most practical way to show EPI's policy and fault-analysis story to an investor.

It demonstrates:

- sealed `.epi` evidence artifact creation
- embedded `policy.json`
- embedded `analysis.json`
- policy-grounded violations
- heuristic observations
- human review workflow via `epi review`

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

## How a normal user would run it

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
- the viewer shows that analysis was performed
- the viewer shows a primary fault and secondary flags

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

## What to say in the investor demo

Use this narrative:

1. "The company defines expected AI behavior in `epi_policy.json`."
2. "The workflow runs and EPI records the execution as a sealed `.epi` artifact."
3. "Before sealing, EPI analyzes the trace against policy and writes `analysis.json`."
4. "Later, a human reviewer confirms or dismisses the flagged faults without modifying the original evidence."
5. "The result is a portable evidence file that contains the execution trace, the rules in effect, the machine analysis, and the human adjudication."

## Why this is practical

A normal organization would use this for:

- loan approvals
- refunds and claims
- customer-support automations
- internal AI control testing
- audit and compliance review
