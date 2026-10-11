# WP-R0 — Small follow-ups from the review

Branch: `fix/review-followups` from the latest `origin/main`. Size: half a day. One PR.


Four small fixes found while reviewing the merged work. Do them in one PR.

### R0.1 `--tsa-root` is ignored for checkpoint timestamps

**Problem.** `epi verify --tsa-root PATH` adds trusted TSA roots for the **seal** timestamp only. These two
call sites still use only the pinned roots plus the `EPI_TSA_TRUST_ROOTS` env var:
- SDK checkpoints: `epi_core/checkpoints.py`, `verify_checkpoints()` (around line 318), which calls
  `validate_tsr(_token, _expected)` around line 387.
- Gateway capture checkpoints: `epi_core/case_store.py`, `verify_capture_checkpoints()` (around line 2543), which calls
  `validate_tsr(token, expected)` around line 2651.

So anyone using their own TSA sees checkpoints as "untrusted" even after passing `--tsa-root`.

**Fix.**
1. Add an optional keyword `trust_roots=None` to both `verify_checkpoints()` and `verify_capture_checkpoints()`,
   and pass it through to `validate_tsr(..., trust_roots=trust_roots)`.
   Keep the default `None` so existing callers behave the same.
2. In `epi_cli/verify.py`, the seal path already builds a list called `trust_roots` (around lines 85–88: pinned
   roots plus `--tsa-root` certificates). Move that construction into a small helper,
   `_tsa_trust_roots(tsa_root_paths)`, call it once in `verify_command`, and pass the same list to both checkpoint
   verifiers (call sites around line 1364 and in the capture-checkpoint step).
3. **Test** in `tests/test_tsa_validation.py`: a checkpoint token signed by the test-only TSA (the `MiniPKI`
   helper already in that file) is `untrusted` without `--tsa-root` and `valid` with it.
   Add the same test for a gateway export in `tests/test_gateway_export_chain.py`.

### R0.2 Checkpoint "UNVERIFIED" messages print as [FAIL]

In `epi_cli/verify.py`, the SDK checkpoint block prints every message in `_cp_messages` with a red `[FAIL]`
label, even when `ok` is true and the message is the warning `CHECKPOINT TIMESTAMP UNVERIFIED ...`.
The gateway block already handles this correctly: it prints `[WARN]` for messages starting with
`CAPTURE TIMESTAMP UNVERIFIED`. Apply the same rule to the SDK block.

Add a test asserting the human output shows `[WARN]`, not `[FAIL]`, for an untrusted-root checkpoint.

### R0.3 Say plainly what the seal timestamp proves

In the normal `record()` flow, the file is first packed unsigned and signed on the second pack. So at stamping time
`imprinted_public_key` is `None`. The seal timestamp therefore proves **"these contents existed no later than
time T"**, not **"this signing key sealed them by time T"**.

Document this, without changing code:
- `docs/VERIFICATION_CONTRACT.md`, in the timestamps section: one paragraph explaining what the imprint covers and
  that the signing key is covered only when `imprinted_public_key` is non-null.
- `docs/KNOWN_LIMITATIONS.md`: a new entry, "Seal timestamp does not bind the signing key in the default
  `record()` flow".
- `epi_cli/verify.py`: when a seal timestamp is `valid` and `imprinted_public_key` is null, the statement line
  must read "contents existed no later than T" (check the current wording and correct it if it implies more).

### R0.4 Tell customers to require a timestamp

`docs/WITNESS.md` already says to verify with `--require-timestamp`. `docs/IDENTITY-ONBOARDING.md` does not.
Add one short "Recommended verify command for customers" section to `IDENTITY-ONBOARDING.md`:

```bash
epi verify run.epi --require-timestamp --witness-log received.jsonl
```

Explain in two sentences: without `--require-timestamp`, a file with no timestamp still passes, so a vendor
could remove the timestamp; with it, such a file FAILs.

**Acceptance for WP-R0:** all new tests pass; the full core suite passes; `CHANGELOG.md` has a "Fixed" entry.

---

## Start

```bash
git fetch origin
git checkout -b fix/review-followups origin/main
```

## Checks before pushing

```bash
python -m pytest tests/test_version_consistency_runtime.py tests/test_truth_consistency.py -q
python -m pytest tests -m "not browser and not experimental" -q --maxfail=20
```

If tests run as root, `test_flag_unwritable_doesnt_crash` fails locally because of root, not because of this change; it passes in CI. Do not skip it.

## After merge

Next: WP-REL, then WP-DEMO (in `plans/REMAINING-WORK-PLAN.md`). Then stop and wait for the owner.
