# EPI LABS — Industry Sector Demo Artifacts & Verification Reference

This directory contains standalone `.epi` evidence containers demonstrating real-world AI decision workflows across 8 key industry sectors.

> [!IMPORTANT]
> **Illustrative Demonstration Notice**  
> These artifacts demonstrate the structural, cryptographic, and governance capabilities of the **EPI Evidence Container Format (v1.1)** using synthetic operational workflows. Like demonstration packages from OPAQUE Systems or AGICOMPLY, these examples illustrate format specifications, audit trails, and policy evaluation mechanics for sales, investor, and pilot evaluation purposes.

---

## Sector Demonstration Index

| Industry Sector | Workflow & Decision Demonstrated | Policy Constraint & Governance Rule | `.epi` Artifact | Verification Command |
| :--- | :--- | :--- | :--- | :--- |
| **Finance / Banking** | **Loan Underwriting:** Credit box eligibility, soft FICO pull, & income verification | Credit Box (`min_fico: 680`, `max_dti: 0.42`) | `demo-finance-loan-underwriter.epi` | `epi verify examples/demo-finance-loan-underwriter.epi` |
| **Healthcare** | **Clinical Triage:** High-risk symptom screening & emergency escalation handoff | ACS Red Flag Screening (`ED_now` disposition) | `demo-healthcare-clinical-triage.epi` | `epi verify examples/demo-healthcare-clinical-triage.epi` |
| **Insurance Claims** | **Claim Adjudication:** Water damage claim line-item audit & payout recommendation | Coverage Limits & Deductible Audit (`HO3-884102`) | `demo-insurance-claim-adjudication.epi` | `epi verify examples/demo-insurance-claim-adjudication.epi` |
| **Legal** | **Contract Review:** Vendor SaaS MSA clause comparison against corporate playbook | Playbook Risk Flags (`limitation_of_liability`) | `demo-legal-contract-review.epi` | `epi verify examples/demo-legal-contract-review.epi` |
| **Banking / AML** | **AML Transaction Monitoring:** International wire transfer compliance screening | `aml_threshold_check` (BSA $10,000 threshold flag) | `demo-banking-aml.epi` | `epi verify examples/demo-banking-aml.epi` |
| **Hiring / HR** | **Candidate Resume Screening:** Technical stack & experience benchmarking | `fair_hiring_no_protected_class` (Non-discrimination) | `demo-hiring-screening.epi` | `epi verify examples/demo-hiring-screening.epi` |
| **Insurance UW** | **Commercial Property Underwriting:** High-valuation property pricing & flood risk | `high_risk_pricing_human_review` (Auto-bind cap) | `demo-insurance-underwriting.epi` | `epi verify examples/demo-insurance-underwriting.epi` |
| **Lending** | **Mortgage Affordability:** Qualified Mortgage debt-to-income affordability check | `debt_to_income_affordability_check` (CFPB ATR 43%) | `demo-lending-affordability.epi` | `epi verify examples/demo-lending-affordability.epi` |

Open any `.epi` with `epi view`, or drop it on <https://epilabs.org/verify>.

---

## How to Verify Any Artifact

Every `.epi` file in this folder is cryptographically sealed and can be verified offline using the `epi` CLI:

```bash
# Verify cryptographic signature, Merkle payload integrity, and identity status
epi verify examples/demo-banking-aml.epi

# View offline in default browser
epi view examples/demo-banking-aml.epi
```

---

## Security & Credential Confirmation

> [!NOTE]
> **API Key Safety Confirmation:**  
> All demo scripts read LLM API keys exclusively from the `GROQ_API_KEY` environment variable or fall back to mock responses if unset. No API keys or sensitive credentials are hardcoded, logged, or present in any committed artifact, trace log, or HTML file in this repository.
