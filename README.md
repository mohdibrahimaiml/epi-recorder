<div align="center">
  <img src="https://raw.githubusercontent.com/mohdibrahimaiml/epi-recorder/main/docs/assets/logo.png" alt="EPI Logo" width="220"/>

# EPI — The PDF for AI Evidence

### One file. One signature. 100% offline verification.

[![PyPI](https://img.shields.io/pypi/v/epi-recorder?color=blue&label=PyPI&style=for-the-badge)](https://pypi.org/project/epi-recorder/)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg?style=for-the-badge)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg?style=for-the-badge)](LICENSE)
[![SCITT Compatible](https://img.shields.io/badge/SCITT-COSE%20Sign1-orange?style=for-the-badge)](docs/standards/scitt-predicate.md)
[![AIUC-1 Ready](https://img.shields.io/badge/AIUC--1-Ready-success?style=for-the-badge)](docs/standards/aiuc-1-evidence.md)
[![Test Suite](https://img.shields.io/badge/tests-passing-brightgreen?style=for-the-badge)](https://github.com/mohdibrahimaiml/epi-recorder/actions)

[Quick Start](#-quick-start) · [What EPI Does](#-what-epi-does) · [Integrations](#-integrations) · [CLI Reference](#-commands) · [Regulatory Mapping](#-regulatory-compliance-mapping) · [Standards](#-standards-alignment)

---

*When a regulator asks what your AI agent did six months ago,*  
*the answer should be a file — not a shrug.*

</div>

---

## 💎 What EPI Does

EPI captures an AI agent's **complete decision trail** — every LLM call, tool invocation, approval, error, and environmental context — and seals it into a single **`.epi` file**: a cryptographically signed, tamper-evident, self-contained forensic container.

**Three lines of Python.** That's it.

```python
from epi_recorder import record, wrap_openai
from openai import OpenAI

client = wrap_openai(OpenAI())

with record("loan-approval.epi", goal="Assess mortgage application #421"):
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": "Review applicant credit history"}]
    )
```

The resulting `.epi` file can be **emailed to an auditor**, **archived for 10 years**, or **opened on an air-gapped machine** — without calling home, without the original runtime, and without trusting the producer.

### What's Inside an `.epi` File

```text
loan-approval.epi
├── [Envelope v2] Binary header — magic bytes, version, payload SHA-256
└── [Payload] Signed polyglot HTML+ZIP
    ├── manifest.json       — Ed25519-signed root of trust + SHA-256 file hashes
    ├── steps.jsonl         — Immutable execution timeline (prev_hash chain)
    ├── environment.json    — Full runtime snapshot (host, Python, packages)
    ├── analysis.json       — 9-pass policy-grounded fault analysis
    ├── policy.json         — The rulebook that governed this run
    ├── review.json         — Signed human review & approval ledger
    ├── viewer.html         — Self-contained offline forensic viewer
    └── VERIFY.txt          — Human-readable verification instructions
```

### Three Pillars of Trust

| Pillar | Mechanism | What It Catches |
|--------|-----------|-----------------|
| **Integrity** | SHA-256 manifest over every file | Any byte modified, added, or removed after sealing |
| **Identity** | Ed25519 signature (RFC 8032) | Spoofed or unknown signers; key revocation supported |
| **Chain** | `prev_hash` linking every step | Inserted, removed, or reordered steps in the timeline |

---

## 🚀 Quick Start

```bash
pip install epi-recorder
```

### 1. Record a Workflow

```python
# my_agent.py
from epi_recorder import record, wrap_openai
from openai import OpenAI

client = wrap_openai(OpenAI())

with record("agent-run.epi", goal="Classify support ticket"):
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": "Route ticket #58291"}]
    )
```

### 2. Verify Integrity

```bash
epi verify agent-run.epi
```
```
────────────────────────────────────────────────────
  EPI Verification Report (v4.2.0)
────────────────────────────────────────────────────
  Trust Level:  HIGH
  Signature:    VALID   (Ed25519)
  Integrity:    OK      (SHA-256 manifest, 15 files)
  Chain:        INTACT  (prev_hash verified, 32 steps)
  Identity:     KNOWN   (production-signer-v4)
  Analysis:     PASSED  (0 faults in 9 passes)

  This artifact has not been modified since sealing.
────────────────────────────────────────────────────
```

### 3. Open the Forensic Viewer

```bash
epi view agent-run.epi
# Opens viewer.html in your browser — zero dependencies, offline-ready.
```

Double-click any `.epi` — they open natively as HTML in any browser.

---

## 🔧 Commands

| Command | What It Does |
|---------|--------------|
| `epi run <script>` | Record an AI workflow and seal it into a `.epi` file |
| `epi verify <file.epi>` | Cryptographic integrity + signature verification |
| `epi view <file.epi>` | Open the offline forensic timeline viewer |
| `epi audit <file.epi>` | Self-audit scoring across AIUC-1, SCITT, and review domains |
| `epi keys generate` | Generate an Ed25519 signing key pair |
| `epi keys list` | List signing key pairs |
| `epi keys trust <key>` | Trust a signing key in the local registry |
| `epi keys revoke <name>` | Revoke a trusted or signing key |
| `epi serve` | Start a FastAPI capture gateway for team workflows |
| `epi policy init` | Create an `epi_policy.json` rulebook |
| `epi review <file.epi>` | Sign and attest a human review of the artifact |
| `epi scitt register <file.epi>` | Anchor an artifact to a SCITT transparency ledger |
| `epi scitt verify <file.epi>` | Verify SCITT receipt and Merkle inclusion proof |
| `pytest --epi` | Generate signed `.epi` evidence for each test |

---

## 🔌 Integrations

EPI plugs into your existing stack — one callback, one wrapper, one line.

| Integration | How | What You Get |
|-------------|-----|--------------|
| **OpenAI / Anthropic** | `wrap_openai(client)` / `wrap_anthropic(client)` | Full chat capture, streaming support, token usage, latency |
| **LangChain** | `ChatOpenAI(callbacks=[EPICallbackHandler()])` | Chain, tool, retriever, and agent traces |
| **LangGraph** | `EPICheckpointSaver` | Agent graph state snapshots |
| **LiteLLM** | `litellm.callbacks = [EPICallback()]` | 100+ providers through one callback |
| **pytest** | `pytest --epi` | Signed forensic evidence per test — CI-ready |
| **OpenTelemetry** | `setup_epi_tracing()` | Bridge OTel spans into signed `.epi` files |
| **FastAPI Gateway** | `epi serve` | Team capture proxy, configurable retention, webhooks |

---

## 🧪 Self-Audit

EPI ships with a built-in self-audit command that produces machine-readable compliance reports.

```bash
epi audit agent-run.epi
```
```
────────────────────────────────────────────────────
  EPI Self-Audit Report
────────────────────────────────────────────────────
  Artifact:      agent-run.epi
  Overall Score: 9.5/10  (Production-Ready)

  AIUC-1 Compliance   ██████████  10/10  ALL DOMAINS PASS
  SCITT Transparency  ████████░░   8/10  Receipt valid, proof included
  Review Binding      ██████████  10/10  Ed25519-signed review present
  Analysis Coverage   ██████████  10/10  9-pass analysis, 0 faults

  Rating: PRODUCTION-READY — suitable for regulatory submission
────────────────────────────────────────────────────
```

Output formats: terminal (Rich), JSON, and Markdown.

---

## ⚖️ Regulatory Compliance Mapping

EPI produces evidence that addresses specific global regulatory requirements. EPI is not a compliance guarantee and does not provide legal advice. Whether the enclosed evidence satisfies a specific regulatory threshold is for the auditor or notified body to determine.

| Requirement | Framework | .epi Evidence |
|:---|:---|:---|
| Logs of operation appropriate to lifecycle | **EU AI Act Art. 12** | `steps.jsonl` + `environment.json` |
| Technical documentation retention (10yr) | **EU AI Act Art. 19** | Sealed `.epi` (format-stable) |
| Evidence of human oversight | **EU AI Act Art. 14** | `review.json` approval ledger |
| Audit trail for regulated software | **FDA 21 CFR Part 11** | Signed `steps.jsonl` + `manifest.json` |
| Non-repudiation of data | **HIPAA § 164.312** | Ed25519 signature over manifest |
| AI risk management documentation | **NIST AI RMF** | `policy.json` + `analysis.json` |
| Verifiable risk evaluation & HITL audit proof | **AIUC-1** (6 domains) | `steps.jsonl` + `review.json` + `analysis.json` |
| Transparency log anchoring | **SCITT (IETF)** | COSE Sign1 statements + Merkle inclusion proofs |

---

## 🏛️ Standards Alignment

- **SCITT (IETF)** — COSE Sign1 statements, transparency receipts with Merkle inclusion proofs, persistent SQLite-backed ledger
- **AIUC-1** — All 6 risk domains validated with substantive cryptographic checks (not file-existence stubs)
- **Ed25519 (RFC 8032)** — Industry-standard digital signatures with DID:WEB identity resolution
- **CycloneDX** — SBOM preservation under `artifacts/sbom/`
- **in-toto (CNCF)** — Roadmap: steps.jsonl as in-toto link files

---

## 🛡️ Security Model

| Threat | Mitigation |
|:---|:---|
| **Post-Seal Tampering** | SHA-256 file manifest + Ed25519 signature over the manifest |
| **Evidence Replay** | Unique `workflow_id` + time-anchored `created_at` |
| **Secret Leakage** | Automatic forensic redaction of API keys, tokens, and PII (HMAC-SHA256 placeholders) |
| **Signature Spoofing** | Strict `ed25519:<keyname>:<hex>` format enforcement |
| **Step Manipulation** | Prev-hash chain — inserting, removing, or reordering steps breaks verification |
| **Key Compromise** | Revocation files at `~/.epi/trusted_keys/*.revoked` |

---

## 📑 Documentation

- 📖 **[Protocol Specification](docs/EPI-SPEC.md)** — The technical wire format
- ⚖️ **[Governance Guide](docs/POLICY.md)** — Managing rulebooks and evaluations
- 🇪🇺 **[EU AI Act Prep](docs/EU-AI-ACT-EVIDENCE-PREP.md)** — Evidence workflow guide for EU compliance
- 🛠️ **[CLI Reference](docs/CLI.md)** — Comprehensive command reference

---

## 🤝 Founding Pilot Program

EPI is seeking regulated enterprises to pilot AI compliance evidence packaging.

If you operate AI agents under the **EU AI Act**, **FDA 21 CFR Part 11**, or **SOC 2**, and you need portable, independently-verifiable evidence:

- **Direct Integration Support** — hands-on assistance from the maintainers
- **Priority Roadmap Influence** — shape the standard based on your compliance needs
- **Founding Partner Recognition** — optional listing as an early adopter

**Contact:** [mohdibrahim@epilabs.org](mailto:mohdibrahim@epilabs.org) — Subject: `EPI Pilot — [Your Organization]`

---

<div align="center">

**Built by EPI Labs.**
*Ensuring that as AI moves faster, accountability stays ahead.*

[MIT License](LICENSE) · [Contributing](CONTRIBUTING.md) · [Security Policy](SECURITY.md) · [epilabs.org](https://epilabs.org)

</div>
