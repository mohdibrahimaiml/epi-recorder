# EPI High-Risk Adoption Roadmap

## Goal

Make EPI the easiest way for teams around the world to create defensible case files for high-risk AI systems.

That means a team should be able to:

- instrument one consequential workflow in under 60 minutes
- produce a useful signed artifact on day one
- map EPI to their industry controls without inventing a new evidence model
- run in cloud, hybrid, or air-gapped environments
- export evidence for audit, incident review, and model-risk workflows without custom glue code

## Product Principles

- **Opinionated first mile**: make the first workflow easy even if the tenth workflow is more configurable.
- **Artifact-first interoperability**: keep the `.epi` file portable across vendors, regulators, and environments.
- **Policy before marketing**: ship concrete control packs instead of vague compliance claims.
- **Trust by default**: make signing, verification, and reviewer accountability work out of the box.
- **Workflow-centric packaging**: sell complete decision workflows, not generic AI plumbing.

## Success Criteria

- `epi init` can scaffold a production-shaped starter workflow by industry, workflow type, framework, and deployment mode.
- Every starter kit includes policy, sample artifacts, reviewer flow, and verifier output.
- Teams can generate JSON evidence exports that plug into GRC, SIEM, and ticketing systems.
- Viewer and review surfaces support localization and deployment in restricted environments.
- Enterprise users can centralize keys, policy distribution, search, retention, and approvals without changing the `.epi` artifact format.

## Workstream 1: Guided Onboarding and Starter Kits

### User outcome

A governance or platform team should be able to start with a named workflow such as underwriting, claims, refunds, or support escalation instead of starting from a blank script.

### Repo-level changes

- Extend `epi init` in `epi_cli/main.py` and split the setup wizard into a dedicated module such as `epi_cli/init.py`.
- Reuse `epi_recorder/bootstrap.py` to generate starter projects instead of only demo output.
- Add a tracked starter-kit home at `examples/starter_kits/`.
- Build the first starter kits:
  - `examples/starter_kits/refunds/`
  - `examples/starter_kits/claims/`
  - `examples/starter_kits/underwriting/`
  - `examples/starter_kits/support_escalation/`
- Each starter kit should contain:
  - workflow code
  - `epi_policy.json`
  - sample signed artifact
  - sample reviewed artifact
  - sample tampered artifact
  - reviewer walkthrough
  - deployment notes
- Add onboarding tests in `tests/test_main.py` and a new `tests/test_init_starter_kits.py`.

### Exit criteria

- A new user can run one command, answer a few prompts, and open a realistic artifact for their workflow.
- The generated project contains a policy-backed run and a reviewable artifact by default.

## Workstream 2: Policy Packs and Jurisdiction Profiles

### User outcome

Teams should not have to translate high-risk logging and approval requirements into raw JSON from scratch.

### Repo-level changes

- Add a new `policy_packs/` directory for reusable pack definitions.
- Extend `epi_cli/policy.py` so users can run commands such as:
  - `epi policy init --pack eu-high-risk`
  - `epi policy init --pack us-finance-model-risk`
  - `epi policy init --pack healthcare-human-review`
- Extend `epi_core/policy.py` to support pack metadata, versioning, and richer control annotations.
- Update [POLICY.md](./POLICY.md) with a "policy packs" section and industry-specific examples.
- Add golden-pack validation tests in a new `tests/test_policy_packs.py`.

### First packs

- EU high-risk logging and human oversight
- US financial approvals and exception review
- healthcare decision support review and escalation
- internal model-risk governance baseline

### Exit criteria

- A user can choose a pack, inspect the generated controls, and run a workflow without first becoming a policy-authoring expert.

## Workstream 3: Trust, Keys, and Verifier Outputs

### User outcome

Signing and verification should feel automatic for small teams and enterprise-ready for regulated deployments.

### Repo-level changes

- Extend `epi_cli/keys.py` with guided key bootstrap, rotation helpers, and clearer trust profiles.
- Extend `epi_core/trust.py` and `epi_core/container.py` to support pluggable signing backends.
- Add enterprise key-provider interfaces for local keys, cloud KMS, and HSM-backed signing.
- Extend `epi_cli/verify.py` with exportable machine-readable outputs such as:
  - `epi verify artifact.epi --json`
  - `epi verify artifact.epi --report out/verification.json`
- Improve trust explanation in `epi_viewer_static/app.js` so non-technical reviewers can understand why an artifact is signed, unsigned, or tampered.
- Add trust-regression tests in `tests/test_trust.py`, `tests/test_truth_consistency.py`, and `tests/test_view_verify_extended.py`.

### Exit criteria

- Small teams can sign immediately with safe defaults.
- Larger teams can plug EPI into enterprise key management without changing application code or artifact semantics.

## Workstream 4: Review Workflow and Audit Export

### User outcome

An analyst, reviewer, or auditor should be able to open one case file, see the control context, add a review decision, and export the result to surrounding systems.

### Repo-level changes

- Extend `epi_core/review.py` to support richer reviewer identity, role, rationale, and approval metadata.
- Extend `epi_cli/review.py` with structured review templates and reviewer role presets.
- Extend `epi_cli/view.py` and the embedded viewer so the primary case summary is visible before raw step inspection.
- Add a new export surface in `epi_cli` for JSON audit bundles that package:
  - manifest
  - policy
  - analysis
  - review
  - trust report
- Add interoperability adapters for SIEM, GRC, and ticketing workflows as JSON-first exports before building native connectors.
- Add review and export tests in `tests/test_review.py`, `tests/test_cli_integration.py`, and a new `tests/test_export.py`.

### Exit criteria

- A reviewer can go from artifact to recorded decision without custom scripting.
- An enterprise team can move a case file into surrounding governance systems with stable exports.

## Workstream 5: Deployment, Gateway, and Restricted Environments

### User outcome

Teams should be able to adopt EPI whether they run in SaaS, self-hosted, hybrid, or air-gapped environments.

### Repo-level changes

- Harden `epi_gateway/main.py`, `epi_gateway/worker.py`, and `epi_gateway/Dockerfile` as the sidecar or service path for enterprise capture.
- Add deployment docs for:
  - local development
  - containerized sidecar
  - Kubernetes
  - air-gapped installation
- Define retention and upload patterns that keep `.epi` portable even when a control plane is added later.
- Add operational smoke tests for the gateway path.

### Exit criteria

- EPI can be piloted without forcing a cloud architecture decision.
- The artifact model remains consistent across deployment models.

## Workstream 6: Localization and Global Readiness

### User outcome

Non-English-speaking reviewers and globally distributed teams should be able to use EPI without translating every interface and workflow themselves.

### Repo-level changes

- Add a `locales/` directory for viewer and CLI strings.
- Refactor `epi_viewer_static/index.html` and `epi_viewer_static/app.js` to separate content strings from UI logic.
- Add localized review labels, trust explanations, and export summaries.
- Add documentation templates that can be translated without rewriting technical content.
- Add localization snapshot tests for the viewer and key CLI flows.

### Exit criteria

- Trust states, review flows, and primary case summaries can be presented in major target languages.

## Open-Source vs Enterprise Split

Open-source EPI should remain the artifact-first system:

- recorder
- verifier
- offline viewer
- policy primitives
- review primitives
- starter kits

Enterprise EPI should add the operational control plane:

- policy distribution
- key management integrations
- search and retention
- RBAC
- approval workflow orchestration
- fleet-level evidence governance
- audit export pipelines

The open-source artifact format should remain stable across both.

## 30 / 60 / 90 Day Execution Plan

### First 30 days

- land `examples/starter_kits/README.md`
- redesign `epi init` around workflow selection
- build one flagship starter kit: underwriting or refunds
- add one policy pack: EU high-risk logging baseline
- add verifier JSON report export

### By 60 days

- ship three starter kits
- ship three policy packs
- add richer reviewer roles and exportable audit bundles
- harden the gateway deployment story

### By 90 days

- localize the viewer and core trust messages
- publish reference deployments for self-hosted and air-gapped teams
- define the enterprise control-plane boundary without breaking the open artifact model

## Immediate Backlog

- [ ] Create `examples/starter_kits/` contents, starting with one flagship workflow.
- [ ] Refactor `epi init` into a real starter-project generator.
- [ ] Add policy-pack support to `epi policy init`.
- [ ] Add verification report export to `epi verify`.
- [ ] Add JSON audit bundle export for review workflows.
- [ ] Harden the gateway path for enterprise capture.
- [ ] Extract viewer strings for localization.

## North Star

EPI becomes the default answer to this question:

> Show me the defensible case file for this AI decision.
