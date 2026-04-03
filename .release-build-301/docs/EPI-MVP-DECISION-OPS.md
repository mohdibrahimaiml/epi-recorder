# EPI MVP: Decision Ops Product Spec

## Product One-Liner

EPI is the system that reviews, explains, and verifies AI decisions before they become problems.

## What This MVP Is

This MVP is not a general AI assistant.
It is not a generic workflow builder.
It is not another observability dashboard.

This MVP is a focused product for one loop:

1. an AI decision happens
2. EPI captures it
3. EPI checks rules
4. EPI flags risk
5. a human reviews it
6. EPI produces a defensible record

## Who This MVP Is For

Primary users:

- operations reviewers
- compliance reviewers
- risk analysts
- team admins

Secondary users:

- auditors
- engineering teams

## What Must Stay Hidden

These remain the backend moat, not the main interface:

- `.epi` files
- raw manifests
- signatures
- low-level trace events
- raw policy JSON
- CLI workflows

They still exist and remain essential, but the product surface should not lead with them.

## What Must Stay Visible

These are the product promises and cannot disappear:

- what happened
- what decision was made
- what rule applied
- who reviewed it
- whether the record is trustworthy

## MVP Surface Area

The MVP should have exactly four product screens:

1. Inbox
2. Case
3. Rules
4. Reports

Everything else should either support those screens or stay in the backend.

---

## Screen 1: Inbox

### Purpose

Show non-technical users which AI decisions need attention right now.

### Primary user

- reviewer
- operations manager
- compliance analyst

### What this screen shows

- list of recent AI decisions
- status for each case
- risk level
- trust status
- review status
- workflow type
- created time

### Required filters

- needs review
- trusted
- tampered
- high risk
- workflow type
- assigned reviewer
- date range

### Required actions

- open case
- assign reviewer
- mark as escalated
- export selected cases

### Row design

Each row should answer at a glance:

- what decision happened
- why it needs attention
- what the current state is

### Example row

- Refund approval for Order 4421
- High risk: approval above threshold without manager signoff
- Status: Needs review
- Trust: Trusted
- Reviewer: Unassigned

### Success condition

A reviewer should know what to open first without reading raw details.

---

## Screen 2: Case

### Purpose

Turn one AI decision into a readable case file for review and action.

### Primary user

- reviewer
- risk analyst
- auditor

### Case layout

The case screen should have five sections in this order:

1. Decision summary
2. Risk and trust
3. Human review
4. Rule and policy context
5. Activity timeline

### Section 1: Decision summary

Must answer:

- what happened
- what decision was made
- which system made it
- when it happened
- what business object was affected

### Section 2: Risk and trust

Must answer:

- was risk detected
- what is the main finding
- can this record be trusted
- what should the reviewer do next

### Section 3: Human review

Must support:

- confirm issue
- dismiss after review
- escalate
- add notes
- assign reviewer

### Section 4: Rule and policy context

Must show:

- which rule was active
- plain-English explanation of the rule
- why this case matched it

### Section 5: Activity timeline

Must show:

- a readable sequence of events
- raw details only on expansion

### Required actions

- confirm issue
- dismiss issue
- escalate case
- download review record
- download case summary
- export case report

### Success condition

A non-technical reviewer can make a decision from this screen without using CLI or reading JSON.

---

## Screen 3: Rules

### Purpose

Let non-technical users define governance rules in business language.

### Primary user

- admin
- compliance lead
- operations lead

### Rules screen has two modes

1. Rule list
2. Rule builder

### Rule list must show

- rule name
- workflow
- trigger condition
- action
- severity
- status
- last updated

### Rule builder must support plain-English inputs

Examples:

- require manager approval above $500
- require human review before denial
- flag decisions made with low confidence
- escalate cases outside business hours

### Builder output

The user sees:

- business-language summary
- preview of what cases the rule will affect

The system handles:

- policy JSON generation
- validation
- versioning

### Required actions

- create rule
- edit rule
- disable rule
- preview impact
- duplicate rule

### Success condition

A compliance or operations lead can set guardrails without hand-authoring policy JSON.

---

## Screen 4: Reports

### Purpose

Give teams audit-ready outputs without asking them to assemble evidence manually.

### Primary user

- compliance
- risk
- audit
- management

### Report types in MVP

1. Case report
2. Daily or weekly review summary
3. Exceptions report
4. Trust failures report

### Required filters

- workflow
- date range
- trust state
- review outcome
- rule
- reviewer

### Export formats

- PDF
- CSV
- JSON

### Required actions

- generate report
- download report
- share summary

### Success condition

A compliance or audit user can get a usable report without engineering help.

---

## Core Navigation

Top-level nav should be only:

- Inbox
- Cases
- Rules
- Reports

Secondary navigation should be minimal and role-based.

## Role Model

### Reviewer

Can:

- open cases
- record decisions
- add notes
- escalate
- export case summaries

### Admin

Can:

- manage rules
- manage workflow settings
- manage retention
- manage integrations

### Auditor

Can:

- view case history
- view trust state
- export reports

## MVP Status Model

Keep it simple.

### Case status

- New
- Needs review
- Reviewed
- Escalated
- Closed

### Trust status

- Trusted
- Source not proven
- Tampered

### Review outcome

- Confirmed issue
- Dismissed after review
- Escalated
- Pending review

## First Integrations

Do not start with everything.

MVP integrations:

- Slack notifications
- email notifications
- CSV import or export

Post-MVP integrations:

- Salesforce
- ServiceNow
- Jira
- Zendesk

## Non-Goals

These are explicitly out of scope for the MVP:

- generic workflow automation builder
- open-ended AI chatbot experience
- broad agent authoring platform
- huge integration marketplace
- custom analytics suite

## Why This Product Wins

The interface becomes simple:

- inbox
- case
- rules
- reports

But the moat stays deep:

- capture
- policy engine
- trust verification
- signed evidence
- traceability

That is the correct shift.

## MVP Acceptance Test

The MVP is good enough when all of these are true:

- a reviewer can decide on a case without engineering help
- an admin can create a common rule without editing JSON
- a compliance user can export a usable report without custom tooling
- an auditor can understand trust and review status from the UI
- engineering still retains the full evidence depth underneath

## Build Order

1. Inbox
2. Case
3. Rule builder
4. Reports

The inbox and case screens matter most.

If those are strong, the product already feels real.
