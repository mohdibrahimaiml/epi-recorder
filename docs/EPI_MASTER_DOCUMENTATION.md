# EPI Master Technical & Enterprise System Reference

**Product:** `epi-recorder` | **Current Release Line:** `v4.4.5` | **Container Spec:** EPI Evidence Format v1.1

---

## 1. Executive Summary & Value Proposition

**EPI (Evidence Packaging Interface)** provides the open cryptographic evidence recording and forensic auditability infrastructure for Autonomous AI Systems.

As AI agents execute high-stakes operational workflows—such as financial loan underwriting, BSA/AML transaction monitoring, insurance claim adjudication, automated code deployment, and healthcare clinical triage—they operate with non-deterministic model calls and complex tool invocations. When policy breaches, hallucinations, or operational failures occur, traditional application logging is insufficient for legal, compliance, and regulatory audits.

**`epi-recorder`** solves the "AI Accountability Black Box" by producing self-contained, portable, self-viewing, and cryptographically sealed evidence artifacts (`.epi` files).

```
   ┌────────────────┐      ┌─────────────────────────┐      ┌────────────────────────┐
   │ Autonomous AI  │ ───► │  `epi-recorder` SDK/CLI │ ───► │ Cryptographic Artifact │
   │ Agent Workflow │      │  Auto-Trace & Policy    │      │    `recording.epi`     │
   └────────────────┘      └─────────────────────────┘      └────────────────────────┘
                                                                          │
                                                                          ▼
                                                             ┌────────────────────────┐
                                                             │ Offline Self-Viewing   │
                                                             │ Forensic & Audit UI    │
                                                             │ (`viewer.html` / CLI)  │
                                                             └────────────────────────┘
```

### Core Design Principles
1. **Zero Vendor Lock-In (Self-Viewing Artifacts):** Every `.epi` artifact contains an embedded, offline-first HTML browser UI (`viewer.html`). Regulators, legal counsel, and third-party auditors can open a `.epi` file in any standard web browser without server backends or database dependencies.
2. **Cryptographic Non-Repudiation:** Evidence payloads are sealed using SHA-256 canonical hashing and signed with Ed25519 or ECDSA public-key cryptography.
3. **Step-Level Hash Chain (`prev_hash`):** EPI builds an immutable hash chain across all steps in the execution timeline. Each step contains the SHA-256 hash of the previous step, preventing step omission, reordering, or injection.
4. **Human Oversight & Attestation (Model A Ledger):** Human auditors can review flagged agent steps, record verdicts, and append cryptographically signed review records (`review.json`) directly onto the evidence ledger.
5. **Zero Data Exfiltration Verification:** Verification happens entirely in local browser memory via WASM/JS crypto (`@noble/ed25519` + SubtleCrypto). No evidence leaves the user's desktop.

---

## 2. System Architecture & Components

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                                    SYSTEM ARCHITECTURE                                  │
├───────────────────────────────────┬─────────────────────────────────────────────────────┤
│ Component                         │ Role & Description                                  │
├───────────────────────────────────┼─────────────────────────────────────────────────────┤
│ 1. The Recorder (epi-recorder)    │ Python SDK & CLI kernel that captures execution     │
│                                   │ streams, redacts secrets, and seals signed .epi     │
│                                   │ containers.                                         │
│ 2. The Browser Verifier           │ Zero-knowledge client-side verification engine in    │
│                                   │ HTML/JS/WASM for instant drop-and-verify audit.     │
│ 3. Enterprise Gateway             │ Async FastAPI verification gateway for automated    │
│                                   │ high-throughput CI/CD & enterprise ingestion.       │
│ 4. Policy & Fault Analyzer        │ Governance rulebook evaluator and 4-pass forensic    │
│                                   │ diagnostic analyzer (P1-P4 passes).                 │
└───────────────────────────────────┴─────────────────────────────────────────────────────┘
```

### A. The Recorder (`epi-recorder`)
- **Role:** The execution instrumentation engine installed in application environments.
- **Mechanism:** Explicit SDK API (`with epi.record(...)`), auto-patching wrappers (`wrap_openai`), or CLI invocation (`epi run script.py`).
- **Output:** Generates `.epi` ZIP containers sealed with cryptographic signatures and containing complete trace, policy evaluation, environment snapshots, and embedded presentation UI.

### B. The Security Kernel (`epi_core/trust.py` & `container.py`)
- **Canonical Hashing:** Sorts JSON keys, normalizes line endings, and generates deterministic SHA-256 hashes over member files.
- **Asymmetric Digital Signatures:** Signs the canonical manifest hash using Ed25519 elliptic curve keys stored in `~/.epi/keys`.
- **Secret Redaction (`epi_core/redactor.py`):** Runs an in-memory regex sanitization engine before writing logs to disk, redacting API keys (`sk-proj-...`, `AKIA...`, private key headers) with `***REDACTED***`.

### C. The Browser Verifier (`verify.html` / `app.js`)
- **Role:** Universal reader and forensic investigation tool.
- **Offline Self-Viewing:** Uses `JSZip` and `@noble/ed25519` in browser memory.
- **Sandboxed Safe-View:** Loads the embedded `viewer.html` into a restricted `<iframe>` sandbox (`sandbox="allow-scripts allow-popups"` without `allow-same-origin`), allowing rich visualization without XSS risks.

### D. The Governance & Fault Engine (`epi_core/fault_analyzer.py` & `policy.py`)
- **Policy Engine:** Evaluates domain rulebooks (`epi_policy.json`) against execution traces, measuring control pass rates and risk thresholds.
- **4-Pass Diagnostic Analyzer:** Analyzes execution logs across 4 heuristic passes:
  - **Pass 1 (P1 Error Continuation):** Detects agents ignoring upstream API errors or exception responses.
  - **Pass 2 (P2 Constraint Violation):** Detects numerical threshold breaches (e.g. $45,000 transfer exceeding $10,000 AML cap) while recognizing compliant escalation holds as policy successes.
  - **Pass 3 (P3 Sequence Violation):** Detects out-of-order tool call workflows.
  - **Pass 4 (P4 Context Drop):** Detects dropped context or missing prompt variables on intermediate non-terminal steps.

---

## 3. `.epi` Evidence Container Specification (v1.1)

An `.epi` container is a portable ZIP archive adhering to the EPI Evidence Specification v1.1.

```
recording.epi (ZIP Archive)
├── manifest.json       # Cryptographic manifest, signature, & member file hashes
├── trace.jsonl          # Step-by-step execution trace with prev_hash chain
├── policy_eval.json     # Formal policy evaluation & governance rule breakdown
├── analysis.json        # 4-pass forensic fault & drift analysis report
├── review.json          # Human review attestation ledger & audit records
├── environment.json     # Execution environment snapshot (Python, OS, packages)
└── viewer.html          # Embedded offline forensic presentation UI
```

### 3.1 File Manifest Contract (`manifest.json`)

```json
{
  "spec_version": "4.4.6",
  "container_version": "1.1",
  "created_at": "2026-08-09T19:50:00Z",
  "workflow_id": "demo_banking_aml",
  "workflow_name": "BSA/AML Transaction Risk Monitoring",
  "signer_identity": "compliance@bank.example",
  "public_key": "ed25519:a1b2c3d4...",
  "signature_algorithm": "ed25519",
  "payload_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
  "file_manifest": {
    "trace.jsonl": "5a91b4...",
    "policy_eval.json": "8c2d1e...",
    "analysis.json": "4f9b2c...",
    "environment.json": "9f3a7b...",
    "review.json": "1b4c9e..."
  },
  "signature": "ed25519:bank_key:3045022100..."
}
```

### 3.2 Trace Step Structure with `prev_hash` Chain (`trace.jsonl`)

Every step in `trace.jsonl` includes timestamping, step kind classification, structured content, and the cryptographic hash of the previous step:

```json
{
  "step_index": 8,
  "timestamp": "2026-08-09T19:50:02.120Z",
  "kind": "agent.decision",
  "prev_hash": "a4f8c2e1d09b3a7f...",
  "content": {
    "decision": "flag_for_compliance_officer",
    "recommendation": "flag_for_compliance_officer",
    "rationale": "Transaction TX-99120 ($45,000) exceeds mandatory $10,000 BSA/AML threshold."
  }
}
```

---

## 4. Human Oversight Ledger & Outcome Mapping

Human auditor attestations are recorded in `review.json` and appended to the `.epi` container without breaking the original manifest signature:

| Auditor Verdict | Ledger Outcome | Meaning in Audit Trail | UI Section 7 Display |
| :--- | :--- | :--- | :--- |
| **Approve** | `dismissed` | Auditor reviewed policy flag and dismissed it | `FLAG CLEARED (APPROVED)` |
| **Reject** | `confirmed_fault` | Auditor confirmed a policy or model violation | `FAULT CONFIRMED (REJECTED)` |
| **Escalate** | `skipped` | Auditor deferred judgment for senior review | `REVIEW SKIPPED` |

---

## 5. EU AI Act & Regulatory Compliance Alignment

EPI is specifically architected to satisfy the technical documentation and record-keeping mandates of the **EU AI Act (Regulation EU 2024/1689)** for High-Risk AI Systems:

- **Article 12 (Record-Keeping / Automatic Logging):** Captures complete execution traces (`trace.jsonl`), timestamped tool calls, and model outputs with tamper-evident cryptographic sealing.
- **Article 14 (Human Oversight):** Provides human-in-the-loop approval workflows (`agent.approval.request` / `agent.approval.response`) and cryptographically signed human attestation ledgers (`review.json`).
- **Article 15 (Accuracy, Robustness & Cybersecurity):** Provides deterministic 4-pass fault analysis, policy control evaluation, secret redaction, and Ed25519 digital signatures.
- **Annex IV (Technical Documentation):** Generates standardized technical evidence bundles for conformity assessments and regulatory audits.

---

## 6. Developer Integration Quickstart

### Python Context Manager
```python
import epi_recorder as epi

with epi.record("banking_aml_audit.epi", workflow_name="BSA/AML Monitoring") as session:
    # 1. Log policy check constraint
    session.log_policy_check("bsa_aml_10k_threshold", passed=True, threshold=10000, actual=45000)
    
    # 2. Execute agent logic & log decision
    session.log_decision("flag_for_compliance_officer", rationale="Exceeds $10,000 threshold.")
    
    # 3. Request & log human supervisor approval
    session.log_approval_request("release_wire_hold")
    session.log_approval_response("release_wire_hold", approved=True, reviewer="aml_officer_sarah@bank.example")
```

### CLI Commands
```bash
# Record an agent execution session
epi record --out audit.epi python agent_script.py

# Verify artifact integrity, signature, and policy compliance
epi verify audit.epi

# Launch offline forensic browser viewer
epi view audit.epi
```

---

## 7. Documentation Directory Catalog

For additional specialized guides, consult the primary documentation catalog:

- **EU AI Act Compliance Matrix**: [`EU-AI-ACT-COMPLIANCE-MATRIX.md`](./EU-AI-ACT-COMPLIANCE-MATRIX.md)
- **Technical Documentation (Annex IV)**: [`ANNEX-IV.md`](./ANNEX-IV.md)
- **Auditor Verification Manual**: [`AUDITORS-GUIDE.md`](./AUDITORS-GUIDE.md)
- **Governance Policy Engine**: [`POLICY-AND-FAULT-ANALYZER.md`](./POLICY-AND-FAULT-ANALYZER.md)
- **Enterprise Trust Profile**: [`ENTERPRISE-TRUST-PROFILE.md`](./ENTERPRISE-TRUST-PROFILE.md)
- **CLI Reference Manual**: [`CLI.md`](./CLI.md)
- **Self-Hosted Deployment Runbook**: [`SELF-HOSTED-RUNBOOK.md`](./SELF-HOSTED-RUNBOOK.md)
- **Sector Demos Overview**: [`assets/SECTOR_DEMOS.md`](./assets/SECTOR_DEMOS.md)
