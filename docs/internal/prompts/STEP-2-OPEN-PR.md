# Prompt for the coding agent: open the PR for step 2 (key-vault signing)

> Paste everything below the line into the coding agent.

---

In the `epi-recorder` repository, branch `claude/optimistic-turing-lusdoj` contains step 2 of `docs/internal/BANK-READINESS-EXECUTION-PLAN.md`: signing with an Ed25519 key held in an HSM or cloud KMS (`epi keys link`, `epi_core/signers.py`, `docs/KEY-CUSTODY.md`, `tests/test_external_signers.py`, `.github/workflows/key-custody.yml`).

1. Merge the latest `main` into that branch (a merge commit, no rebase or force-push), and resolve conflicts if any.
2. Run, and paste the results into the PR:
   - `python -m pytest tests/test_external_signers.py -q -o addopts=""` (install `softhsm2` and `pip install -e ".[test,pkcs11]"` first so the real-HSM tests run, and set `EPI_TEST_REQUIRE_SOFTHSM=1` so they can't silently skip);
   - `python -m pytest tests -m "not browser and not experimental" -q -o addopts=""`. Known pre-existing failure: `tests/test_v271_features.py::TestReliabilityFixes::test_flag_unwritable_doesnt_crash` when run as root; confirm it also fails on `main`.
3. Open a PR into `main` titled `feat(keys): sign with an Ed25519 key held in an HSM or cloud KMS`. In the description:
   - what it does: `epi keys link`; PKCS#11, AWS KMS and GCP KMS backends; `EPI_REQUIRE_EXTERNAL_KEY=1`; the swap guard; the per-signature self-check; no raw key bytes for the witness header;
   - that the `.epi` format and every verifier are unchanged (pure Ed25519);
   - the Google Cloud KMS enum bug that hands-on testing found and fixed;
   - what was tested on a real SoftHSM and what was only checked against the AWS/GCP API models, not real cloud accounts;
   - that Azure Key Vault is unsupported (no Ed25519).
4. Watch CI, including the new `Key custody (real HSM)` job. Fix real failures in the PR, re-run once only for an infrastructure failure, and never skip or disable tests.
