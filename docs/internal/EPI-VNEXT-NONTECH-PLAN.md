# EPI vNext: Non-Technical Product Plan

## Goal

Make EPI easy for non-technical people to use inside real business systems.

A compliance manager, operations lead, reviewer, or auditor should be able to use EPI without reading JSON, running CLI commands, or asking an engineer for help.

## Core Product Shift

Today, EPI feels strongest as a developer-facing evidence tool.

To reach non-technical users, EPI should evolve into a:

- case-management product
- governance product
- reviewer workflow product
- audit-ready records product

The key shift is simple:

> Stop exposing infrastructure first. Start exposing decisions, cases, rules, reviews, and reports.

## Primary Non-Technical Users

- Operations manager
- Compliance reviewer
- Risk analyst
- Internal auditor
- Team admin

These users do not want tracing primitives.
They want:

- a case to review
- a rule to approve
- a report to export
- a status they can trust

## P0: Must-Have Changes

These are the highest-impact improvements.

### 1. Web Dashboard Instead of CLI-First Usage

EPI needs a simple application with five primary screens:

- Workflows
- Cases
- Rules
- Reviews
- Reports

This should become the main experience for non-technical users.
The CLI can remain for developers and advanced setup.

### 2. Plain-English Rule Builder

Non-technical users should not edit raw policy JSON.

They should be able to create rules like:

- Manager approval required above $1,000
- Human review required before denial
- Escalate when confidence is below 80%
- Block actions outside business hours

The system can still generate structured policy under the hood.

### 3. Case File Summary View

Every EPI record should open to a simple summary, not a raw timeline.

The first screen should answer:

- What happened
- What decision was made
- Which rule applied
- Who approved it
- Whether the record is trusted

Raw steps should still exist, but as a secondary detail.

### 4. Reviewer Inbox

Non-technical teams need a queue of items to act on.

Each case should support:

- Approve
- Reject
- Escalate
- Add note
- Export

This makes EPI part of normal business operations instead of a specialist tool.

### 5. Trust Status That Needs No Training

Trust should be obvious at a glance.

Use simple states:

- Trusted
- Needs review
- Tampered

Each state should include a one-sentence explanation in plain language.

## P1: Next Most Important Changes

These make EPI easier to adopt in real organizations.

### 6. Role-Based Experience

Different users should see different views.

- Operator: recent cases and decisions
- Reviewer: pending items and rule failures
- Auditor: evidence history and reports
- Admin: policies, retention, permissions, integrations

This avoids overwhelming non-technical users with everything at once.

### 7. One-Click Report Export

Non-technical teams need outputs they can share immediately.

EPI should export:

- PDF for audit and legal review
- CSV for operations reporting
- JSON for technical and system integrations
- email-friendly summary for managers

### 8. Connectors to Existing Business Systems

Non-technical people already work in other tools.

EPI should connect to:

- Salesforce
- Zendesk
- ServiceNow
- Jira
- Slack
- Microsoft Teams
- email

The goal is to bring EPI into the workflow they already use.

### 9. Organization-Specific Language

Different industries describe the same pattern differently.

Examples:

- bank: loan review
- insurer: claim approval
- hospital: clinical review
- support team: escalation review

EPI should let organizations rename workflow labels and status language to match their environment.

## P2: Adoption and Scale Improvements

These improvements increase usability across larger organizations and global teams.

### 10. Guided Setup Wizard

Instead of asking users how to instrument a system, ask:

- What type of decision is being made?
- Which system makes it?
- Who reviews exceptions?
- What rules matter?
- What needs to be retained?

Then configure EPI around those answers.

### 11. Localization

Non-technical users should be able to review cases in their own language.

The first surfaces to localize:

- trust labels
- review actions
- case summary headings
- report templates

### 12. Background Trust and Retention Management

Non-technical users should not manage keys or storage details manually.

EPI should handle:

- signing in the background
- automatic verification
- retention defaults
- archive/export flows

Admins can override settings, but ordinary users should not need to think about them.

## Product Design Rules

To stay usable for non-technical teams, EPI should follow these rules:

- lead with the decision, not the trace
- lead with the case, not the file format
- use plain English before technical detail
- make actions obvious
- keep technical detail available, but secondary
- explain trust in human language

## Suggested Release Phases

### Phase 1

- web dashboard shell
- case summary view
- reviewer inbox
- trusted / needs review / tampered status model

### Phase 2

- plain-English rule builder
- role-based views
- PDF and CSV exports
- Slack and email notifications

### Phase 3

- Salesforce, ServiceNow, Jira, Zendesk connectors
- localization
- deeper admin and retention controls

## Best First Five Features

If the team has to choose only five things, choose these:

1. web dashboard
2. case summary view
3. reviewer inbox
4. plain-English rule builder
5. one-click report export

## North Star

EPI should feel simple enough that a compliance or operations team can use it directly, while still giving technical teams the deep evidence underneath.

That is when EPI stops feeling like a developer tool and starts feeling like real infrastructure for high-risk AI systems.

MVP product shape: [EPI-MVP-DECISION-OPS.md](./EPI-MVP-DECISION-OPS.md)

Implementation backlog: [EPI-VNEXT-NONTECH-BACKLOG.md](./EPI-VNEXT-NONTECH-BACKLOG.md)
