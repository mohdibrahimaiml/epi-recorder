# Data retention and deletion (EPI Cloud)

**Product version:** 4.6.3. Related: [SUBPROCESSORS](./SUBPROCESSORS.md),
[DPA](./DPA.md), [CLOUD](./CLOUD.md). Plan entitlements are enforced in
`cloud/src/lib/plans.ts`; the table below states them in product words.

Open-source use keeps no data with EPI Labs at all: sealed `.epi` files live
wherever you put them, and `epi verify` runs offline.

## Retention by plan

| Plan | Customers | Stored runs | Retention | Share links |
|------|-----------|-------------|-----------|-------------|
| Free | 1 | 50 | 30 days | 1 |
| Startup | 3 | 1,000 | 1 year | 3 |
| Growth | 15 | 10,000 | 7 years | unlimited |
| Design partner | 5 | 2,000 | 7 years | 10 |
| Enterprise | As entitled | As entitled | As entitled | As entitled |

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
- **Login data:** OAuth identifiers are deleted with the account.
- **Legacy Render share uploads:** `epi share` links honor `--expires`.
  Ask for early deletion any time.

## How to request export or deletion

There is no self-serve checkout or self-serve deletion while Cloud is in
private beta. Email `mohdibrahim@epilabs.org` with the workspace name:

- **Export:** we return your Evidence Room files plus your witness lines.
- **Deletion:** account + files + queryable metadata, confirmed in writing.
  Target: completed within 30 days, usually much faster.

## Backups

Point-in-time D1 exports to R2, last 4 kept (4-week window) — this is still a
manual weekly founder op. The daily cron in `cloud/wrangler.toml` publishes
witness checkpoints; it does **not** back up the database. The backup runbook is
internal.
Restores are documented per incident. Backup contents follow the same
retention as live data — old backups age out; nothing is archived
indefinitely.
