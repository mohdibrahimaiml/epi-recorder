# Data retention and deletion (EPI Cloud)

**Product version:** 4.6.2. Related: [SUBPROCESSORS](./SUBPROCESSORS.md),
[DPA](./DPA.md), [CLOUD](./CLOUD.md). Plan entitlements are enforced in
`cloud/src/lib/plans.ts`; the table below states them in product words.

Open-source use keeps no data with EPI Labs at all: sealed `.epi` files live
wherever you put them, and `epi verify` runs offline.

## Retention by plan

| Plan | Stored runs | Retention |
|------|-------------|-----------|
| Free | 50 | 30 days |
| Startup | 1,000 | 1 year |
| Growth | 10,000 | 7 years |
| Design partner | 2,000 | 7 years (10 agents / 5 inboxes) |
| Enterprise | As entitled | As entitled |

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

Point-in-time D1 exports to R2, last 4 kept (4-week window) — currently a
manual founder op until the M1 cron ships ([../internal/cloud-ops.md](../internal/cloud-ops.md)).
Restores are documented per incident. Backup contents follow the same
retention as live data — old backups age out; nothing is archived
indefinitely.
