# ADR-0001: Ship `.epi` as an HTML+ZIP polyglot (envelope-v2)

**Date:** 2026-04 (envelope-v2; viewer-hash seal added 4.4.1). **Status:** Accepted.

## Context

A bank reviewer will not install our CLI to look at a file. If double-clicking
the evidence shows nothing, the format loses to a PDF. If verification needs
our servers, the "offline" story dies.

## Decision

One file, two readings: a 128-byte header (`<!--` magic, version, payload
length, UUID, `created_at`, payload SHA-256, outer-viewer SHA-256 in
`reserved_tail[0:32]`), then self-contained viewer HTML, then the ZIP payload
(`epi_core/container.py`, `docs/spec/EPI-SPEC.md` §2). The ZIP is the sealed
evidence; the HTML is a convenience renderer. Since 4.4.1 the outer viewer's
hash is sealed too, so display-layer edits FAIL `epi verify`.

## Alternatives considered

- **Pure ZIP + sidecar viewer:** safest rendering story, but two files to keep
  together through email gateways — chain-of-custody UX dies.
- **Pure ZIP only:** still available (`epi migrate --legacy-zip`) as the
  data-only handover for strict gateways. Not the default because reviewers
  open archives less than pages.

## Consequences

- HTML+JS+ZIP in one attachment matches HTML-smuggling *shapes*; handled in
  [docs/FILE-SAFETY.md](../FILE-SAFETY.md) (no external calls, verify-without-opening, data-only form).
- The in-file viewer paints its own verdict, so it can never be the authority
  (`epi verify` is). Accepted: convenience preview, enforced by `VERIFY.txt`
  and the threat model.
