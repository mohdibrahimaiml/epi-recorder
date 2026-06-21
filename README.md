<div align="center">
  <img src="https://raw.githubusercontent.com/mohdibrahimaiml/epi-recorder/main/docs/assets/logo.png" alt="EPI Logo" width="220"/>

# EPI — The PDF for AI Evidence

### One file. One signature. 100% offline verification.

[![PyPI](https://img.shields.io/pypi/v/epi-recorder?color=blue&label=PyPI&style=for-the-badge)](https://pypi.org/project/epi-recorder/)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg?style=for-the-badge)](https://python.org)
[![Version v4.2.0](https://img.shields.io/badge/version-v4.2.0-purple?style=for-the-badge)](https://github.com/mohdibrahimaiml/epi-recorder/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg?style=for-the-badge)](LICENSE)
[![SCITT Compliant](https://img.shields.io/badge/SCITT-COSE_Sign1-orange?style=for-the-badge)](docs/standards/scitt-predicate.md)
[![AIUC-1 + EU AI Act](https://img.shields.io/badge/AIUC--1-EU%20AI%20Act-success?style=for-the-badge)](docs/standards/aiuc-1-evidence.md)
[![AGT Compatible](https://img.shields.io/badge/Microsoft%20AGT-Importer-blue?style=for-the-badge)](epi_recorder/integrations/agt_adapter/)
[![Tests](https://img.shields.io/badge/tests-1300%2B%20passing-brightgreen?style=for-the-badge)](https://github.com/mohdibrahimaiml/epi-recorder/actions)

```
pip install epi-recorder
epi demo
```

[Quick Start](#-quick-start) · [Developer API](#-developer-api) ·
[Enterprise Features](#-enterprise-features) · [AGT Import](#-microsoft-agt-import) ·
[SCITT & AIUC-1](#-standards) · [CLI Reference](#-commands)

</div>

---

> **EPI Labs builds the evidence layer for the AI economy.**
> `epi-recorder` is the open-source CLI and Python SDK for capturing, signing, and
> verifying AI agent decisions into portable `.epi` files.

*A regulator asks what your AI agent did six months ago. The answer is a file.*

---

## What EPI Does

EPI captures an AI agent's **complete decision trail** — every LLM call, tool invocation,
approval, error, and environmental context — and seals it into a single `.epi` file:
a cryptographically signed, tamper-evident, self-contained forensic container.

**Verification never requires calling home.** Open any `.epi` on an air-gapped machine,
email it to an auditor, archive it for 10 years — it proves itself.

### Evidence Lifecycle

```
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│ CAPTURE  │───→│  SEAL    │───→│  SHARE   │───→│ VERIFY   │───→│  AUDIT   │
│          │    │          │    │          │    │          │    │          │
│ 3 lines  │    │ Ed25519  │    │ Email,   │    │ Offline  │    │ AIUC-1, │
│ of code  │    │ signed   │    │ local,   │    │ browser  │    │ SCITT,  │
│          │    │ container│    │ gateway  │    │ verifier │    │ policy  │
└──────────┘    └──────────┘    └──────────┘    └──────────┘    └──────────┘
```

### Built For

- **AI Engineers** — Drop in one wrapper: `wrap_openai()`, `wrap_anthropic()`, or a LiteLLM callback. No redesign.
- **Compliance Teams** — Open any `.epi` in a browser. Verify signatures, integrity, and chain of custody without installing anything.
- **Enterprises** — Evidence maps to EU AI Act, FDA 21 CFR Part 11, HIPAA, NIST AI RMF, AIUC-1, and SCITT requirements out of the box.

---

## Quick Start

### Install

```bash
pip install epi-recorder
```

### Record + Verify in 60 Seconds

```python
# agent.py
from epi_recorder import record, wrap_openai
from openai import OpenAI

client = wrap_openai(OpenAI())

with record("agent.epi", goal="Analyze sales data"):
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": "Who are our top 3 customers?"}]
    )
```

```bash
python agent.py
epi verify agent.epi
```

You'll see a verification report with:

| Check | Result |
|-------|--------|
| Integrity (SHA-256) | ✅ Verified — every byte accounted for |
| Signature (Ed25519) | ✅ Valid — signed by a known key |
| Identity | ✅ KNOWN — key in trusted registry |
| Policy Decision | ✅ TRUSTED — no policy violations |

### Open the Viewer (No Install Required)

```bash
epi view agent.epi
```

Double-click any `.epi` file — it opens natively as HTML in any browser. The viewer is **self-contained**: no server, no internet, no dependencies.

### Sign & Anchor

```bash
# Generate a key (first time only)
epi keys generate

# Sign the artifact
epi sign agent.epi

# Anchor to a local SCITT transparency ledger
epi scitt register agent.epi

# Verify with SCITT trust
epi verify agent.epi --aiuc1
```

---

## Developer API

### OpenAI / Anthropic

```python
from epi_recorder import record, wrap_openai, wrap_anthropic

# OpenAI
with record("run.epi"):
    client = wrap_openai(OpenAI())
    client.chat.completions.create(model="gpt-4o", messages=[...])

# Anthropic
with record("run.epi"):
    client = wrap_anthropic(Anthropic())
    client.messages.create(model="claude-3-opus", messages=[...])
```

### LangChain

```python
from epi_recorder.integrations.langchain import EPICallbackHandler
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(model="gpt-4o", callbacks=[EPICallbackHandler()])
```

### LiteLLM (100+ Providers)

```python
from epi_recorder.integrations.litellm import EPICallback

litellm.callbacks = [EPICallback()]
response = litellm.completion(model="gpt-4o", messages=[...])
```

### OpenTelemetry

```python
from epi_recorder.integrations.opentelemetry import setup_epi_tracing

setup_epi_tracing()
# All OTel spans are bridged into signed .epi files
```

### pytest Plugin

```bash
pytest --epi                # Generates .epi for each test
pytest --epi-store-failed   # Only keeps failing test evidence
```

### API-Only (No CLI)

```python
from epi_recorder import EpiRecorder

recorder = EpiRecorder()
with recorder.session(goal="Process loan") as session:
    session.log_tool_call("Calculator", input="23 * 17", output="391")
    artifact = session.capture()
```

---

## Enterprise Features

### Tamper-Proof Audit Trail

Every `.epi` file uses the **Envelope v2** container format — a **polyglot HTML+ZIP**
binary that opens natively in any browser and can be extracted programmatically.

Contents:

```
agent.epi
├── manifest.json       — Ed25519-signed root of trust + SHA-256 file hashes
├── steps.jsonl         — Immutable timeline (linked list via prev_hash)
├── environment.json    — Full runtime snapshot (host, Python, deps)
├── analysis.json       — 9-pass policy-grounded fault analysis
├── policy.json         — The rulebook that governed execution
├── review.json         — Signed human review & approval ledger
├── viewer.html         — Self-contained offline browser viewer
└── VERIFY.txt          — Plain-text verification instructions for auditors
```

| Pillar | Mechanism | What It Catches |
|--------|-----------|-----------------|
| **Integrity** | SHA-256 manifest over every file | Any byte modified, added, or removed after sealing |
| **Identity** | Ed25519 signature (RFC 8032) | Spoofed signers; key revocation via `epi keys revoke` |
| **Chain** | `prev_hash` linking every step | Inserted, removed, or reordered steps |
| **Redaction** | HMAC-SHA256 PII replacement | API keys, tokens, secrets never leave the machine in plaintext |
| **Transparency** | SCITT COSE_Sign1 + Merkle receipt | Public ledger anchoring for non-repudiation |

### Gateway (Team Capture Proxy)

```bash
epi gateway serve
```

Starts a FastAPI proxy that captures all AI traffic for a team:
- Automatic .epi generation for every request
- Configurable retention and storage
- OAuth2 / GitHub login for access control
- Webhook integration for SIEM pipelines

### SCITT Transparency Service

```bash
# Local (no dependencies — works offline)
epi scitt register agent.epi

# Remote transparency service
epi scitt register agent.epi --service https://your-scitt-service
```

EPI ships with a **built-in local SCITT service** powered by SQLite + Ed25519. Every registration produces a COSE_Sign1 statement and a Merkle-inclusion receipt — the same structure used by IETF SCITT transparency services.

### Compliance Mapping

| Requirement | Framework | Evidence in .epi |
|-------------|-----------|-------------------|
| Logs of system operation | **EU AI Act Art. 12** | `steps.jsonl` + `environment.json` |
| 10-year technical retention | **EU AI Act Art. 19** | Self-contained `.epi` (format-stable) |
| Human oversight proof | **EU AI Act Art. 14** | `review.json` — signed approval ledger |
| Audit trail (21 CFR Part 11) | **FDA** | Signed `steps.jsonl` + electronic signatures |
| Non-repudiation | **HIPAA § 164.312** | Ed25519 signature over the manifest |
| AI risk management | **NIST AI RMF** | `policy.json` + `analysis.json` |
| Verifiable risk evaluation | **AIUC-1** | 6-domain scoring over full evidence |
| Transparency anchoring | **SCITT (IETF)** | COSE_Sign1 + Merkle inclusion proof |

> EPI is not a compliance guarantee and does not provide legal advice. Whether evidence
> satisfies a specific regulatory threshold is for the auditor or notified body to determine.

---

## Microsoft AGT Import

EPI natively consumes **Microsoft Agent Governance Toolkit (AGT)** evidence — audit logs, flight
recorder data, policy decisions — and converts it into signed `.epi` forensic containers.

```bash
# Auto-detect format and import
epi import agt evidence.json

# Import from a directory
epi import agt evidence/

# Import with strict deduplication
epi import agt evidence.json --strict
```

Supports all AGT export formats: native JSON, CloudEvents, manifest bundles, and directory conventions.
The adapter preserves every AGT field and maps it to the corresponding EPI step types — tool calls,
policy decisions, errors, and metadata — with zero data loss.

[Full AGT integration docs →](epi_recorder/integrations/agt_adapter/)

---

## Standards

### SCITT (IETF Draft)

EPI implements `draft-ietf-scitt-scrapi` with:
- **COSE_Sign1** statements over **Ed25519** — signed statement per artifact
- **Transparency receipts** with Merkle inclusion proofs
- **Local or remote** service: built-in SQLite-backed ledger or any SCITT-compatible service
- **Trust upgrade**: verification reports show `TRANSPARENCY: VERIFIED` when a SCITT receipt is present, raising the trust level from LOW to MEDIUM

[SCITT details →](verify_portal/static/scitt.html)

### AIUC-1

EPI scores artifacts against all **6 AIUC-1 domains** with deterministic, evidence-based checks:

| Domain | Check | Evidence Required |
|--------|-------|-------------------|
| A — Data & Privacy | Redaction quality, env snapshot | `environment.json`, steps with redacted PII |
| B — Security | Signature, integrity | Signed manifest |
| C — Safety | Step integrity chain | `prev_hash` linked timeline |
| D — Reliability | Error handling | Error step detection |
| E — Accountability | Human review binding | Signed `review.json` |
| F — Society | Analysis findings | `analysis.json` with substantive findings |

```bash
epi verify agent.epi --aiuc1
```

Each domain scores PASS / PARTIAL / FAIL with specific evidence gaps reported. An overall summary
determines whether the artifact meets AIUC-1 evidence thresholds.

[AIUC-1 details →](verify_portal/static/aiuc1.html)

### Format Commitment

- **Ed25519** (RFC 8032) — industry-standard digital signatures
- **SCITT** (IETF draft) — COSE Sign1, transparency receipts, Merkle proofs
- **AIUC-1** — all 6 published domains, substantive checks
- **CycloneDX** — SBOM preservation under `artifacts/sbom/`
- **DID:WEB** — decentralized identity resolution for enterprise trust registries

---

## Commands

| Command | What It Does |
|---------|--------------|
| `epi demo` | Record + verify in 60 seconds |
| `epi run <script>` | Record an AI workflow |
| `epi record <session>` | Start an interactive recording session |
| `epi verify <file.epi>` | Integrity, signature, and policy verification |
| `epi verify <file.epi> --aiuc1` | Full AIUC-1 compliance scoring |
| `epi view <file.epi>` | Open the offline forensic viewer |
| `epi audit <file.epi>` | Self-audit across all trust domains |
| `epi sign <file.epi>` | Sign an artifact with Ed25519 |
| `epi keys generate` | Create a signing key pair |
| `epi keys list` | List all keys |
| `epi keys trust <key>` | Trust a public key |
| `epi keys revoke <name>` | Revoke a key |
| `epi share <file.epi> --local` | Share offline (writes to `~/.epi/shares/`) |
| `epi share <file.epi>` | Upload to share portal (no sign-in needed) |
| `epi import agt <file>` | Import AGT evidence |
| `epi scitt register <file.epi>` | Anchor to SCITT (defaults to local) |
| `epi scitt verify <file.epi>` | Verify SCITT receipt |
| `epi review <file.epi>` | Sign a human review |
| `epi gateway serve` | Start the team capture proxy |
| `epi auth login --local` | Local dev session |
| `epi policy init` | Create `epi_policy.json` |
| `pytest --epi` | Generate .epi per test |

---

## Troubleshooting

**`epi: command not found`** — activate your virtual environment or run `pip install epi-recorder` in the same shell.

**`DECISION: WARN` on first verify** — the signing key isn't in your trusted registry yet. Run `epi keys trust <public-key>` to add it. The artifact's integrity and signature are still valid.

**`Integrity: FAILED`** — the `.epi` file was modified after creation. Discard it and re-run.

**`Transparency: FAILED`** — you registered with a remote SCITT service but the receipt verification failed. Use `--local` for an offline receipt that always verifies.

**Share upload fails** — the default share portal may have a transient outage. Use `--local` to write to your local share directory instead.

**AGT import fails** — ensure the input file is a valid AGT export (JSON, JSONL, or directory). Use `--debug` to see the detection steps.

---

## Integration Matrix

| Integration | Status | How |
|-------------|--------|-----|
| OpenAI | ✅ Stable | `wrap_openai()` |
| Anthropic | ✅ Stable | `wrap_anthropic()` |
| LangChain | ✅ Stable | `EPICallbackHandler` |
| LangGraph | ✅ Stable | `EPICheckpointSaver` |
| LiteLLM | ✅ Stable | `EPICallback` — 100+ providers |
| pytest | ✅ Stable | `pytest --epi` |
| OpenTelemetry | ✅ Stable | `setup_epi_tracing()` |
| Microsoft AGT | ✅ Stable | `epi import agt` — auto-detect format |
| FastAPI Gateway | ✅ Stable | `epi gateway serve` |

---

## Security Model

| Threat | Mitigation |
|--------|------------|
| Post-seal tampering | SHA-256 manifest + Ed25519 signature |
| Evidence replay | Unique `workflow_id` + `created_at` timestamp |
| Secret leakage | HMAC-SHA256 redaction of API keys, tokens, PII |
| Signature spoofing | Strict `ed25519:<key>:<sig>` format enforcement |
| Step manipulation | `prev_hash` chain — breaks on insert/remove/reorder |
| Key compromise | `epi keys revoke <name>` — revocation files in `~/.epi/` |

---

## Open Core

| Free / Open Source | Hosted / Team (EPI Labs) |
|--------------------|--------------------------|
| CLI recording & verification | `epi gateway serve` capture proxy |
| Local Ed25519 signing keys | Shared team workspaces |
| Offline browser viewer | Hosted share links |
| AIUC-1 & SCITT auto-audit | Compliance dashboards |
| AGT importer | Enterprise support & SLAs |
| pytest plugin | Priority roadmap influence |

The core `.epi` format and verifier will always be free.

---

## Founding Pilot Program

Working under the EU AI Act, FDA 21 CFR Part 11, or SOC 2? EPI Labs offers hands-on
support for regulated enterprises evaluating EPI as an evidence pipeline.

- **Direct integration support** from maintainers
- **Priority roadmap influence** — shape the standard
- **Founding partner recognition** — optional listing

**Contact:** [mohdibrahim@epilabs.org](mailto:mohdibrahim@epilabs.org?subject=EPI%20Pilot)

---

## Documentation

- [Protocol Specification](docs/EPI-SPEC.md) — technical wire format
- [CLI Reference](docs/CLI.md) — full command reference
- [EU AI Act Evidence Prep](docs/EU-AI-ACT-EVIDENCE-PREP.md) — compliance workflow guide
- [AGT Integration](epi_recorder/integrations/agt_adapter/) — Microsoft AGT importer docs
- [SCITT Conformance](verify_portal/static/scitt.html) — SCITT standard alignment
- [AIUC-1 Compliance](verify_portal/static/aiuc1.html) — AIUC-1 domain scoring
- [AGT Integration Page](verify_portal/static/agt.html) — AGT ↔ EPI pipeline

---

<div align="center">

**Built by [EPI Labs](https://epilabs.org).**
*Ensuring that as AI moves faster, accountability stays ahead.*

[MIT License](LICENSE) · [Contributing](CONTRIBUTING.md) · [Security Policy](SECURITY.md)

</div>
