# EPI DOC v3.0.2

Author: Codex
Date: 2026-04-05
Repo analyzed: `C:\Users\dell\epi-recorder`
Release line observed: `v3.0.2`
PyPI status: `epi-recorder 3.0.2` published and live

---

## 1. What EPI is, in plain language

EPI is an evidence system for AI workflows.

Its job is to turn one AI run into one portable, reviewable, tamper-evident
artifact:

- capture what happened
- preserve the execution trail
- optionally evaluate it against policy
- optionally attach human review
- let anyone later verify that the artifact was not modified after sealing

The main output is a `.epi` file.

That `.epi` file is the center of the whole product.

Everything else in the repo exists to do one or more of these jobs:

1. create `.epi`
2. inspect `.epi`
3. verify `.epi`
4. review `.epi`
5. share `.epi`
6. export `.epi` into a business-readable report

This repo is not only a Python package. It is a full product stack:

- a Python SDK
- a core artifact and trust layer
- a CLI
- a browser review app
- a self-hosted gateway
- a hosted-share path
- starter kits and demos
- a pytest plugin
- packaging, installer, and release scripts

If you remember one sentence, remember this:

**EPI turns an AI workflow into a sealed, reviewable case file.**

---

## 2. The best mental model for the whole system

Think of EPI as five layers:

```text
Capture layer
    -> Artifact layer
        -> Trust layer
            -> Review layer
                -> Sharing / gateway layer
```

In repo terms:

- `epi_recorder/` = capture API
- `epi_core/` = artifact format, schemas, trust, policy, storage, review
- `epi_cli/` = human-facing terminal workflows
- `web_viewer/` = human-facing browser review UI
- `epi_gateway/` = live capture, shared review workspace, approval callbacks, hosted-share services
- `pytest_epi/` = test evidence capture for regressions

The key product idea is simple:

- a developer captures the run once
- EPI seals the run into a portable artifact
- reviewers, operators, or auditors can reopen that same case later
- trust checks and human decisions happen against the same artifact, not against reconstructed logs

That makes EPI closer to a decision record than to generic observability.

---

## 3. What is actually important in this repo

This repo is broad. It has core runtime code, browser code, gateway code, docs,
tests, examples, notebooks, packaging, and release tooling.

The folders that matter most are:

- `epi_recorder/`
- `epi_core/`
- `epi_cli/`
- `epi_gateway/`
- `web_viewer/`
- `pytest_epi/`
- `tests/`
- `examples/`
- `docs/`

The product-critical packages are:

### `epi_recorder/`

This is the local Python SDK and developer front door.

It answers:

- how a developer wraps a workflow with `record(...)`
- how steps are logged
- how async recording works
- how integrations and wrappers capture LLM/tool activity with minimal code changes

Important surfaces include:

- `record(...)`
- `async with record(...)`
- `log_step(...)`
- `alog_step(...)`
- `agent_run(...)`
- framework integrations and wrappers

### `epi_core/`

This is the technical heart of the system.

It answers:

- what a `.epi` file is
- how manifests, steps, environment, policies, and review records are represented
- how integrity and signatures work
- how policy evaluation and fault analysis work
- how case files are packed, unpacked, exported, and verified

If `epi_recorder` is the capture surface, `epi_core` is the product moat.

### `epi_cli/`

This is the main terminal UX.

It answers:

- how a user records, views, verifies, exports, reviews, shares, and connects artifacts
- how the browser review surface gets opened
- how policy files are created and explained
- how self-healing and developer workflows are exposed

The canonical entrypoint is `epi`.

### `epi_gateway/`

This is the live and shared-runtime layer.

It answers:

- how structured events can be posted over HTTP
- how a self-hosted shared review workspace works
- how approval callbacks and notifications work
- how hosted-share and gateway-backed review flows are supported

This matters when EPI moves from local artifact review to shared operational review.

### `web_viewer/`

This is the canonical browser review UI.

It powers:

- the default `epi view` review experience
- the embedded `viewer.html` baked into each `.epi`
- the extracted `viewer.html` produced by `epi view --extract`

Important nuance in `v3.0.2`:

- the generated embedded and extracted viewer HTML is intended to work offline
- the raw repo-hosted `web_viewer/index.html` is still a source app that expects companion assets nearby

### `pytest_epi/`

This is the pytest plugin surface.

It turns EPI into test evidence infrastructure:

- `pytest --epi`
- `--epi-on-pass`
- failing and passing tests can emit sealed case files instead of only text logs

### `examples/`

This is not filler.

It is where the product story becomes runnable:

- refund workflow
- insurance claim denial workflow
- notebooks and starter kits
- demo scripts for first-time users

These examples matter because EPI is easiest to understand through one concrete case.

---

## 4. Top-level repo map

### Core runtime packages

- `epi_recorder/`
- `epi_core/`
- `epi_cli/`
- `epi_gateway/`
- `epi_analyzer/`
- `pytest_epi/`

### Browser and review surfaces

- `web_viewer/`
- `epi_viewer_static/`
- `epi-viewer/`
- `epi_web_verifier/`

### Product docs and examples

- `docs/`
- `examples/`

### Packaging, installer, and release

- `installer/`
- `scripts/`
- `pyproject.toml`
- `MANIFEST.in`
- `Dockerfile`
- `docker-compose.yml`
- `docker-compose.prod.yml`
- `Caddyfile`

### Website and public-facing surfaces

- `website/`
- `website_bundle/`
- `docs/assets/`

### Generated or local runtime directories

- `.epi/`
- `.epi-shared-workspace/`
- `epi-recordings/`
- `evidence_vault/`
- `build/`
- `dist/`
- `htmlcov/`
- `.tmp-*`

These generated directories matter operationally, but they are not the core source.

---

## 5. The main product surfaces

There are two major runtime modes.

### Mode A: local artifact mode

This is the simplest and most important EPI path.

Flow:

1. a Python workflow runs inside `record(...)`
2. steps are logged
3. an environment snapshot is captured
4. EPI packs the run into `.epi`
5. the manifest is hashed and signed
6. the user opens it with `epi view`, verifies it with `epi verify`, exports it with `epi export-summary`, or shares it as needed

This mode requires no always-on server.

It is the current front door for:

- first-time developers
- bug report artifacts
- local replay and review
- tamper checks
- policy-grounded case review

### Mode B: gateway and shared review mode

This is the shared or live mode.

Flow:

1. an app posts structured events to the gateway
2. the gateway persists them into a case-oriented store
3. reviewers open cases through the shared workspace
4. human review, approval, and export happen against the same case model
5. cases can still be exported back to `.epi`

This mode enables:

- local team review workspaces
- LAN or temporary remote shared review
- approval callbacks
- shared review state
- live source record fetch during setup

Important caveat:

- some hosted or share flows depend on a deployed backend and should not be described as always available by default

For the supported local shared-review path today, see [CONNECT.md](CONNECT.md) and
[SELF-HOSTED-RUNBOOK.md](SELF-HOSTED-RUNBOOK.md).

---

## 6. The most important nouns in the codebase

To understand EPI, you need to understand these objects.

### `.epi`

A ZIP-based artifact representing one case file.

Common contents include:

- `mimetype`
- `manifest.json`
- `steps.jsonl`
- `environment.json`
- optional `analysis.json`
- optional `policy.json`
- optional `policy_evaluation.json`
- optional `review.json`
- optional `artifacts/...`
- `viewer.html`

The product promise is that this single file can move between developers,
reviewers, and auditors without losing context or trust state.

### `manifest.json`

This is the trust and metadata header for the artifact.

It carries:

- spec version
- workflow ID
- timestamps
- file hashes
- signature metadata
- trust-related fields
- business metadata such as goal, notes, metrics, and tags

### `steps.jsonl`

This is the event timeline.

Each line is one structured step in the case.

Important kinds include:

- `session.start`
- `session.end`
- `agent.run.start`
- `agent.run.end`
- `tool.call`
- `tool.response`
- `llm.request`
- `llm.response`
- `agent.approval.request`
- `agent.approval.response`
- `agent.decision`
- `session.error`

This file is the narrative spine of the case.

### `environment.json`

This is the environment snapshot.

It captures:

- OS metadata
- Python version
- installed packages
- runtime context useful for reproduction

That matters because a trustworthy AI bug report is not only the prompt and output.
It is also the execution environment.

### `policy.json` and `policy_evaluation.json`

These files matter when EPI is used for governed workflows.

They let the same case file answer:

- what rules were in effect
- which rules passed
- which rules failed
- what the analyzer concluded

This is especially important in insurance, approvals, refunds, and other
consequential workflows.

### `review.json`

This is the human review layer.

It lets a reviewer attach structured review notes and outcomes without rewriting
the original captured evidence.

That additive review model is one of the compliance-critical parts of the system.

### `viewer.html`

This is the browser review surface.

In practical terms, it is what turns a case file into something a reviewer can
actually use.

In `v3.0.2` the important change is:

- generated `viewer.html` now inlines the JSZip runtime instead of relying on a remote CDN script
- extracted review HTML is now intended to work in offline and air-gapped environments

---

## 7. What changed from `3.0.0` to `3.0.2`

The release line tells a useful product story.

### `3.0.0`

`3.0.0` established the stable evidence release line, but it still had front-door
gaps when judged as a strict first-time-user product from clean PyPI.

Those gaps mattered because EPI is only as credible as the first artifact a new
user can actually create, open, and trust.

### `3.0.1`

`3.0.1` was the front-door reliability patch.

It fixed the major first-user blockers:

- packaged browser viewer assets
- LangChain callback stability
- insurance policy threshold alignment with public example data
- threshold analyzer realism for investigation-vs-decision steps

That made `3.0.1` the correct public launch target instead of `3.0.0`.

### `3.0.2`

`3.0.2` closes the remaining offline extracted-viewer gap.

The key fix:

- `epi view --extract` now vendors and inlines `jszip.min.js` into generated `viewer.html`
- extracted review HTML no longer depends on a remote JSDelivr script to unpack case data
- the release audit now checks for the vendored viewer runtime asset in the package

In product terms:

- `3.0.1` made the front door reliable
- `3.0.2` made the extracted browser review artifact align with the offline and air-gapped promise

For the exact release note wording, see [CHANGELOG.md](../CHANGELOG.md).

---

## 8. Current validation and release state

This section is intentionally factual, not marketing language.

### What is concretely true now

- `epi-recorder 3.0.2` is published on PyPI
- the current `main` release line passed the GitHub `Release Gate`
- the release gate covered:
  - targeted consistency tests
  - the full test suite
  - wheel and source-distribution build
  - packaging audits
- the Windows installer version mismatch that briefly broke the gate was corrected before the final `3.0.2` release state

### External-user validation status

A strict external-user validation suite was rerun from a clean temp workspace
using a PyPI-installed `epi-recorder 3.0.2` environment and no API keys.

As written, that strict harness reported:

- 19 tests passed directly
- 1 test remained red

That pass confirmed, again, that the major product surfaces work from a clean
install:

- basic recording
- metadata capture
- `AgentRun` flow
- LangChain integration
- offline OpenAI wrapper construction
- policy initialization
- policy failure detection
- policy-compliant path
- tamper detection
- Decision Record export
- artifact attachment
- multiple recordings in one script
- error handling
- CLI help surfaces
- environment capture
- async recording
- pytest plugin behavior
- `epi demo`
- additive review append

Important nuance:

- the strict harness still reports one red item in its browser-viewer test because it flags any literal `http://` or `https://` string anywhere in extracted HTML
- that is broader than the actual `3.0.2` release requirement, which was to remove external script dependencies from generated viewer HTML
- focused verification of the extracted `viewer.html` confirmed the `3.0.2` fix target: no external `<script src=...>` dependencies remain, and the JSZip runtime is inlined

So the honest release summary is:

- the substantive `3.0.2` extracted-viewer bug is fixed
- the automated external harness still contains an overly broad HTML URL check that should be tightened in a future pass

This is the right way to describe the current shipped status without pretending the harness itself is already perfect.

---

## 9. What EPI is ready for now

As of `v3.0.2`, EPI is ready for serious local-first use as an evidence and
review tool for consequential AI workflows.

What it is clearly ready for:

- capturing AI workflow evidence into one portable artifact
- cryptographic integrity and signature verification
- policy-grounded workflow review
- browser-based case inspection
- printable business-facing Decision Record export
- offline extracted browser review HTML
- pytest-based regression evidence
- human review append without rewriting the original evidence

Who can use it today:

- developers debugging AI workflows
- teams running governed approval or denial workflows
- operators reviewing one decision case at a time
- compliance or risk reviewers who need a portable case file instead of raw logs

The strongest product fit today is not generic model experimentation.

It is workflows where someone may later ask:

- what happened
- why did the system decide this
- who approved it
- what rules were in effect
- can we trust this artifact

---

## 10. What should still be caveated

EPI should still be described honestly in a few areas.

### Hosted sharing

Hosted sharing is deployment-dependent.

The local product and local browser review flow are real and validated. A hosted
share link still depends on the appropriate backend being deployed and configured.

That is why the docs should keep making a distinction between:

- local artifact review
- local shared review workspace
- deployment-backed hosted sharing

### Raw source viewer vs generated offline viewer

The offline guarantee applies to:

- the embedded viewer packaged into a `.epi`
- the extracted `viewer.html` produced by `epi view --extract`

It does **not** mean that the raw source file `web_viewer/index.html` is itself a
single self-contained artifact.

### Live model validation

The offline and local-first paths have been exercised heavily.

Any live-model or hosted integration claim should still be tied to the exact pass
that validated it, especially when credentials or external services are involved.

---

## 11. Recommended mental model for the product and for buyers

The best short description of EPI is:

**EPI is a tamper-evident decision record for AI workflows.**

That is a better framing than:

- generic logging
- generic tracing
- generic observability

Why that framing works:

- the center is the decision case, not only the telemetry stream
- the artifact is portable and reviewable later
- policy and review are first-class
- trust and tamper evidence are built into the artifact model

The strongest buyers or internal champions are likely to be teams that feel the
pain of consequential AI actions:

- refunds
- claim denials
- approvals
- escalations
- customer-impacting workflow decisions

Those teams do not only need to know that a run happened.

They need a case file they can reopen, verify, explain, and sign off on later.

That is where EPI is strongest.

---

## 12. The practical starting paths

For a developer, the easiest first path is:

1. `pip install epi-recorder`
2. `epi demo`
3. `epi view <artifact>`
4. `epi verify <artifact>`

For a governed workflow team, the practical next path is:

1. capture a workflow with `record(...)`
2. define an `epi_policy.json`
3. run the workflow and inspect policy output
4. export a Decision Record
5. attach human review

For a team-review workflow, the practical local path is:

1. start `epi connect open`
2. open the browser workspace
3. review cases locally or on the LAN
4. export reviewed case files back to `.epi`

---

## 13. Related docs

Use this document as the flagship current-state explainer.

Use these docs when you want a narrower or more operational view:

- [CLI Reference](CLI.md)
- [Policy Guide](POLICY.md)
- [Self-Hosted Runbook](SELF-HOSTED-RUNBOOK.md)
- [Codebase Walkthrough](EPI-CODEBASE-WALKTHROUGH.md)
- [External User Readiness Report v3.0.1](archive/EXTERNAL-USER-READINESS-REPORT-v3.0.1.md)
- [Changelog](../CHANGELOG.md)

The relationship is:

- this doc explains the product and codebase as they exist in the shipped `3.0.2` line
- the walkthrough is a practical repo map
- the `v3.0.1` readiness report is historical launch evidence for that release
- the changelog is the canonical release-by-release change log

---

## 14. Final plain-language summary

EPI is now best understood as infrastructure for portable AI case files.

It captures what happened, seals it into a `.epi` artifact, lets policy and human
review sit on top of the same evidence, and gives the next person a way to verify
that the case was not altered.

`v3.0.1` made the first-user experience reliable.
`v3.0.2` finished the offline extracted-viewer correction.

That means the core promise is now much tighter:

- one run
- one artifact
- one browser review surface
- one trust story

And that is the right mental model for both the product and the repo.
