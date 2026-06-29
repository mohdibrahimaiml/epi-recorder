# EPI File Format Specification

**Status:** Open Standard | **Version:** 4.2.0 | **Date:** 2026-06

This directory contains the open, language-agnostic specification for the EPI
container format. Anyone may implement `.epi` file producers and consumers
conforming to this specification without depending on the Python reference
implementation.

## Contents

| File | Purpose |
|------|---------|
| `EPI-SPEC.md` | Complete wire format specification |
| `schemas/manifest.schema.json` | JSON Schema for `manifest.json` |
| `schemas/step.schema.json` | JSON Schema for `steps.jsonl` entries |
| `schemas/environment.schema.json` | JSON Schema for `environment.json` |
| `schemas/analysis.schema.json` | JSON Schema for `analysis.json` |
| `schemas/policy.schema.json` | JSON Schema for `policy.json` |
| `test-vectors/` | Sample inputs and expected outputs for conformance testing |

## Reference Implementation

The Python package `epi-recorder` (MIT license) is the canonical
reference implementation. It is not required for conformance — any
implementation passing the test vectors produces valid `.epi` files.

- **PyPI:** https://pypi.org/project/epi-recorder/
- **GitHub:** https://github.com/mohdibrahimaiml/epi-recorder
- **Website:** https://epilabs.org/

## License

This specification is an open standard, licensed under the MIT License. Implementations may
carry their own licensing terms. The `.epi` format itself carries no
intellectual property restrictions — it is a documented file format.

## Contributions

Specification changes are managed via GitHub Pull Requests to
`docs/spec/`. Proposed changes must include updated schemas and test
vectors.
