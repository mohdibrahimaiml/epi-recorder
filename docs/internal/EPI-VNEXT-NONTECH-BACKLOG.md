# EPI vNext: Non-Technical Backlog

## Epic 1: Case Review Experience

### Issue 1.1

Title:
- Replace artifact-first viewer language with case-review language

Acceptance criteria:
- Top of the viewer reads like a case file, not a trace viewer
- trust state includes a plain-English status
- summary defaults use "case" and "decision" language
- non-technical users can tell what happened before reading raw steps

### Issue 1.2

Title:
- Add a "Case Actions" panel to the embedded viewer

Acceptance criteria:
- viewer shows next steps based on trust state, primary finding, and review state
- tampered records show stop-and-escalate guidance
- flagged-but-unreviewed records show review guidance
- clean trusted records show continue-and-export guidance

### Issue 1.3

Title:
- Add a dedicated case summary card ahead of the timeline

Acceptance criteria:
- first visible section answers what happened, what decision was made, which rule applied, who reviewed it, and whether it is trusted
- timeline remains available but is secondary

## Epic 2: Reviewer Workflow

### Issue 2.1

Title:
- Build a reviewer inbox for pending cases

Acceptance criteria:
- reviewer can see a list of cases needing action
- list can be filtered by trust state, workflow, and review status
- each row links into the case summary view

### Issue 2.2

Title:
- Add approve, reject, escalate, and note actions in a non-technical UI

Acceptance criteria:
- reviewer can record a decision without CLI usage
- notes are stored alongside the existing review model
- actions map back to `review.json` safely

### Issue 2.3

Title:
- Show human-friendly review outcome labels

Acceptance criteria:
- `confirmed_fault` appears as "Confirmed issue"
- `dismissed` appears as "Dismissed after review"
- pending reviews are shown as "Pending review"

## Epic 3: Rule Builder

### Issue 3.1

Title:
- Build a plain-English rule builder on top of policy JSON

Acceptance criteria:
- users can create rules like approval thresholds, required human review, low-confidence escalation, and time-based restrictions
- builder exports valid policy JSON using existing policy engine semantics
- users never need to hand-edit raw JSON for common cases

### Issue 3.2

Title:
- Ship rule templates by workflow type

Acceptance criteria:
- templates exist for refunds, underwriting, claims, and support escalation
- templates can be customized in business language

## Epic 4: Reporting and Sharing

### Issue 4.1

Title:
- Add one-click PDF case report export

Acceptance criteria:
- report includes summary, trust state, primary finding, review outcome, and key facts
- report is readable by audit, compliance, and management users

### Issue 4.2

Title:
- Add CSV and email-friendly summary export

Acceptance criteria:
- operations teams can export structured summaries without JSON parsing
- managers can receive a compact readable summary

## Epic 5: System Integrations

### Issue 5.1

Title:
- Add Slack and email notifications for review-required cases

Acceptance criteria:
- review-required cases can trigger a notification
- notification includes case title, trust status, and direct review link

### Issue 5.2

Title:
- Add connectors for Salesforce, ServiceNow, Jira, and Zendesk

Acceptance criteria:
- EPI cases can be linked to tickets or records in existing systems
- review updates can be synced back to the host system

## Epic 6: Role-Based Product Experience

### Issue 6.1

Title:
- Create separate views for operators, reviewers, auditors, and admins

Acceptance criteria:
- operators see recent cases and outcomes
- reviewers see pending actions
- auditors see history and exports
- admins see rules, retention, and integrations

## Epic 7: Global Readiness

### Issue 7.1

Title:
- Localize trust labels, review actions, and case summary headings

Acceptance criteria:
- core non-technical terms can be translated without changing business logic
- localization covers the main reviewer workflow first

### Issue 7.2

Title:
- Support organization-specific terminology

Acceptance criteria:
- teams can rename workflow labels and domain terms to match their industry
- examples: loan review, claim approval, clinical review, escalation review

## Recommended Build Order

1. case-review language improvements in the viewer
2. case actions panel
3. human-friendly review labels
4. reviewer inbox
5. plain-English rule builder
6. PDF export
7. Slack and email notifications
8. broader connectors and localization
