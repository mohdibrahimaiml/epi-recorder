<div align="center">
  <img src="https://raw.githubusercontent.com/mohdibrahimaiml/epi-recorder/main/docs/assets/logo.png" alt="EPI Logo" width="220"/>
  <br>

# EPI: Evidence Packaged Infrastructure

### Portable Evidence for AI Execution.

Helps generate structured, tamper-evident evidence for AI agent compliance workflows, including AIUC-1 accountability controls.

[![PyPI](https://img.shields.io/pypi/v/epi-recorder?color=blue&label=PyPI&style=for-the-badge)](https://pypi.org/project/epi-recorder/)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg?style=for-the-badge)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg?style=for-the-badge)](LICENSE)
[![SCITT Compatible](https://img.shields.io/badge/SCITT-COSE%20Sign1-orange?style=for-the-badge)](docs/standards/scitt-predicate.md)
[![AIUC-1 Ready](https://img.shields.io/badge/AIUC--1-Ready-success?style=for-the-badge)](docs/standards/aiuc-1-evidence.md)
[![Release Gate](https://img.shields.io/badge/release%20gate-passing-brightgreen?style=for-the-badge)](https://github.com/mohdibrahimaiml/epi-recorder/actions)

[**Pilot Program**](#-founding-pilot-program) · [Quick Start](#🚀-quick-start) · [Integrations](#🔌-integrations) · [Regulatory Mapping](#⚖️-regulatory-compliance-mapping) · [Standards](#🏛️-standards-alignment) · [Docs](docs/)

---

*When a regulator asks what your AI agent did six months ago,*  
*the answer should be a file — not a shrug.*

</div>

---

## 🏛️ The Problem

AI agents make decisions that carry legal, financial, and safety consequences. Those decisions happen in memory, get logged in transient cloud infrastructure, and are tied to a runtime that may not exist when an auditor arrives six months later.

**EU AI Act Article 12** requires providers of high-risk AI systems to maintain logs of operation appropriate to the system's lifecycle. **FDA 21 CFR Part 11** requires tamper-evident audit trails. **SOC 2 CC7.2** requires logging of unauthorized activity. None of these regulations define *how* evidence must be packaged for external review.

**EPI closes that packaging gap.**

---

## 💎 What EPI Does

EPI packages AI agent execution—the complete decision trail, governance evaluation, tool calls, inputs, outputs, approvals, and environmental context—into a single **.epi** artifact: a cryptographically signed, tamper-evident, self-contained forensic container.

The artifact can be **emailed to an auditor**, **archived for 10 years**, or **opened on an air-gapped machine**—without calling home, without the original runtime, and without trusting the producer.

### The Forensic Container Architecture
```text
agent_run.epi
├── [Envelope] EPI1 Header  — Binary magic, version, and payload SHA-256
└── [Payload] Signed ZIP    — Wrap with EPI1 Envelope
    ├── manifest.json       — Ed25519 signed root of trust + file hashes
    ├── steps.jsonl         — Immutable execution timeline (prev_hash chain)
    ├── governance.json     — The rulebook that governed the run
    ├── environment.json    — Host & Python runtime context snapshot
    ├── artifacts/          — Raw evidence preserved verbatim (e.g., AGT bundles)
    ├── viewer.html         — Self-contained offline forensic viewer
    └── VERIFY.txt          — Human-readable offline verification guide
```

---

## 🚀 Quick Start

```bash
pip install epi-recorder
```

### 1. Instrument an Agent
Capture any LLM-backed workflow with minimal boilerplate.

```python
from epi_recorder import record, wrap_openai
from openai import OpenAI

# 1. Wrap your client for high-fidelity capture
client = wrap_openai(OpenAI())

# 2. Record the forensic context
with record("loan-approval.epi", workflow_name="Credit-V4"):
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": "Assess applicant #421"}]
    )
```

### 2. Verify the Artifact
```bash
epi verify --strict loan-approval.epi
```

```text
────────────────────────────────────────────────────
  EPI Verification Report (v4.1.0)
────────────────────────────────────────────────────
  Trust Level:  HIGH
  Signature:    VALID   (Ed25519)
  Integrity:    OK      (SHA-256 manifest, 23 files)
  Chain:        INTACT  (prev_hash verified, 47 steps)
  Identity:     KNOWN   (production-signer-v4)

  This artifact has not been modified since sealing.
────────────────────────────────────────────────────
```

### 3. Open the Offline Viewer
```bash
epi view loan-approval.epi
# Opens viewer.html in your browser — zero dependencies, offline-ready.
```

---

## 🔌 Integrations

EPI acts as a universal evidence layer for the entire AI ecosystem:

- **LangChain**: `ChatOpenAI(..., callbacks=[EPICallbackHandler()])`
- **LiteLLM**: `litellm.callbacks = [EPICallback()]`
- **Microsoft AGT**: `epi import agt <bundle>` — adapter for regulatory evidence.
- **OpenTelemetry**: `setup_epi_tracing()` — turn spans into signed artifacts.
- **pytest**: `pytest --epi` — automatic forensic evidence for failing tests.

---

## ⚖️ Regulatory Compliance Mapping

EPI produces evidence that addresses specific global regulatory requirements. EPI is not a compliance guarantee and does not provide legal advice. Whether the enclosed evidence satisfies a specific regulatory threshold is for the auditor or notified body to determine.

| Requirement | Framework | .epi Evidence |
|:---|:---|:---|
| Logs of operation appropriate to lifecycle | **EU AI Act Art. 12** | `steps.jsonl` + `environment.json` |
| Technical documentation retention (10yr) | **EU AI Act Art. 19** | Sealed `.epi` (format-stable) |
| Evidence of Human Oversight | **EU AI Act Art. 14** | `review.json` approval ledger |
| Audit trail for regulated software | **FDA 21 CFR Part 11** | Signed `steps.jsonl` + `manifest.json` |
| Non-repudiation of data | **HIPAA § 164.312** | Ed25519 signature over manifest |
| AI Risk Management documentation | **NIST AI RMF** | `governance.json` + `analysis.json` |
| Verifiable risk evaluation & HITL audit proof | **AIUC-1 (SOC 2 for Agents)** | `steps.jsonl` + `review.json` + `analysis.json` |

---

## 🏛️ Standards Alignment

- **SCITT (IETF)**: EPI produces SCITT-compatible COSE Sign1 statements for transparency log anchoring.
- **AIUC-1 (Compliance)**: EPI generates structured compliance audit evidence mapping to the six AIUC-1 risk domains for autonomous agent audits. See [AIUC-1 Evidence Mapping](docs/standards/aiuc-1-evidence.md) for details.
- **CycloneDX**: Preserves CycloneDX SBOMs under `artifacts/sbom/` for software supply chain transparency.
- **in-toto (CNCF)**: Roadmap: Exporting `steps.jsonl` as in-toto link files for execution supply chain verification.
- **Ed25519 (RFC 8032)**: All manifests are signed using industry-standard Ed25519 digital signatures.

---

## 🤝 Founding Pilot Program

**EPI is seeking regulated enterprises to pilot AI compliance evidence packaging.**

If you operate AI agents under the **EU AI Act**, **FDA 21 CFR Part 11**, or **SOC 2**, and you need portable, independently-verifiable evidence, we invite you to join our Pilot Program.

### What Pilots Receive:
- **Direct Integration Support**: Hands-on assistance from the maintainers.
- **Priority Roadmap Influence**: Shape the standard based on your compliance needs.
- **Founding Partner Recognition**: Optional listing as an early adopter.

**Contact**: [mohdibrahim@epilabs.org](mailto:mohdibrahim@epilabs.org) — Subject: `EPI Pilot — [Your Organization]`

---

## 📑 Documentation

- 📖 **[Protocol Specification](docs/EPI-SPEC.md)**: The technical wire format.
- ⚖️ **[Governance Guide](docs/POLICY.md)**: Managing rulebooks and evaluations.
- 🇪🇺 **[EU AI Act Prep](docs/EU-AI-ACT-EVIDENCE-PREP.md)**: Evidence workflow guide.
- 🛠️ **[CLI Reference](docs/CLI.md)**: Comprehensive command guide.

---

## 🛡️ Security Model

| Threat | Mitigation |
|:---|:---|
| **Post-Seal Tampering** | SHA-256 file manifest + Ed25519 signature. |
| **Evidence Replay** | Unique `workflow_id` + time-anchored `created_at`. |
| **Secret Leakage** | Automatic forensic redaction of API keys, tokens, and PII. |
| **Signature Spoofing** | Strict `ed25519:<key>:<hex>` format enforcement. |

---

<div align="center">

**Built by EPI Labs.**  
*Ensuring that as AI moves faster, accountability stays ahead.*

[MIT License](LICENSE) | [Contributing](CONTRIBUTING.md) | [Security Policy](SECURITY.md)

</div>
