# Roadmap (what's next, honestly)

No dates. Dates are promises; this is a small team with one maintainer.
Three lists: committed (in `CHANGELOG.md` `[Unreleased]`, being built),
shipped in the last release, considering (open GitHub issues, not decided),
and the standing rule for everything else.

## Committed - `CHANGELOG.md` `[Unreleased]`

- **Cloud funnel coherence.** The public site and the Cloud app must describe
  the same access model: a free, self-serve workspace with visible limits
  (1 customer relationship, 1 share link, 10 files a year, 30 days), an optional onboarding
  checklist, and paid Team/Business tiers that are not sold through a public
  checkout yet.
- **One plan ladder.** Free / Team / Business / Enterprise in `plans.ts`,
  the dashboard, `/plans`, `CLOUD.md` and `DATA-RETENTION.md`. Legacy
  workspace ids are mapped on read, never migrated in place.
- **One deploy path per surface.** `website/` -> `site/` -> Cloudflare Pages;
  `PRIVATE-EPI/cloud/` -> Cloudflare Worker. The duplicate `wrangler.jsonc`
  docs Worker is retired.

## Shipped in 4.9.0

- **Open core, corrected.** The checker and approver stay free:
  `epi approvers`, `epi review`, single-user `epi oversight report` and
  `epi org bundle` are in the public Apache-2.0 package. `epi audit`, `epi annex`,
  `epi notify`, `epi chat` and the `epi enterprise` kit are the paid layer.
- **Cloud share is live.** `epi share` defaults to `https://cloud.epilabs.org`
  and `POST /api/share` is verified end to end.
- **Cloudflare edge compatibility.** CLI requests send
  `User-Agent: epi-recorder/<version>`; older clients fall back to the legacy
  portal when Cloud returns 403.

## Shipped in 4.6.2

- **M4 - customer-owned storage.** Sealed `.epi` straight to the vendor's own
  S3-compatible bucket; EPI Cloud never sees bytes or credentials.
- **M5 - key registry.** Public-key history with revocations as tombstones.
  Informational only, never a pin.
- **M6 - evidence pack.** Reviewer-side zip: hash-checked bytes, `trust.json`,
  `witness.json`, offline verify commands, per-file `MANIFEST.json`.

## Considering - open issues, no commitment

- **#153 - sealed-viewer hardening.** CSP meta tag; reconsider the
  plain-text browser signing seed (non-extractable WebCrypto, session-only,
  or passphrase-wrapped).
- **#76 - `.epi` evidence files vs HTTP API receipts.** Positioning question,
  not a build task yet.
- **#31 - gateway streaming capture.** 501 forces streamed calls onto the
  weaker path; fixing means closing the completeness gap honestly.
- **Account linking.** GitHub and Google are separate identities today. Link
  them only when both emails are verified, or show the provider clearly enough
  that an empty workspace is never a surprise.
- **Decouple the envelope spec version from the package version.** Before any
  5.0 rename. `spec_version` currently defaults to `get_version()` in
  `epi_core/schemas.py`, and `epi_core/serialize.py` treats any version below
  4.4.1 — including every `0.x` — as the legacy `cbor` format. So a package
  renumber would silently change the signature canonicalization of every newly
  sealed record, and the browser verifier's dispatch (matched to the 4.4.1
  tuple) would read them differently. Fix: a frozen `ENVELOPE_SPEC_VERSION`
  that `spec_version` defaults to, with `producer_version` carrying the package
  version, plus a test that a `0.x` and a `5.x` package both write the frozen
  spec and verify offline. Filed 4 November 2026 during the 4.9.0-only PyPI
  cleanup; deliberately deferred so it is not done in the same breath as a
  version change.

## Everything else

File an issue. The investment rule (stated in full internally) still applies:
fixes always, new surfaces only with external users asking.
Security reports skip the queue ([SUPPORT](../SUPPORT.md)).
