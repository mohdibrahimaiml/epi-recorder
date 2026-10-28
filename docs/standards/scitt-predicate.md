# EPI SCITT Predicate & COSE Sign1 Specification

**Status:** Active (technical note)  
**Date:** 2026-05-17  
**Version:** 1.0.0  
**Product version:** 4.7.0  
**Authors:** EPI Project Team  

This is a **format note**, not a user guide. Product docs: [../README.md](../README.md). A SCITT receipt proves a statement was logged; it does not certify a regulation. Local `epi-register` without `--service` is self-issued — see [../EPI_MASTER_DOCUMENTATION.md](../EPI_MASTER_DOCUMENTATION.md).

---

## Abstract

This document defines the integration of the **Supply Chain Integrity, Transparency, and Trust (SCITT)** standard within the **Evidence Packaged Infrastructure (EPI)** framework. Specifically, it specifies the manual `COSE_Sign1` signed statement implementation, the transparency receipt structure, and the custom EPI predicate type utilized to register `.epi` evidence artifacts with SCITT transparency registries.

---

## 1. Overview

EPI implements the **Mode B: SCITT Producer** role described in the emerging
IETF SCITT architecture. When a transparency service is configured, EPI
registers an EPI evidence container's manifest with it and embeds the returned
receipt. This is a transparency registration, not a claim of decentralization:
the trust anchor is whichever service you point `--service` at.

When registered, the transparency registry issues a cryptographic **SCITT Receipt**, which is embedded back into the `.epi` archive under `artifacts/scitt/receipt.cbor`. Together with the **SCITT Signed Statement** (`artifacts/scitt/statement.cbor`), a reviewer can check offline that **this statement was logged** by that registry. A receipt does not prove the entire execution history was captured, and `epi-register` without `--service` is a local self-issued receipt, not an independent ledger entry.

> **Operational note:** Public transparency endpoints such as `https://epilabs.org/scitt` may be protected by Cloudflare and can return HTTP 403 when accessed from automated CLI contexts. For CI, local development, or offline testing, run a local or mock SCITT service and point `--service` at it.

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

The payload is the canonical SHA-256 hash of the `manifest.json` (excluding the signature field). Because the manifest maps the hashes of the sealed members listed in `file_manifest` (including `steps.jsonl` when present), a valid receipt binds exactly those bytes to the transparency registration. It does **not** prove that the recorder captured every action, that the listed steps are truthful, or that files omitted from `file_manifest` existed — capture completeness is a separate claim.

### 3.2 SCITT Receipt
A SCITT transparency service registers the statement and returns a **SCITT Receipt**, which is a `COSE_Sign1` message signed by the transparency service itself.

* **Content Type:** `"application/vnd.scitt.receipt"`
* **Payload:** The raw SHA-256 hash of the original *SCITT Statement* bytes, cryptographically binding the receipt to the statement.
* **Cryptographic Proof:** Signed by the registry's private key, sealing the statement's registration event and placing it in a tamper-evident, append-only transparency log.

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
3. **Receipt Validation:** Verifies the receipt's COSE signature against the
   service's Ed25519 key. If the key cannot be fetched, the result is
   **unverified**, never “valid”; a `local` self-issued receipt is never counted
   as independent transparency.
4. **Trust Assessment:** A cryptographically verified receipt from a
   **non-local** service upgrades a cryptographically valid but unknown-identity
   container from `LOW` to `MEDIUM` — evidence that the statement was
   registered with that service. It does not upgrade a `MISMATCH`/`REVOKED`
   identity, and a local/self-issued receipt leaves the level unchanged.
