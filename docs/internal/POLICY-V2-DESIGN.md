# EPI Policy v2 Design

**Status:** Proposed design for the next enterprise policy layer after `v3.0.2`
**Audience:** Product, platform, security, compliance, and engineering teams  
**Goal:** Make EPI policy useful as a real enterprise control system for AI workflows

---

## Why Policy v2

`v3.0.2` policy is already useful for sealing a workflow rulebook into a `.epi` artifact and checking a run against it after the fact.

That is strong for:
- workflow-specific controls
- reviewable fault analysis
- portable evidence

But enterprises usually need more than a local rule file. They need to answer:

- what was this AI system allowed to do
- which controls applied at runtime
- what should have been blocked, escalated, or approved
- which environment, team, or application policy was active
- whether the workflow followed the organization rulebook, not just a local JSON file

Policy v2 is meant to turn EPI policy into a **portable enterprise control layer for AI decisions**.

---

## Design Goals

Policy v2 should:

- keep the current EPI strengths: portable, reviewable, machine-readable, sealed into the artifact
- stay understandable to non-engineering reviewers
- support enterprise controls without requiring a cloud platform
- distinguish between **detecting** a problem and **enforcing** a control
- support layered policy inheritance
- make policy provenance explicit inside the `.epi`
- remain backward compatible with current `epi_policy.json` workflows

Policy v2 should not:

- replace existing cloud guardrails from providers like AWS, Azure, Google, OpenAI, or Anthropic
- become a generic policy language for everything in an enterprise
- require an always-on control plane before EPI can function

---

## Core Shift

Policy v1 is mostly:

- a workflow-level rulebook
- loaded from the working directory
- used at pack time
- checked against a completed run

Policy v2 should become:

- a layered control specification
- aware of organization, team, application, workflow, and environment
- usable for both post-run analysis and future runtime enforcement
- explicit about intervention points, enforcement modes, and approval requirements

---

## Policy v2 Mental Model

Policy v2 separates three things:

1. **What scope this policy applies to**
2. **What controls it defines**
3. **What happened when those controls were evaluated**

That means:

- `policy.json` remains the embedded rulebook
- `analysis.json` remains the human-readable finding summary
- a future `policy_evaluation.json` can capture exact control outcomes in a more structured way

---

## Proposed Top-Level Schema

```json
{
  "policy_format_version": "2.0",
  "policy_id": "finance-refund-prod",
  "policy_name": "Finance Refund Production Controls",
  "policy_version": "2026-04-01",
  "description": "Controls for production refund agents.",
  "owners": [
    {
      "name": "Risk Platform",
      "email": "risk@company.com",
      "role": "policy_owner"
    }
  ],
  "scope": {
    "organization": "Acme Corp",
    "team": "finance-ops",
    "application": "refund-agent",
    "workflow": "refund-approval",
    "environment": "production"
  },
  "defaults": {
    "mode": "detect",
    "review_required_on": ["high", "critical"]
  },
  "inherits_from": [
    {
      "policy_id": "org-baseline",
      "policy_version": "2026-03-15",
      "sha256": "..."
    }
  ],
  "rules": [],
  "approval_policies": [],
  "metadata": {
    "frameworks": ["langgraph", "openai-agents"],
    "data_classes": ["pii", "financial"],
    "jurisdictions": ["US"],
    "control_objectives": ["human_approval", "data_minimization"]
  }
}
```

### Key top-level additions

- `policy_format_version`
  - separates future schema evolution from the product version
- `policy_id`
  - stable identifier for enterprise policy management
- `owners`
  - makes policy ownership explicit
- `scope`
  - explains where the policy applies
- `defaults.mode`
  - establishes the baseline intervention behavior
- `inherits_from`
  - allows layered policies
- `approval_policies`
  - centralizes approval definitions that multiple rules can reference

---

## Policy Layers

Policy v2 should support layered inheritance in this order:

1. `organization`
2. `team`
3. `application`
4. `workflow`
5. `environment override`

Example:

- org policy: never output secrets
- finance team policy: large payouts require approval
- refund-agent policy: verify identity before refund
- production override: allowlisted tools only

### Merge rules

- child policies can add stricter rules
- child policies should not weaken inherited `block` rules without an explicit exception record
- the artifact should embed:
  - effective policy hash
  - layer sources
  - applied exceptions

---

## Intervention Points

Policy v2 should support explicit intervention points:

- `input`
- `prompt`
- `model_request`
- `model_response`
- `tool_call`
- `tool_response`
- `memory_read`
- `memory_write`
- `decision`
- `output`
- `handoff`
- `review`

This matters because enterprises care about when a rule applies, not just what the final timeline contains.

---

## Enforcement Modes

Each rule should support a `mode`:

- `detect`
  - record the issue, do not block
- `warn`
  - mark the issue clearly for operators
- `block`
  - prevent the action from proceeding
- `require_approval`
  - pause until approval is recorded
- `redact`
  - scrub sensitive content before continuing
- `quarantine`
  - isolate the run or artifact for deeper review
- `escalate`
  - mark for higher-level review or incident handling

### Why this matters

Current EPI policy is mostly detect-and-explain.

Policy v2 should be able to say:

- detect this
- require signoff here
- block this tool call
- redact this class of data

Even if initial EPI runtime support implements only `detect` and `require_approval`, the schema should leave room for the full set.

---

## Rule Families

Policy v2 should keep the current rule types and add enterprise control families.

### Keep

- `constraint_guard`
- `sequence_guard`
- `threshold_guard`
- `prohibition_guard`
- `approval_guard`

### Add

- `tool_permission_guard`
- `model_allowlist_guard`
- `data_classification_guard`
- `memory_guard`
- `handoff_guard`
- `retry_budget_guard`
- `cost_budget_guard`
- `connector_scope_guard`
- `domain_guard`
- `runtime_boundary_guard`

---

## Rule Shapes

### 1. `tool_permission_guard`

Use this to control which tools can be used and how.

```json
{
  "id": "R100",
  "name": "Refund Agent Tool Allowlist",
  "type": "tool_permission_guard",
  "severity": "critical",
  "mode": "block",
  "applies_at": "tool_call",
  "allowed_tools": ["lookup_order", "verify_identity", "create_refund"],
  "denied_tools": ["delete_customer", "export_ledger"],
  "description": "Only approved refund tools may be called in production."
}
```

### 2. `model_allowlist_guard`

Use this to restrict the models that can be used.

```json
{
  "id": "R101",
  "name": "Approved Production Models Only",
  "type": "model_allowlist_guard",
  "severity": "high",
  "mode": "block",
  "applies_at": "model_request",
  "allowed_models": ["gpt-5.4-mini", "gpt-5.4", "claude-sonnet-4-5"],
  "description": "Production workflows must use approved model versions only."
}
```

### 3. `data_classification_guard`

Use this to stop certain data classes from reaching specific destinations.

```json
{
  "id": "R102",
  "name": "No PII To Unapproved Models",
  "type": "data_classification_guard",
  "severity": "critical",
  "mode": "block",
  "applies_at": "model_request",
  "data_classes": ["pii"],
  "restricted_destinations": ["external_model"],
  "description": "PII must not be sent to non-approved external models."
}
```

### 4. `memory_guard`

Use this to control memory access and retention.

```json
{
  "id": "R103",
  "name": "Do Not Persist Payment Secrets",
  "type": "memory_guard",
  "severity": "critical",
  "mode": "block",
  "applies_at": "memory_write",
  "restricted_classes": ["credentials", "payment_secret"],
  "description": "Sensitive payment material must never be written to agent memory."
}
```

### 5. `handoff_guard`

Use this when certain decisions require escalation or a different agent.

```json
{
  "id": "R104",
  "name": "Escalate Low Confidence Refund Decisions",
  "type": "handoff_guard",
  "severity": "high",
  "mode": "require_approval",
  "applies_at": "decision",
  "when_confidence_below": 0.8,
  "handoff_to": "human-review",
  "description": "Low-confidence refund decisions must be handed off."
}
```

### 6. `retry_budget_guard`

Use this to stop loops and repeated failures.

```json
{
  "id": "R105",
  "name": "Retry Budget For Failed Refund Calls",
  "type": "retry_budget_guard",
  "severity": "medium",
  "mode": "escalate",
  "applies_at": "tool_response",
  "target_action": "create_refund",
  "max_retries": 2,
  "description": "Refund creation should not retry indefinitely."
}
```

### 7. `cost_budget_guard`

Use this to stop expensive workflows from drifting.

```json
{
  "id": "R106",
  "name": "Approval For High-Cost Runs",
  "type": "cost_budget_guard",
  "severity": "high",
  "mode": "require_approval",
  "applies_at": "decision",
  "threshold_value": 5.0,
  "currency": "USD",
  "description": "Runs above the cost budget require explicit approval."
}
```

### 8. `connector_scope_guard`

Use this to restrict read/write access for connectors and systems.

```json
{
  "id": "R107",
  "name": "CRM Read Only",
  "type": "connector_scope_guard",
  "severity": "critical",
  "mode": "block",
  "applies_at": "tool_call",
  "connector": "salesforce",
  "allowed_scopes": ["read"],
  "denied_scopes": ["write", "delete"],
  "description": "The support workflow may read CRM data but not modify it."
}
```

### 9. `domain_guard`

Use this for browser or computer-use agents.

```json
{
  "id": "R108",
  "name": "Browser Domain Allowlist",
  "type": "domain_guard",
  "severity": "critical",
  "mode": "block",
  "applies_at": "tool_call",
  "allowed_domains": ["refunds.company.com", "id.company.com"],
  "description": "Browser automation may only operate on approved internal domains."
}
```

### 10. `runtime_boundary_guard`

Use this to control vendor, region, or environment boundaries.

```json
{
  "id": "R109",
  "name": "US-Only Runtime Boundary",
  "type": "runtime_boundary_guard",
  "severity": "critical",
  "mode": "block",
  "applies_at": "model_request",
  "allowed_regions": ["us"],
  "description": "This workflow must stay within approved region boundaries."
}
```

---

## Approval Policies

Approval behavior should become reusable instead of repeated in every rule.

```json
{
  "approval_policies": [
    {
      "approval_id": "manager-refund-approval",
      "required_roles": ["manager"],
      "minimum_approvers": 1,
      "expires_after_minutes": 30,
      "reason_required": true,
      "separation_of_duties": true
    }
  ]
}
```

Rules can then reference that approval policy:

```json
{
  "id": "R110",
  "name": "Refund Approval Required",
  "type": "approval_guard",
  "severity": "critical",
  "mode": "require_approval",
  "applies_at": "decision",
  "approval_action": "approve_refund",
  "approval_policy_ref": "manager-refund-approval",
  "description": "Refund execution requires manager approval."
}
```

---

## Policy Provenance Inside The Artifact

Each `.epi` should show:

- `policy_id`
- `policy_version`
- `policy_format_version`
- effective policy hash
- inherited policy sources
- policy owners
- environment scope
- which controls were evaluated
- which controls passed, failed, blocked, or required approval

### Proposed new embedded file

`policy_evaluation.json`

This file should be more structured than `analysis.json`.

Suggested shape:

```json
{
  "policy_id": "finance-refund-prod",
  "policy_version": "2026-04-01",
  "effective_policy_sha256": "...",
  "evaluation_mode": "post_run",
  "controls_evaluated": 12,
  "results": [
    {
      "rule_id": "R110",
      "status": "failed",
      "mode": "require_approval",
      "applies_at": "decision",
      "step_number": 8,
      "plain_english": "The agent executed approve_refund without a matching manager approval."
    }
  ]
}
```

`analysis.json` should remain the reviewer-friendly summary layer.

---

## CLI Changes

### Current commands to keep

- `epi policy init`
- `epi policy validate`
- `epi policy show`

### New commands

- `epi policy test`
  - run a policy against one or more `.epi` files and show rule outcomes
- `epi policy simulate`
  - preview which controls would fire on a run without rewriting evidence
- `epi policy diff`
  - compare two policy versions
- `epi policy explain`
  - describe how a specific rule works in reviewer language
- `epi policy layers`
  - show effective policy sources and overrides

### Example CLI flow

```bash
epi policy init --mode enterprise
epi policy validate
epi policy explain R110
epi policy test --policy epi_policy.json --artifact refund_case.epi
epi policy diff old_policy.json new_policy.json
```

---

## API Changes

### Proposed `record(...)` additions

```python
with record(
    "refund_case.epi",
    policy="epi_policy.json",
    policy_scope={"environment": "production", "team": "finance-ops"},
):
    ...
```

### Proposed `agent_run(...)` additions

```python
with epi.agent_run(
    "refund-agent",
    user_input="Refund order 123",
    policy_context={
        "application": "refund-agent",
        "workflow": "refund-approval",
        "environment": "production",
        "data_classes": ["pii", "financial"]
    }
) as agent:
    ...
```

### Proposed runtime hooks

Even before full runtime blocking exists, EPI should support emitting structured control-check events like:

- `policy.check`
- `policy.warn`
- `policy.block`
- `policy.approval.required`
- `policy.redaction`

These events would help bridge post-run analysis and future runtime enforcement.

---

## Example Enterprise Policy

```json
{
  "policy_format_version": "2.0",
  "policy_id": "refund-agent-prod",
  "policy_name": "Refund Agent Production Policy",
  "policy_version": "2026-04-01",
  "description": "Enterprise controls for the production refund workflow.",
  "owners": [
    {
      "name": "Finance Risk",
      "email": "risk@company.com",
      "role": "policy_owner"
    }
  ],
  "scope": {
    "organization": "Acme Corp",
    "team": "finance-ops",
    "application": "refund-agent",
    "workflow": "refund-approval",
    "environment": "production"
  },
  "defaults": {
    "mode": "detect",
    "review_required_on": ["high", "critical"]
  },
  "rules": [
    {
      "id": "R001",
      "name": "Verify Identity Before Refund",
      "severity": "critical",
      "mode": "detect",
      "type": "sequence_guard",
      "applies_at": "decision",
      "required_before": "refund",
      "must_call": "verify_identity",
      "description": "Identity verification must happen before refund."
    },
    {
      "id": "R002",
      "name": "Manager Approval Before Refund",
      "severity": "critical",
      "mode": "require_approval",
      "type": "approval_guard",
      "applies_at": "decision",
      "approval_action": "approve_refund",
      "approval_policy_ref": "manager-refund-approval",
      "description": "Refund approval requires explicit manager signoff."
    },
    {
      "id": "R003",
      "name": "Only Approved Tools",
      "severity": "critical",
      "mode": "block",
      "type": "tool_permission_guard",
      "applies_at": "tool_call",
      "allowed_tools": ["lookup_order", "verify_identity", "approve_refund"],
      "description": "The production refund workflow may only use approved tools."
    },
    {
      "id": "R004",
      "name": "No Secrets In Output",
      "severity": "critical",
      "mode": "redact",
      "type": "prohibition_guard",
      "applies_at": "output",
      "prohibited_pattern": "(sk-[A-Za-z0-9]+|api[_-]?key)",
      "description": "Secret-like tokens must never appear in output."
    }
  ],
  "approval_policies": [
    {
      "approval_id": "manager-refund-approval",
      "required_roles": ["manager"],
      "minimum_approvers": 1,
      "expires_after_minutes": 30,
      "reason_required": true,
      "separation_of_duties": true
    }
  ]
}
```

---

## Migration Strategy

Policy v2 should be additive, not disruptive.

### Phase 1: Schema extension

- keep current `epi_policy.json` valid
- support `policy_format_version`
- accept v1 and v2 files
- continue embedding `policy.json` and `analysis.json`

### Phase 2: Structured evaluation

- add `policy_evaluation.json`
- extend CLI policy inspection
- improve viewer policy presentation

### Phase 3: Runtime-assisted controls

- introduce runtime control events
- support `require_approval` cleanly during execution
- optionally support `block` and `redact` in selected integrations

### Phase 4: Enterprise workflows

- layered policy sources
- policy testing and diffing
- team review and approval workflow support

---

## Recommended Implementation Order

If EPI implements Policy v2 incrementally, the best order is:

1. add `policy_format_version`, `policy_id`, `scope`, `mode`, and `applies_at`
2. add `approval_policies` and improve approval evaluation
3. add `tool_permission_guard` and `model_allowlist_guard`
4. add `policy_evaluation.json`
5. add CLI commands: `test`, `diff`, `explain`
6. add viewer support for layered policy and control outcomes
7. add runtime-assisted enforcement for `require_approval`

This order keeps EPI aligned with its current strengths:

- clear artifacts
- explainable review
- portable evidence
- gradual enterprise maturity

---

## Product Positioning

The best way to describe Policy v2 is:

**EPI Policy v2 defines what an AI workflow was allowed to do, how those controls were applied, and what evidence proves the workflow followed or broke them.**

That makes EPI stronger for:

- enterprise AI governance
- approval-heavy workflows
- regulated environments
- cross-team review
- proving both behavior and controls later

---

## Final Recommendation

EPI should not try to become a generic cloud guardrail platform.

It should become the best system for:

- portable AI evidence
- control-aware artifacts
- human review
- trust verification

Policy v2 is the right path if it stays grounded in that identity.
