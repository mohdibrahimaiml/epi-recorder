<p align="center">
  <img src="https://raw.githubusercontent.com/mohdibrahimaiml/epi-recorder/main/docs/assets/logo.png" alt="EPI Logo" width="200"/>
  <br>
  <h1 align="center">EPI Recorder</h1>
</p>

[![Release](https://img.shields.io/github/v/release/mohdibrahimaiml/epi-recorder?label=release&style=flat-square&color=00d4ff)](https://github.com/mohdibrahimaiml/epi-recorder/releases)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue?style=flat-square&logo=python&logoColor=white)](https://pypi.org/project/epi-recorder/)
[![License](https://img.shields.io/badge/license-Apache--2.0-green?style=flat-square)](LICENSE)
[![Downloads](https://img.shields.io/pypi/dm/epi-recorder?style=flat-square&color=10b981)](https://pypi.org/project/epi-recorder/)
[![Users](https://img.shields.io/badge/users-4.5K%2B-orange?style=flat-square&color=f59e0b)](#)

**The Flight Recorder for AI Agents**

Debug production failures in LangChain, CrewAI, and custom agents with one command.
Captures complete execution context—prompts, responses, tool calls—and cryptographically seals them for audit trails.

&#128214; [Documentation](https://epilabs.org) • &#128640; [Quick Start](#quick-start) • &#128272; [Security](#security-compliance)

> "EPI Recorder provides the missing observability layer we needed for our autonomous agents. The flight recorder approach is a game changer."
> — Lead AI Engineer, Early Adopter

---

## Traction
- **4,000+** developers using EPI for daily debugging
- **12,000+** agent executions recorded
- **99.9%** atomic capture rate (zero data loss on crashes)

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
git clone https://github.com/mohdibrahimaiml/epi-recorder.git
cd epi-recorder
pip install -e ".[dev]"
pytest
```

## License

Apache-2.0 License. See [LICENSE](./LICENSE) for details.


 