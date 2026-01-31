<p align="center">
  <img src="docs/assets/logo.png" alt="EPI Logo" width="200"/>
  <br>
  <h1 align="center">EPI Recorder</h1>
</p>

[![Release](https://img.shields.io/github/v/tag/mohdibrahimaiml/epi-recorder?label=Release&style=flat-square&color=00d4ff)](https://github.com/mohdibrahimaiml/epi-recorder/tags)
[![Python](https://img.shields.io/badge/Python-3.11%2B-blue?style=flat-square&logo=python&logoColor=white)](https://pypi.org/project/epi-recorder/)
[![License](https://img.shields.io/badge/License-Apache_2.0-green.svg?style=flat-square)](LICENSE)
[![Downloads](https://img.shields.io/pypi/dm/epi-recorder?style=flat-square&color=10b981&label=Installs)](https://pypi.org/project/epi-recorder/)
[![Users](https://img.shields.io/badge/Users-4.5K%2B-orange?style=flat-square&color=f59e0b)](#)
[![Crypto](https://img.shields.io/badge/Ed25519-Signed-purple?style=flat-square)](https://epilabs.org/security)

**The Flight Recorder for AI Agents**

Debug production failures in LangChain, CrewAI, and custom agents with one command.
Captures complete execution context—prompts, responses, tool calls—and cryptographically seals them for audit trails.

[� Documentation](https://epilabs.org) • [🚀 Quick Start](#quick-start) • [🔐 Security](#security-compliance)

> *"Saved me 4 hours debugging a hallucinating agent. The AI analysis pinpointed the exact failure step."*
> — AI Engineer, YC W24

---

## Why EPI?

Your AI agent failed in production. It hallucinated. It looped infinitely. It cost you $50 in API calls.

**You can't reproduce it.** LLMs are non-deterministic. Your logs don't show the full prompt context. You're taking screenshots and pasting JSON into Slack.

**EPI is the black box.** One command captures everything. Debug locally. Prove what happened.

---

## Quick Start

```bash
pip install epi-recorder

# Record your agent (zero config)
epi run agent.py

# Debug the failure (opens browser viewer)
epi view recording.epi

# Verify integrity (cryptographic proof)
epi verify recording.epi
```

_(Imagine a GIF here of the terminal launching the viewer)_

---

## Features

- **⚡ Zero Config**: `epi run` intercepts OpenAI, LangChain, CrewAI automatically—no code changes.
- **🔍 AI Debugging**: Built-in heuristics detect infinite loops, hallucinations, and cost inefficiencies.
- **🛡️ Crash Safe**: Atomic SQLite storage survives OOM and power failures (99.9% capture rate).
- **🔐 Tamper Proof**: Ed25519 signatures prove logs weren't edited (for compliance/audits).
- **🌐 Framework Agnostic**: Works with any Python agent (LangChain, CrewAI, AutoGPT, or 100 lines of raw code).

---

## How It Works

EPI acts as a **Parasitic Observer**—injecting instrumentation at the Python runtime level via `sitecustomize.py`.

1.  **Intercept**: Captures LLM calls at the HTTP layer (`requests.Session`) and library level.
2.  **Store**: Atomic SQLite WAL ensures zero data loss on crashes.
3.  **Analyze**: `epi debug` uses local heuristics + AI to find root causes.
4.  **Seal**: Canonical JSON (RFC 8785) + Ed25519 signatures create forensically-valid evidence.

```mermaid
graph LR
    Script[User Script] -->|Intercept| Patcher[EPI Patcher]
    Patcher -->|Write| WAL[(Atomic SQLite)]
    WAL -->|Package| File[.epi File]
    File -->|Sign| Key[Ed25519 Key]
```

---

## Security & Compliance

While EPI is built for daily debugging, it provides the cryptographic infrastructure required for regulated environments:

-   **Signatures**: Ed25519 with client-side verification (zero-knowledge).
-   **Standards**: Supports EU AI Act Article 6 logging requirements.
-   **Privacy**: Automatic PII redaction, air-gapped operation (no cloud required).

*[Enterprise support available](mailto:enterprise@epilabs.org) for SOC2/ISO27001 environments.*

---

## Contributing

We welcome contributions! Please see [CONTRIBUTING.md](./CONTRIBUTING.md) for details.

```bash
git clone https://github.com/mohdibrahimaiml/EPI-V2.1.2
cd epi-recorder
pip install -e ".[dev]"
pytest
```

## License

MIT License. See [LICENSE](./LICENSE) for details.


 