# AIUC-1 Contribution Submission — EPI Labs

**Organization:** EPI Labs  
**Contact:** [your email]  
**Project:** EPI (Episodic Process Integrity) Recorder  
**Portal:** https://epilabs.org/verify  
**DID:** did:web:epilabs.org  
**GitHub:** https://github.com/mohdibrahimaiml/epi-recorder  

---

## Executive Summary

EPI is an open-source protocol for cryptographically recording, verifying, and attesting to AI system behavior. Every decision, guardrail check, and redaction is sealed in a tamper-evident `.epi` artifact that can be independently verified by anyone with a browser — no installation required.

**Live demo:** Drop any `.epi` file at https://epilabs.org/verify to get an instant trust report with AIUC-1 domain mapping.

---

## How EPI Maps to AIUC-1's Six Trust Domains

### Domain A — Data & Privacy

| Evidence | How EPI Provides It |
|---|---|
| Data minimization | Automatic regex-based redaction of API keys, tokens, PII with HMAC-SHA256 placeholders |
| Environment isolation | `environment.json` captures system context separately from workflow data |
| Redaction audit trail | HMAC-SHA256 placeholders allow forensic re-verification without exposing secrets |

**Status:** PARTIAL (redaction works; formal data-retention policy not yet documented)

---

### Domain B — Security

| Evidence | How EPI Provides It |
|---|---|
| Cryptographic integrity | SHA-256 file manifest; any tampering breaks verification |
| Authenticity | Ed25519 signatures on every manifest; signer identity checked against trust registry |
| Transparency | Optional SCITT (Supply Chain Integrity, Transparency and Trust) anchoring to transparency logs |
| DID:WEB identity | `did:web:epilabs.org` resolves to public key at `/.well-known/did.json` |

**Status:** PARTIAL (signature + integrity are live; SCITT is opt-in, not yet deployed to production)

---

### Domain C — Safety

| Evidence | How EPI Provides It |
|---|---|
| Tamper-evident sequence | `prev_hash` chain links every step; breaking the chain invalidates the artifact |
| Monotonic timestamps | Steps verified to have non-decreasing timestamps |
| Sequence completeness | Every tool.call must have a tool.response; every llm.request has a response or error |

**Status:** PASS (all checks automated in verification pipeline)

---

### Domain D — Reliability

| Evidence | How EPI Provides It |
|---|---|
| Completeness | Audit checks that every request has a corresponding response |
| Error capture | `llm.error` steps are captured and displayed, not hidden |
| Step count attestation | Manifest `total_steps` is signed and verified against actual step count |

**Status:** PASS (all checks automated)

---

### Domain E — Accountability

| Evidence | How EPI Provides It |
|---|---|
| Digital signature | Every artifact is signed with Ed25519; signer checked against trust registry |
| Identity verification | Signer public key matched against local registry, DID:WEB, or remote trust anchor |
| Human review | `review.json` support for manual compliance review |
| Policy enforcement | `policy.json` + `policy_evaluation.json` for guardrail evidence |

**Status:** PARTIAL (signing is live; human review workflow exists but is not yet mandatory)

---

### Domain F — Society

| Evidence | How EPI Provides It |
|---|---|
| Analysis | `analysis.json` captures automated or manual forensic analysis |
| Redaction audit trail | HMAC-SHA256 placeholders prove redaction occurred without revealing secrets |
| Open source | Full protocol and reference implementation on GitHub |

**Status:** PARTIAL (analysis framework exists; community governance model not yet formalized)

---

## What Is Ready Now

| Component | Status | Evidence |
|---|---|---|
| Verify portal | ✅ Live | https://epilabs.org/verify |
| DID document | ✅ Live | https://epilabs.org/.well-known/did.json |
| Trust registry | ✅ Live | https://epilabs.org/.well-known/epi-trust-registry.json |
| Ed25519 signing | ✅ Working | CLI `epi verify` + web portal both validate |
| SCITT module | ✅ Code complete | `epi_recorder/auto_scitt.py` — opt-in via env var |
| AIUC-1 mapping | ✅ Working | 6-domain mapping in `epi_core/aiuc1_mapping.py` |
| Independent verification | ✅ Verified | Fresh environment test passed with only DID document |

## What Is Still Pending

| Gap | Impact | Timeline |
|---|---|---|
| Production SCITT service | "SCITT-anchored" claim requires live transparency log | Q3 2026 (evaluating providers) |
| Formal AIUC-1 control IDs | Mapping is to domains only; specific controls need AIUC-1 team input | After consultation |
| Horizontal rate limiting | In-memory store resets on deploy; needs Redis for scale | Post-revenue |
| EU AI Act specific mappings | Need legal review before claiming compliance | Q3 2026 |

---

## Artifacts for Review

1. **Demo artifact:** `epi-recordings/demo_refund.epi` — verified at https://epilabs.org/verify
2. **Portal source:** `verify_portal/` in GitHub repo
3. **AIUC-1 mapping source:** `epi_core/aiuc1_mapping.py`
4. **Trust layer source:** `epi_core/trust.py`
5. **DID document source:** `verify_portal/static/.well-known/did.json`

---

## Honest Disclosures

- We do **not** claim full AIUC-1 compliance. We map to the six declared domains and are seeking guidance on specific control IDs.
- The EU AI Act "Omnibus" dates in our earlier marketing draft were unverifiable and have been removed.
- SCITT anchoring is opt-in (`EPI_SCITT_AUTO_ANCHOR=1`) because we do not yet operate a production transparency service.
- We are a pre-revenue solo-founder project. Infrastructure cost is ~$5/month.

---

*Prepared: 2026-05-24*
*EPI Labs — did:web:epilabs.org*
