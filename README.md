<p align="center">
  <img src="https://raw.githubusercontent.com/mohdibrahimaiml/epi-recorder/main/docs/assets/logo.png" alt="EPI Logo" width="180"/>
  <br>
  <h1 align="center">EPI</h1>
  <p align="center"><strong>Verifiable Execution Evidence for AI Systems / AI Agents</strong></p>
  <p align="center">
    <em>A portable, cryptographically sealed artifact format for AI execution records.</em>
  </p>
</p>

<p align="center">
  <a href="https://pypi.org/project/epi-recorder/"><img src="https://img.shields.io/pypi/v/epi-recorder?style=for-the-badge&color=00d4ff&label=PyPI" alt="PyPI"/></a>
  <a href="https://github.com/mohdibrahimaiml/epi-recorder"><img src="https://img.shields.io/badge/python-3.11%2B-blue?style=for-the-badge&logo=python&logoColor=white" alt="Python"/></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green?style=for-the-badge" alt="License"/></a>
</p>

---

## What is EPI?

EPI (Evidence Package for AI) is a **file format** for capturing and verifying AI execution evidence.

An `.epi` file is to AI execution what PDF is to documents:
- **Self-contained** — prompts, responses, environment, viewer — all in one file
- **Universally viewable** — opens in any browser, no software required
- **Tamper-evident** — Ed25519 signatures prove the record wasn't altered

EPI is designed for **adversarial review**: audits, incident response, compliance, litigation.

---

## Design Guarantees

EPI artifacts provide the following guarantees:

| Guarantee | Implementation |
|:----------|:---------------|
| **Explicitness** | Evidence capture is intentional and reviewable in source code |
| **Portability** | Single file, no external dependencies, works offline |
| **Offline Verifiability** | Signature verification requires no network or cloud services |
| **Adversarial Review** | Format assumes the reviewer does not trust the producer |

These are not features. They are **constraints** that define what EPI is.

---

## Quick Start

```bash
pip install epi-recorder
```

### Capture Evidence (Explicit API)

```python
from epi_recorder import record

with record("evidence.epi") as epi:
    response = client.chat.completions.create(model="gpt-4", messages=[...])
    epi.log_llm_call(response)  # Explicit capture
```

### Capture Evidence (Wrapper Client)

```python
from epi_recorder import record, wrap_openai
from openai import OpenAI

client = wrap_openai(OpenAI())

with record("evidence.epi"):
    response = client.chat.completions.create(...)  # Captured via wrapper
```

### Verify Evidence

```bash
epi verify evidence.epi
```

---

## The `.epi` Artifact Format

An `.epi` file is a ZIP archive with a defined structure:

```
evidence.epi
├── mimetype              # "application/epi+zip"
├── manifest.json         # Metadata + Ed25519 signature
├── steps.jsonl           # Execution steps (NDJSON)
├── env.json              # Runtime environment snapshot
└── viewer/
    └── index.html        # Self-contained offline viewer
```

The embedded viewer allows any recipient to:
- View the complete execution timeline
- Verify cryptographic integrity
- Inspect individual steps

No software installation required.

---

## CLI Reference

### Primary Commands

| Command | Purpose |
|:--------|:--------|
| `epi run <script.py>` | Capture execution evidence to `.epi` |
| `epi verify <file.epi>` | Verify artifact integrity and signature |
| `epi view <file.epi>` | Open artifact in browser viewer |
| `epi keys list` | Manage signing keys |

### Secondary Tools

These tools consume evidence artifacts for analysis:

| Command | Purpose |
|:--------|:--------|
| `epi debug <file.epi>` | Heuristic analysis (loops, errors, inefficiencies) |
| `epi chat <file.epi>` | Natural language querying via LLM |

> **Note:** `debug` and `chat` are convenience tools built on top of the evidence format.
> They are not part of the core specification.

---

## Cryptographic Properties

| Property | Implementation |
|:---------|:---------------|
| **Signatures** | Ed25519 (RFC 8032) |
| **Hashing** | SHA-256 content addressing |
| **Key Storage** | Local keyring, user-controlled |
| **Verification** | Client-side, zero external dependencies |

Signatures are **optional but recommended**. Unsigned artifacts are still valid but cannot prove origin.

---

## When to Use EPI

### Appropriate Use Cases

- Post-incident forensics
- Compliance documentation
- Audit trails for autonomous systems
- Reproducibility evidence for research
- Litigation-grade execution records

### Not Designed For

- Real-time monitoring dashboards
- High-frequency telemetry
- System health metrics
- Application performance monitoring

EPI produces **artifacts**, not **streams**.

---

## Supported Providers

| Provider | Capture Method |
|:---------|:---------------|
| OpenAI | Wrapper client or explicit API |
| Anthropic | Explicit API |
| Google Gemini | Explicit API |
| Any HTTP-based LLM | Explicit API via `log_llm_call()` |

EPI does not depend on provider-specific integrations. The explicit API works with any response format.

---

## v2.3.0 — Design Correction

This release corrects EPI's evidence capture model.

| Before (v2.2.x) | After (v2.3.0) |
|:----------------|:---------------|
| Implicit monkey-patching | Explicit capture |
| Fragile to SDK changes | Stable across versions |
| Hidden instrumentation | Reviewable in source |

**Rationale:** Evidence systems must be intentional. Implicit capture was convenient but violated the explicitness guarantee.

**Migration:** Replace implicit capture with `epi.log_llm_call(response)` or `wrap_openai()`.

**Legacy mode:** `record(legacy_patching=True)` is deprecated and will be removed in v3.0.

---

## Release History

| Version | Date | Summary |
|:--------|:-----|:--------|
| **2.3.0** | 2026-02-06 | Explicit capture, wrapper clients, design correction |
| **2.2.0** | 2026-01-30 | SQLite storage, async support, context isolation |
| **2.1.3** | 2026-01-24 | Gemini capture, evidence querying |
| **2.1.0** | 2025-12-15 | Initial release |

See [CHANGELOG.md](./CHANGELOG.md) for full details.

---

## Contributing

```bash
git clone https://github.com/mohdibrahimaiml/epi-recorder.git
cd epi-recorder
pip install -e ".[dev]"
pytest
```

See [CONTRIBUTING.md](./CONTRIBUTING.md) for guidelines.

---

## License

MIT License. See [LICENSE](./LICENSE).
