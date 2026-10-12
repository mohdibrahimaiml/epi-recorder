# Release 4.6.0 — owner runbook (copy-paste)

PR with the prep: `chore/release-4.6.0` → `main`. Merge that PR first.
Do NOT run anything below until the PR is merged and `main` is green.

## 0. Sanity (on latest `main` after merge)

```powershell
git fetch origin
git checkout main
git pull --ff-only
python -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])"
# expect: 4.6.0
python -m pytest tests/test_version_consistency_runtime.py tests/test_truth_consistency.py -q
```

## 1. Build

```powershell
python -m build
python -m pytest tests/test_tsa_validation.py -q -k built_wheel_contains_tsa_roots
```

Wheel must contain (verified in prep):
`epi_core/assets/tsa_roots/ROOTS.json`, `freetsa_root.pem`,
`digicert_g4_root.pem`, `digicert_assured_id_root.pem`, `freetsa_signer.pem`.

## 2. Check

```powershell
python -m twine check dist/epi_recorder-4.6.0*
```

Expect `PASSED` for both wheel and sdist (verified in prep).

## 3. Fresh-venv demo (verified in prep — PASS)

```powershell
python -m venv C:\epi-temp\opencode\rel460-venv
C:\epi-temp\opencode\rel460-venv\Scripts\python -m pip install dist/epi_recorder-4.6.0-py3-none-any.whl
C:\epi-temp\opencode\rel460-venv\Scripts\epi demo --no-browser
```

With network the timestamp line reads `Timestamp: VERIFIED`;
without network it reads `Timestamp: none` and still PASSes.

## 4. Upload to PyPI (owner only)

```powershell
python -m twine upload dist/epi_recorder-4.6.0*
```

## 5. Tag + push tag (owner only)

```powershell
git tag -a v4.6.0 -m "EPI 4.6.0: offline timestamps, customer witness, chained gateway exports, did:web, checkpoints off the hot path"
git push origin v4.6.0
```

## 6. GitHub release notes (paste into the v4.6.0 release)

```markdown
## Highlights
- Offline RFC 3161 timestamp validation for seal and checkpoints.
- Customer witness on every seal (hash-only, outbox-first).
- Hash-chained gateway exports with capture-time checkpoints.
- did:web identity onboarding and key pinning.
- Checkpoints moved off the agent's hot path (background submit).

## Fixes (from review follow-ups)
- `--tsa-root` now applies to checkpoint timestamps too.
- Checkpoint `UNVERIFIED` prints as `[WARN]`, not `[FAIL]`.
- Seal timestamp scope stated plainly (contents-only when `imprinted_public_key` is null).
- Customer docs recommend `epi verify run.epi --require-timestamp --witness-log received.jsonl`.

Verify: `pip install epi-recorder==4.6.0 && epi demo --no-browser`
Full changelog: CHANGELOG.md `[4.6.0] - 2026-10-12`.
```
