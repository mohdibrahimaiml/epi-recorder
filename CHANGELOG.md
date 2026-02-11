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