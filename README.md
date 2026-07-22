<div align="center">
  <img src="https://raw.githubusercontent.com/mohdibrahimaiml/epi-recorder/main/docs/assets/logo.png" alt="EPI Logo" width="200"/>

# EPI — Evidence for AI agents

### Record. Seal. Verify offline. The answer is a **file**.

[![PyPI](https://img.shields.io/pypi/v/epi-recorder?color=blue&label=PyPI)](https://pypi.org/project/epi-recorder/)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://python.org)
[![Version v4.3.0](https://img.shields.io/badge/version-v4.3.0-purple)](https://github.com/mohdibrahimaiml/epi-recorder/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-passing-brightgreen)](https://github.com/mohdibrahimaiml/epi-recorder/actions)

```bash
pip install epi-recorder
epi demo --no-browser    # record → seal → verify (no API key)
```

[60-second path](#-60-second-path) · [With OpenAI](#-with-openai) · [Integrations](#-integrations) · [CLI](#-cli) · [Standards](#-standards--compliance)

</div>

---

> When someone asks what your agent did six months ago,  
> the answer should be a **`.epi` file** — not a dashboard login and a shrug.

`epi-recorder` captures agent decisions into a portable, signed, **offline-verifiable** artifact.  
**View** and **integrity/signature verify** work offline. **Identity** checks may consult a local trust store and, if configured, DID/remote registry. **Seal** may contact a TSA for RFC 3161 notarization (`EPI_NOTARIZE=1` by default; `EPI_NOTARIZE=0` for offline seal).  
Enterprise trust model: [`docs/ENTERPRISE-TRUST-PROFILE.md`](docs/ENTERPRISE-TRUST-PROFILE.md) ·  
Trust bundle: `epi keys bundle-export` / `epi keys bundle-import` ·  
[`docs/ENTERPRISE-TRUST-BUNDLE.md`](docs/ENTERPRISE-TRUST-BUNDLE.md) ·  
Decision-grade content profile: [`docs/evidence-profile/v0.1.json`](docs/evidence-profile/v0.1.json).

---

## 60-second path

Works **without** any LLM API key:

```python
# demo.py
from epi_recorder import record, get_current_session

with record("demo.epi", goal="show the golden path"):
    s = get_current_session()
    s.log("tool.call", tool="lookup", id="A-1")
    s.log("tool.response", ok=True, balance=250)
    s.log("decision", action="approve", reason="within limit")
```

```bash
python demo.py
epi verify demo.epi
epi view demo.epi
```

| Step | Command | What you get |
|------|---------|----------------|
| **Record + seal** | `python demo.py` | Signed `demo.epi` (secrets redacted by default) |
| **Verify** | `epi verify demo.epi` | Integrity + signature checks offline |
| **View** | `epi view demo.epi` | Self-contained browser viewer (no server) |

Typical first-run verify:

| Check | Result |
|-------|--------|
| Integrity (SHA-256) | ✅ Valid |
| Signature (Ed25519) | ✅ Valid |
| Identity | ⚠ UNKNOWN until you `epi keys trust` your key |
| Secrets | ✅ Redacted by default (`redact=True`) |

> **DECISION: WARN** on first verify is normal — integrity and signature still pass.  
> Trust identity with: `epi keys trust <name>` after `epi keys list`.

That’s the product. Everything below is optional depth.

---

## With OpenAI

```python
from openai import OpenAI
from epi_recorder import record, wrap_openai

client = wrap_openai(OpenAI())  # needs OPENAI_API_KEY

with record("agent.epi", goal="Answer a user question"):
    client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": "Hello"}],
    )
```

```bash
python agent.py
epi verify agent.epi
epi view agent.epi
```

API keys in prompts/headers are **redacted automatically** before they land in the file.

---

## What a `.epi` file is

Every `.epi` uses the **Envelope v2** container format — a **polyglot HTML+ZIP**
binary that opens natively in any browser and can be extracted programmatically.

```text
demo.epi
├── manifest.json     # Ed25519 signature + SHA-256 file hashes
├── steps.jsonl       # Timeline (hash-linked steps)
├── environment.json  # Runtime snapshot (sensitive env redacted)
├── viewer.html       # Offline forensic UI
└── VERIFY.txt        # Plain-text auditor instructions
```

| Guarantee | How |
|-----------|-----|
| **Integrity** | SHA-256 over every sealed member |
| **Authenticity** | Ed25519 signature on the manifest |
| **Chain** | Each step’s `prev_hash` links the timeline |
| **Privacy** | Default secret redaction (API keys, tokens, PII) |

---

## Integrations

| Stack | How |
|-------|-----|
| OpenAI | `wrap_openai(OpenAI())` |
| Anthropic | `wrap_anthropic(Anthropic())` |
| LangChain | `EPICallbackHandler` |
| LiteLLM | `EPICallback` |
| pytest | `pytest --epi` |
| Microsoft AGT | `epi import agt <file>` |

```python
# LangChain
from epi_recorder.integrations.langchain import EPICallbackHandler
llm = ChatOpenAI(model="gpt-4o-mini", callbacks=[EPICallbackHandler()])
```

```bash
# pytest — attach evidence to failing tests
pytest --epi
```

More: [docs/FRAMEWORK-INTEGRATIONS-5-MINUTES.md](docs/FRAMEWORK-INTEGRATIONS-5-MINUTES.md)

---

## CLI

| Command | Purpose |
|---------|---------|
| `epi verify <file.epi>` | Offline integrity + signature check |
| `epi view <file.epi>` | Open offline viewer |
| `epi run <script.py>` | Run a script under recording |
| `epi keys generate` | Create a local signing key |
| `epi keys list` / `trust` / `revoke` | Key management |
| `epi demo` | Guided demo (alias of `epi dev`) |
| `epi scitt register <file.epi>` | Optional transparency anchor |
| `epi import agt <path>` | Import Microsoft AGT evidence |

---

## Security defaults

- **Redaction is on** (`redact=True`). Keys/tokens/PII become `***REDACTED***:…` placeholders.
- Prefer **not** using `redact=False` in production (it warns).
- Verification is **local** — no network required for integrity/signature.
- First-run identity WARN is expected until you trust your key.

---

## Standards & compliance

EPI produces **evidence files** that help with audit trails. It is **not a compliance guarantee**
and **does not provide legal advice**. Whether evidence satisfies a specific regulatory threshold
is for the auditor or notified body to determine.

| Topic | Docs |
|-------|------|
| EU AI Act Annex IV | [docs/ANNEX-IV.md](docs/ANNEX-IV.md) |
| AIUC-1 domains | [docs/standards/aiuc-1-evidence.md](docs/standards/aiuc-1-evidence.md) |
| SCITT | [docs/standards/scitt-predicate.md](docs/standards/scitt-predicate.md) |
| CLI deep dive | [docs/CLI.md](docs/CLI.md) |
| Auditors guide | [docs/AUDITORS-GUIDE.md](docs/AUDITORS-GUIDE.md) |

```bash
epi verify agent.epi --aiuc1   # optional domain scoring
```

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `epi: command not found` | Activate the same venv where you `pip install`ed, or use `python -m epi_cli` |
| `DECISION: WARN` first verify | Normal — integrity/signature OK. Run `epi keys trust …` for KNOWN identity |
| `Integrity: FAILED` | File was modified after seal — re-record |
| Share / portal fails | Hosted features need a live backend; local record/verify never depends on them |

---

## Project layout (contributors)

| Path | Role |
|------|------|
| `epi_recorder/` | Python SDK (`record`, wrappers) |
| `epi_core/` | Container, crypto, redaction, verify |
| `epi_cli/` | `epi` command |
| `website/` | **Public site source of truth** (`epilabs.org`) |
| `verify_portal/` | Hosted verify/auth API (optional) |
| `tests/test_core_loop_golden.py` | Golden path regression |

Website edits: only under `website/`, then `python scripts/sync_website.py`.

---

## License

MIT — see [LICENSE](LICENSE).

**Site:** [epilabs.org](https://epilabs.org) · **Issues:** [GitHub Issues](https://github.com/mohdibrahimaiml/epi-recorder/issues)
