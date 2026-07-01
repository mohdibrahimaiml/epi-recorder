# EU AI Act Annex IV Technical Documentation

EPI provides a complete subsystem for generating, signing, and verifying
EU AI Act Annex IV technical documentation. All 9 sections are covered
with structured Pydantic schemas, Ed25519 cryptographic signing, and a
browser-viewable compliance report.

## Quick Start

```
epi annex init              # Create all 9 section templates
epi annex validate          # Validate against schemas
epi annex sign 1            # Sign section 1 with Ed25519
epi annex sign all          # Sign all 9 sections
epi annex verify all         # Verify all signatures
epi annex status            # Show per-section completion
epi annex compile           # Generate compliance-summary.json
epi annex report            # Generate HTML compliance report
```

## The 9 Sections

| Sec | Section | Description |
|-----|---------|-------------|
| 1 | System Description | 1(a) intended purpose, version, provider |
| 2 | Development Process | 2(a-h) architecture, data, testing, cybersecurity |
| 3 | Monitoring and Control | capabilities, limitations, subgroup accuracy |
| 4 | Performance Metrics | justification of chosen metrics |
| 5 | Risk Management | full FMEA-ML risk register with RPN scores |
| 6 | Lifecycle Changes | change log, modification classification |
| 7 | Applied Standards | harmonised standards register, gap analysis |
| 8 | EU Declaration of Conformity | formal legal statement with Ed25519 |
| 9 | Post-Market Monitoring | drift detection, incident escalation |

## Signing and Verification

Each section is signed independently using Ed25519. The canonical JSON is
computed deterministically (sort_keys, no whitespace) so verification
is portable across systems. Keys are stored in ~/.epi/keys/ and
auto-generated on first use.

```
epi annex sign 1 --key compliance-officer --officer did:web:example.com
epi annex verify 1
```

## Artifact Structure

All files live under artifacts/annex_iv/ and can be packed into a .epi
container using EPIContainer.pack() for signed, portable compliance artifacts.

```
artifacts/annex_iv/
  section-01.json
  section-02.json
  ...
  section-09.json
  compliance-summary.json
  datasheets/
    training-datasheet.json
    validation-datasheet.json
    test-datasheet.json
```

## CLI Reference

| Command | Description |
|---------|-------------|
| init | Generate template JSON files for all 9 sections |
| validate | Validate JSON against Pydantic schemas |
| status | Show per-section completion and approval |
| compile | Generate compliance-summary.json |
| sign | Ed25519 sign a section (or "all") |
| verify | Verify Ed25519 signatures |
| report | Generate browser-viewable HTML report |

## Data Models

The schemas are defined in epi_core.annex_schemas and include:
- RiskEntry with auto-computed RPN scoring (probability x severity)
- DatasetDatasheet with bias analysis and provenance tracking
- Full FMEA-ML risk register
- EU Declaration of Conformity with machine-readable structure
- Post-market monitoring plan with Art. 73 reporting deadlines

## Integration with .epi Container

Annex IV artifacts follow the same pattern as SCITT artifacts:
place them under artifacts/annex_iv/ and call EPIContainer.pack().
They will be included in the ZIP payload and cryptographically hashed
in the file_manifest, ensuring tamper-evident compliance documentation.