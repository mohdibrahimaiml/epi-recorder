# EPI Auditor's Guide — Independent Verification of .epi Evidence

**Version:** 1.0 | **Last updated:** 2026-07-02

This guide is for auditors, notified bodies, and reviewers who receive a `.epi` file and need to independently verify its cryptographic integrity without contacting the vendor.

## Before You Begin

**You do NOT need to install any software.** You can verify at https://epilabs.org/verify using your browser, which runs all checks client-side. Nothing is uploaded.

**Optionally**, you can install the CLI:
```bash
pip install epi-recorder
```

**You need:**
- The `.epi` file provided by the organization
- The public key fingerprint (provided by the organization, typically 16 hex characters)

---

## Step 1: Open the File

### Option A: Browser (recommended — no install required)

1. Go to https://epilabs.org/verify
2. Drag the `.epi` file into the drop zone, or click to browse
3. Verification runs immediately — nothing is uploaded, everything is client-side

### Option B: CLI

```bash
epi verify <file.epi> --verbose
```

Both produce identical results. They are two interfaces to the same cryptographic verification logic.

---

## Step 2: Interpret the Verification Output

Here is an annotated example of the verification output:

```
[VERIFY] Checking structural integrity...     ✓ ZIP format valid, mimetype present
```
**What this checks:** The file is a valid ZIP archive with an EPI mimetype marker. A failure means the file is corrupted or not an EPI file.

```
[VERIFY] Checking manifest schema...            ✓ 9 sections, all required fields
```
**What this checks:** The manifest conforms to the EPI schema. For Annex IV, this means all 9 sections are present with required fields. A failure means the submission is incomplete.

```
[VERIFY] Checking hash chain integrity...       ✓ All prev_hash values match
```
**What this checks:** Each step in the evidence chain links cryptographically to the previous step via SHA-256 hashes. A failure means a step was inserted, deleted, or modified.

```
[VERIFY] Checking Ed25519 signatures...         ✓ Signed: ed25519:enterprise-key
```
**What this checks:** The manifest was signed with an Ed25519 private key matching the claimed public key. A failure means either the key is wrong (verify the fingerprint the organization provided) or the file was tampered with after signing.

```
[VERIFY] Checking SCITT transparency...         ✓ COSE_Sign1 receipt anchored
```
**What this checks:** The artifact was registered with a SCITT transparency service, providing third-party proof of when it was created. If this check is absent, the organization may be using local SCITT only (acceptable, but less verifiable by third parties).

```
[VERIFY] Checking Annex IV completeness...      ✓ All 9 sections present and signed

DECISION: PASS — No tampering detected. All signatures verified.
```

---

## Step 3: Map to EU AI Act Articles

Use the compliance matrix at `docs/EU-AI-ACT-COMPLIANCE-MATRIX.md` in the repository.

For each article the organization claims compliance with:
1. Find the article in the matrix
2. Check which EPI section and evidence type is listed
3. Open the corresponding section in the .epi viewer
4. Verify the auditor check listed passes

**Example:** Article 13 (Transparency)
- Matrix says: Section 1 (System Description), check `intended_purpose` field
- Open Section 1 of the .epi → verify `intended_purpose` is non-empty and clearly stated
- Confirm the section has a valid Ed25519 signature

---

## Step 4: What To Do If Verification Fails

| Failure | What it means | Action |
|---------|-------------|--------|
| **Hash chain broken** | File was modified after sealing | Request the original, unmodified file from the organization |
| **Signature invalid** | Key mismatch or tampering | Verify the public key fingerprint with the organization. If fingerprint matches but signature fails, the file was modified after signing |
| **SCITT receipt missing** | No third-party transparency | Not all deployments use remote SCITT. Ask if local SCITT is configured. If neither, note as reduced transparency |
| **Section missing** | Incomplete submission | Ask the organization for the missing section(s) |
| **Schema validation fails** | Required fields empty | Flag as incomplete documentation — ask the organization to populate required fields |

---

## Step 5: Escalation and Retention

1. **Save the .epi file and VERIFY.txt output** to your audit file
2. **Record the verification timestamp** and SHA-256 hash
3. **If tampering is detected:** Preserve the tampered file as evidence. Request the original from the organization. Document the discrepancy
4. **File hash chain of custody:** SHA-256 of the entire .epi serves as immutable proof this is the file you received

---

## Step 6: Advanced Verification (CLI)

For deeper forensic analysis, use the CLI:

```bash
# Full verbose verification
epi verify file.epi --verbose --aiuc1 --policy policies/annex-compliance.json

# Extract and inspect individual steps
epi ls file.epi

# View the interactive timeline
epi view file.epi

# Export a verification report
epi audit file.epi --output audit-report.json
```

---

## Appendix A: Glossary

| Term | Definition |
|------|-----------|
| **.epi** | Portable evidence file — a polyglot ZIP+HTML container with cryptographically sealed AI agent decisions |
| **Ed25519** | Elliptic-curve digital signature algorithm used by EPI for signing and verification |
| **SCITT** | Supply Chain Integrity, Transparency, and Trust — IETF standard for transparency services |
| **COSE_Sign1** | CBOR Object Signing and Encryption format used for SCITT receipts |
| **Hash chain** | Each step contains a SHA-256 hash of the previous step, creating an unbreakable chain |
| **prev_hash** | The hash of the previous step, linking each step to its predecessor |
| **Manifest** | The manifest.json file containing step metadata, signatures, and file inventory |
| **mimetype** | A marker at the start of the ZIP identifying it as an EPI container |
| **Declaration of Conformity** | EU AI Act Article 47/Annex V document, 25 typed fields in EPI |
| **Risk Priority Number (RPN)** | probability × severity = RPN score, auto-calculated for risk entries |

---

## Appendix B: Sample Verification Walkthrough

**Scenario:** You receive `annex-iv-compliance.epi` from Acme Corp for their CreditRiskModel-v3 system.

### Browser verification

1. Go to https://epilabs.org/verify
2. Drag `annex-iv-compliance.epi` into the drop zone

**Output:**
```
✓ Structural Integrity — PASS
✓ Manifest Schema — PASS
✓ SHA-256 Integrity — PASS
✓ Hash Chain — PASS
✓ Ed25519 Signature — PASS
DECISION: PASS
SHA-256: e7f3a8b24c1d9e6f5a3b8c2d1e4f7a9b
```

### CLI verification

```bash
$ epi verify annex-iv-compliance.epi --verbose
DECISION: PASS

$ epi ls annex-iv-compliance.epi
Section 01: System Description (signed: ed25519:acme-key)
Section 02: Development Process (signed: ed25519:acme-key)
...
Section 09: Post-Market Monitoring (signed: ed25519:acme-key)
compliance-summary.json (signers: CTO, ML_Engineer)

$ epi audit annex-iv-compliance.epi
Audit report generated: audit-report.json
Findings: 0 critical, 0 high, 0 medium, 0 low
```

### Audit file entry

- **File:** annex-iv-compliance.epi
- **SHA-256:** e7f3a8b24c1d9e6f5a3b8c2d1e4f7a9b
- **Verification:** DECISION: PASS
- **Signatures:** ed25519:acme-key (valid)
- **SCITT:** Local registration present
- **Multi-signer chain:** CTO, ML_Engineer
- **Verified by:** [Auditor name]
- **Date:** [Date]
- **Audit action:** Accepted
