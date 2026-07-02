# EU AI Act — 113-Article Compliance Matrix for EPI

**Version:** 1.0 | **Generated:** 2026-07-02 | **Tool:** epi-recorder v4.2.0

This matrix maps every article of the EU AI Act (Regulation 2024/1689) to EPI's evidence capabilities. Each article is categorized by whether EPI directly generates evidence, indirectly supports a process, or is out of scope.

| Column | Meaning |
|--------|---------|
| **Art.** | Article number and short title |
| **Category** | `Evidence` (generates artifacts), `Governance` (organizational), `Institutional` (EU bodies), `Procedural` (enforcement), `Transitional` (phasing) |
| **EPI** | `Direct` (EPI generates evidence), `Indirect` (EPI supports process), `Out of scope` (not evidence-related) |
| **Section** | Annex IV section(s) mapping |
| **Evidence** | What EPI produces |
| **Command** | CLI command |
| **Auditor check** | What the auditor verifies |

---

## Articles 1-20: Scope and Prohibited Practices

| Art. | Category | EPI | Section | Evidence | Command | Auditor Check |
|------|----------|-----|---------|----------|---------|---------------|
| 1 — Subject matter | Transitional | Out of scope | — | — | — | N/A |
| 2 — Scope | Transitional | Out of scope | — | — | — | N/A |
| 3 — Definitions | Transitional | Out of scope | — | — | — | N/A |
| 4 — AI literacy | Governance | Indirect | 2 (Development) | Training records in development docs | — | Verify training documentation references |
| 5 — Prohibited AI practices | Evidence | Direct | 1, 5, 8 | System description, risk register, DoC | epi annex pack → verify | Verify system not in prohibited category, risk assessment complete |
| 6 — Classification of high-risk | Evidence | Direct | 1, 5 | System description, risk classification | epi annex pack | Verify classification rationale in Section 1 |
| 7 — Amendments to Annex III | Institutional | Out of scope | — | — | — | N/A |
| 8 — Compliance with requirements | Evidence | Direct | All 9 | Full Annex IV artifact | epi annex pack → verify | Verify all 9 sections present and signed |
| 9 — Risk management system | Evidence | Direct | 5 (Risk Mgmt) | Risk register with RPN scores | epi annex report | Verify risk entries have probability×severity, risk_level computed |
| 10 — Data and data governance | Evidence | Direct | 2 (Development), 7 (Standards) | Training/validation/test datasheets | epi annex report | Verify datasheets present, data governance model complete |
| 11 — Technical documentation | Evidence | Direct | 1, 2, 4, 5, 7 | System description, dev process, metrics, risk, standards | epi annex pack → verify | Verify hash chain, all required sections, SCITT receipt |
| 12 — Record-keeping | Evidence | Direct | 3 (Monitoring) | Event logs, monitoring records | epi annex report | Verify logging records present, retention policy documented |
| 13 — Transparency | Evidence | Direct | 1 (System) | System description, intended_purpose | epi annex report | Verify intended_purpose field non-empty, user_interface_description present |
| 14 — Human oversight | Evidence | Direct | 3 (Monitoring) | Human-in-the-loop configuration | epi annex report | Verify override controls documented |
| 15 — Accuracy, robustness, cybersecurity | Evidence | Direct | 4 (Metrics), 5 (Risk) | Performance metrics, cybersecurity risk entries | epi annex report | Verify accuracy metrics, robustness thresholds, cybersecurity measures |
| 16 — Obligations of providers | Governance | Indirect | 8 (DoC) | Declaration of Conformity | epi annex multi-sign | Verify DoC signed by authorized representative |
| 17 — Quality management system | Evidence | Indirect | 2 (Development), 7 (Standards) | QMS documentation references | epi annex report | Verify QMS documentation references in development section |
| 18 — Documentation retention | Evidence | Indirect | 3 (Monitoring) | Retention policy, timestamps | epi verify | Verify timestamps present, retention period documented |
| 19 — Authorized representatives | Governance | Indirect | 8 (DoC) | Authorized representative in DoC | epi annex multi-sign | Verify representative name and mandate in DoC |
| 20 — Importers | Governance | Indirect | 8 (DoC) | Importer information | epi annex report | Verify importer info if applicable |

## Articles 21-40: Notified Bodies and Standards

| Art. | Category | EPI | Section | Evidence | Command | Auditor Check |
|------|----------|-----|---------|----------|---------|---------------|
| 21 — Obligations of importers | Governance | Indirect | 8 (DoC) | Importer verification records | epi annex report | Verify importer compliance check documented |
| 22 — Distributors | Governance | Indirect | 8 (DoC) | Distribution chain | epi annex report | Verify distribution compliance documented |
| 23 — Deployer obligations | Evidence | Direct | 3 (Monitoring) | Monitoring records, human oversight logs | epi annex report | Verify deployer monitoring plan |
| 24 — Provider becomes deployer | Governance | Indirect | 6 (Lifecycle) | System modification records | epi annex report | Verify modification history |
| 25 — Value chain responsibilities | Governance | Indirect | 1, 6 | System description, lifecycle changes | epi annex report | Verify supply chain documentation |
| 26 — Obligations of product manufacturers | Governance | Indirect | 1 (System) | Product integration docs | epi annex report | Verify product safety integration |
| 27 — Notified bodies | Institutional | Out of scope | — | — | — | N/A — institutional |
| 28 — Subsidiaries and subcontractors | Governance | Indirect | 8 (DoC) | Organizational structure | epi annex report | Verify organizational documentation |
| 29 — Application for notification | Institutional | Out of scope | — | — | — | N/A — institutional |
| 30 — Requirements for notified bodies | Institutional | Out of scope | — | — | — | N/A — institutional |
| 31 — Presumption of conformity | Evidence | Direct | 7 (Standards) | Applied standards database | epi annex report | Verify harmonised standards listed |
| 32 — Conformity assessment bodies | Institutional | Out of scope | — | — | — | N/A — institutional |
| 33 — Operational obligations | Institutional | Out of scope | — | — | — | N/A — institutional |
| 34 — Information obligations | Institutional | Out of scope | — | — | — | N/A — institutional |
| 35 — Notifying authorities | Institutional | Out of scope | — | — | — | N/A — institutional |
| 36 — Coordination of notified bodies | Institutional | Out of scope | — | — | — | N/A — institutional |
| 37 — Conformity assessment procedures | Evidence | Direct | 8 (DoC) | Conformity assessment method | epi annex report | Verify assessment procedure documented |
| 38 — EU declaration of conformity | Evidence | Direct | 8 (DoC) | DeclarationOfConformity (25 fields) | epi annex multi-sign | Verify all 25 DoC fields completed |
| 39 — CE marking | Governance | Indirect | 8 (DoC) | CE marking status | epi annex report | Verify CE marking referenced |
| 40 — Harmonised standards | Evidence | Direct | 7 (Standards) | Standards database | epi annex report | Verify standards listed with versions |

## Articles 41-60: Transparency and Governance

| Art. | Category | EPI | Section | Evidence | Command | Auditor Check |
|------|----------|-----|---------|----------|---------|---------------|
| 41 — Common specifications | Governance | Indirect | 7 (Standards) | Specification references | epi annex report | Verify common specs referenced |
| 42 — Presumption of conformity | Evidence | Indirect | 7, 8 | Standards + DoC alignment | epi annex report | Verify standards mapped to requirements |
| 43 — Conformity assessment for high-risk | Evidence | Direct | 8 (DoC), All sections | Full Annex IV package | epi verify --verbose | Verify all sections, signatures, SCITT |
| 44 — Certificates | Evidence | Direct | 8 (DoC) | Certificate references | epi annex report | Verify certificate numbers |
| 45 — EU database registration | Evidence | Direct | 1, 8 | System registration record | epi annex notify | Verify registration exists, system metadata matches |
| 46 — Registration obligations | Evidence | Direct | 1, 8 | Registration records | epi annex notify | Verify registration obligations met |
| 47 — Information to notified bodies | Evidence | Direct | 8 (DoC) | Notified body communication log | epi annex report | Verify communication records |
| 48 — General-purpose AI models | Evidence | Direct | 1, 4, 5 | System description, risk for GPAI | epi annex report | Verify GPAI classification, risk category |
| 49 — Obligations for GPAI providers | Evidence | Direct | 1, 2, 4 | GPAI documentation | epi annex pack | Verify GPAI requirements documented |
| 50 — Self-assessment for GPAI | Evidence | Direct | 5 (Risk), 8 (DoC) | Self-assessment records | epi annex report | Verify self-assessment complete |
| 51 — Downstream provider obligations | Governance | Indirect | 6 (Lifecycle) | Downstream modifications | epi annex report | Verify downstream changes documented |
| 52 — Systemic risk GPAI | Evidence | Direct | 5 (Risk) | Systemic risk register entries | epi annex report | Verify systemic risk assessment |
| 53 — Codes of practice | Governance | Indirect | 7 (Standards) | Code of practice references | epi annex report | Verify code adherence documented |
| 54 — Transparency for certain AI systems | Evidence | Direct | 1 (System), 3 (Monitoring) | Transparency documentation | epi annex report | Verify transparency measures documented |
| 55 — AI regulatory sandboxes | Institutional | Out of scope | — | — | — | N/A — institutional |
| 56 — Testing in real-world conditions | Evidence | Direct | 3 (Monitoring), 4 (Metrics) | Real-world testing results | epi annex report | Verify testing conditions, results, consent |
| 57 — Measures for SMEs and startups | Procedural | Out of scope | — | — | — | N/A — procedural |
| 58 — Processing personal data | Evidence | Indirect | 1, 3 | Data processing documentation | epi annex report | Verify data processing documented |
| 59 — Post-market monitoring | Evidence | Direct | 9 (Post-Market) | Post-market monitoring plan | epi annex report | Verify monitoring plan, thresholds, escalation |
| 60 — Reporting of serious incidents | Evidence | Direct | 9 (Post-Market) | Serious incident definition, deadlines | epi annex report | Verify incident reporting thresholds |

## Articles 61-80: Enforcement and Governance

| Art. | Category | EPI | Section | Evidence | Command | Auditor Check |
|------|----------|-----|---------|----------|---------|---------------|
| 61 — Market surveillance | Procedural | Out of scope | — | — | — | N/A — enforcement |
| 62 — AI Office | Institutional | Out of scope | — | — | — | N/A — institutional |
| 63 — European AI Board | Institutional | Out of scope | — | — | — | N/A — institutional |
| 64 — Advisory forum | Institutional | Out of scope | — | — | — | N/A — institutional |
| 65 — Scientific panel | Institutional | Out of scope | — | — | — | N/A — institutional |
| 66 — EU database | Evidence | Indirect | 1, 8 | Registration data | epi annex notify | Verify registration data matches .epi |
| 67 — Access to data by Commission | Procedural | Out of scope | — | — | — | N/A — procedural |
| 68 — Confidentiality | Procedural | Out of scope | — | — | — | N/A — procedural |
| 69 — Designation of national authorities | Institutional | Out of scope | — | — | — | N/A — institutional |
| 70 — Powers of authorities | Procedural | Out of scope | — | — | — | N/A — enforcement |
| 71 — Administrative fines / penalties | Procedural | Out of scope | — | — | — | N/A — enforcement |
| 72 — Penalties for providers | Procedural | Out of scope | — | — | — | N/A — enforcement |
| 73 — Right to lodge complaint | Procedural | Out of scope | — | — | — | N/A — procedural |
| 74 — Right to explanation | Evidence | Direct | 1 (System), 3 (Monitoring) | Decision explanation records | epi annex report | Verify explanation mechanism documented |
| 75 — Representative actions | Procedural | Out of scope | — | — | — | N/A — procedural |
| 76 — Supervision of notified bodies | Institutional | Out of scope | — | — | — | N/A — institutional |
| 77 — Evaluation by Commission | Procedural | Out of scope | — | — | — | N/A — procedural |
| 78 — Delegated acts | Procedural | Out of scope | — | — | — | N/A — procedural |
| 79 — Exercise of delegation | Procedural | Out of scope | — | — | — | N/A — procedural |
| 80 — Committee procedure | Procedural | Out of scope | — | — | — | N/A — procedural |

## Articles 81-100: Implementation and Amendments

| Art. | Category | EPI | Section | Evidence | Command | Auditor Check |
|------|----------|-----|---------|----------|---------|---------------|
| 81 — Amendment to Regulation (EC) 300/2008 | Procedural | Out of scope | — | — | — | N/A |
| 82 — Amendment to Regulation (EU) 167/2013 | Procedural | Out of scope | — | — | — | N/A |
| 83 — Amendment to Regulation (EU) 168/2013 | Procedural | Out of scope | — | — | — | N/A |
| 84 — Amendment to Directive (EU) 2016/797 | Procedural | Out of scope | — | — | — | N/A |
| 85 — Amendment to Directive (EU) 2016/798 | Procedural | Out of scope | — | — | — | N/A |
| 86 — Amendment to Regulation (EU) 2018/858 | Procedural | Out of scope | — | — | — | N/A |
| 87 — Amendment to Regulation (EU) 2019/2144 | Procedural | Out of scope | — | — | — | N/A |
| 88 — Amendment to Directive 2006/42/EC | Procedural | Out of scope | — | — | — | N/A |
| 89 — Amendment to Directive 2009/48/EC | Procedural | Out of scope | — | — | — | N/A |
| 90 — Amendment to Directive 2013/53/EU | Procedural | Out of scope | — | — | — | N/A |
| 91 — Amendment to Directive 2014/53/EU | Procedural | Out of scope | — | — | — | N/A |
| 92 — Amendment to Directive 2014/68/EU | Procedural | Out of scope | — | — | — | N/A |
| 93 — Amendment to Regulation (EU) 2018/1139 | Procedural | Out of scope | — | — | — | N/A |
| 94 — Amendment to Regulation (EU) 2019/881 | Procedural | Out of scope | — | — | — | N/A |
| 95 — Voluntary codes of conduct | Governance | Indirect | 7 (Standards) | Voluntary code adherence | epi annex report | Document any voluntary codes adopted |
| 96 — Existing AI systems | Transitional | Out of scope | — | — | — | N/A — transitional |
| 97 — Evaluation and review | Procedural | Out of scope | — | — | — | N/A |
| 98 — Committee for conformity assessment | Procedural | Out of scope | — | — | — | N/A |
| 99 — Penalties for other operators | Procedural | Out of scope | — | — | — | N/A |
| 100 — Monitoring and reporting | Evidence | Indirect | 9 (Post-Market) | Monitoring report records | epi annex report | Document monitoring reports |

## Articles 101-113: Final Provisions

| Art. | Category | EPI | Section | Evidence | Command | Auditor Check |
|------|----------|-----|---------|----------|---------|---------------|
| 101 — Guidelines from Commission | Procedural | Out of scope | — | — | — | N/A |
| 102 — Review of Annex I | Procedural | Out of scope | — | — | — | N/A |
| 103 — Existing systems grace period | Transitional | Out of scope | — | — | — | N/A — transitional |
| 104 — High-risk systems in law enforcement | Transitional | Out of scope | — | — | — | N/A — transitional |
| 105 — Large-scale IT systems | Transitional | Out of scope | — | — | — | N/A — transitional |
| 106 — GPAI models placed before entry | Transitional | Out of scope | — | — | — | N/A — transitional |
| 107 — Commission information duty | Procedural | Out of scope | — | — | — | N/A |
| 108 — EU database transitional | Transitional | Out of scope | — | — | — | N/A — transitional |
| 109 — Annual report | Procedural | Out of scope | — | — | — | N/A |
| 110 — Financial provisions | Procedural | Out of scope | — | — | — | N/A |
| 111 — Territorial application | Transitional | Out of scope | — | — | — | N/A |
| 112 — Entry into force | Transitional | Out of scope | — | — | — | N/A |
| 113 — Addressees | Transitional | Out of scope | — | — | — | N/A |

---

## Summary

| Category | Count |
|----------|-------|
| **Direct evidence (EPI generates)** | 32 articles |
| **Indirect support (EPI supports process)** | 22 articles |
| **Out of scope (institutional/procedural/transitional)** | 59 articles |
| **Total** | 113 |

EPI covers all 32 evidence-generating articles through the 9-section Annex IV framework, Ed25519 signing, SCITT anchoring, multi-signer chains, and the compliance policy engine.

## Quick Reference: Key Evidence Articles

| Priority | Articles | EPI Check |
|----------|----------|-----------|
| **Critical** | 5, 6, 8, 9, 10, 11, 13, 14, 15 | Annex IV all sections |
| **High** | 12, 17, 23, 31, 37, 38, 43, 44, 45, 46, 48, 52, 59, 60, 74 | Annex IV + verify + notify |
| **Medium** | 4, 16, 18, 19, 20, 25, 26, 28, 42, 49, 50, 51, 54, 56, 66, 95, 100 | Annex IV sections as noted |
