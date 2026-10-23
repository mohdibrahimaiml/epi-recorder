# Customer witness

**Product version:** 4.6.3. Cloud product claims: [CLOUD.md](./CLOUD.md).

How a vendor reports every seal to its customer, and how the customer keeps
and checks those reports. A witness receipt is **hash-only**. It is not a
copy of the run and not a regulatory certificate.

## What it is

When the vendor seals a run with a witness configured, their system POSTs a
small hash-only report to an endpoint **the customer** controls, at seal time:

```json
{"schema": "epi-witness/v1", "type": "epi.sealed",
 "workflow_id": "...", "manifest_hash": "<sha256>", "file_sha256": "<sha256>",
 "content_digest": "<sha256>",
 "public_key": "<hex>", "key_fingerprint": "<16 hex>",
 "steps": 12, "sealed_at": "<vendor clock>", "seal_timestamp": {"status": "present", "gen_time": "..."}}
```

No content, no prompts, no step data — hashes and counts only. The vendor
cannot edit the customer's copy afterwards.

`steps` counts every sealed step, including the session and environment
steps EPI adds itself, so it can be larger than the "N steps" printed at seal
time (a run printed as `3 steps` reports `"steps": 6`).

`content_digest` covers the sealed evidence: every manifest field and file
hash except the signature and transparency receipts added after sealing.

## Vendor setup

Point sealing at the customer's endpoint, either with environment variables:

```bash
export EPI_WITNESS_URL=https://witness.customer.example/      # comma-separated for several customers
export EPI_WITNESS_SECRET=SHARED_SECRET                       # agreed with the customer out of band
```

or per call:

```python
from epi_recorder import record

with record("case-002.epi",
            witness_url="https://witness.customer.example/",
            witness_secret="SHARED_SECRET"):
    ...
```

Explicit arguments win over the environment. `witness_include_goal=True`
adds the run goal to the report (off by default, since goals can be
sensitive); it makes it easier for the customer to tell which case an entry
belongs to.

Delivery never fails or slows the seal. Each report goes to an outbox first,
is sent from a background thread, and `record()` waits at most
`EPI_WITNESS_TIMEOUT` seconds (default 5). Undelivered reports stay in the
outbox:

```text
$ epi witness status
                  Witness outbox (/home/vendor/.epi/witness_outbox.jsonl)
┏━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ id       ┃ created             ┃ workflow ┃ pending ┃ delivered ┃ last error                     ┃
┡━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ aae10e34 │ 2026-10-12T09:34:55 │ 53e0b2f2 │ 0       │ 1         │                                │
│ 4425f106 │ 2026-10-12T09:35:00 │ 844bedb5 │ 1       │ 0         │ http://127.0.0.1:8099/: HTTP   │
│          │                     │          │         │           │ Error 401: Unauthorized        │
└──────────┴─────────────────────┴──────────┴─────────┴───────────┴────────────────────────────────┘
2 entries, 1 URLs pending.

$ EPI_WITNESS_SECRET=SHARED_SECRET epi witness flush
Delivered: http://127.0.0.1:8099/
```

`epi witness flush` retries everything pending (`--secret` overrides
`EPI_WITNESS_SECRET`, `--timeout` sets the per-request timeout, default 10s).
The secret is never written to the outbox, so `flush` needs it again. Run
`flush` from cron, or after any outage of the customer's endpoint. An entry
that can never be delivered (for example, a customer endpoint that no longer
exists) can be removed with `epi witness drop <id>`, using the `id` column
from `epi witness status`.

## Customer setup: receive (5 minutes)

1. Run the witness receiver (installed with `epi-recorder`, stdlib only) on
   any small server:

   ```bash
   EPI_WITNESS_SECRET=SHARED_SECRET epi witness serve --port 8099 --out received.jsonl
   ```

   It prints the URL to give the vendor (`EPI_WITNESS_URL`) and the log path
   to pass to `epi verify --witness-log`. It listens on 127.0.0.1 by default.
   For a vendor on another network, use `--host 0.0.0.0` behind a
   TLS-terminating reverse proxy and give the vendor the `https://` URL. The
   secret comes from `EPI_WITNESS_SECRET` or `--secret`; without one it
   refuses to start (`--insecure-no-secret` for a local trial only). Reports
   with a bad HMAC are rejected (HTTP 401) and logged:

   ```text
   Witness receiver listening on 127.0.0.1:8099 (HMAC check on)
   Give the vendor:  EPI_WITNESS_URL=http://127.0.0.1:8099/
   ...
   [2026-10-12T09:35:00+00:00] rejected: bad or missing X-EPI-Signature HMAC from 127.0.0.1 (workflow 844bedb5-...) - check the shared secret
   ```

   The reference script `examples/witness_receiver/receiver.py` remains in
   the repository for reference; it is a thin wrapper around the same code.

   Or point the webhook at your own system: accept the POST, check
   `X-EPI-Signature: sha256=<hex>` (HMAC-SHA256 of the raw body), stamp
   `received_at`, append to `received.jsonl`.
2. Optionally check `X-EPI-Seal-Signature: ed25519:<key>:<hex>` against the
   vendor's pinned public key — authenticated without any shared secret.
3. Keep `received.jsonl` append-only, backed up, in a system the vendor
   cannot write to. That independence is the whole point.

## Hosted witness (EPI Cloud, M1)

Instead of running your own receiver, point the vendor at a hosted inbox:

```bash
export EPI_WITNESS_URL=https://cloud.epilabs.org/w/inb_abc
export EPI_WITNESS_SECRET=<secret shown once at inbox creation>
```

The protocol is identical (same `X-EPI-Signature` HMAC, same
`epi-witness/v1` body, ≤16 KB). The server appends each report to an
ordered, hash-chained log:

```
entry_hash = sha256(prev_hash ‖ sha256(payload_raw) ‖ received_at)
```

starting at `GENESIS`. Three public endpoints per inbox:

- `GET /w/{id}/export.jsonl` — raw payload lines in order, byte-compatible
  with `received.jsonl` above. This is what `epi verify --witness-log` reads.
- `GET /w/{id}/chain.jsonl` — audit envelopes
  (`seq`, `received_at`, `payload_raw`, `prev_hash`, `entry_hash`).
- `GET /w/{id}/checkpoints` — daily signed checkpoints with Rekor and
  RFC 3161 references. Public keys at
  `/.well-known/epi-witness-key.json`.

Audit EPI Labs itself (verifies checkpoint signatures, recomputes the chain,
checks Rekor anchoring):

```bash
epi witness check --inbox-url https://cloud.epilabs.org/w/inb_abc
```

A daily cron ( `cloud/wrangler.toml`: `crons = ["5 0 * * *"]` ) signs
`{"inbox","day","count","head_hash"}` with the EPI Cloud witness Ed25519 key
and anchors it in the Sigstore Rekor transparency log and an RFC 3161
timestamp. Rewriting the log would require rewriting both public anchors.

A separate public git mirror (`epi-witness-checkpoints`) is **planned but not
published** as of 23 Oct 2026 — the GitHub URL currently returns 404. Until it
exists, the signed `/w/{id}/checkpoints` endpoint plus Rekor are the public
record; do not tell customers to cross-check a repo that is not there. The
daily cron does **not** back up D1 — database exports are still a weekly
manual founder op (see `internal/cloud-ops.md` §5).

## Customer: check a file

```bash
epi verify run.epi --policy strict --witness-log received.jsonl
```

Add `--require-timestamp` **only if** the vendor seals with a reachable RFC
3161 timestamp service; without it, a file with no valid timestamp still
passes. Scripts must rely on the exit code with `--policy strict`:
`epi verify` exits `0` on WARN, and under the default policy a seal missing
from your log is only a WARN.

The SEAL block shows one `Witness:` line:

- `WITNESSED (received <time>)` — the sealed contents of this file match what
  the vendor reported (`content_digest`) at seal time. It does **not** mean
  the file is byte-identical: a file re-packaged afterwards, for example by
  `epi-register` adding a transparency receipt, still reports WITNESSED.
  WITNESSED compares the manifest with your log; whether the files inside
  still match that manifest is the separate `Integrity:` line. If integrity
  fails, the line instead reads "a report for this case exists …, but THIS
  file was altered", in red.
- `NOT IN WITNESS LOG` — you were never told about this seal. A PASS becomes
  WARN (`⚠ NOT IN YOUR WITNESS LOG · SIGNER PINNED`), and FAIL (exit 1) under
  `--policy strict`, because this is what a re-run or re-sealed case looks like. For a case you know happened, that
  absence is itself evidence: ask the vendor why.
- `NOT CHECKED` — the `--witness-log` file could not be read (wrong path,
  permissions). Verification FAILs, so a typo never silently skips the check.
- `DIFFERENT VERSION` (JSON status `MISMATCH`) — you were sent reports for
  this workflow id, but none for this copy: a re-signed copy, or a gateway
  re-export of the same case that was never reported. The file's own seal may
  be valid; it is simply not what you were told about. Headline
  `✘ FAIL — NOT THE VERSION REPORTED TO YOU`, in every policy.

## Re-runs: one case, several seals

A vendor re-running a case produces a **new, separately witnessed seal**
(a new `workflow_id`), not a change to the old one. Both reports stay in your
log. The witness log lets you see every seal the vendor reported, so look
for **multiple entries for the same case**: a case sealed three times when
you were shown one file is a question to ask. Ask the vendor to set
`witness_include_goal=True` (or a case reference in the goal) so entries can
be matched to cases.

Gateway exports are different: every export of one gateway case keeps that
case's `workflow_id`, and each report carries `case_id` (for example
`trace::trace-123`). Exporting a case twice gives two reports with the same
`workflow_id`; a copy you receive must match one of them.

## Limits (read these)

- The witness proves **what was sent**, not what happened. A vendor can
  choose not to send a seal, and can only send seals for runs they record.
- It does not prove the agent behaved correctly, completely, or compliantly
  — only that these contents were sealed at (no later than) the recorded time.
- `sealed_at` is the vendor's clock; the independent time is the TSA
  `gen_time` inside `seal_timestamp` (checked offline by `epi verify`).
