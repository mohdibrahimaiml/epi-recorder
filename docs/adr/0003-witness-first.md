# ADR-0003: Customer witness (hash-only, outbox-first) instead of file escrow

**Date:** 2026-10. **Status:** Accepted.

## Context

Signatures stop *alteration after sealing*. They do nothing against
*silent re-seal*: the vendor alters the file and re-signs with their own key
before handing it over — signature valid, nothing looks wrong. The fix needs
a third party that saw the original. Holding vendors' full files would make
EPI Cloud a custody honeypot (and kill the $0-cost story).

## Decision

Witness-first: every seal reports a small hash-only receipt
(`epi-witness/v1`: workflow id, manifest and file hashes) to an endpoint the
*customer* controls, at seal time, outbox-first so a down endpoint never
fails an export. `epi verify --witness-log` compares the handed-over file
against the customer's independent record.

## Alternatives considered

- **Full-file escrow in EPI Cloud:** custody liability, bandwidth/storage
  cost, and a bigger breach blast radius. Rejected; Evidence Room holds only
  vendor-selected files, never required.
- **No witness:** leaves silent re-seal unanswerable. Rejected for
  claim-grade use (`--policy strict` + witness log is the deliverable rule).

## Consequences

- The witness proves what was *sent*, not what was *recorded*: a vendor can
  choose not to send, and capture completeness stays a separate problem.
  A missing entry for a case the customer knows happened is itself evidence.
- Receipts are hashes and counts only (goal only with explicit opt-in), so
  the witness learns nothing about content.
- Cloud economics work because the hot path is 1 receipt, not N megabytes
  ([internal/cloud-ops.md](../../internal/cloud-ops.md)).
