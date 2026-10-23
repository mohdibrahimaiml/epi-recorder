# ADR-0002: No per-call TSA anchoring; seal-time + heartbeat checkpoints instead

**Date:** 2026-03. **Status:** Accepted (also stated in
[THREAT_MODEL](../THREAT_MODEL.md) assumptions).

## Context

Independent time ("this existed no later than T, attested by someone other
than the vendor") is the only answer to "the signer backdated `created_at`
before signing." The strongest form is a timestamp on every model call.

## Decision

Per-call TSA anchoring was attempted and abandoned: a network round-trip to
an outside authority in the path of every model call makes recorder
reliability hostage to that authority's uptime. Instead:

- **Seal-time notarization:** RFC 3161 token over the seal imprint
  (`epi-tsa-imprint/v1`), validated offline by `epi verify` since 4.6.0
  against pinned roots.
- **Heartbeat checkpoints:** periodic TSA timestamps of the hash-chain head,
  so in-process history is anchored without per-call cost.

## Alternatives considered

- **Per-call TSA:** rejected (reliability hostage, latency, cost per call).
- **Seal-time only, no heartbeats:** weaker for long runs; heartbeats close
  the gap without touching the hot path.
- **No third-party time at all:** leaves backdating-by-signer unanswerable;
  rejected for regulated use.

## Consequences

- Default `record()` timestamps attest *contents existed no later than T*,
  not key binding, unless `imprinted_public_key` is present
  ([KNOWN_LIMITATIONS](../KNOWN_LIMITATIONS.md)).
- Pre-4.6 tokens are legacy presence-only; the verifier says so instead of
  pretending.
- Offline validation assumes TSA key/clock honesty and performs no revocation
  checks — stated, not hidden.
