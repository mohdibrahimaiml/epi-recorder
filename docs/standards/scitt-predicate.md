# EPI SCITT Predicate & COSE Sign1 Specification

**Status:** Active  
**Date:** 2026-05-17  
**Version:** 1.0.0  
**Authors:** EPI Project Team  

---

## Abstract

This document defines the integration of the **Supply Chain Integrity, Transparency, and Trust (SCITT)** standard within the **Evidence Packaged Infrastructure (EPI)** framework. Specifically, it specifies the manual `COSE_Sign1` signed statement implementation, the transparency receipt structure, and the custom EPI predicate type utilized to register `.epi` compliance artifacts with SCITT transparency registries.

---

## 1. Overview

EPI implements **Mode B: SCITT Producer** as defined in the emerging IETF SCITT architecture. This integration provides a decentralized, auditable trust anchor by registering an EPI evidence container's manifest with a SCITT transparency service. 

When registered, the transparency registry issues a cryptographic **SCITT Receipt**, which is embedded back into the `.epi` archive under `artifacts/scitt/receipt.cbor`. Together with the **SCITT Signed Statement** (`artifacts/scitt/statement.cbor`), this enables completely offline, independent verification of the container's integrity and regulatory audit-trail authenticity.

---

## 2. COSE_Sign1 Implementation

To maintain a minimal runtime footprint and maximize package compatibility, EPI implements `COSE_Sign1` (CBOR tag 18) manually using the `cbor2` and standard `cryptography` libraries. This avoids importing heavy external dependencies like `pycose` while maintaining strict compliance with the COSE standard.

### 2.1 COSE Header Parameters
EPI uses standard COSE header labels mapped to their standard IANA values:
* **Algorithm (`alg`, label `1`):** Maps to `COSE_ALG_EDDSA` (`-8`), representing Ed25519 digital signatures.
* **Content Type (`content-type`, label `3`):** Designates the payload as `"application/vnd.epi.manifest+hash"`, declaring that the payload is an EPI manifest cryptographic hash assertion.
* **Key Identifier (`kid`, label `4`):** A byte string containing the unique public key identifier of the signer (defaulting to `b"default"` when not specified).
* **CWT Claims (`cwt-claims`, label `-260`):** Consistent with emerging SCITT implementations, EPI embeds claims in the protected header using the private-use CWT label `-260` (to be migrated to IANA-registered labels upon final standard approval).

### 2.2 CWT Claim Structure
The CWT claims map contains two primary fields:
1. **Issuer (`iss`, claim `1`):** A string containing the identity of the signer (e.g., a DID `did:web:epilabs.org` or a public key name).
2. **Subject (`sub`, claim `2`):** The canonical SHA-256 hex hash of the EPI `manifest.json`.

---

## 3. Cryptographic Binding

EPI creates a secure cryptographic binding between the Ed25519-signed manifest and the SCITT registry.

### 3.1 SCITT Signed Statement
The SCITT Signed Statement is a `COSE_Sign1` envelope structured as follows (shown in CBOR Diagnostic Notation):

```cbor
18([
  protected: {
    1: -8,                             // alg: EdDSA (Ed25519)
    3: "application/vnd.epi.manifest+hash",
    -260: {
      1: "did:web:epilabs.org",        // iss (Issuer DID or Key Name)
      2: "a2fd4b...3c99"               // sub (Subject: canonical manifest SHA-256 hex)
    }
  },
  unprotected: {
    4: h'64656661756c74'               // kid: b"default"
  },
  payload: b"a2fd4b...3c99",           // UTF-8 encoded manifest hash
  signature: h'...'                    // Signature over Sig_structure
])
```

The payload is the canonical SHA-256 hash of the `manifest.json` (excluding the signature field). Because the manifest maps the hashes of all execution files, tool calls, and telemetry logs (`steps.jsonl`), signing the manifest hash guarantees that the entire execution history is bound to the SCITT ledger.

### 3.2 SCITT Receipt
A SCITT transparency service registers the statement and returns a **SCITT Receipt**, which is a `COSE_Sign1` message signed by the transparency service itself.

* **Content Type:** `"application/vnd.scitt.receipt"`
* **Payload:** The raw SHA-256 hash of the original *SCITT Statement* bytes, cryptographically binding the receipt to the statement.
* **Cryptographic Proof:** Signed by the registry's private key, sealing the statement's registration event and placing it in a cryptographically immutable, append-only transparency log.

---

## 4. Verification Workflow

During container auditing via the CLI or offline viewer, the `epi verify` command automatically initiates transparency checks if a SCITT metadata entry is present.

### 4.1 Manifest Metadata Expansion
A registered `.epi` container contains a dedicated `scitt` section in the manifest's `governance` metadata:

```json
"governance": {
  "scitt": {
    "service_url": "https://scitt.epilabs.org",
    "entry_id": "8c2576b5f92a348a74e5088fef295a02",
    "registered_at": "2026-05-17T23:55:00Z",
    "statement_path": "artifacts/scitt/statement.cbor",
    "receipt_path": "artifacts/scitt/receipt.cbor",
    "issuer": "production-signer-v4",
    "algorithm": "EdDSA"
  }
}
```

### 4.2 CLI Verification Logic
When verifying an `.epi` file, `epi verify` executes the following checks:
1. **Extraction:** Retrieves `artifacts/scitt/statement.cbor` and `artifacts/scitt/receipt.cbor` from the binary envelope's embedded ZIP payload.
2. **Payload Match:** Asserts that the statement's payload exactly matches the canonical SHA-256 hash of `manifest.json` (excluding the signature).
3. **Receipt Validation:** Resolves and validates the receipt's structural CBOR integrity.
4. **Trust Assessment:** A valid SCITT receipt elevates the container's trust level. For example, if a signature is cryptographically valid but belongs to an unknown identity (not listed in local trust registries), the presence of a valid SCITT receipt upgrades the overall trust rating from `LOW` to `MEDIUM`—offering independent evidence that the execution was registered with a public, auditable transparency registry.
