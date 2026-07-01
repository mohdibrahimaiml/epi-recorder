# CEN-CENELEC Standards Mapping for EU AI Act Annex IV

Maps EPI-recorder Annex IV compliance artifacts to CEN-CENELEC standards.

## Applicable Standards

### prEN 18286: AI Risk Management

| Clause | Description | Annex IV Mapping |
|--------|-------------|------------------|
| 5 | Risk identification | Section 5 Risk Management |
| 6 | Risk evaluation | Section 5 Risk Register |
| 7 | Risk treatment | Section 5 Mitigation |
| 8 | Risk monitoring | Section 9 Post-Market |
| 9 | Documentation | Sections 1, 8 |
| 10 | Communication | Section 2 Development |

### prEN 18228: AI Transparency and Logging

| Clause | Description | Annex IV Mapping |
|--------|-------------|------------------|
| 4 | Transparency | Section 1 System Description |
| 5 | Logging | Section 3 Monitoring |
| 6 | Retention | Section 3 |
| 7 | Notification | Section 1 |
| 8 | Audit trail | Section 6 Lifecycle |
| 9 | Explainability | Section 4 Metrics |

## Section-to-Standard Mapping

| Sec | Title | Primary Standard | Supporting |
|-----|-------|-----------------|------------|
| 1 | System Description | prEN 18228, 18286 | ISO/IEC 5338, 22989 |
| 2 | Development Process | prEN 18286 | ISO/IEC 42001, 9001 |
| 3 | Monitoring and Control | prEN 18228 | ISO/IEC 27001 |
| 4 | Performance Metrics | prEN 18228 | ISO/IEC 25010, 25023 |
| 5 | Risk Management | prEN 18286 | ISO 31000, 23894 |
| 6 | Lifecycle Changes | prEN 18228 | ISO/IEC 5338 |
| 7 | Applied Standards | Cross-reference | ISO/IEC 42001, IEC 61508 |
| 8 | Declaration of Conformity | prEN 18286 | EU AI Act Art. 16, 47 |
| 9 | Post-Market Monitoring | prEN 18286 | ISO 9001, 42001 |

## EPI Implementation Status

- Risk register with auto-RPN: Section 5
- Ed25519 signatures: All 9 sections
- Multi-signer chain: compliance-summary
- SCITT anchoring: Local and remote
- Compliance report: HTML
- Trust registry: Auto-registered

## Verification Procedure

1. epi annex init
2. Populate sections
3. epi annex sign all --key name
4. epi annex pack
5. epi verify --verbose
6. epi annex multi-sign role
7. epi annex pack

## References
- EU AI Act Reg 2024/1689 Annex IV
- CEN/CLC JTC 21 Standards Roadmap
- ISO/IEC 42001, 5338, 22989
- ISO 31000
