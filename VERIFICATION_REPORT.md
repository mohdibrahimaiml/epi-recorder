# Verification report — adversarial review round 1 (priorities 1–7)

Wheel under test: `epi-recorder==4.4.8` (PyPI), fresh venv
`C:\epi-temp\epi-verify-448`, `PYTHONPATH=""`, workdir outside repo
(`C:\epi-temp`) so the wheel — not repo code — is imported.
Spot check in every log: `epi_recorder.__file__` must point at
`...\epi-verify-448\Lib\site-packages\...`. Prefer `python -I` for
evidence commands (isolated mode ignores cwd/`PYTHONPATH`).

Uncommitted baseline at review start: `9143354`.
System editable install (`4.4.6`) could not be uninstalled without admin
rights; contained by the workdir/`PYTHONPATH` discipline above.

| # | Claim | Attack tried | Command | Output (excerpt) | Mutation check | Status | Commit | Next action |
|---|-------|--------------|---------|------------------|----------------|--------|--------|-------------|
| 1 | Wheel test setup: published wheel in fresh venv | `import epi_recorder` from repo cwd resolves local code | `python -I -c "import epi_recorder; print(epi_recorder.__file__)"` (workdir `C:\epi-temp`) | `...\epi-verify-448\Lib\site-packages\epi_recorder\__init__.py`, version `4.4.8`, `epi verify sample-hello.epi --json` exit 0, integrity+signature true | N/A (setup) | VERIFIED | — | Use `python -I` + print `__file__` in all future logs; uninstall editable from admin terminal |
| 2 | `epi_signature_valid` means cryptographically valid | Feed manifest with garbage signature `"00"*64` | `C:\epi-temp\repro_f1b.py` on wheel | `crypto valid=False reason=Invalid signature format exporter would report=True` | Mutated fix to `True`: new test FAILs; restored: PASSes | FIXED (pending release) | `1ec1eaa` | Re-verify against 4.5.0 wheel after publish |
| 3 | Client cannot downgrade fail-closed via header | Wheel `_resolve_failure_mode` honors `x-epi-failure-mode` | Inspect wheel source + gateway test with `headers={"x-epi-failure-mode": "fail-open"}` | Wheel returns override; after fix manifest `gateway_enforcement=fail_closed`, `fail_open_events=[]`, `enforcement_downgraded False` | Restored header override: downgrade test FAILs; re-fixed: PASSes | FIXED (pending release) | `52192b7` | Re-verify against 4.5.0 wheel |
| 4 | Secure gateway defaults everywhere; site matches code | `serve` ran `redacted_hashes`/`fail-open`, CORS `*`, `/metrics` open | `tests/test_gateway_secure_defaults.py` (5 tests incl. new non-loopback refusal) | `52192b7` pre-guard: 4 pass; after guard: 5 pass | CLI default back to `fail-open`: defaults test FAILs; restored: PASSes | FIXED (pending release) | `52192b7` | Re-verify against 4.5.0 wheel; do not deploy site until release live |
| 5 | TSA token claims are presence-only | Grep for `timestamped` overclaims | `tests/test_tsa_presence_honesty.py` | Viewer/checkpoint/marketing wording fixed; mirrors synced via `scripts/sync_website.py` | N/A (wording; no logic branch) | FIXED (pending release) | `35d3643` | None; validation itself still planned |
| 6 | Contract lists all verdicts; browser ≤ CLI | Browser `MEDIUM` for unsigned outranked CLI `LOW` | `tests/test_verifier_parity.py` (contract grep, JS static cap, 12 demo files) | All 3 pass; demo parity holds | JS back to `MEDIUM`: static test FAILs; restored: PASSes | FIXED (pending release) | `8e2d292` | Re-verify against 4.5.0 wheel |
| 7 | Limitations current; strict easy to find | `KNOWN_LIMITATIONS` said PyPI `4.4.5`; strict buried | `tests/test_known_limitations_current.py` | PyPI `4.4.8`, sprint-strict section, `--policy` help names strict | N/A (docs + help text; asserted by grep) | FIXED (pending release) | pending (this report) | Bump PyPI line again at 4.5.0 release |

Sealed-artifact safety: 65 tracked `.epi` files hash-identical before/after
(`git show HEAD:path` SHA-256 comparison). The "315 copies" are
`scripts/sync_website.py` mirrors: 105 `website/` source files × 3 targets
(`site/`, `verify_portal/static/`, `epi-official/`); changed types in this
round were `.html`/`.js`/`.py`/`.md` only, no `.epi`.

Full suite: running separately (large); targeted suites (20 tests) green at
each commit. Re-run items 1–7 against the 4.5.0 wheel in a fresh venv after
publish, then mark each row VERIFIED.
