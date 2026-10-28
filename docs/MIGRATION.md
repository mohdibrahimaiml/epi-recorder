# Migration guide (old `.epi` files and old recorders)

**Product version:** 4.7.0. Old files still verify — this page says what
verdicts to expect and what changed, so a legacy artifact never surprises
you. Background: [KNOWN_LIMITATIONS](./KNOWN_LIMITATIONS.md),
[spec/EPI-SPEC](./spec/EPI-SPEC.md).

## Upgrading to 4.7

**Old `.epi` files verify exactly as before** — same verdicts, same policy, no
re-seal and no migration. What changed is around approvals.

- **Approvals are `review_version` 1.2.0.** The record shape is unchanged: an
  approval rides inside the existing `reviews` list, so an older (4.6.x) verifier
  computes the same content hash and raises no tamper alarm. It just shows a
  signed review and never "human approved". Nothing you already hold is affected.
- **A "signed review" is no longer a human approval.** `epi review` and
  `epi review bind` keep working, but their signatures classify as
  `signed_by_sealing_key` or `signed_unknown_key`, **never** `human_signed`. To
  assert that a person approved, pin their key (`epi approvers add`) and have
  them sign with `epi review <file.epi> approve`. `epi verify` gains a
  `human_approval` field and `--require-human-approval`; `--policy strict` does
  **not** imply it.
- **Analysis wording changed.** An `agent.approval.response` step (or
  `approved_by`) is labelled "reported by the agent (not signed by a person)"
  wherever the CLI and the browser print it, and an anonymous gateway link click
  no longer satisfies a policy's "approval required" rule in `epi analyze`. Cases
  already recorded by an older gateway keep their stored label and their existing
  result.
- **Gateway approval links now need a token, and old links stop working.** Every
  link issued before this change returns 403 (no fallback) — deliberately: the
  old link was an unauthenticated GET that a mail scanner could trigger on its
  own. Re-issue approvals after upgrading; new links expire after
  `EPI_APPROVAL_LINK_TTL_HOURS` (default 72).
- **New seals are stamped 4.7.0**, so `spec_version` on files you seal from now
  on moves 4.6.3 → 4.7.0. Verification dispatches on the value **in the file**,
  so this changes nothing about artifacts you already have.

## Rule 0: never "fix" an old file by re-sealing it

A wrong number in an old artifact (e.g. the 4.4.1–4.4.6 `controls_failed`
undercount) **cannot** be corrected: changing sealed bytes breaks the file's
own signature. Recount from `results`, never from the header. A format where
old artifacts could be quietly rewritten would be a worse format.

## What to expect by seal version

| Sealed with | `epi verify` today | Notes |
|---|---|---|
| Pre-4.4.1 | WARN (legacy canonicalization) | `json.dumps(sort_keys=True)` era; verifier dispatches by `spec_version`, no re-hash. Chain check passes vacuously on pre-chain files. |
| 4.4.1–4.4.6 | Verify OK, but recount `controls_failed` from `results` | Auto-extract merge reset the baseline count. Fixed forward in 4.4.7. |
| 4.4.2 | Unusual | Withdrawn before PyPI (new field's JSON `null` broke Ed25519 for older seals). If you hold one, treat it as suspect and re-record. |
| 4.4.3+ | Current semantics | `content_truncated=false` on new seals; verify **FAILs** when `true`, **WARNs** when absent (everything through 4.4.1). |
| Pre-4.6 timestamps | Presence-only | Seal-time/checkpoint tokens attest nothing checkable. Since 4.6.0, new-scheme tokens are validated offline (imprint, CMS signature, EKU, chain). |
| All-zero viewer hash (legacy polyglot) | PASS possible, display forgeable | Outer viewer HTML is not integrity-covered. Trust `epi verify`, not the double-click colours. New seals (4.4.1+) hash the viewer; 4.6.3+ also binds it in the signed `file_manifest`. |

## Moving to envelope-v2

New seals default to `envelope-v2` (HTML shell + ZIP). A pure-ZIP handover
is one command and verifies identically:

```bash
epi migrate case.epi --out case-data.epi --legacy-zip
```

## Moving to current capture

- Through 4.4.1, long strings truncated at 2000 chars in sealed
  `steps.jsonl`. 4.4.3+ seals full payloads. Old files are incomplete
  transcripts — re-record if you need the tail.
- `epi_signature_valid` in the old AGT helper was presence-only; current
  code runs a real check. Re-verify, don't trust old helper output.
- Gateway streaming is rejected (501): streaming apps must use the SDK path
  or bypass explicitly — either way the gap is declared, not silent.
