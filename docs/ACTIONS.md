# EPI GitHub Actions for CI/CD

Copy-pasteable workflow snippets for adding EPI evidence and compliance to your CI/CD pipelines.

---

## Quick Start: Add Evidence to Your AI Pipeline

```yaml
name: AI Pipeline with Evidence
on: [push]
jobs:
  run-and-record:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Run AI agent and record evidence
        uses: mohdibrahimaiml/epi-recorder/.github/actions/epi-evidence@main
        with:
          epi-dir: './evidence'
          epi-on-pass: 'true'

      - name: Verify evidence
        uses: mohdibrahimaiml/epi-recorder/.github/actions/verify-epi@main
        with:
          path: './evidence'
          fail-on-tampered: true
          generate-summary: true
```

## EU AI Act Annex IV Compliance Gate

Add this to your PR checks to ensure compliance evidence is generated and verified before merge:

```yaml
name: EU AI Act Compliance
on:
  pull_request:
    branches: [main]
jobs:
  compliance:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: mohdibrahimaiml/epi-recorder/.github/actions/annex-iv-compliance@main
        with:
          signing-key: ${{ secrets.EPI_SIGNING_KEY }}
          fail-on-block: true
          report-format: pdf
```

**Secrets required:**
- `EPI_SIGNING_KEY`: Generate with `epi keys generate --name ci-compliance` and copy the hex-encoded private key. Add to GitHub repo Settings → Secrets → Actions.

## Share Verified Evidence with Auditors

Auditors can independently verify the artifact without any shared secrets:

```bash
# Auditor downloads the artifact from GitHub Actions
# No shared secrets needed - the .epi proves itself
pip install epi-recorder
epi verify annex-iv-compliance.epi --verbose
```

## Available Actions

| Action | Purpose | Key Input |
|--------|---------|-----------|
| `epi-evidence` | Generate .epi files from AI tests | `epi-dir` |
| `verify-epi` | Verify integrity and signatures | `path`, `fail-on-tampered` |
| `annex-iv-compliance` | Full EU AI Act Annex IV pipeline | `signing-key`, `fail-on-block` |
