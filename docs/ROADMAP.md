# Roadmap (what's next, honestly)

No dates. Dates are promises; this is a private beta with one maintainer.
Three lists: committed (in `CHANGELOG.md` `[Unreleased]`, being built),
shipped in the last release, considering (open GitHub issues, not decided),
and the standing rule for everything else.

## Committed — `CHANGELOG.md` `[Unreleased]`

Nothing beyond the 4.6.3 security/docs release (see `CHANGELOG.md`).

## Shipped in 4.6.2

- **M4 — customer-owned storage.** Sealed `.epi` straight to the vendor's own
  S3-compatible bucket; EPI Cloud never sees bytes or credentials.
- **M5 — key registry.** Public-key history with revocations as tombstones.
  Informational only, never a pin.
- **M6 — evidence pack.** Reviewer-side zip: hash-checked bytes, `trust.json`,
  `witness.json`, offline verify commands, per-file `MANIFEST.json`.

## Considering — open issues, no commitment

- **#153 — sealed-viewer hardening.** CSP meta tag; reconsider the
  plain-text browser signing seed (non-extractable WebCrypto, session-only,
  or passphrase-wrapped).
- **#76 — `.epi` evidence files vs HTTP API receipts.** Positioning question,
  not a build task yet.
- **#31 — gateway streaming capture.** 501 forces streamed calls onto the
  weaker path; fixing means closing the completeness gap honestly.

## Everything else

File an issue. The investment rule ([internal/scope.md](../internal/scope.md))
still applies: fixes always, new surfaces only with external users asking.
Security reports skip the queue ([SUPPORT](../SUPPORT.md)).
