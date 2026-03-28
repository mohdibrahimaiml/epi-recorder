# EPI Open-Core Architecture

EPI should evolve as:

- **Open-source capture and proof layer**
- **Enterprise control plane on top**

That keeps adoption fast for developers while preserving a real commercial product for governance, reviewer operations, and audit workflows.

## Open-Source Layers

These should remain open and portable:

- `epi_core`
  - schemas
  - portable `.epi` proof format
  - signing and verification
  - review append semantics
- `epi_recorder`
  - SDK/runtime instrumentation
  - framework adapters
  - wrappers for model and workflow execution
- `epi_gateway`
  - low-friction capture proxy/service
  - shared capture-event ingestion
  - append-only local spool/batch persistence
- `web_viewer`
  - local and embedded case review experience
  - browser policy editor
  - portable report/review flows

## Enterprise Control Plane

The commercial layer should add what large organizations need operationally:

- multi-user reviewer inbox
- assignments and comments
- org auth and RBAC
- central search across decisions
- retention policies
- policy distribution and policy history
- fleet-wide connector management
- audit workspaces and exports
- incident review timelines

Important rule:

The control plane should **consume** open capture events and `.epi` exports, not replace them.

## Contract Between the Layers

EPI needs one stable contract underneath everything:

- shared capture event schema
- provider-normalized LLM interaction schema
- explicit provenance and trust class
- stable `trace_id`, `decision_id`, and `case_id`
- append-only batch persistence
- portable `.epi` export

That means:

- developers can adopt EPI through a gateway or SDK without buying anything first
- reviewers can use a friendlier UI later
- auditors still get the same signed, portable proof artifact

## Adoption Path

### Developers

Fastest path:

1. `pip install "epi-recorder[gateway]"`
2. `epi gateway serve`
3. point AI traffic or an adapter at the gateway

Then expand to SDK or framework instrumentation where deeper capture is needed.

### Reviewers

Use the browser and Decision Ops surface:

- open case
- read plain-language trust state
- confirm or dismiss issues
- export review and reports

### Auditors

Use:

- signed `.epi` artifacts
- embedded review record
- explicit trust class
- stable verification output

## Reliability Rules

For EPI to be infrastructure-grade, the capture layer should always prefer:

- append-only writes
- generated IDs at ingress
- explicit provenance labels
- fail-open or fail-closed modes chosen by the integrator
- eventual `.epi` export rather than forcing cloud dependence

## What This Repo Should Do Next

Near-term:

- keep hardening the shared capture schema in `epi_core`
- make `epi_gateway` the easiest developer capture path
- normalize OpenAI-compatible, Anthropic, Gemini, LiteLLM, and generic provider payloads into one event model
- expose provider-compatible proxy routes that still land in the same capture schema
- keep `.epi` the portable proof format
- let `web_viewer` and future enterprise surfaces consume the same underlying case data

Longer-term:

- add a central case store
- add auth/RBAC
- add reviewer assignments
- add enterprise policy distribution
- add hosted and self-hosted control plane deployments
