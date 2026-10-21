# GitHub Actions shipped in this repo

**Product version:** 4.6.2.

These are the composite actions under `.github/actions/`. They check or pack **files**. They do not certify EU AI Act conformity, SOC 2, or any other regime.

There is **no** `epi-evidence` composite action in this repository. To record tests in CI, install `epi-recorder` and run `pytest --epi` ([PYTEST-AGENT-REGRESSIONS.md](./PYTEST-AGENT-REGRESSIONS.md)).

## `verify-epi`

Verifies `.epi` files in a workflow: integrity and signatures. Source: `.github/actions/verify-epi/`.

```yaml
name: Verify sealed runs
on: [push]
jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: mohdibrahimaiml/epi-recorder/.github/actions/verify-epi@main
        with:
          path: './epi-recordings'
          fail-on-tampered: true
          generate-summary: true
```

Inputs that exist today: `path`, `fail-on-tampered`, `fail-on-unsigned`, `python-version`, `generate-summary`.

A green job means those files still match their sealed hashes and (when signed) their signatures. It does not mean the agent captured every call, or that a reviewer has pinned the sealer key.

## `annex-iv-compliance`

Runs `epi annex` in CI and packs the JSON you (or the templates) produced into a `.epi`. Source: `.github/actions/annex-iv-compliance/`.

The action name says “compliance.” That is historical. The job **generates and signs Annex IV *templates*** you still have to fill with true system facts. A passing workflow is not an EU declaration of conformity.

```yaml
name: Pack Annex IV templates
on:
  pull_request:
    branches: [main]
jobs:
  annex:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: mohdibrahimaiml/epi-recorder/.github/actions/annex-iv-compliance@main
        with:
          signing-key: ${{ secrets.EPI_SIGNING_KEY }}
          fail-on-block: true
          report-format: html
```

`EPI_SIGNING_KEY` is an Ed25519 private key your org generates (`epi keys generate`) and stores as a GitHub Actions secret. EPI Labs does not hold it.

Details of the nine sections: [ANNEX-IV.md](./ANNEX-IV.md). Boundary: [EU-AI-ACT-EVIDENCE-PREP.md](./EU-AI-ACT-EVIDENCE-PREP.md).

## After CI: independent check

Anyone with the file can re-check it without GitHub or your secrets:

```bash
pip install epi-recorder
epi verify path/to/file.epi
```

`--policy strict` fails on WARN (unpinned sealer). Default `epi verify` treats WARN as exit 0. See [CLI.md](./CLI.md) and [VERIFICATION_CONTRACT.md](./VERIFICATION_CONTRACT.md).
