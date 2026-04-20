# EPI Recorder — Agent Context

> This file provides concise, structured context for AI agents working on this codebase.
> For full documentation, see `docs/` and `README.md`.

## Project

**EPI** (Evidence Packaged Infrastructure) is the reference implementation of the EPI standard
for packaging AI execution into portable, verifiable `.epi` artifacts.

**Version**: 4.0.1 · **Python**: ≥3.11 · **License**: MIT

## Package Map

```
epi_core/           Core logic — schemas, container, trust, fault analysis, case store
epi_recorder/       Runtime instrumentation — patching, wrappers, integrations
epi_cli/            CLI commands — record, run, view, verify, share, review, policy
epi_gateway/        FastAPI capture service — proxy, cases, auth, worker
epi_guardrails/     Guardrails AI integration — instrumentor, session, state
epi_analyzer/       Extended fault detection (wraps epi_core.fault_analyzer)
epi_viewer_static/  Embedded browser viewer (HTML/JS/CSS, bundled into .epi files)
web_viewer/         Server-rendered case viewer for gateway dashboard
pytest_epi/         Pytest plugin — automatic per-test evidence recording
```

## Critical Files (Do NOT modify without understanding impact)

| File | Why it matters |
|:-----|:--------------|
| `epi_core/schemas.py` | Defines ManifestModel and StepModel — the EPI interface contract |
| `epi_core/container.py` | Dual-format container (legacy-zip + envelope-v2) with integrity verification |
| `epi_core/trust.py` | Ed25519 cryptographic signing and verification |
| `epi_core/fault_analyzer.py` | Four-pass deterministic heuristic engine (no LLM required) |
| `epi_core/case_store.py` | SQLite-backed Decision Ops engine for gateway mode |
| `epi_core/serialize.py` | CBOR canonical hashing — changing this breaks all existing signatures |
| `epi_recorder/patcher.py` | Runtime monkey-patching for OpenAI, Gemini, and HTTP interception |
| `epi_recorder/api.py` | User-facing `record()` context manager and `AgentRun` helper |
| `epi_cli/main.py` | CLI router — Typer app with lazy imports for fast startup |
| `pyproject.toml` | Build config, dependencies, entry points, test markers |

## Architecture: Four Stages of Evidence

1. **Setup** — Prepare recording context before workflow execution
2. **Recording** — Capture execution steps via patching, wrappers, or explicit logging
3. **Safety Net** — Persist steps atomically to SQLite (crash-safe)
4. **Seal** — Package into `.epi` artifact with SHA-256 hashes and Ed25519 signature

## Key Patterns

- **Container Format**: `.epi` files use `envelope-v2` (64-byte `EPI1` header + ZIP payload) by default
- **Trust**: Manifests are canonicalized to CBOR, hashed with SHA-256, and signed with Ed25519
- **Fault Analysis**: Deterministic passes — Error Continuation, Constraint Violation, Policy Guard, Context Drop
- **Thread Safety**: `contextvars.ContextVar` for async-safe recording context isolation
- **Redaction**: Pattern-based secret scrubbing before evidence hits disk

## Dependencies

**Core** (always installed): `pydantic`, `cryptography`, `cbor2`, `typer`, `rich`

**Optional extras**: `[openai]`, `[anthropic]`, `[langchain]`, `[langgraph]`, `[litellm]`, `[opentelemetry]`, `[gateway]`, `[analytics]`, `[integrations]`, `[all]`

## Testing

```bash
pytest tests/ -v                    # Run all tests
pytest tests/ -m unit               # Unit tests only
pytest tests/ -m integration        # Integration tests
pytest tests/ -m security           # Crypto and redaction tests
pytest tests/ -m compliance         # Spec compliance tests
```

Test markers: `unit`, `integration`, `security`, `browser`, `framework`, `compliance`, `slow`, `network`
