# EPI Pilot Readiness Roadmap

## Goal

Make EPI reliable enough for real design-partner pilots and early customer deployments.

This document is intentionally narrower than the long-term platform vision. The target here is not "support everything." The target is:

- one supported deployment shape
- one clear operational model
- one reliable path from live capture to shared review to portable proof

## Supported Pilot Shape

The first supported pilot shape for EPI is:

- single-node self-hosted deployment
- `epi_gateway` as the canonical shared backend
- `web_viewer` as the shared reviewer interface
- SQLite case store plus append-only event spool on disk
- `.epi` as the portable export/proof format
- OpenAI-compatible and Anthropic-compatible capture paths first
- local file import and connector preview still supported

This is the shape we should harden before expanding to multi-node, multi-tenant, or broad enterprise packaging.

## Non-Goals For This Milestone

Do not block pilots on:

- multi-tenant SaaS
- org-wide RBAC complexity
- every provider and framework
- broad no-code workflow automation
- full enterprise notification systems
- every possible connector

## Current Stage

As of March 28, 2026, EPI is in the **pilot-hardening stage**:

- core capture, review, export, and trust flows exist
- the gateway-backed shared inbox exists
- reviewer workflow fields now exist
- the full test suite passes

What is missing is the operational hardening that makes a real pilot survivable without constant founder intervention.

## Pilot Readiness Bar

EPI is pilot-ready only when all of these are true:

- a new team can install the supported stack in under 15 minutes
- accepted events survive process restarts and replay cleanly
- shared cases, reviews, comments, assignments, and due dates survive restart
- exported `.epi` artifacts verify through the normal verify flow
- one documented backup/restore path exists and is tested
- one documented upgrade path exists for schema/runtime changes
- basic access control exists for reviewer-facing deployments
- one 24-hour soak test completes without data loss or unrecoverable errors
- one operator runbook exists for health checks, logs, storage, restart, and export troubleshooting

## P0 Checklist: Must-Have Before External Pilots

### 1. Install And Deployment

- Provide one supported deployment path:
  - `docker compose up`
  - or one documented self-hosted local install path
- Add a production-shaped `.env.example`
- Add startup-time config validation with actionable error messages
- Add `/health` and `/ready` semantics that operators can trust
- Document ports, storage paths, and required environment variables

Repo work:

- add `docker-compose.yml`
- add gateway/runtime env docs in [CLI.md](../CLI.md)
- add a deployment guide in a new `docs/PILOT-DEPLOYMENT.md`
- add config validation in [main.py](/Users/dell/epi-recorder/epi_gateway/main.py)

### 2. Durability And Recovery

- Prove that accepted events are not lost on normal restart
- Prove that replay is idempotent
- Prove that case rebuild does not erase workflow metadata
- Detect partial/corrupt spool batches clearly
- Add explicit operator messaging for replay count and recovery status

Repo work:

- harden spool replay in [worker.py](/Users/dell/epi-recorder/epi_gateway/worker.py)
- harden case rebuild rules in [case_store.py](/Users/dell/epi-recorder/epi_core/case_store.py)
- add corruption/recovery tests in [test_gateway_worker.py](/Users/dell/epi-recorder/tests/test_gateway_worker.py)

### 3. Shared Workflow Correctness

- Shared assignee, due date, status, comments, and review must persist
- Review actions must not race with workflow updates
- Status transitions must remain simple and predictable
- Shared inbox filtering must stay consistent after refresh/restart

Repo work:

- continue hardening [case_store.py](/Users/dell/epi-recorder/epi_core/case_store.py)
- expand gateway workflow API tests in [test_gateway_cases.py](/Users/dell/epi-recorder/tests/test_gateway_cases.py)
- expand browser workflow checks in [test_web_viewer_mvp.py](/Users/dell/epi-recorder/tests/test_web_viewer_mvp.py)

### 4. Portable Proof Path

- Every shared case must export to `.epi`
- Exported `.epi` must pass `epi verify`
- Reopened exported artifacts must preserve review and trust presentation
- Signed and unsigned exports must both be honest and understandable

Repo work:

- keep export path unified in [container.py](/Users/dell/epi-recorder/epi_core/container.py)
- extend export regression checks in:
  - [test_container.py](/Users/dell/epi-recorder/tests/test_container.py)
  - [test_view_verify_extended.py](/Users/dell/epi-recorder/tests/test_view_verify_extended.py)
  - [test_truth_consistency.py](/Users/dell/epi-recorder/tests/test_truth_consistency.py)

### 5. Basic Access Control

Even if this milestone is not full enterprise auth, pilot customers still need basic protection.

Minimum bar:

- local login or shared secret gate for the reviewer UI
- admin/reviewer/auditor roles can be very simple at first
- exported artifacts remain readable offline
- access events are logged

Repo work:

- add a lightweight auth module under `epi_gateway/`
- protect write actions first:
  - review save
  - workflow update
  - comment add
  - export if desired by customer policy
- add gateway auth tests in a new `tests/test_gateway_auth.py`

### 6. Privacy And Secret Handling

- secrets must never be written to browser local storage
- gateway logs must avoid leaking tokens or prompt content accidentally
- content retention/redaction mode must be explicit
- browser must clearly distinguish local-only data from shared data

Repo work:

- audit secret handling in:
  - [connect.py](/Users/dell/epi-recorder/epi_cli/connect.py)
  - [app.js](/Users/dell/epi-recorder/web_viewer/app.js)
  - [main.py](/Users/dell/epi-recorder/epi_gateway/main.py)
- add retention/redaction config in gateway runtime
- add regression tests around secret persistence and log shaping

### 7. Operator Observability

- structured logs with case IDs, decision IDs, and trace IDs
- queue depth visibility
- replay metrics
- export failures visible in logs
- disk/storage warnings

Repo work:

- improve runtime logging in:
  - [main.py](/Users/dell/epi-recorder/epi_gateway/main.py)
  - [worker.py](/Users/dell/epi-recorder/epi_gateway/worker.py)
- add an operator status panel to the browser only if lightweight
- otherwise keep metrics CLI-first for this milestone

### 8. Backup, Restore, And Upgrade

- document exactly what to back up:
  - event spool
  - `cases.sqlite3`
  - signing keys
  - env/config
- provide one restore test
- provide one schema migration policy

Repo work:

- add `scripts/backup-gateway.ps1`
- add `scripts/restore-gateway.ps1`
- add migration/version notes in [OPEN-CORE-ARCHITECTURE.md](./OPEN-CORE-ARCHITECTURE.md)
- add backup/restore tests if practical, otherwise scripted verification docs

### 9. End-To-End Acceptance Testing

Before pilots, EPI should pass real scenario tests, not just unit tests.

Required scenarios:

- OpenAI-compatible request enters gateway -> shared case appears -> review saved -> `.epi` exported -> verify passes
- Anthropic-compatible request enters gateway -> same path works
- connector preview becomes a shared preview case -> comment -> review -> export
- restart gateway in the middle of a pilot workflow -> no accepted data is lost
- import local `.epi` while gateway is offline -> local review/export still works

Repo work:

- add scenario tests under `tests/` for gateway-backed flows
- keep `scripts/run-tests.ps1` as the main local verification path

## P1 Checklist: Strongly Recommended During First Pilots

### 1. Postgres Backend Option

- keep SQLite as the default pilot path
- add a storage interface that allows Postgres without changing case models

### 2. Streaming Proxy Support

- support streaming OpenAI-compatible and Anthropic-compatible traffic without losing traceability

### 3. Better Audit Exports

- PDF summary
- CSV case queue export
- machine-readable audit bundle

### 4. Better Operator Controls

- retention settings
- replay command
- export cleanup and disk maintenance

### 5. Better Authentication

- password auth is enough first
- SSO can wait for the next phase unless a design partner requires it

## P2 Checklist: After Pilot Proof

- multi-node deployment
- stronger org/workspace boundaries
- RBAC expansion
- KMS/HSM-backed signing defaults
- notification delivery
- broader connectors
- hosted control plane

## Concrete Repo Workstreams

### Workstream A: Gateway Runtime Hardening

Focus:

- restart safety
- config validation
- auth gate
- observability

Primary files:

- [main.py](/Users/dell/epi-recorder/epi_gateway/main.py)
- [worker.py](/Users/dell/epi-recorder/epi_gateway/worker.py)
- [gateway.py](/Users/dell/epi-recorder/epi_cli/gateway.py)

### Workstream B: Shared Case Store Hardening

Focus:

- replay safety
- workflow metadata durability
- migration/versioning
- backup/restore behavior

Primary files:

- [case_store.py](/Users/dell/epi-recorder/epi_core/case_store.py)
- [container.py](/Users/dell/epi-recorder/epi_core/container.py)
- [trust.py](/Users/dell/epi-recorder/epi_core/trust.py)

### Workstream C: Reviewer Product Stability

Focus:

- inbox correctness
- shared workflow clarity
- trust/report continuity
- safe offline fallback

Primary files:

- [index.html](/Users/dell/epi-recorder/web_viewer/index.html)
- [app.js](/Users/dell/epi-recorder/web_viewer/app.js)
- [styles.css](/Users/dell/epi-recorder/web_viewer/styles.css)

### Workstream D: Deployment And Operations

Focus:

- Docker packaging
- health checks
- backup/restore
- upgrade docs

Primary files:

- new deployment files at repo root or `deploy/`
- [CLI.md](../CLI.md)
- new `docs/PILOT-DEPLOYMENT.md`

### Workstream E: Acceptance Testing

Focus:

- gateway capture
- shared review flow
- export/verify continuity
- restart/replay resilience

Primary files:

- [test_gateway_worker.py](/Users/dell/epi-recorder/tests/test_gateway_worker.py)
- [test_gateway_cases.py](/Users/dell/epi-recorder/tests/test_gateway_cases.py)
- [test_gateway_proxy.py](/Users/dell/epi-recorder/tests/test_gateway_proxy.py)
- [test_web_viewer_mvp.py](/Users/dell/epi-recorder/tests/test_web_viewer_mvp.py)
- [test_view_verify_extended.py](/Users/dell/epi-recorder/tests/test_view_verify_extended.py)

## 30 / 60 / 90

### 30 Days

- freeze the supported pilot shape
- add Docker/self-hosted packaging
- add config validation
- add basic auth gate
- add backup/restore docs and scripts
- add restart/replay acceptance tests

### 60 Days

- run an internal soak test
- harden logs and operator metrics
- fix pilot friction from installation and review usage
- validate export/verify continuity with real pilot data

### 90 Days

- onboard 2 to 3 design partners
- keep scope narrow to one or two workflows
- add only the enterprise features that unblock real pilot usage

## Pilot Acceptance Scenarios

EPI is ready for external pilots when these scenarios pass reliably:

1. Fresh install

- operator starts the stack with one documented path
- health checks pass
- browser opens the shared inbox

2. Live shared case

- request flows through gateway
- shared case appears
- assignee and due date are saved
- comment is added
- review is saved

3. Portable proof

- the shared case exports to `.epi`
- `epi verify` succeeds
- the exported artifact reopens with the same review story

4. Restart recovery

- gateway is stopped and restarted
- no accepted data disappears
- comments/reviews/assignee/status remain intact

5. Backup and restore

- operator restores from documented files
- cases and exports remain usable

## Minimum Demo For Pilot Customers

The pilot demo should show only the supported shape:

- gateway capture
- shared inbox
- assignment
- comment
- review
- `.epi` export
- verify

Do not demo unstable side paths as if they are equally supported.

## Recommended Wedge For First Pilots

Pick one:

- refund approvals
- claims review
- access decisions

Do not run broad horizontal pilots first.

## Final Rule

EPI becomes pilot-ready not when it has the most features, but when one narrow system is boringly reliable.

That is the right standard before asking real teams to depend on it.
