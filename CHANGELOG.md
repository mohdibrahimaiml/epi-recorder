# Changelog

All notable changes to EPI Recorder are documented here.

EPI follows [Semantic Versioning](https://semver.org/) and treats version changes as
**corrections to evidence guarantees**, not just feature updates.

---

## [4.0.2] - 2026-05-02

### Viewer Consistency & AGT Interoperability Release

#### Fixed

- **Eliminated stale "old viewer" across all open paths** — `_open_viewer()` in `epi_cli/run.py` was using a throwaway temp dir (`epi_view_<uuid>`) and regenerating the legacy embedded viewer (`epi-data` format). It now uses the persistent viewer cache (`~/.epi/view-cache/`) and the current decision-ops viewer (`epi-preloaded-cases` format), matching `epi view` behavior.
- **`EPIContainer._create_embedded_viewer()` now bakes the new viewer format** — the embedded `viewer.html` inside every `.epi` artifact now uses the `epi-preloaded-cases` payload (`cases[]` + `ui` config) instead of the legacy flat `epi-data` format. This fixes:
  - Windows double-click VBS fallback
  - `epi extract` output
  - `epi refresh-viewer` output
  - Offline/email sharing of the baked-in viewer

#### Added

- AGT export features and interoperability adapters:
  - workspace and archive exporters in `epi_recorder.integrations.agt.exporter`
  - `EPIContainer.pack(..., embed_agt=True)` to optionally embed `artifacts/agt_export.json` into `.epi` artifacts
  - identity resolution using the local `epi_cli.identity` mapping to populate AGT `agent` fields
  - compact `agt_compat` summary block in `policy_evaluation.json` for downstream governance systems
- Demo and pitch assets: `demo_assets/README.md` and `scripts/package_demo.py` to create a demo bundle
- Unit tests and automation: added `tests/test_policy_evaluation_agt_compat.py`, `tests/test_workspace_to_agt_exporter.py`, `tests/test_export_identity_resolution.py`, and the reusable verifier `tests/verify_3layer.py`

#### Changed

- Documentation and examples updated to describe AGT export, embedding, and identity mapping workflows

#### Notes

- This release focuses on EPI-side interoperability for AGT without modifying AGT itself; features are opt-in and additive.
- The viewer fix is a **correction to evidence guarantees** — previously, auto-open paths (`epi run`, `epi init`) and the baked-in viewer could display stale or incomplete verification context. All paths now render the same current decision-ops UI.

---

## [4.0.1] - 2026-04-12

### Go-To-Market Layer

#### Added

- **Privacy-first opt-in telemetry**
  - `epi telemetry status|enable|disable|test` now manages local opt-in state
  - no telemetry is sent, and no install ID is created, before opt-in
  - telemetry is limited to non-content metrics such as command, integration type, success/failure, artifact bytes, artifact count, CI flag, Python version, OS, and EPI version
- **Pilot signup**
  - `epi telemetry enable --join-pilot` captures explicit contact consent
  - telemetry can be linked to a pilot profile only with explicit `--link-telemetry` consent
- **Onboarding distribution commands**
  - `epi init --github-action` can create a safe CI evidence workflow
  - `epi integrate <target>` generates examples for `pytest`, `langchain`, `litellm`, `opentelemetry`, and `agt`
- **Gateway telemetry ingestion**
  - self-hosted gateways can enable `POST /api/telemetry/events` and `POST /api/telemetry/pilot-signups` with `EPI_GATEWAY_TELEMETRY_ENABLED=true`
  - telemetry records and pilot signup records are stored separately as append-only JSONL

#### Documentation

- Added telemetry privacy documentation.
- Added legal-safe `.epi` evidence-preparation guidance.
- Added an internal go-to-market execution plan with AGT outreach thresholds, framework PR fallbacks, dashboard beta definition, and contingency paths.

---

## [4.0.0] - 2026-04-08

### `.epi` Envelope Format

#### Added

- **New binary `.epi` outer envelope**
  - newly written artifacts now use an `EPI1` header instead of starting with ZIP magic bytes
  - the envelope stores payload length and SHA-256 so readers can fail fast before opening the embedded evidence payload
- **Dual-format container support**
  - EPI now reads both legacy ZIP-based `.epi` files and the new envelope-based `.epi` files transparently
  - legacy artifacts remain valid and readable
- **Artifact migration command**
  - `epi migrate` converts between legacy ZIP and envelope container formats without changing the inner evidence payload

#### Changed

- **Default wire format**
  - `EPIContainer.pack()` and the normal CLI write paths now default to `envelope-v2`
  - the signed inner manifest remains the trust root for this release line
- **Share and gateway transport**
  - new envelope artifacts are served as `application/vnd.epi`
  - legacy ZIP artifacts keep `application/vnd.epi+zip`

#### Fixed

- **Raw artifact identity during sharing**
  - `.epi` files no longer begin with ZIP bytes by default, which avoids the most common “compressed folder” misclassification path in download channels
- **Container abstraction coverage**
  - `view`, `verify`, `review`, `export-summary`, policy inspection, AGT import, and share validation now route through one shared container layer instead of assuming the outer file is a ZIP archive

---

## [3.0.3] - 2026-04-07

### AGT Front-Door Release Polish

#### Added

- **Microsoft Agent Governance Toolkit quickstart**
  - the public docs now treat `epi import agt` as a first-class onboarding path instead of leaving it buried in examples
  - a canonical `AGT -> EPI` walkthrough now starts from `examples/agt/sample_bundle.json`
- **Imported-evidence trust guidance**
  - current docs now explain the imported artifact surfaces that matter most to reviewers:
    - `steps.jsonl`
    - `policy.json`
    - `policy_evaluation.json`
    - `analysis.json`
    - `artifacts/agt/mapping_report.json`

#### Improved

- **Current release documentation alignment**
  - README, docs hub, CLI reference, policy guide, spec, self-hosted runbook, and flagship explainer now align on `v3.0.3`
  - the current docs set now points at the `v3.0.3` flagship explainer instead of the previous release-line document
- **First-time AGT user flow**
  - the CLI help and importer output now make the `import -> verify -> view` flow more obvious to users coming from exported AGT evidence

#### Notes

- `v3.0.3` is a release-polish line focused on discoverability, trust clarity, and current-doc consistency for the AGT import path.

---

## [3.0.2] - 2026-04-04

### Offline Viewer Packaging Fix

#### Fixed

- **Extracted browser viewer**
  - `epi view --extract` now vendors and inlines `jszip.min.js` instead of leaving a JSDelivr dependency in the generated `viewer.html`
  - extracted viewers now open cleanly in offline and air-gapped environments without remote script loading
- **Embedded and policy editor viewer parity**
  - the shared viewer inlining path now bundles the same JSZip runtime for embedded artifact viewers and the browser policy editor
- **Release audit coverage**
  - wheel auditing now fails if the vendored `web_viewer/jszip.min.js` runtime asset is missing from the built package

---

## [3.0.1] - 2026-04-02

### Front-Door Reliability Patch

#### Fixed

- **Packaged browser viewer**
  - `epi view` now works from a clean wheel install because the `web_viewer` assets ship in the package and are loaded through package resources
- **LangChain callback stability**
  - `EPICallbackHandler` no longer crashes when LangChain omits `serialized` metadata in callback payloads
- **Insurance policy threshold alignment**
  - the built-in `insurance.claim-denial` profile now evaluates the public `amount` field shape while keeping `claim_amount` compatibility
- **Threshold analyzer realism**
  - high-value approval rules now wait for the consequential decision/action instead of flagging intermediate fraud or coverage investigation steps

#### Improved

- **Release audit coverage**
  - wheel auditing now fails if required viewer assets are missing from the packaged artifact
- **Current release docs**
  - release-facing documentation now matches the packaged `3.0.1` behavior and current share/view guidance

---

## [2.8.10] - 2026-03-24

### Notebook Packaging Correction

#### Fixed

- **Source release demo assets**
  - `colab_demo.ipynb` and `EPI NEXUA VENTURES.ipynb` are now packaged in the source distribution
  - older notebook snapshots are explicitly kept out of the release artifact
- **Release audit coverage**
  - release gating now audits the source tarball for the required notebooks and rejects temporary packaging leaks
- **Release honesty**
  - release-facing docs now describe the notebooks as GitHub/source-release assets while keeping the wheel runtime-focused

## [2.8.9] - 2026-03-24

### Colab Viewer Fix and Policy Schema Hotfix

#### Added

- **Branded investor notebook**
  - `EPI NEXUA VENTURES.ipynb` added to the repo as an investor-grade Colab walkthrough

#### Improved

- **Colab demo fidelity**
  - both notebook surfaces now render the actual extracted `viewer.html` inside an iframe so Colab shows the real embedded artifact viewer
- **Release alignment**
  - current release surfaces now align on `2.8.9`

#### Fixed

- **Policy schema compatibility**
  - reusable approval policies now accept both `approval_id` and `id`
  - policy rules now accept list-valued `applies_at`
  - tool-permission evaluation now handles list-valued `applies_at`
- **Notebook product fit**
  - tracked Colab demos now match the current Policy v2 and viewer behavior instead of relying on brittle notebook-only fallbacks

## [2.8.8] - 2026-03-24

### Tight Release Hardening

#### Added

- **OpenAI Agents-style event bridge**
  - `OpenAIAgentsRecorder`
  - `record_openai_agent_events(...)`
  - stream-event mapping into EPI agent steps for messages, tools, approvals, handoffs, memory, and decisions

#### Improved

- **Policy validation UX**
  - `epi policy validate` now accepts both standalone policy files and embedded artifact policies
  - invalid JSON now reports line-and-column diagnostics
  - invalid schema fields now report clearer field-level validation errors
- **Viewer reviewer flow**
  - jumping from failed controls into the timeline auto-opens the target step details

#### Fixed

- **Release consistency**
  - release surfaces aligned on `2.8.8`
- **Windows installer guardrails**
  - regression coverage now prevents unsupported Inno task flags from slipping back into the installer script

## [3.0.0] - 2026-04-01

### Stable Evidence Release Line

#### Added

- **Policy-first workflow surfaces**
  - guided `epi policy init`
  - sealed `policy.json` and `policy_evaluation.json`
- **Insurance/compliance-facing review flow**
  - Decision Record export
  - browser review surfaces for trust, policy, and case evidence
- **Hosted pilot foundations**
  - gateway share routes
  - hosted browser case page

#### Fixed

- **Release packaging and docs**
  - release surfaces aligned around the `3.0.0` evidence workflow and policy model

#### Notes

- `3.0.0` is the stable software line for the current `.epi` evidence specification.

---

## [2.8.7] - 2026-03-24

### Policy v2 Foundation and Trust Hardening

#### Added

- **Policy v2 metadata**
  - `policy_format_version`, `policy_id`, policy scope, approval policy references, rule `mode`, and rule `applies_at`
- **Enterprise control support**
  - `tool_permission_guard`
  - structured `policy_evaluation.json` output sealed into artifacts when policy is present
- **Viewer control review flow**
  - control outcomes panel in the embedded viewer
  - jump-to-step navigation from failed controls into the timeline

#### Improved

- **Policy review clarity**
  - `epi policy show` surfaces policy ID and scope when present
  - policy docs now describe both the current rulebook model and the next enterprise direction
- **Version consistency**
  - installer metadata and current-version docs now align with `2.8.7`

#### Fixed

- **Desktop trust verification**
  - the separate `epi-viewer` app now performs real Ed25519 manifest verification instead of format-only checks
- **Windows association honesty**
  - association repair now fails honestly if post-registration diagnostics are still broken
  - system elevation prefers the current install's adjacent `epi.exe` instead of a stale `PATH` entry
- **Packaging/release hygiene**
  - stale static-file manifest include removed
  - release/version drift checks tightened

## [2.8.6] - 2026-03-22

### Product Hardening and Agent-First Workflow Evidence

This release makes the `v2.8.x` line feel much more like a product for both normal users and AI-agent workflows.

#### Added

- **Agent-first recording surface**
  - `epi.agent_run(...)` / `epi.agent(...)` for direct `record(...)` sessions
  - `get_current_session().agent_run(...)` in `epi run` bootstrap mode
  - first-class agent events for plans, tool calls/results, decisions, approvals, memory reads/writes, handoffs, and pause/resume checkpoints
- **Agent-aware viewer flow**
  - agent timeline filter
  - clearer summaries for agent/tool/approval/memory events
  - case-level highlights for approvals, handoffs, and pause/resume checkpoints
- **`approval_guard` policy rule**
  - explicit policy rule for actions that require an approved response before execution

#### Improved

- **First-run onboarding**
  - `epi init` now behaves more like a setup wizard
  - generated demo content teaches the difference between console evidence and structured workflow evidence
- **`epi run` usability**
  - captures plain `print(...)` output as `stdout.print`
  - distinguishes console-only evidence from richer structured workflow evidence
  - prefers a child script's real `record(...)` artifact over a misleading bootstrap artifact
- **Reviewer trust flow**
  - `epi review` shows trust state first and blocks tampered evidence from review
  - `epi policy show` now works directly on `.epi` artifacts with embedded rulebooks
- **Viewer clarity**
  - better plain-language trust guidance
  - clearer review-first and rulebook-first explanations for non-technical reviewers
- **CLI responsiveness**
  - lazy imports and narrower startup checks make basic commands materially faster on Windows
- **Windows opening reliability**
  - association/open flow now prefers the live `epi view \"%1\"` path to avoid stale viewer launches

#### Fixed

- **Front-door trust issues**
  - onboarding/demo artifacts no longer get noisy `stdout` context-drop faults
  - short healthy workflows no longer trigger misleading context-drop findings
- **Viewer packaging/injection**
  - embedded viewer data is HTML-safe
  - stale generated files are cleared before sealing
  - repeated reviews replace `review.json` cleanly instead of creating duplicate ZIP entries
- **Trust consistency**
  - `run`, `view`, `verify`, and `ls` now interpret signed/unsigned/invalid artifacts more consistently
- **CLI and Windows dev quality**
  - stale standalone test scripts were repaired for Windows encoding/path behavior
  - developer association diagnostics are stricter about stale launcher drift

## [2.7.2] - 2026-03-14

### Bug Fixes & Reliability

This patch release closes a critical verification gap for pre-v2.7.1 evidence files and hardens the CLI across the board.

#### Fixed

- **Legacy Signature Compatibility (Critical)**: `verify_signature()` now auto-detects encoding — it tries **Hex** first (current format) and falls back to **Base64** (pre-v2.7.1 format). Previously, any `.epi` file signed by an older version would fail verification with a cryptic error instead of a meaningful result.
- **Browser Viewer Signature Compatibility**: `crypto.js` (inlined into every new `.epi` file) now applies the same hex-then-base64 fallback, so the built-in HTML viewer correctly verifies both old and new files.
- **`epi associate` Exit Code**: The `associate` command incorrectly returned exit code `1` when the file association was already registered. It now prints a confirmation and exits `0`.
- **Verbose Verify Traceback**: In `--verbose` mode, `epi verify` would print a spurious Python traceback when verification failed (e.g. tampered file). `typer.Exit` is now re-raised before the generic exception handler catches it.
- **Analytics Import Crash**: `import epi_recorder` would crash with `ModuleNotFoundError` if `pandas` was not installed, even for users who never use analytics. Import is now lazy with a clear error on first use.
- **Missing `wrap_anthropic` Export**: `wrap_anthropic` and `TracedAnthropic` were not exported from the top-level `epi_recorder` package despite being documented.
- **Incorrect Google AI Studio URL**: `epi chat` help text linked to a dead URL for obtaining a Gemini API key. Fixed to `aistudio.google.com/app/apikey`.
- **`analytics` Missing from Optional Dependencies**: `pyproject.toml` had no `analytics` extras group, so `pip install epi-recorder[analytics]` failed. Added `analytics = ["pandas>=1.5.0", "matplotlib>=3.5.0"]`.

#### Internal

- Extracted shared subprocess helpers (`ensure_python_command`, `build_env_for_child`) from `epi_cli/run.py` and `epi_cli/record.py` into `epi_cli/_shared.py`, eliminating duplicate code.
- `associate` command in `main.py` now calls `_needs_registration()` before delegating to `register_file_association()` to produce the correct "already registered" message.

---

## [2.7.1] – 2026-03-12

### 🛡️ Decentralized Trust & Architectural Symmetry

This release stabilizes the v2.7 series by aligning decentralized verification logic across all components and hardening the file association system.

#### Added
- **Self-Healing File Association**: Registry hooks now perform real-time health checks on every CLI run. If associations are missing or broken (due to OS updates or manual deletion), they are automatically repaired silently.
- **Embedded Public Key Verification**: `epi run` and `epi verify` now prioritize the public key embedded in the `.epi` manifest, enabling zero-config verification on air-gapped or guest machines without local keys.

#### Fixed
- **Architectural Symmetry**: aligned all cryptographic components to use **Hex** encoding for signatures (matching backend/gateway) and **Canonical JSON** for hashing v2.x manifests.
- **SQL Integrity (Critical)**: Fixed a column index mismatch in `epi_analyzer/detector.py` that caused JSON decoding failures when loading recordings from SQLite.
- **`epi run` Verification Logic**: Fixed a bug where `epi run` would incorrectly report successful verification for signed files even if the signer's identity wasn't embedded.
- **Windows Encoding**: Ensured UTF-8 wrap for stdout/stderr is applied at the entry point of every CLI command.

#### Internal
- Final comprehensive audit of `epi_cli`, `epi_core`, and `epi_recorder` completed.
- Full parity between CLI verification and GitHub Actions verification logic.

---

## [2.7.0] – 2026-03-11

### 🚀 Zero-Friction File Opening & Unicode Safety

This release makes `.epi` files first-class OS citizens — double-clicking opens the viewer automatically — and eliminates Unicode crashes across the codebase.

#### Added

**Cross-Platform File Association** (`epi_core/platform/associate.py`)
- Automatic OS-level registration of `.epi` file type at first CLI use
- Windows: `HKEY_CURRENT_USER\Software\Classes` registry (no admin required)
- macOS: Minimal `EPI Viewer.app` bundle with UTI declaration
- Linux: `xdg-mime` MIME type + `.desktop` launcher
- Idempotent: runs once, never duplicates entries
- `epi associate` — manually (re)register file association
- `epi unassociate` — clean removal of file association

#### Fixed

**Unicode Safety (Windows Critical)**
- Windows console encoding fixed at CLI entry point (`cp1252` → `utf-8`)
- All file I/O now uses explicit `encoding="utf-8"` (3 calls fixed in `main.py`, `run.py`)
- All path operations use `pathlib.Path` — no string concatenation
- `epi view` uses `webbrowser.open(path.as_uri())` — correct cross-platform method

**`epi view` Robustness**
- Stem resolution now picks most recent match by mtime when multiple files match
- Temp directories auto-cleaned after 5 seconds via daemon thread
- Explicit `BadZipFile` handling with clear error message
- Warning when file lacks `.epi` extension
- Exit code 1 on all error paths

#### Internal
- New `epi_core/platform/` package for OS integration utilities
- `pyproject.toml` `setuptools.packages.find` includes `epi_core*` (covers new subpackage)

---

## [2.6.0] – 2026-02-20

### 🚀 Framework Integrations, CI Verification & OpenTelemetry Support

This release transforms EPI from a standalone recorder into a **framework-native evidence layer** — integrating with the tools AI engineers already use.

#### Added

**LiteLLM Integration** (`epi_recorder.integrations.litellm`)
- `EPICallback` — callback handler for 100+ LLM providers
- `enable_epi()` / `disable_epi()` — one-line global activation
- Captures request, response, error, and streaming events

**LangChain Callback Handler** (`epi_recorder.integrations.langchain`)
- `EPICallbackHandler` — logs LLM, tool, chain, retriever, and agent events
- Works with LangChain, LangGraph, and any callback-compatible framework
- Graceful fallback when LangChain is not installed

**OpenAI Streaming Support**
- `stream=True` auto-routed to streaming handler in `TracedCompletions`
- Chunks yielded in real-time, assembled response logged after completion
- Usage stats captured from final streaming chunk

**pytest Plugin** (`pytest-epi`)
- `--epi` flag generates signed `.epi` evidence per test
- `--epi-dir` for custom output directory
- End-of-session summary with file listing
- Registered via `pytest11` entry point

**GitHub Action** (`.github/actions/verify-epi/`)
- Composite action for CI/CD pipeline verification
- Scans for `.epi` files, verifies integrity and signatures
- Generates GitHub Step Summary with pass/fail table
- Configurable `fail-on-tampered` and `fail-on-unsigned` inputs

**Global Install/Uninstall** (`epi install --global` / `epi uninstall --global`)
- Injects EPI auto-recording into `sitecustomize.py`
- Idempotent installation (safe to run multiple times)
- Clean removal with `EPI_AUTO_RECORD=0` disable flag
- Respects existing sitecustomize.py content

**OpenTelemetry Exporter** (`epi_recorder.integrations.opentelemetry`)
- `EPISpanExporter` — converts OpenTelemetry spans to signed `.epi` files
- `setup_epi_tracing()` — one-line setup for any OTel-instrumented application
- Trace-level grouping, LLM semantic conventions, batch flushing
- Graceful fallback when OpenTelemetry is not installed

#### Fixed

- **Signature verification**: `verify_signature()` now correctly extracts public key from manifest
- **LangChain handler**: Warns instead of crashing when LangChain is not installed
- **pytest plugin**: Uses `makereport` hookwrapper for correct test outcome capture
- **pytest plugin**: Safe `config.getini()` access with fallback

#### Internal
- 60 end-to-end test assertions, all passing
- Real `.epi` file generation and verification in tests
- Real `sitecustomize.py` round-trip testing

## [2.5.0] – 2026-02-13

### 🚀 Major Features

#### Added

**Anthropic Claude Wrapper**
- `wrap_anthropic()` — proxy wrapper for Anthropic's Claude API
- `TracedAnthropic` — fully wrapped client with automatic evidence capture
- `TracedMessages` — traced `messages.create()` for Claude conversations
- Captures `temperature`, `top_p`, and `system` parameters in evidence logs
- Full request/response logging: messages, tokens, latency, model info
- Mirrors `wrap_openai()` architecture for consistency

**Enhanced Provider Support**
- Anthropic now has first-class wrapper support (not just explicit API)
- Updated supported providers table

#### Fixed

**Critical: Path Resolution Bug**
- Fixed `_resolve_output_path()` double-prepending `epi-recordings/` directory
- Before: `record("epi-recordings/test.epi")` → `epi-recordings/epi-recordings/test.epi` (broken)
- After: `record("epi-recordings/test.epi")` → `epi-recordings/test.epi` (correct)
- Root cause: relative paths containing the recordings directory name were not detected

**Signing & Verification**
- Confirmed Ed25519 signing and verification are fully operational
- Fixed file creation appearing to fail due to path resolution bug above

#### Internal
- Comprehensive signing/verification test suite
- Path resolution test coverage
- Anthropic wrapper test suite (19 tests, 100% pass rate)

---

## [2.4.0] – 2026-02-12

### 🚀 Major Features

This release adds comprehensive agent development and monitoring capabilities.

#### Added

**Agent Analytics Engine**
- `AgentAnalytics` class for analyzing `.epi` files in batch
- Performance summary: success rates, costs, duration trends
- Error pattern detection and analysis
- Tool usage distribution tracking
- Period comparison (this week vs last week, etc.)
- HTML dashboard generation (`generate_report()`)

**Async/Await Support**
- Async context manager (`async with record()`)
- `__aenter__` and `__aexit__` methods
- `alog_step()` async logging method
- Non-blocking I/O using `asyncio.run_in_executor()`
- Full backward compatibility with sync mode
- Perfect for LangGraph, AutoGen, and async-first frameworks

**LangGraph Integration**
- `EPICheckpointSaver` class (native checkpoint backend)
- Implements LangGraph's `BaseCheckpointSaver` interface
- Async checkpoint methods: `aput()`, `aget()`, `alist()`
- Smart state serialization (hashes large states >1MB)
- Automatic capture of all state transitions
- Integration with EPI recording sessions

**Local LLM Support (Ollama)**
- Full compatibility with Ollama's OpenAI-compatible API
- Enables free, unlimited local testing
- Works with DeepSeek-R1, Llama, and other Ollama models
- Zero API costs for development and testing

#### Documentation
- Updated README with "New in v2.3.0" section
- Comprehensive feature documentation
- Code examples for all new features
- Usage guides for analytics, async, LangGraph, and Ollama

#### Internal
- Created `epi_recorder/analytics/` package
- Created `epi_recorder/integrations/` package
- Added comprehensive test suites (15 new tests)
- All tests passing

---

## [2.3.0] – 2026-02-06

### ⚠️ Design Correction (Migration Required)

This release clarifies EPI's role as an **evidence system**, not a passive logger.

#### Breaking
- **Implicit monkey-patching disabled by default**
  - Automatic interception of LLM calls is no longer enabled
  - Evidence capture is now **explicit by design**

#### Rationale
Evidence systems must be:
- intentional
- reviewable in code
- stable across SDK versions

Implicit interception was convenient but fragile.  
Explicit capture provides stronger evidentiary guarantees.

#### Added
- **Explicit evidence API**
  - `log_llm_call(response)` — structured capture of LLM responses
  - `log_chat(data)` — simplified, framework-agnostic capture
- **Wrapper clients**
  - `wrap_openai()` — proxy wrapper enabling capture without SDK modification
- **TracedOpenAI**
  - Fully wrapped OpenAI client with automatic evidence capture

#### Deprecated
- `legacy_patching=True`
  - Temporary compatibility flag
  - Will be removed in v3.0.0

---

## [2.2.1] – 2026-02-06

### Fixed
- Guaranteed creation of `steps.jsonl` at recording start
- Updated tests to match current evidence specification
- Removed brittle test return semantics

### Added
- `unpatch_all()` to restore original methods in legacy patching mode
- Viewer support for error-level evidence steps:
  - `llm.error`
  - `http.request`
  - `http.response`
  - `http.error`

### Changed
- Evidence spec version bumped to 2.2.1

---

## [2.2.0] – 2026-01-30

### Clarified Scope
- EPI's primary artifact is a **portable, verifiable `.epi` artifact that packages execution as evidence**
- Debugging tools are treated as **secondary consumers** of evidence

### Added
- Thread-safe recording using `contextvars`
- Crash-safe SQLite-based evidence storage
- `epi debug` — heuristic analysis of recorded evidence
- Async recording API for concurrent workflows

### Changed
- License standardized to MIT
- Documentation updated to emphasize execution evidence

### Technical
- Replaced global state with context-isolated recording
- Introduced atomic, append-only storage guarantees

---

## [2.1.3] – 2026-01-24

### Added
- Google Gemini evidence capture
- `epi chat` — natural language querying of evidence files

### Fixed
- Windows terminal compatibility issues
- Improved error classification and reporting
- Reduced SDK deprecation noise

---

## [2.1.2] – 2026-01-17

### Security
- Client-side, offline signature verification in embedded viewer
- Canonical serialization and public-key inclusion in evidence manifests

### Changed
- Viewer trust indicators updated
- Evidence specification versioned

---

## [2.1.1] – 2025-12-16

### Added
- Reliable `python -m epi_cli` fallback
- Automatic PATH repair on Windows
- Universal install scripts
- Self-healing `epi doctor` diagnostics

### Fixed
- Windows Unicode terminal issues
- Packaging and installer reliability

---

## [1.0.0] – 2025-12-15

### Initial Release
- Portable `.epi` evidence format
- Cryptographic sealing with Ed25519
- Embedded offline viewer
- Zero-config CLI recording
