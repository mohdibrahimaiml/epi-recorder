# EPI External-User Readiness Report v3.0.1

Date: 2026-04-02

Scope: strict first-time user validation for `epi-recorder`

Question:

Can a Python developer at a small AI startup go from zero to a trustworthy `.epi` workflow in under 15 minutes using only PyPI and public docs?

## Executive Summary

Yes, the published PyPI `3.0.1` package passes the external-user readiness bar.

Important nuance:

- the previously published PyPI `3.0.0` package did **not** pass the first strict external-user run
- the fixed `3.0.1` source candidate passed locally
- the published PyPI `3.0.1` package now also passes the same strict external-user run in a brand-new temp workspace

Release outcome:

- `epi-recorder 3.0.1` is now the correct public launch target
- public launch should use `3.0.1`, not `3.0.0`

## Test Method

Environment rules used for this pass:

- Windows
- fresh temporary workspace outside the repo
- fresh virtual environment
- install from public package artifacts only
- use only public documentation:
  - `README.md`
  - `docs/CLI.md`
  - `docs/FRAMEWORK-INTEGRATIONS-5-MINUTES.md`
  - `docs/POLICY.md`
  - `https://epilabs.org/verify`

Three runs were performed:

1. strict clean install from the previously published PyPI `3.0.0`
2. strict clean install from the rebuilt `3.0.1` candidate wheel produced from the current source tree
3. strict clean install from the newly published PyPI `3.0.1`

Artifacts and machine-readable results:

- failing PyPI run:
  - `C:\epi-temp\epi_external_readiness_20260402_142543\readiness_results.json`
- passing candidate run:
  - `C:\epi-temp\epi_external_readiness_rc2_20260402_161500\readiness_results.json`
- passing published PyPI `3.0.1` run:
  - `C:\epi-temp\epi_external_readiness_pypi301_20260402_1645\readiness_results.json`

## Final Scorecard

### Core acceptance tests

| Test | Result | Notes |
|---|---|---|
| Test 1: First-time setup | Pass | `.epi` created and `epi verify` returned clear HIGH trust |
| Test 2: LangChain integration | Pass | `EPICallbackHandler` captured `llm.request` and `llm.response` cleanly |
| Test 3: Policy evaluation | Pass | built-in insurance policy produced clear failures and Decision Record export |
| Test 4: Trust / tamper detection | Pass | original artifact verified, tampered artifact failed clearly |
| Test 5: Viewer experience | Pass | `epi view` opened and extracted the full case-first viewer |
| Test 6: Realistic insurance workflow | Pass | compliant run passed; non-compliant run failed clearly |

### Launch questions

| Question | Answer |
|---|---|
| Did install work without errors? | Yes |
| Did the API make sense from docs alone? | Yes |
| Did every core test produce a valid `.epi` file? | Yes |
| Did policy evaluation catch what it should? | Yes |
| Did tamper detection work? | Yes |
| Did the viewer look professional enough to show a prospect? | Yes |
| Would a developer finish setup in under 15 minutes? | Yes |
| Would a compliance person understand the output? | Yes |

## Timing

Measured from the passing published PyPI `3.0.1` run:

- fresh PyPI install plus LangChain dependency install completed cleanly in a new temp workspace
- Test 1 time to first success:
  - artifact creation plus verify: `17.54s`
- Test 2 first LangChain artifact:
  - `1.98s`
- Test 5 viewer open:
  - `8.98s`
- full 6-test acceptance runner completed in about `35.9s` after install on a warm network/cache path

Conclusion:

- the core bar is comfortably below the 15-minute requirement

## What Failed In The First Strict PyPI Run

The first clean run against the already-published PyPI `3.0.0` exposed real front-door problems.

### P0: `epi view` broken from the published wheel

Symptom:

- `epi view` failed because the packaged wheel did not contain `web_viewer/index.html`

Impact:

- a brand-new user could create an artifact but could not open the main reviewer UI

Fix:

- added `web_viewer` as a packaged module
- added viewer assets to package data
- added a `viewer_assets` loader with safe package-resource fallback
- updated wheel audit to fail if viewer assets are missing

### P1: LangChain callback emitted runtime errors

Symptom:

- `EPICallbackHandler` could throw:
  - `AttributeError("'NoneType' object has no attribute 'get'")`

Impact:

- the documented LangChain integration looked flaky for a first-time user

Fix:

- hardened the callback handler to tolerate missing `serialized` payloads
- added regression coverage

### P1: Built-in insurance threshold rule did not match public example-shaped data

Symptom:

- built-in insurance policy used `claim_amount`
- public examples and real first-user scripts naturally log `amount`

Impact:

- high-value review threshold could silently fail to fire

Fix:

- changed the insurance profile to use:
  - `threshold_field: "amount"`
  - `watch_for: ["amount", "claim_amount"]`

### P1: Threshold rule fired too early on investigation steps

Symptom:

- after a high-value amount was observed, the analyzer treated any later `tool.call` as “the agent proceeded”
- this incorrectly failed a realistic insurance run that did:
  - claim lookup
  - fraud check
  - coverage check
  - human approval
  - denial decision

Impact:

- compliant insurance workflows could look non-compliant

Fix:

- threshold rules now trigger on consequential actions and final decisions, not intermediate investigation calls
- added regression coverage for this exact insurance-shaped path

### P2: Public docs needed front-door honesty

Symptom:

- `epi share` wording could be read as always live, even when the hosted share service is not deployed

Fix:

- clarified `README.md` and `docs/CLI.md`
- documented `EPI_SHARE_API_URL` / `--api-base-url`

## Fixes Applied In This Pass

Code and packaging:

- `epi_core/viewer_assets.py`
- `epi_core/container.py`
- `epi_cli/view.py`
- `epi_cli/policy.py`
- `epi_recorder/integrations/langchain.py`
- `epi_core/policy.py`
- `epi_core/fault_analyzer.py`
- `pyproject.toml`
- `MANIFEST.in`
- `setup.py`
- `scripts/audit_wheel.py`

Tests:

- `tests/test_langchain_integration.py`
- `tests/test_policy_cli.py`
- `tests/test_audit_wheel.py`
- `tests/test_fault_analyzer.py`

Docs:

- `README.md`
- `docs/CLI.md`
- `docs/POLICY.md`

## Validation Performed

Repo validation:

- targeted regression suite: passed
- full release gate: passed
- result:
  - `820 passed, 9 skipped`
  - wheel and sdist audit passed

External-user validation:

- failing run reproduced from published PyPI `3.0.0`
- passing run confirmed from rebuilt `3.0.1` candidate wheel in a fresh temp workspace
- passing run confirmed again from published PyPI `3.0.1` in a separate fresh temp workspace

## Open Blockers

For the current source and published `3.0.1` package:

- none at `P0`
- none at `P1`

## Remaining Non-Blocking Follow-Up

These are not launch blockers, but they are worth doing soon:

- run one optional live OpenAI-backed pass when an API key is available
- keep hosted sharing documented as deployment-dependent until `api.epilabs.org` is fully live

## Safe Launch Narrative

This is the honest product statement after this readiness pass:

`epi-recorder` is ready for public use as a local-first evidence and verification tool for consequential AI workflows. A new developer can install it, create signed `.epi` artifacts, verify tamper evidence, evaluate policy rules, and open the reviewer UI without internal guidance.

This is what should **not** be claimed until the hosted backend is live and the optional live-model pass is completed:

- that hosted sharing works without a deployed share backend
- that the live OpenAI path has been validated in this exact pass without credentials

## Recommendation

Do this next, in order:

1. launch publicly against PyPI `3.0.1`
2. keep the hosted-sharing caveat explicit until `api.epilabs.org` is fully live
3. run one optional live OpenAI-backed pass and add it to this report when credentials are available

Bottom line:

- published PyPI `3.0.1`: launch-ready
- older PyPI `3.0.0`: superseded by the fixed patch release
