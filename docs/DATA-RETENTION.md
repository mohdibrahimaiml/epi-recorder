# Data retention and deletion (EPI Cloud)

**Product version:** 4.10.0. Related: [SUBPROCESSORS](./SUBPROCESSORS.md),
[DPA](./DPA.md), [CLOUD](./CLOUD.md). Plan entitlements are enforced by the
hosted service, which is not in this repository; the table below states them in
product words.

Open-source use keeps no data with EPI Labs at all: sealed `.epi` files live
wherever you put them, and `epi verify` runs offline.

## Retention by plan

| Plan | Customers | Stored runs | Retention | Share links |
|------|-----------|-------------|-----------|-------------|
| Free | 1 | 10 | 30 days | 1 (7 days) |
| Team | 5 | 5,000 / month | 1 year | 10 |
| Business | 15 | 25,000 / month | 7 years | unlimited |
| Enterprise | as entitled | as entitled | as entitled | as entitled |

Verification is never metered and witness receipts are hash-only. Evidence
Room files max 25 MB each. Expiry is enforced, not promised: every upload
stores `retention_until`, and the daily cron deletes R2 objects past
retention (audit-logged per file, `artifact.retention_delete`). A deletion
record (file id, timestamp) remains in the audit log — the bytes do not come
back. A legal hold pauses deletion for that file until released.

## What "deleted" means

- **Evidence Room files:** object deleted from R2 (a deletion record stays in
  the audit log; file bytes are gone, subject to the backup window below).
- **Witness log entries:** the log is an ordered, hash-chained record with
  daily checkpoints mirrored publicly. Individual entries cannot be rewritten
  without breaking the chain — that is the point of a witness. Closing a
  customer frees its plan slot but does not rewrite history; the chain
  anchors remain, containing hashes only, never content. Full account removal
  is a written request (below), not a button.
- **Activation metrics:** the first time an account signs in, creates a workspace,
  connects a computer, uploads a run and creates a share link is recorded as a
  pseudonymous user id, event name and timestamp. No email, prompt, model output
  or artifact content is stored, and the rows are deleted with the account.
- **Share uploads:** `epi share` links (EPI Cloud by default, legacy portal as
  fallback) honor `--expires`, capped at 30 days. Ask for early deletion any time.

## How to request export or deletion

There is no self-serve deletion yet. Email `mohdibrahim@epilabs.org` with the workspace name:

- **Export:** we return your Evidence Room files plus your witness lines.
- **Deletion:** account + files + queryable metadata, confirmed in writing.
  Target: completed within 30 days, usually much faster.

## Backups

Point-in-time D1 exports to R2, last 4 kept (4-week window) — this is still a
manual weekly founder op. The daily cron in the hosted service publishes
witness checkpoints; it does **not** back up the database. The backup runbook is
internal.
Restores are documented per incident. Backup contents follow the same
retention as live data — old backups age out; nothing is archived
indefinitely.
