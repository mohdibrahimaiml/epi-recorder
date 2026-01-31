# Changelog

All notable changes to EPI Recorder will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.2.0] - 2026-01-30

### Changed
- **Repositioned as AI Agent Debugger**: EPI is now positioned as a debugging tool for LangChain, CrewAI, and autonomous agents
- **License changed to MIT**: More permissive licensing for wider adoption
- **Updated README**: Clean "Debug AI agents like a black box" pitch
- **Updated PyPI metadata**: Keywords now focus on debugging, observability, and agent tracing

### Added
- **Thread-safe recording**: Using `contextvars` for concurrent agent support
- **SQLite storage**: Atomic, crash-safe storage replacing JSONL
- **`epi debug` command**: Automatic mistake detection (loops, hallucinations, inefficiencies)
- **Async API support**: `record_async()` context manager for async workflows

### Technical
- Migrated from global context to `contextvars.ContextVar` for thread isolation
- SQLite-based `EpiStorage` class with atomic operations
- `MistakeDetector` analyzes execution traces for common agent bugs

## [2.1.3] - 2026-01-24

### Added
- **Google Gemini Support**: Automatic interception of Gemini API calls via `patch_gemini()`
- **`epi chat` command**: Interactive AI-powered querying of evidence files using natural language
- **google-generativeai dependency**: Gemini AI features work out of the box

### Changed
- Updated `patch_all()` to include Gemini alongside OpenAI
- Added 'gemini' to package keywords

### Fixed
- **Windows Compatibility**: Replaced Unicode emojis in CLI output with ASCII to prevent crashes on legacy terminals
- **Error Handling**: Improved API error reporting (e.g., Quota Exceeded) with user-friendly UI panels
- **Deprecation Warnings**: Suppressed `FutureWarning` spam from google-generativeai SDK

## [2.1.2] - 2026-01-17

### Security
- **Client-Side Verification**: Embedded HTML viewer now verifies Ed25519 signatures offline using JS
- **Manifest V1.1**: Canonical JSON hashing and public key inclusion

### Changed
- Updated trust badges in Viewer UI
- Spec version bump to 1.1-json

## [2.1.1] - 2025-12-16

### Added
- **Python module fallback**: `python -m epi_cli` now works as 100% reliable alternative to `epi` command
- **Automatic PATH configuration**: Post-install script (`epi_postinstall.py`) auto-fixes Windows PATH issues
- **Universal installation scripts**: One-command installers for Unix/Mac/Windows in `scripts/` directory
- **Enhanced `epi doctor` command**: Auto-detects and fixes PATH issues, provides clear diagnostics

### Changed
- Installation success rate improved from 85% to 90% with auto-fix
- `epi doctor` now attempts automatic PATH repair on Windows
- Better error messages for installation issues

### Fixed
- Fixed Unicode errors in Windows terminal output (removed emoji characters)
- Fixed `pyproject.toml` syntax error in `[tool.setuptools.py-modules]`
- Improved Windows PATH detection and configuration
- Better handling of Microsoft Store Python installations

### Security
- All changes maintain backward compatibility
- No changes to cryptographic implementation
- Post-install script only modifies user PATH (not system)

## [2.1.0] - 2024-12-XX

### Added
- Zero-config `epi run` command
- Interactive `epi init` wizard
- `epi ls` command for listing recordings
- Enhanced viewer with timeline
- Automatic API key redaction
- Ed25519 cryptographic signatures

### Changed
- Improved CLI UX
- Better error messages
- Enhanced documentation

---

## Migration Guide

### From 2.1.x to 2.2.0

**No breaking changes** - all existing commands work identically.

**New features:**
```bash
# Debug your agent recordings
epi debug agent_session.epi

# Thread-safe recording for concurrent agents
# Just works - no code changes needed
```

**License change:**
- Migrated from Apache 2.0 to MIT license
- More permissive for commercial use

### From 2.1.0 to 2.1.1

**No breaking changes** - all existing commands work identically.

**New features you can use:**
```bash
# Now you can always use:
python -m epi_cli run script.py

# Or let the auto-fix handle it:
epi doctor
```

**If upgrading:**
```bash
pip install --upgrade epi-recorder

# Recommended: Fix PATH if needed
python -m epi_cli doctor
```
