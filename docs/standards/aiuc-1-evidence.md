# EPI AIUC-1 Compliance & Evidence Specification

**Status:** Active  
**Date:** 2026-05-18  
**Version:** 1.0.0  
**Authors:** EPI Project Team  

---

## Abstract

This document specifies how the **Evidence Packaged Infrastructure (EPI)** framework acts as the definitive technical evidence container for the **AIUC-1 Compliance and Assurance Framework** (commonly referred to as the "SOC 2 for AI agents"). Specifically, it maps EPI’s cryptographic, timeline, and policy structures directly to the six core trust domains evaluated under an AIUC-1 audit.

---

## 1. Overview of AIUC-1

The **AIUC-1** framework is the industry-standard compliance and assurance program designed specifically for autonomous AI agents. Unlike broad governance structures that only evaluate corporate policy, AIUC-1 demands **verifiable technical proof** of an AI agent's behavior, safety limits, and boundaries in production, including mandatory quarterly adversarial testing and continuous operational audit logging.

By packing all agent inputs, outputs, environmental parameters, and evaluation records into a single cryptographically sealed `.epi` file, EPI provides a portable, self-contained evidence container that auditors can verify offline to demonstrate compliance with AIUC-1 controls.

---

## 2. Core AIUC-1 Trust Domains & EPI Mapping

EPI satisfies the strict evidence requirements of the six AIUC-1 trust domains:

### 2.1 Security (Control Domain 1)
*   **AIUC-1 Requirement:** Verifiable protection against adversarial attacks (prompt injection, jailbreaking), unauthorized tool invocation, and data exfiltration.
*   **EPI Evidence Mapping:**
    *   **Ed25519 Cryptographic Signatures:** Every `.epi` artifact's manifest is signed with Ed25519, ensuring the entire evidence package is completely tamper-evident.
    *   **SCITT Transparency Logging:** Integration with SCITT logs registers the manifest's canonical SHA-256 hash in a public or private append-only transparency ledger, ensuring non-repudiation.
    *   **Tool Execution Capture:** The `steps.jsonl` timeline captures every tool call, its parameters, and returned values in order, allowing auditors to verify that the agent never invoked unauthorized resources or executed unsafe commands.

### 2.2 Privacy and Data Governance (Control Domain 2)
*   **AIUC-1 Requirement:** Strict protection of sensitive data (PII, credentials) from being leaked, logged, or ingested for unauthorized training.
*   **EPI Evidence Mapping:**
    *   **Automatic Forensic Redaction:** Built-in regex-based scanners in `epi_core.redactor` automatically scrub API keys, authorization headers, environment secrets, and PII from the execution steps before they are written to disk.
    *   **Data Boundary Isolation:** The environmental context (`environment.json`) explicitly documents which runtime and package dependencies were used, verifying that training boundaries were respected.

### 2.3 Safety (Control Domain 3)
*   **AIUC-1 Requirement:** Prevention of out-of-scope, harmful, or unintended behaviors.
*   **EPI Evidence Mapping:**
    *   **Deterministic Step Chronology:** `steps.jsonl` records all inputs, reasoning traces, and outputs in an index-sequenced, time-monotonic chain using `prev_hash` binding. If an agent drifts out-of-scope or behaves unsafely, the exact timeline is sealed and cannot be altered.

### 2.4 Reliability (Control Domain 4)
*   **AIUC-1 Requirement:** Consistency of performance and robust error handling.
*   **EPI Evidence Mapping:**
    *   **Error Continuation Auditing:** EPI’s forensic analyzer seals both successful completions and raw exception traces, letting auditors verify how the system handled API failures, bad inputs, or rate limits.

### 2.5 Accountability and Transparency (Control Domain 5)
*   **AIUC-1 Requirement:** Human-in-the-loop (HITL) oversight, clear audit trails, and process transparency.
*   **EPI Evidence Mapping:**
    *   **Human Review Addendum:** The `review.json` ledger provides a cryptographically bound log of human evaluations, sign-offs, and risk verdicts. This file is appended cleanly without modifying or compromising the original raw execution history.
    *   **Policy Preserving:** The `policy.json` and `policy_evaluation.json` payloads travel with the container, preserving the exact rules and thresholds that evaluated the agent run.

### 2.6 Societal Impact (Control Domain 6)
*   **AIUC-1 Requirement:** Alignment of agent behavior with ethical boundaries and risk limits.
*   **EPI Evidence Mapping:**
    *   **Sealed Analyzer Findings:** The `analysis.json` record captures heuristic and policy-grounded evaluations, providing a persistent, machine-readable proof of compliance for safety reviews.

---

## 3. Continuous Audit Verification

Using the `epi verify` command, an auditor can mathematically confirm an agent's continuous alignment with the AIUC-1 standard in seconds:

```bash
epi verify --policy strict loan-approval.epi
```

This command parses the container, recalculates all SHA-256 hashes, validates the Ed25519 signature, checks OTel sequence monotonicity, and confirms SCITT ledger registration—producing an objective, tamper-proof verification report that directly maps back to AIUC-1 control proofs.
