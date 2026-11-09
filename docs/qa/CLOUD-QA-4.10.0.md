# Cloud QA addendum — 4.10.0 candidate (2026-11-09)

Run from a separate cloud session against production `cloud.epilabs.org`,
using a 4.10.0 wheel built from `release/4.10.0-site` (`c03912a0`) in a clean
venv. Test workspace "EPI Live Test", customer "QA Test Customer", connected
by device login (push-only key). Nothing published or merged.

## Verdict: NO-GO for Cloud users until C7 is fixed

| ID | Check | Result |
|---|---|---|
| C-pre | `/v1/version` | PASS — `min_cli_version 4.6.1`, 4.10.0 allowed |
| C-anon | Signed-out API | PASS — clean JSON errors ("Sign in first.", "Member, read key, or share token required.") |
| C6a | `epi cloud login` (device flow) | PASS — code shown, approved in browser, `[OK] Recording for QA Test Customer` |
| C6b | `epi cloud status` | PASS — workspace, customer, witness "set up", 0 waiting |
| C6c | 3 normal seals → Cloud witness | PASS — all 3 `epi.sealed` reports delivered |
| C6d | `epi cloud push` | PASS — `Seal: valid · Witness: witnessed` |
| C8 | Anonymous `epi share` → open link signed out → download → verify | PASS — same SHA-256; verifies with 4.10.0 and 4.9.0 |
| **C7a** | `epi witness heartbeat` → Cloud | **FAIL** — HTTP 400. CLI message is clear, not retried. |
| **C7b** | `epi release create` → `epi.release` report → Cloud | **FAIL** — HTTP 400. |
| **C7c** | Customer audit of what Cloud accepted (seals #1,#2,#3,#5; release was #4) | **P0** — `MISSING #4`, exit 1. A false accusation that the vendor hid a record. |
| C7d | `epi cloud push` of the release file | Shows `Witness: not_in_witness` (same cause) |
| C7e | Pre-action approval reports (`epi.approval_*`) | Not run; same mechanism (Cloud accepts only `epi.sealed`), so expected to fail and leave order evidence vendor-only. Must be tested after the fix. |
| C9 | Free-plan limits | Not run (would consume the test workspace's quota) |
| C5/C10/C11/C12 | Browser sign-in, dashboard, sign-out, sign-in again | Needs a human browser session — see checklist below |

## New findings

- **P0 — Cloud witness accepts only `epi.sealed`.** Heartbeats, releases and
  approval reports are rejected (HTTP 400). Because a release takes a seal
  number but is reported as `epi.release`, the customer's Cloud log has a hole
  and `epi witness audit` reports `MISSING #N` for every release.
- **P1 — reviewer wording for a file verified on its own.** `epi verify` on a
  shared 4.10.0 file prints `Release: … RELEASE NOT FOUND` and
  `Pre-action: UNKNOWN APPROVER (DEMO APPROVER)`. To a reviewer both read as
  failures. They mean "release file not supplied" and "approver not pinned".
  Suggested: `Release: rel_… declared — add --release-dir to check it` and
  `Pre-action: signed by DEMO APPROVER (not pinned — epi approvers add …)`.
- **P2 — `epi cloud login` prints nothing without a TTY** (CI, pipes) until
  output is unbuffered; the code never appears in automation logs.
- **P2 — workspace name has a leading space** (`" EPI Live Test"`) in
  `cloud.json` / status output; trim on save.

## Fix plan

1. **Client (4.10.0, in this repo) — every numbered seal also sends a normal
   `epi.sealed` report.** A release is a sealed record; send `epi.sealed` for
   it (with `seal_seq`) and the `epi.release` report as an extra. Then old
   receivers and Cloud never see a hole. Heartbeat/approval reports stay
   extras: when the receiver rejects them, the audit says "tail-gap check not
   available on this receiver" and pre-action order falls back to "vendor
   record only — not independent", never a false MISSING.
   Add `epi witness status`/`epi cloud status` line: "This witness accepts:
   seals ✓, heartbeats ✗, releases ✗, approvals ✗".
   Test: an old receiver that accepts only `epi.sealed` → release + seals →
   audit clean.
2. **Cloud service (separate repo) — accept the new types** (`epi.heartbeat`,
   `epi.release`, `epi.release_approval`, `epi.approval_request`,
   `epi.approval_response`, `epi.approval_executed`) with the same HMAC and
   signature checks, store them, and include them in the log export.
   Deploy before announcing release/approval features to Cloud users.
3. Re-run C7a–C7e and the customer audit against Cloud.

## Cleanup still to do (needs the dashboard)

- Delete runs `art_5f9be6d229ecca1795eb9df3` and `art_29152f4cee6d031d02df1375`.
- Revoke the device key for this test computer ("disconnect" in Cloud).
- Anonymous share `923c97a432af3c715cd8ffe9` expires on its own 2026-11-10.

## Browser checklist (human, 5 minutes)

1. Sign in at cloud.epilabs.org → dashboard shows "EPI Live Test".
2. Runs list shows `qa-case-1.epi` (witnessed) and `qa-policy-1.0.epi`.
3. Create a share/trust link for QA Test Customer → open it in a private
   window → download → `epi verify` passes.
4. Try a 2nd share link → is the free-plan limit message clear?
5. Sign out → open the dashboard URL → must go to sign-in; Back button shows
   nothing private.
6. Sign in again → data still there → do the cleanup above.
