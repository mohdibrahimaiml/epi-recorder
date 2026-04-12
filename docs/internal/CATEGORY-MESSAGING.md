# EPI Category Messaging

## Category

EPI is **AI Evidence Infrastructure**.

Short version:

> EPI creates tamper-evident decision case files for AI systems that approve, reject, escalate, or act.

Longer version:

> EPI is the evidence layer and system of record for consequential AI decisions. It records what happened, which policy applied, who reviewed it, and whether the evidence is still trustworthy.

## Primary Buyer

Primary buyer:
- Head of AI Governance
- Model Risk leader
- Compliance Engineering lead

Economic buyer:
- CISO
- CRO
- CIO

Champion:
- AI platform lead
- Applied AI engineering lead

## Urgent Need

- AI systems are moving from assistants to decision participants in workflows that affect money, access, safety, and compliance.
- When something goes wrong, enterprises need a portable case file, not just an ephemeral trace in a vendor dashboard.
- Governance teams need to see the active control framework, the execution record, the human approval path, and the trust status in one place.
- Multi-vendor AI stacks fragment evidence unless one durable record travels with the decision.
- High-risk AI logging and accountability expectations are getting more concrete, including Article 12-style logging requirements.
- For EU-facing teams, August 2, 2026 is a real forcing function as most EU AI Act provisions come into effect.

## Homepage Copy

Headline:

> AI Evidence Infrastructure for Consequential AI

Subhead:

> Tamper-evident decision case files for AI systems that approve, reject, escalate, or act.

Supporting proof:

- What happened
- Which policy applied
- Who approved or reviewed it
- Whether the evidence is still trustworthy

CTA direction:

- Start with one workflow
- Create a case file
- Verify trust

## 30-Second Pitch

When AI affects money, access, safety, or compliance, the hard question is not just whether the workflow ran. The hard question is whether you can defend the decision later. EPI creates a tamper-evident case file for every consequential AI run so governance, risk, and platform teams can see what happened, what control applied, who approved it, and whether the evidence still holds.

## What EPI Is Not

- Not another tracing dashboard
- Not only a debugging tool
- Not only a compliance checklist
- Not a hosted system that traps the record inside one vendor

## Best Initial Wedge

Start with AI-assisted approvals in regulated or sensitive operations:

- refunds and claims
- underwriting and credit decisions
- support escalations
- internal exception approvals

This wedge is strong because it naturally combines policy, human approval, incident review, and trust verification.

## Demo Narrative

Open with:

> An AI-supported workflow made a consequential decision. Now a governance or risk team needs the case file.

Show in order:

1. trusted artifact
2. primary finding
3. control outcomes
4. human review
5. tampered copy

Close with:

> EPI is the case file you bring to audit, incident review, and AI governance when a consequential AI decision needs to be defended.

## What To Avoid

- Do not lead with the `.epi` file format.
- Do not lead with Ed25519, ZIP structure, or embedded viewer internals.
- Do not lead with "developer tooling" or "cool tracing."
- Do not position EPI as a generic observability replacement.

Lead with buyer pain, operational consequence, and the need for a defensible record.

## Packaging Direction

Open-source EPI:
- recorder
- verifier
- offline viewer
- policy and review primitives

Enterprise EPI:
- policy distribution
- retention and search
- RBAC
- key management
- approval and review workflow
- audit export
- cross-run evidence governance
