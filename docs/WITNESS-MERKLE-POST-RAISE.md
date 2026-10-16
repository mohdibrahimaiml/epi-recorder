# Post-raise: Merkle inclusion proofs for witness lines

Status: designed, NOT built. The M6 signed-receipt stopgap ships first.

## Why

Today the witness log is a sequential hash chain
(`entry_hash = sha256(prev_hash ‖ sha256(payload) ‖ received_at)`,
`cloud/src/lib/witnessChain.ts`) and checkpoints sign only
`{inbox, day, count, head_hash}`. Verifying line N requires replaying every
line from GENESIS to N, so a link-scoped export cannot be tied to a
checkpoint without revealing the vendor's other runs.

M6 closes the reviewer story with per-line Ed25519 receipts ("stamped
tickets"): each line carries a witness-signed statement
`{inbox_id, seq, line_sha256, artifact_sha256, received_at}`, checkable
offline. That proves the witness *said* the line, but not that the line is
*in the committed log* — a malicious witness could sign a line it never
appended (equivocation). The daily checkpoint + Rekor anchor still covers
full-log consistency, but only for reviewers holding the whole chain.

## What "proper" looks like

A Merkle Mountain Range (or equivalent append-only authenticated log) over
the entries, with the checkpoint committing to the MMR root instead of (or
in addition to) `head_hash`. The link-scoped endpoint then returns each line
with an O(log n) inclusion proof against the signed root: no other lines
revealed, no trust in the server at serving time.

Same idea as Certificate Transparency / Sigsum. Any design must keep:

- 10 ms Worker CPU rules (`docs/CLOUD.md` §3): proving is reviewer-side;
  the server only serves stored hashes.
- Byte-compat of `export.jsonl` / `received.jsonl` (reviewers and
  `epi verify --witness-log` depend on it).
- Cross-language golden vectors (noble ↔ `cryptography`), as M6 did for
  receipt canonical bytes.
- A migration story for the existing sequential chain (checkpoints to date
  commit to `head_hash`; both formats must verify during transition).

## Trigger

Build this after the raise, when design partners ask for auditor-grade
non-equivocation proofs or when log volume makes full-chain replay
impractical. Not before.
