# Changelog

All notable changes to EPI Recorder are documented here.

EPI follows [Semantic Versioning](https://semver.org/) and treats version changes as
**corrections to evidence guarantees**, not just feature updates.

---

## [3.0.0] – Planned

> **Status:** Pre-RFC. This is a directional commitment, not a release.

### Intent

v3.0.0 will finalize EPI as a **stable evidence specification**.

#### Planned Changes

- **Removal of legacy patching**
  - `legacy_patching=True` will no longer be supported
  - All evidence capture will be explicit

- **Stabilized evidence specification**
  - Manifest schema frozen
  - Backward-compatibility guarantees for `.epi` files

- **Forward-compatibility primitives**
  - Versioned step schemas
  - Extension mechanism for custom evidence types

- **Trust model refinements** (under consideration)
  - Organization-level key management
  - Multi-party signing
  - Delegation chains

#### Design Philosophy

v3.0.0 is not about features. It is about **guarantees**.

After v3.0.0, the `.epi` format should be:
- readable by any future version
- verifiable without the original tooling
- suitable for long-term archival

---

## [2.7.2] – 2026-03-14

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
- EPI's primary artifact is a **portable execution evidence file (.epi)**
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