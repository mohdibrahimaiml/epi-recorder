# EPI DOC

Author: Codex
Date: 2026-04-01
Repo analyzed: `C:\Users\dell\epi-recorder`
Release line observed: `v4.0.1`

---

## 1. What EPI is, in plain language

EPI is an AI evidence system.

Its job is to turn an AI run into one portable, reviewable, tamper-evident artifact:

- capture what happened
- preserve the execution trail
- optionally evaluate it against rules
- optionally attach a human review
- let anyone later verify that the artifact was not modified after sealing

The main output is a `.epi` file.

That `.epi` file is the center of the whole product.

Everything else in the repo exists to do one of these jobs:

1. create `.epi`
2. inspect `.epi`
3. verify `.epi`
4. review `.epi`
5. share `.epi`
6. export `.epi` into a business-readable report

The repo is not just a Python package. It is really a full product stack:

- a Python SDK
- a core packaging and trust layer
- a CLI
- a browser review app
- a self-hosted gateway
- a hosted share flow
- starter kits and demos
- a pytest plugin
- release and packaging scripts

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
- `epi_core/` = artifact, schema, trust, policy, storage
- `epi_cli/` = human-facing terminal workflows
- `web_viewer/` = human-facing browser workflows
- `epi_gateway/` = live capture, shared workspace, export, share, approval callbacks

If you remember one sentence, remember this:

EPI turns an AI workflow into a sealed case file that can be reviewed and verified later.

---

## 3. What is actually important in this repo

This repo is large and contains both core code and a lot of generated or historical material.

Approximate current scope from direct repo inspection:

- `epi_recorder/`: 88 files, 20 Python files, about 6.9k text lines
- `epi_core/`: 100 files, 20 Python files, about 8.3k text lines
- `epi_cli/`: 97 files, 20 Python files, about 7.7k text lines
- `epi_gateway/`: 29 files, 6 Python files, about 2.8k text lines
- `web_viewer/`: 4 files, about 7.6k text lines
- `tests/`: 236 files, 58 Python files, about 15k text lines
- `examples/`: 112 files, 33 Python files, many notebooks and demos

The most important top-level folders are:

- `epi_recorder/`
- `epi_core/`
- `epi_cli/`
- `epi_gateway/`
- `web_viewer/`
- `tests/`
- `examples/`
- `docs/`

The rest matters, but it is secondary, historical, generated, or support tooling.

---

## 4. Top-level repo map

### Core runtime packages

- `epi_recorder/`
- `epi_core/`
- `epi_cli/`
- `epi_gateway/`
- `epi_analyzer/`
- `pytest_epi/`

### Browser / desktop surfaces

- `web_viewer/`
- `epi_viewer_static/`
- `epi-viewer/`
- `epi_web_verifier/`

### Product docs and examples

- `docs/`
- `examples/`

### Release / packaging / deployment

- `installer/`
- `scripts/`
- `pyproject.toml`
- `MANIFEST.in`
- `Dockerfile`
- `docker-compose.yml`
- `docker-compose.prod.yml`
- `Caddyfile`

### Public site related

- `epi-official-site/`
- `EPI-OFFICIAL/`
- `website/`
- `website_bundle/`

### Generated / local / non-source directories

- `.epi/`
- `.epi-temp/`
- `.epi_associate/`
- `.epi-shared-workspace/`
- `epi-recordings/`
- `evidence_vault/`
- `build/`
- `dist/`
- `htmlcov/`
- `.tmp-*`
- `.pytest-*`

These generated directories are important to understand operationally, but they are not the core source code.

---

## 5. The main product surfaces

There are two major runtime modes.

### Mode A: Local artifact mode

This is the simplest and most important mode.

Flow:

1. your Python workflow runs inside `record(...)`
2. steps are logged
3. environment snapshot is captured
4. EPI packs the workspace into `.epi`
5. EPI optionally signs the manifest
6. you open it with `epi view`, verify with `epi verify`, export with `epi export-summary`

This mode requires no server.

### Mode B: Gateway mode

This is the shared / live mode.

Flow:

1. an app posts structured events to the gateway
2. the gateway persists them
3. the gateway projects them into a case store
4. reviewers can open cases through the shared workspace
5. cases can be exported back into `.epi`
6. hosted share links can expose the raw artifact safely

This mode is what enables:

- browser team review
- hosted share links
- approval callbacks
- webhook / email approval notifications
- shared case inboxes

---

## 6. The most important nouns in the codebase

To understand EPI, you need to understand these data objects.

### `.epi`

A ZIP-based artifact containing:

- `mimetype`
- `steps.jsonl`
- `environment.json`
- optional `analysis.json`
- optional `policy.json`
- optional `policy_evaluation.json`
- optional `review.json`
- optional `artifacts/...`
- `viewer.html`
- `manifest.json`

### Manifest

Defined in `epi_core/schemas.py` as `ManifestModel`.

This is the metadata and trust header for the artifact.

It carries:

- version
- workflow ID
- created time
- file hashes
- embedded public key
- signature
- analysis status
- business metadata like goal, notes, metrics, tags

### Step

Defined in `epi_core/schemas.py` as `StepModel`.

Each step is one event in the timeline.

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
- `test.start`
- `test.result`

### Capture event

Defined in `epi_core/capture.py` as `CaptureEventModel`.

This is the normalized event shape used by the gateway and open ingestion layer.

### Policy

Defined in `epi_core/policy.py` as `EPIPolicy`, `PolicyRule`, and related models.

This is the rulebook for deterministic fault and compliance analysis.

### Case

Defined mainly through models in `epi_core/case_store.py`.

A case is the shared reviewer-side representation of one workflow or decision trail.

---

## 7. `epi_recorder/`: the Python capture SDK

This package is the main developer API.

Important files:

- `epi_recorder/__init__.py`
- `epi_recorder/api.py`
- `epi_recorder/async_api.py`
- `epi_recorder/patcher.py`
- `epi_recorder/environment.py`
- `epi_recorder/bootstrap.py`
- `epi_recorder/wrappers/`
- `epi_recorder/integrations/`
- `epi_recorder/analytics/`

### `epi_recorder/__init__.py`

This is the public package surface.

It exports:

- `record`
- `EpiRecorderSession`
- `AgentRun`
- `get_current_session`
- wrapper helpers like `wrap_openai` and `wrap_anthropic`

It also lazily exposes `AgentAnalytics`.

One important implementation detail:

- on Windows, import-time code tries to register `.epi` file association silently

So the package is not just a pure library import. It also tries to improve local UX on Windows.

### `epi_recorder/api.py`

This is the single most important Python file in the repo.

It contains:

- `_normalize_archive_path`
- `_warn_if_local_policy_invalid`
- `_StdStreamCapture`
- `AgentRun`
- `EpiRecorderSession`
- `record`
- path resolution helpers
- current-session helpers

#### `record(...)`

This is the convenience front door.

It supports:

- direct context manager use
- decorator use
- auto-generated artifact names
- metadata like `goal`, `notes`, `metrics`
- optional signing
- print capture

#### `EpiRecorderSession`

This is the local recording context manager.

What it does in `__enter__`:

1. creates a writable temp workspace
2. warns if `epi_policy.json` exists but is invalid
3. creates a `RecordingContext`
4. installs it as the active recording context
5. optionally patches libraries in legacy mode
6. logs `session.start`
7. optionally captures stdout/stderr

What it does in `__exit__`:

1. captures environment
2. logs `session.error` if an exception happened
3. logs `session.end`
4. finalizes the recording context
5. builds a `ManifestModel`
6. calls `EPIContainer.pack(...)`
7. signs the artifact if enabled
8. prints a human-readable session summary
9. cleans up temp workspace and recording context

#### `AgentRun`

This is the higher-level agent-shaped helper inside a recording session.

It gives structured methods such as:

- `plan`
- `message`
- `tool_call`
- `tool_result`
- `decision`
- `approval_request`
- `approval_response`
- `handoff`
- `memory_read`
- `memory_write`
- `pause`
- `resume`
- `error`

This is one of the clearest examples of EPI moving from raw event logging toward product-shaped AI workflow evidence.

#### Artifact attachment

`log_artifact(...)` lets a session copy external files into the case workspace so they travel inside the archive.

This logic now validates archive paths and prevents:

- empty archive paths
- absolute paths
- traversal like `..`
- reserved root names like `manifest.json`

That matters because attached files become part of the sealed evidence structure.

### `epi_recorder/patcher.py`

This file provides the recording context plumbing plus monkey-patching hooks.

Important roles:

- store active recording context
- patch OpenAI / Gemini / requests paths
- support legacy automatic capture

This is older-style capture infrastructure. The codebase is gradually leaning more toward wrappers and explicit logging rather than broad monkey patching.

### `epi_recorder/environment.py`

Captures:

- OS info
- Python info
- installed packages
- selected environment variables
- working directory

This becomes `environment.json`.

### `epi_recorder/wrappers/`

This is the safer modern capture path for model clients.

Important wrappers:

- `openai.py`
- `anthropic.py`
- `base.py`

These wrap client objects and turn model operations into EPI steps.

### `epi_recorder/integrations/`

This contains framework-specific hooks for:

- LangChain
- LangGraph
- LiteLLM
- OpenAI Agents
- OpenTelemetry

These are important because EPI is not only a manual logging library; it also wants to meet existing AI stacks where they already are.

### `epi_recorder/async_api.py`

Provides async recorder support through `AsyncRecorder`.

### `epi_recorder/bootstrap.py`

This is startup capture plumbing for bootstrap and stream capture behavior.

### `epi_recorder/analytics/`

Optional analytics surface that depends on `pandas`.

This is deliberately lazy-loaded so it does not make basic `import epi_recorder` fail.

---

## 8. `epi_core/`: the artifact and trust engine

This is the technical heart of the product.

Important files:

- `schemas.py`
- `container.py`
- `trust.py`
- `serialize.py`
- `policy.py`
- `fault_analyzer.py`
- `capture.py`
- `case_store.py`
- `review.py`
- `artifact_inspector.py`
- `workspace.py`
- `storage.py`
- `auth_local.py`
- `platform/associate.py`

### `schemas.py`

Defines the two foundational data models:

- `ManifestModel`
- `StepModel`

Notable current manifest fields:

- `spec_version`
- `workflow_id`
- `created_at`
- `cli_command`
- `env_snapshot_hash`
- `file_manifest`
- `public_key`
- `signature`
- `analysis_status`
- `analysis_error`
- `goal`
- `notes`
- `metrics`
- `approved_by`
- `tags`

The `analysis_status` field is important because the artifact now explicitly tells you whether deterministic analysis:

- completed
- was skipped
- failed

That prevents silent ambiguity.

### `container.py`

This file turns a recording workspace into a `.epi`.

Important responsibilities:

- hash files
- build `file_manifest`
- generate and embed `viewer.html`
- optionally run deterministic analysis before packing
- optionally embed policy and policy evaluation
- sign the manifest before baking the viewer
- pack ZIP members in the correct order

Key design choices:

- `mimetype` is written first and uncompressed
- `manifest.json` is written last
- `viewer.html` is generated from the current browser viewer assets
- `viewer.html` is intentionally excluded from `file_manifest`
- `manifest.json` obviously cannot include its own hash

#### Embedded viewer generation

`_create_embedded_viewer(...)` reads:

- `web_viewer/index.html`
- `web_viewer/app.js`
- `web_viewer/styles.css`
- `epi_viewer_static/crypto.js`

It then injects:

- manifest
- steps
- analysis
- policy
- policy evaluation
- review
- environment
- stdout/stderr
- raw file bytes

So every `.epi` carries a self-contained offline browser UI.

### `trust.py`

This implements Ed25519 signing and verification.

Important functions:

- `sign_manifest`
- `verify_signature`
- `decode_embedded_public_key`
- `verify_embedded_manifest_signature`
- `sign_manifest_inplace`
- `create_verification_report`

Trust model:

1. canonical hash of manifest data is computed
2. Ed25519 signs that hash
3. the public key is embedded in the manifest
4. later verification recomputes the hash and checks the signature

This gives:

- integrity
- signer identity
- tamper evidence

### `serialize.py`

This is where canonical hashing behavior lives.

It matters because signing only works reliably if serialization is deterministic.

### `policy.py`

This defines the rulebook language.

Key models:

- `PolicyScope`
- `ApprovalPolicy`
- `PolicyRule`
- `EPIPolicy`

Built-in profiles include:

- `finance.loan-underwriting`
- `finance.refund-agent`
- `insurance.claim-denial`
- healthcare-oriented profiles

Supported rule families:

- `constraint_guard`
- `sequence_guard`
- `threshold_guard`
- `prohibition_guard`
- `approval_guard`
- `tool_permission_guard`

This is not an LLM policy engine. It is a deterministic structured rule system.

### `fault_analyzer.py`

This is the deterministic analysis layer.

It performs both:

- heuristic analysis
- policy-grounded analysis

It is explicitly designed to be:

- deterministic
- conservative
- additive
- non-LLM

It produces:

- `analysis.json`
- `policy_evaluation.json`

Important concepts in the analyzer:

- primary fault
- secondary flags
- review required
- plain-English summaries
- coverage metrics
- policy pass/fail outputs

The analyzer is one of the most product-important files in the repo because it turns raw step data into human-meaningful findings.

### `capture.py`

Defines the shared open ingestion event schema:

- `CaptureEventModel`
- `CaptureBatchModel`
- `CaptureProvenanceModel`

This is the contract between SDK-like emitters and the gateway.

### `case_store.py`

This is one of the biggest and most important files in the whole repo.

It implements the gateway-backed shared reviewer database on top of SQLite.

It handles:

- case summaries
- case payloads
- comments
- activities
- review records
- auth users and sessions
- open session tracking
- event-to-case projection
- case export back into `.epi`
- spool replay

This file is where EPI stops being "just an artifact format" and becomes a review system.

Important internal ideas:

- derive case IDs from workflow or trace context
- normalize workflow status
- summarize a case from captured events
- project event batches into shared state
- export shared cases back into portable artifacts

### `review.py`

This manages `review.json`.

It supports:

- reading review records
- creating review entries
- appending human review to existing artifacts

Review is additive. It does not replace the original sealed evidence.

### `artifact_inspector.py`

This is a utility layer for validating that an artifact is structurally safe and shareable before upload or export operations.

### `workspace.py`

This provides workspace safety and temp-directory creation.

It is important because many flows create temp workspaces and Windows temp-directory behavior can be unreliable.

### `storage.py`

Contains `EpiStorage`, which is a lower-level storage abstraction used by parts of the system.

### `platform/associate.py`

This is Windows integration code for `.epi` file association and launch behavior.

It is important operationally because EPI strongly cares about double-click usability on Windows.

---

## 9. `epi_cli/`: the human terminal interface

This package is the practical user front door.

Important files:

- `main.py`
- `view.py`
- `verify.py`
- `share.py`
- `export_summary.py`
- `policy.py`
- `connect.py`
- `gateway.py`
- `run.py`
- `review.py`
- `ls.py`
- `debug.py`

### `main.py`

This is the Typer entry point for the `epi` command.

It does several things:

- shows help and version
- wires together subcommands
- manages first-run ergonomics
- performs Windows association health checks in limited safe paths
- contains the `demo` and `init` style front-door logic

The CLI help text itself is product-shaped. It is not just a technical menu.

It tries to lead the user into:

- `epi demo`
- `epi connect open`
- `epi view`
- `epi verify`
- `epi share`

### `view.py`

This is the local browser viewer launcher.

It:

1. resolves a `.epi` file by exact path or by name from `epi-recordings/`
2. unpacks it
3. rebuilds or refreshes viewer content
4. injects verification context
5. preloads case payload data
6. opens the browser

Important behavior:

- uses `Path.as_uri()` for safer browser launching
- supports bare artifact-name resolution
- includes local share hints after opening

### `verify.py`

This performs CLI-side trust verification.

It produces:

- human-readable trust output
- optional JSON output
- saved verification report output

### `share.py`

This uploads a `.epi` to the gateway share API.

It does:

- local artifact preflight
- size check
- shareability validation
- POST to `/api/share`
- returns the hosted URL
- opens the browser unless `--no-open` is passed

### `export_summary.py`

This builds the regulator-facing Decision Record.

It reads a `.epi` and produces:

- text summary
- printable HTML summary

Current design emphasis:

- a real Decision Record, not just raw logs pasted into HTML
- plain business-language sections
- print-ready output
- use by compliance / audit / review stakeholders

### `policy.py`

This is the rulebook CLI.

It supports:

- `epi policy init`
- `epi policy profiles`
- `epi policy validate`
- `epi policy show`
- browser-side policy editor generation

It is where guided policy creation lives, including business-shaped starter profiles.

### `connect.py`

This is the local review workspace and connector-bridge orchestration layer.

It can:

- start a local shared workspace
- host browser review surfaces
- bridge to mock or live systems
- export starter packs for real workflows
- persist browser workspace state

This file is a major part of the "decision ops" direction inside the repo.

### `gateway.py`

CLI commands for self-hosted gateway operations like:

- serve
- export case
- add/list users
- backup
- export all

### `run.py`

This wraps execution of an instrumented Python script and helps detect the produced artifact.

It tries to make the "run my script and then open/verify the artifact" loop simpler.

### `review.py`

This is the human review CLI for appending review notes and trust output.

### `ls.py`

Lists local artifacts and summarizes them.

### `debug.py`

Debugging surface for mistake detection and agent run analysis.

This file recently had a release fix so `MistakeDetector` is stable at module scope for tests and runtime import behavior.

---

## 10. `epi_gateway/`: the live service layer

This package is the self-hosted backend.

Important files:

- `main.py`
- `worker.py`
- `share.py`
- `proxy.py`
- `approval_notify.py`
- `Dockerfile`

### `main.py`

This creates the FastAPI app and runtime settings.

Important concepts inside this file:

- gateway runtime settings from environment
- auth and local-user auth
- CORS
- capture endpoints
- proxy capture endpoints
- share endpoints
- case APIs
- approval callback endpoint
- rate limiting
- webhook and SMTP notification dispatch

The gateway runtime settings already include first-class support for:

- share limits
- R2 / S3-compatible object storage
- approval webhook URL
- approval webhook signing secret
- SMTP fallback

This means the gateway is not just a test utility anymore. It is a serious pilot backend.

### `worker.py`

This contains `EvidenceWorker`, the background persistence engine.

It is responsible for:

- batching captured events
- writing append-only spool files
- replaying spool on restart
- projecting events into SQLite via `CaseStore`
- exporting cases
- recovering orphan sessions

This is the operational heart of the gateway.

### `share.py`

This implements hosted artifact sharing.

Important components:

- `ShareMetadataStore`
- `FileShareObjectStore`
- `S3ShareObjectStore`
- `ShareService`

It handles:

- validation
- quota tracking
- expiry
- object storage
- share metadata
- hosted URL generation

### `proxy.py`

This contains proxy-relay helpers for OpenAI-like and Anthropic-like traffic.

It lets the gateway act as a capture-aware proxy.

### `approval_notify.py`

This sends:

- signed approval webhooks
- SMTP approval emails

This is what makes the gateway's human-in-the-loop story real instead of simulated.

---

## 11. `web_viewer/`: the browser review application

This is the canonical browser UI.

Files:

- `web_viewer/index.html`
- `web_viewer/app.js`
- `web_viewer/styles.css`
- `web_viewer/README.md`

This app is much larger than a simple file previewer.

It contains:

- inbox view
- case view
- optional rules view
- optional reports view
- setup wizard
- connector profile handling
- shared workspace auth
- shared workspace refresh
- local review drafting
- review signing
- report downloads
- policy editor
- case export helpers
- trust display
- preloaded artifact mode

### What it really is

It is a case review workstation implemented in browser code.

It can work in several modes:

- local `.epi` open
- preloaded artifact open from `epi view`
- embedded artifact mode from `viewer.html`
- shared workspace mode
- hosted share page support through shared verifier logic

### Why it matters

This file is where EPI becomes legible to non-technical reviewers.

The local and hosted trust story are only useful if a human can understand the case.

---

## 12. `epi_viewer_static/`

This contains static viewer-side crypto support, especially browser verification helpers.

It is embedded into artifacts during `viewer.html` generation.

---

## 13. `pytest_epi/`

This turns EPI into testing infrastructure.

Important file:

- `pytest_epi/plugin.py`

When `pytest --epi` is enabled:

1. each test gets an EPI session
2. test metadata is logged
3. test result is logged
4. failing test artifacts are kept by default
5. passing artifacts can also be retained with `--epi-on-pass`

This is strategically important because it makes EPI useful not just for demos and production runs, but also for CI and regression evidence.

---

## 14. `epi_analyzer/`

This is a smaller separate analysis package.

The main file is `epi_analyzer/detector.py`.

It powers debugging and mistake-detection style workflows beyond the core deterministic artifact packer.

---

## 15. Examples and starter kits

The `examples/` tree is large.

It contains:

- simple API examples
- demo scripts
- live demos
- notebooks
- investor materials
- starter kits

### Important starter kits

#### `examples/starter_kits/refund/`

Refund-oriented workflow.

#### `examples/starter_kits/insurance_claim/`

This is the current flagship design-partner starter kit.

It contains:

- `agent.py` for offline simulated approval
- `agent_live_approval.py` for real gateway-backed approval
- `epi_policy.json` for insurance claim-denial rules
- a dedicated README

This kit is product-important because it translates EPI from "generic artifact system" into a concrete regulated-industry workflow.

---

## 16. Tests

The `tests/` directory is large and broad.

It covers:

- core schemas
- packing and unpacking
- trust and verification
- CLI behavior
- Windows association logic
- gateway worker behavior
- gateway share flow
- approval notification flow
- viewer behavior
- starter kits
- release audit and packaging hygiene

This is a strong sign that the repo is not just a prototype anymore. It is trying to enforce release discipline.

Important release quality themes visible in tests:

- version consistency
- wheel and sdist content hygiene
- installer behavior
- starter-kit integrity
- hosted share correctness
- policy analysis correctness

---

## 17. Packaging, release, and deployment

### `pyproject.toml`

This defines:

- package metadata
- dependencies
- optional extras
- entry points
- pytest plugin registration

The CLI entry point is:

- `epi = epi_cli.main:cli_main`

### `MANIFEST.in`

Controls sdist contents.

This is important because the repo contains notebooks, demos, generated dirs, and multiple site folders, so packaging hygiene matters.

### `scripts/release-gate.ps1`

This is the release discipline script.

It performs:

1. version checks
2. targeted consistency tests
3. full test suite
4. wheel and sdist build
5. `twine check`
6. sdist audit
7. wheel audit

This is a serious release gate, not a cosmetic script.

### `installer/windows/setup.iss`

This is the Windows installer configuration.

That matters because EPI wants:

- `epi.exe`
- file association
- better double-click behavior
- friendlier local adoption

### Docker and self-hosting

Relevant files:

- `Dockerfile`
- `docker-compose.yml`
- `docker-compose.prod.yml`
- `Caddyfile`
- `epi_gateway/Dockerfile`

These support self-hosted gateway and reverse-proxy style deployment.

---

## 18. Public site code inside this repo

This repo currently contains several public-site related directories:

- `epi-official-site/`
- `EPI-OFFICIAL/`
- `website/`
- `website_bundle/`
- `epi_web_verifier/`

The important practical truth is:

- `epi-official-site/` is the current authoritative public-site working copy
- `website/` is an older lighter site mirror
- `epi_web_verifier/` is an older standalone verifier surface
- `EPI-OFFICIAL/` is another nested site repo copy

These are important for understanding the repo, but they are not the main artifact engine.

The main product code still lives in the Python packages plus `web_viewer/`.

---

## 19. How the local workflow actually works

This is the most important execution path to understand.

### Local recording flow

```text
your script
  -> record(...)
    -> EpiRecorderSession.__enter__()
      -> create temp workspace
      -> install RecordingContext
      -> log session.start
      -> run your code
      -> log steps / artifacts / LLM calls / tool calls
    -> EpiRecorderSession.__exit__()
      -> capture environment
      -> log session.end
      -> finalize workspace
      -> build ManifestModel
      -> EPIContainer.pack(...)
      -> sign manifest
      -> write .epi
```

### What gets written during a run

Inside the temp workspace, EPI may write:

- `steps.jsonl`
- `environment.json`
- `stdout.log`
- `stderr.log`
- attached artifacts
- later generated analysis / policy files

### What happens during packing

`EPIContainer.pack(...)`:

1. initializes analysis status
2. optionally clears stale generated analysis files
3. loads policy if present
4. runs `FaultAnalyzer`
5. writes `analysis.json`
6. writes `policy.json` and `policy_evaluation.json` when applicable
7. hashes evidence files
8. updates `manifest.file_manifest`
9. signs the manifest if signer exists
10. bakes `viewer.html`
11. writes ZIP members

### What happens during verification

`epi verify`:

1. reads `manifest.json`
2. recomputes file hashes for `file_manifest`
3. validates integrity
4. verifies embedded public key and Ed25519 signature
5. prints trust output and optional JSON report

### What happens during viewing

`epi view`:

1. resolves the artifact path
2. unpacks it
3. builds preloaded case payload
4. injects trust context into viewer HTML
5. opens browser

---

## 20. How the gateway workflow works

Gateway mode is different.

### Event path

```text
client app
  -> POST /capture or related endpoint
    -> CaptureEventModel validation
    -> EvidenceWorker queue
    -> append-only spool batch
    -> CaseStore projection into SQLite
    -> shared case APIs
    -> export back to .epi if needed
```

### Recovery

The gateway is designed for restart safety through:

- spool replay
- projection replay
- orphan-session tracking
- orphan-session recovery

That means it is not just a simple memory server.

### Case export path

The gateway can export a case to `.epi`, so the live shared workspace and the portable artifact model stay aligned.

---

## 21. How sharing works

There are two sharing concepts.

### CLI share

`epi share file.epi`

This:

1. resolves the artifact
2. runs local artifact inspection
3. checks size and structure
4. uploads raw bytes to the gateway
5. receives a hosted URL
6. optionally opens it in the browser

### Gateway share backend

The gateway:

1. validates uploaded `.epi`
2. stores raw bytes in private storage
3. stores share metadata in SQLite
4. enforces expiry and quota limits
5. serves raw artifact bytes back to the hosted page

### Hosted page model

The hosted browser page does not need to execute the artifact's embedded viewer.

The safer design is:

- hosted page fetches raw `.epi`
- hosted page parses it client-side
- hosted page renders through trusted site code

That distinction matters a lot for safety.

---

## 22. How human review works

There are two review layers.

### Local artifact review

This is done through:

- browser review UI
- `epi review`
- optional signed `review.json`

### Gateway approval review

This is the live human-in-the-loop path.

Flow:

1. agent emits `agent.approval.request`
2. gateway stores the request
3. gateway sends webhook and/or email
4. reviewer clicks approve / deny callback URL
5. gateway records `agent.approval.response`
6. workflow continues

This is what turns approval from simulated logging into a real operational flow.

---

## 23. Policy and analysis logic

EPI policy is deterministic, not prompt-based.

That is an important philosophical point.

The analyzer checks captured steps against structured rules.

Examples:

- a fraud check must happen before denial
- amounts above threshold require human approval
- prohibited output patterns must never appear
- unapproved tool usage can be flagged

Outputs include:

- `analysis.json`
- `policy_evaluation.json`

The browser and Decision Record both depend on these files to explain what happened in plain language.

---

## 24. Trust model

EPI trust is built from two separate checks:

### Integrity

Do the files listed in `manifest.file_manifest` still match their original SHA-256 hashes?

### Signature

Does the Ed25519 signature still validate against the manifest's canonical hash and embedded public key?

Possible states include:

- signed and intact
- unsigned but intact
- tampered
- structurally broken

This is why EPI can say not just "it opens" but "it is still trustworthy" or "it was changed after sealing."

---

## 25. Browser UX philosophy in the current codebase

The current viewer direction is case-first, not raw-log-first.

That means the UI increasingly tries to present:

- inbox
- selected case
- human guidance
- plain-language decision summary
- trust state
- next action

And only then raw timeline detail.

This is visible especially in:

- `web_viewer/app.js`
- `epi_cli/export_summary.py`
- insurance starter-kit work
- hosted share page work

So the repo is moving from "debugging artifact viewer" toward "AI decision review system."

---

## 26. Windows-specific logic

The repo contains substantial Windows-specific work.

Why?

Because EPI wants `.epi` double-click to feel native.

Important components:

- `epi_core/platform/associate.py`
- CLI `associate` / `unassociate`
- installer config
- `epi.exe` path behavior
- browser launch behavior

Recent direction in the codebase:

- prefer direct executable association
- avoid normal runtime dependence on VBS/WSH for opening files
- keep repair behavior explicit and safer

This is a serious UX concern in the product, not a side detail.

---

## 27. What is generated versus what is source

When reading this repo, do not confuse generated runtime state with product source.

### Generated / runtime state

- `.epi-temp/`
- `.epi_associate/`
- `epi-recordings/`
- `evidence_vault/`
- `build/`
- `dist/`
- `htmlcov/`
- `.tmp-*`

### Source

- `epi_recorder/`
- `epi_core/`
- `epi_cli/`
- `epi_gateway/`
- `web_viewer/`
- `tests/`
- `scripts/`
- `examples/`

This distinction is important because the repo contains a lot of local operational residue.

---

## 28. What is mature versus what is transitional

### Mature / central

- local recording flow
- artifact packing
- trust verification
- browser viewing
- CLI command surface
- starter kits
- policy and analysis
- release gate and packaging discipline

### Transitional / mixed

- multiple site directories
- old verifier surfaces
- legacy patching paths
- older mirrors like `website/`
- multiple desktop/browser viewer variants

This is a codebase that has clearly evolved fast and contains both current architecture and older paths that are still present.

---

## 29. The single most important architectural truth

The repo is not best understood as "a logging library."

It is better understood as:

an evidence pipeline with a portable artifact at the center

That pipeline is:

1. capture
2. normalize
3. seal
4. verify
5. review
6. share

If you understand that, the folder structure starts making sense.

---

## 30. If you want to learn the codebase in the fastest correct order

Read in this order:

1. `README.md`
2. `pyproject.toml`
3. `epi_recorder/api.py`
4. `epi_core/schemas.py`
5. `epi_core/container.py`
6. `epi_core/trust.py`
7. `epi_core/policy.py`
8. `epi_core/fault_analyzer.py`
9. `epi_cli/main.py`
10. `epi_cli/view.py`
11. `epi_cli/verify.py`
12. `epi_cli/export_summary.py`
13. `epi_gateway/main.py`
14. `epi_gateway/worker.py`
15. `epi_core/case_store.py`
16. `web_viewer/index.html`
17. `web_viewer/app.js`
18. `examples/starter_kits/insurance_claim/`
19. `tests/`

That order teaches:

- what EPI promises
- how it captures
- how it seals
- how it proves trust
- how it explains the result to humans
- how it scales into shared workflows

---

## 31. Final summary

If I had to explain the entire repo in one paragraph:

`epi-recorder` is a full-stack AI evidence product centered on a portable `.epi` artifact. The `epi_recorder` package captures agent activity, `epi_core` turns it into a sealed and signed case file, `epi_cli` exposes practical workflows, `web_viewer` makes the case understandable to humans, and `epi_gateway` adds live ingestion, collaboration, approvals, and hosted sharing. Around that core are tests, starter kits, installers, and release tooling that make the system usable as real software rather than just a format experiment.

If I had to explain it in one sentence:

EPI is the evidence layer that turns an AI run into a portable, reviewable, cryptographically verifiable case file.
