# Use `pytest --epi` for Agent Regressions

`pytest --epi` is the fastest way to turn a failing AI test into a portable repro artifact.

By default, EPI keeps artifacts for failing tests. Add `--epi-on-pass` when you also want `.epi` files for successful tests.

## Install and first run

```bash
pip install epi-recorder
pytest --epi
```

Common variants:

```bash
pytest --epi --epi-dir=evidence
pytest --epi --epi-on-pass
pytest --epi --epi-dir=evidence --epi-no-sign
```

## What each failing test artifact contains

Each kept `.epi` file is scoped to one test case, not the entire test session. A failing test artifact can include:

- test metadata such as node id, markers, and test file
- the LLM/tool sequence emitted during that test
- the final `test.result` step with pass/fail outcome
- truncated failure text when pytest exposes it
- trust metadata and signature state for the artifact itself

That is what makes it useful in PRs and CI: one artifact maps to one failing test.

## How the plugin hooks in

`epi-recorder` registers the pytest plugin automatically through the `pytest11` entry point. You usually do not need to import it yourself.

If you want to pin the plugin explicitly in a repo, this `conftest.py` is a clear pattern:

```python
# conftest.py
pytest_plugins = ("pytest_epi.plugin",)

import pytest
from openai import OpenAI
from epi_recorder import wrap_openai


@pytest.fixture(scope="session")
def llm_client():
    # The plugin starts an EPI recording around each test when --epi is set.
    # Wrapping the client here means calls made inside tests are captured
    # automatically inside the per-test .epi artifact.
    return wrap_openai(OpenAI())
```

What happens around that fixture:

1. `pytest_runtest_setup` starts an EPI session before the test body runs.
2. Your fixtures and test code execute inside that active session.
3. `pytest_runtest_makereport` captures the test outcome.
4. `pytest_runtest_teardown` logs `test.result`, finalizes the `.epi`, and keeps it if the test failed.
5. `--epi-on-pass` changes step 4 so passing tests are kept too.

## Output directory and retention behavior

Use `--epi-dir` to control where artifacts land:

```bash
pytest --epi --epi-dir=evidence
pytest --epi --epi-dir=artifacts/epi
```

Use `--epi-on-pass` when you want artifacts for green runs too:

```bash
pytest --epi --epi-on-pass
pytest --epi --epi-dir=evidence --epi-on-pass
```

Useful defaults:

- local debugging: `pytest --epi`
- CI failures only: `pytest --epi --epi-dir=evidence`
- baseline capture for comparisons: `pytest --epi --epi-on-pass`

## GitHub Actions example

```yaml
name: tests

on:
  pull_request:
  push:

jobs:
  pytest:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install dependencies
        run: |
          pip install -U pip
          pip install -e .[dev]

      - name: Run tests with EPI artifacts
        run: pytest --epi --epi-dir=evidence

      - name: Upload EPI artifacts
        if: failure()
        uses: actions/upload-artifact@v4
        with:
          name: epi-evidence
          path: evidence/
```

That pattern keeps the CI story simple:

```text
test fails -> CI uploads evidence/ -> engineer downloads .epi -> epi view -> faster repro
```

## What to attach to a PR or issue

When a test fails, the engineer workflow should be:

1. download the failing `.epi` from CI or reproduce locally
2. run `epi view evidence/<name>.epi`
3. run `epi verify evidence/<name>.epi`
4. attach the `.epi` to the PR or issue with a one-paragraph summary

Use the browser verifier when someone only needs a trust check:

- [epilabs.org/verify](https://epilabs.org/verify)

Use `epi view` when they need the full local browser review flow.

## Why this works well for agent regressions

Plain logs usually tell you that a test failed.
`.epi` tells you how the run reached that failure:

- the user input
- the model/tool path
- the approval or decision step
- the failure record from pytest
- the trust state of the artifact you attached

That makes `pytest --epi` a good default for multi-step agent debugging, tool-permission mistakes, approval-flow regressions, and framework upgrades that subtly change behavior.

## Related guides

- [Share one failure with `.epi`](SHARE-A-FAILURE.md)
- [Framework integrations in 5 minutes](FRAMEWORK-INTEGRATIONS-5-MINUTES.md)
- [Share with your team locally](CONNECT.md)
