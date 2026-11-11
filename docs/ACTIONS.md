# GitHub Actions shipped in this repo

**Product version:** 4.10.0.

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

## `annex-iv-compliance` (EPI Enterprise)

The Annex IV compliance action is part of **EPI Enterprise** and is not in this
repository. `epi annex` is a paid command; the free CLI records, verifies and
views evidence without it. Licensed customers get the action from their private
distribution.

## After CI: independent check

Anyone with the file can re-check it without GitHub or your secrets:

```bash
pip install epi-recorder
epi verify path/to/file.epi
```

`--policy strict` fails on WARN (unpinned sealer). Default `epi verify` treats WARN as exit 0. See [CLI.md](./CLI.md) and [VERIFICATION_CONTRACT.md](./VERIFICATION_CONTRACT.md).
