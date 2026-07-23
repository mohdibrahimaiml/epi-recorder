<div align="center">
  <img src="https://raw.githubusercontent.com/mohdibrahimaiml/epi-recorder/main/docs/assets/logo.png" alt="EPI Labs" width="160"/>

# EPI — Evidence for AI agents

### Record. Seal. Verify offline. The answer is a **file**.

[![PyPI](https://img.shields.io/pypi/v/epi-recorder?color=blue&label=PyPI)](https://pypi.org/project/epi-recorder/)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-passing-brightgreen)](https://github.com/mohdibrahimaiml/epi-recorder/actions)
[![Website](https://img.shields.io/badge/site-epilabs.org-0a84ff)](https://epilabs.org)

```bash
pip install epi-recorder
epi demo --no-browser   # record → seal → verify (no API key)
```

[60-second path](#-60-second-path) · [What’s a `.epi`?](#-whats-a-epi-file) · [OpenAI](#-with-openai) · [CLI](#-cli) · [Trust model](#-trust-model-be-honest) · [Docs](#-docs--standards)

</div>

---

> When someone asks what your agent did six months ago,  
> the answer should be a **`.epi` file** — not a dashboard login and a shrug.

**EPI** (`epi-recorder`) captures agent runs into a **portable, signed, offline-verifiable** artifact.

| You can… | Offline? | Notes |
|----------|----------|--------|
| **Record + seal** | Yes* | `*Seal may contact a TSA if `EPI_NOTARIZE=1` (default). Use `EPI_NOTARIZE=0` for air-gap. |
| **Verify integrity + signature** | Yes | No upload required |
| **View in the browser** | Yes | Self-contained viewer / Decision Ops UI |
| **Know who the sealer is** | Local trust store | First run often **WARN** until you `epi keys trust` |

---

## See a real `.epi` file

Open a sealed artifact in any browser — this is the **embedded forensic viewer inside the `.epi` itself** (polyglot HTML+ZIP), not a remote dashboard:

<p align="center">
  <img
    src="https://raw.githubusercontent.com/mohdibrahimaiml/epi-recorder/main/docs/assets/epi-file-viewer-full.png"
    alt="EPI .epi forensic artifact viewer — integrity, verdict, evidence timeline, and attestation"
    width="920"
  />
</p>

<p align="center">
  <em>Official forensic record from a sealed <code>.epi</code>: integrity, case context, verdict, chronological evidence log, and sign-off — all offline.</em>
</p>

Try it yourself:

```bash
# After any record/demo:
epi view your-run.epi          # opens the .epi forensic viewer
epi verify your-run.epi        # CLI integrity + signature

# Or open the sample shipped with this repo:
epi view docs/assets/readme-demo.epi
```

Or drop a file into the hosted verifier: **[epilabs.org/verify](https://epilabs.org/verify/)** (checks run in your browser).

---

## 60-second path

Works **without** an LLM API key:

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

| Step | Command | Result |
|------|---------|--------|
| **Record + seal** | `python demo.py` | Signed `demo.epi` (secrets redacted by default) |
| **Verify** | `epi verify demo.epi` | Integrity + signature offline |
| **View** | `epi view demo.epi` | Case UI in the browser (no server) |

**First-run verify is often `WARN` on identity** — that is expected:

| Check | Typical first run |
|-------|-------------------|
| Integrity (SHA-256) | Pass |
| Signature (Ed25519) | Pass |
| Identity | **Unknown** until `epi keys trust <name>` |
| Secrets | Redacted by default |

```bash
epi keys list
epi keys trust default    # or your key name
epi verify demo.epi       # identity can become KNOWN
```

---

## What’s a `.epi` file?

A **polyglot Envelope-v2** container: valid **HTML + archive**, signed and hash-linked.

```text
demo.epi
├── manifest.json      # Ed25519 signature + SHA-256 member hashes
├── steps.jsonl        # Timeline (prev_hash chain)
├── environment.json   # Runtime snapshot (sensitive env redacted)
├── viewer.html        # Offline UI shell
├── analysis.json      # Optional fault / policy analysis
├── review.json        # Optional additive human review (Model A)
└── VERIFY.txt         # Plain-text auditor notes
```

| Guarantee | How |
|-----------|-----|
| **Integrity** | SHA-256 over sealed members |
| **Authenticity** | Ed25519 on the manifest |
| **Timeline** | Hash-linked steps |
| **Privacy** | Default redaction (API keys, tokens, common secrets) |
| **Human review** | Additive bound review — does **not** rewrite the original seal |

Sample artifacts (current seal shell): [`docs/assets/readme-demo.epi`](docs/assets/readme-demo.epi),
[`sample-hello.epi`](docs/assets/sample-hello.epi) — see [`docs/assets/SAMPLES.md`](docs/assets/SAMPLES.md).
`epi verify` on these samples is **WARN** (signature valid, signer not pinned) until
`epi keys trust docs/assets/sample-hello.epi --name sample`.

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
python agent.py && epi verify agent.epi && epi view agent.epi
```

Keys in prompts/headers are **redacted by default** before they land in the file.

---

## Trust model (be honest)

EPI separates three facts:

1. **Integrity** — bytes match the seal  
2. **Signature** — sealed under a given public key  
3. **Identity** — whether *you* already trust that key  

| Level | Meaning |
|-------|---------|
| **HIGH** | Integrity + valid sig + key in your local trust store |
| **LOW / WARN** | Valid seal, key not yet trusted (common first run) |
| **NONE / FAIL** | Tamper, bad signature, or failed checks |

**EPI does not prove** that free-text names are real employees, or that the agent’s decision was *correct* — only that the recorded evidence was sealed and not altered.

Enterprise / org trust bundles:

- Profile: [`docs/ENTERPRISE-TRUST-PROFILE.md`](docs/ENTERPRISE-TRUST-PROFILE.md)  
- Bundles: `epi keys bundle-export` / `epi keys bundle-import` · [`docs/ENTERPRISE-TRUST-BUNDLE.md`](docs/ENTERPRISE-TRUST-BUNDLE.md)

---

## Integrations

| Stack | Hook |
|-------|------|
| OpenAI | `wrap_openai(OpenAI())` |
| Anthropic | `wrap_anthropic(Anthropic())` |
| LangChain | `EPICallbackHandler` |
| LiteLLM | `EPICallback` |
| pytest | `pytest --epi` |
| Microsoft AGT | `epi import agt <file>` |

```python
from epi_recorder.integrations.langchain import EPICallbackHandler
# llm = ChatOpenAI(model="gpt-4o-mini", callbacks=[EPICallbackHandler()])
```

```bash
pytest --epi    # evidence attached to test runs
```

More: [docs/FRAMEWORK-INTEGRATIONS-5-MINUTES.md](docs/FRAMEWORK-INTEGRATIONS-5-MINUTES.md)

---

## CLI

| Command | Purpose |
|---------|---------|
| `epi demo` | Guided record → seal → verify (no API key) |
| `epi verify <file.epi>` | Offline integrity + signature |
| `epi view <file.epi>` | Open browser case UI |
| `epi run <script.py>` | Run a script under recording |
| `epi keys generate / list / trust` | Local signing keys |
| `epi keys bundle-export / import` | Org trust bundles |
| `epi review <file.epi>` | Human review of faults / outcomes |
| `epi scitt register <file.epi>` | Optional transparency anchor |
| `epi import agt <path>` | Import Microsoft AGT evidence |

```bash
epi verify agent.epi --json
epi verify agent.epi --policy strict    # requires trusted sealer
epi verify agent.epi --review           # check bound human review
```

---

## Security defaults

- **Redaction on** (`redact=True`) — prefer never `redact=False` in production  
- **Verify is local** — no network for integrity/signature  
- **Seal** may use RFC 3161 notarization when online (`EPI_NOTARIZE=0` to disable)  
- First-run identity **WARN** is normal until you trust your key  

---

## Docs & standards

EPI produces **evidence files** for audit trails. It is **not** a compliance guarantee or legal advice.

| Topic | Link |
|-------|------|
| EU AI Act Annex IV | [docs/ANNEX-IV.md](docs/ANNEX-IV.md) |
| AIUC-1 | [docs/standards/aiuc-1-evidence.md](docs/standards/aiuc-1-evidence.md) |
| SCITT | [docs/standards/scitt-predicate.md](docs/standards/scitt-predicate.md) |
| Auditors | [docs/AUDITORS-GUIDE.md](docs/AUDITORS-GUIDE.md) |
| CLI deep dive | [docs/CLI.md](docs/CLI.md) |
| Website | [epilabs.org](https://epilabs.org) |

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `epi: command not found` | Same venv as `pip install`, or `python -m epi_cli` |
| `DECISION: WARN` first verify | Integrity/sig OK — `epi keys trust …` for KNOWN identity |
| `Integrity: FAILED` | File changed after seal — re-record |
| Share / portal errors | Hosted extras need a backend; **local record/verify never do** |

---

## Project layout

| Path | Role |
|------|------|
| `epi_recorder/` | Python SDK (`record`, wrappers) |
| `epi_core/` | Container, crypto, redaction, verify |
| `epi_cli/` | `epi` command |
| `website/` | **epilabs.org source of truth** |
| `docs/assets/` | Logo + README screenshots + sample `.epi` |
| `tests/` | Regression suite |

Website edits: change only `website/`, then `python scripts/sync_website.py`.

---

## License

MIT — see [LICENSE](LICENSE).

**PyPI:** [epi-recorder](https://pypi.org/project/epi-recorder/) · **Site:** [epilabs.org](https://epilabs.org) · **Issues:** [GitHub Issues](https://github.com/mohdibrahimaiml/epi-recorder/issues)
