# Customer witness

**Product version:** 4.10.0. Cloud product claims: [CLOUD.md](./CLOUD.md).

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
 "seal_seq": 57, "ledger_id": "<uuid>",
 "prev_seq": 56, "prev_content_digest": "<sha256>",
 "steps": 12, "sealed_at": "<vendor clock>", "seal_timestamp": {"status": "present", "gen_time": "..."}}
```

No content, no prompts, no step data — hashes and counts only. The vendor
cannot edit the customer's copy afterwards.

The `seal_seq`, `ledger_id`, `prev_seq` and `prev_content_digest` fields are
additive: older receivers ignore them, and older reports simply lack them.

`steps` counts every sealed step, including the session and environment
steps EPI adds itself, so it can be larger than the "N steps" printed at seal
time (a run printed as `3 steps` reports `"steps": 6`).

`content_digest` covers the sealed evidence: every manifest field and file
hash except the signature and transparency receipts added after sealing.

## Sequence numbers and gaps

Every seal made with a signing key gets a number (1, 2, 3…) and the
fingerprint of the previous seal, written **inside the signed manifest**
(`seal_chain`) and repeated in the witness report. The signature covers the
number, so a vendor cannot renumber a file afterwards without breaking it.

### One chain per customer, not per key

A chain belongs to an **audience**, not to a key. One key that reports to two
customers keeps two independent 1..n sequences, so a number missing from one
customer's log is never a hole in the other's. The audience is the explicit
`record(customer="acme-bank")` when given, otherwise the Cloud inbox id, then
a hash of the normalised witness URL, then `local:unwitnessed` for seals made
before any witness exists.

`customer=` also keeps a chain continuous when the witness URL changes; a
changed URL without it reads as a NEW CHAIN warning. A seal with no witness
lands on its own `local:unwitnessed` chain and never creates a hole in a
customer's chain.

When one seal goes to more than one audience, the file stores only salted
commitments for every audience (`artifacts/seal_chains.json`); the full entry
and its nonce travel only in that audience's report. A file handed to one
customer therefore reveals no audience id, number or count for another. A
single-audience file keeps the plaintext `seal_chain`, as before.

`prev_seq` names the last *committed* seal, which is not always `seq - 1`:
two seals can be allocated and sealed at the same time (the gateway does
this), and a seal cannot link to a number whose content digest is not known
yet. In serial operation `prev_seq == seq - 1`.

### Audit the log

```bash
epi witness audit received.jsonl          # plain English
epi witness audit received.jsonl --json   # machine-readable
```

Per `(audience, key fingerprint, ledger id)` it reports:

| Finding | Meaning |
| --- | --- |
| `MISSING #2` | the vendor sealed #2 but never reported it |
| `FORK at #57` | two different seals were reported with the same number |
| `CHAIN BREAK at #58` | `prev_content_digest` does not match the seal at `prev_seq` |
| `TAIL GAP` | a heartbeat says the chain runs past the last seal you received |
| `BURNED #57 (vendor-declared)` | the vendor says #57 was allocated but never sealed. **Not verifiable**: it is shown as a warning, never counted as clean, and `--strict` makes it exit 1 |
| `NEW CHAIN` | the same key now has a second chain starting at #1 (state wiped, restored elsewhere, or a second machine). A warning, shown rather than hidden |

Exit codes: `0` clean; `1` on MISSING, FORK, CHAIN BREAK or TAIL GAP (and,
with `--strict`, on BURNED and NEW CHAIN); `2` when the log cannot be read.
Reports from before sequence numbers — and seals made in the browser with
"Sign & seal" — have no ledger and are listed as **unsequenced**, never as
errors.

### Heartbeat: stop the last few seals from being withheld

A daily audit cannot see a seal the vendor simply never sent. An hourly
signed heartbeat ("I have sealed up to #412") closes that tail:

```bash
EPI_WITNESS_URL=https://witness.customer.example/ \
EPI_WITNESS_SECRET=SHARED_SECRET \
epi witness heartbeat --key default
```

Run it from cron (hourly is a good default):

```cron
0 * * * * EPI_HOME=/var/lib/epi EPI_WITNESS_URL=https://witness.customer.example/ EPI_WITNESS_SECRET=... /usr/local/bin/epi witness heartbeat --key default
```

The heartbeat goes through the same outbox and is signed with the same key
(`X-EPI-Seal-Signature`). It reports the last committed number and any
vendor-declared burns. If the customer's receiver predates heartbeats it
answers HTTP 400; the vendor is told plainly that the receiver needs
upgrading, and the entry is not retried forever.

`epi verify --witness-log` adds one line for the file's chain position, for
example `Sequence: #57 of chain 3f2a…, log contiguous 1..412`. Files sealed
before this feature show `Sequence: not present`, and their verdict does not
change.


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

A daily cron in the hosted service (`crons = ["5 0 * * *"]`) signs
`{"inbox","day","count","head_hash"}` with the EPI Cloud witness Ed25519 key
and anchors it in the Sigstore Rekor transparency log and an RFC 3161
timestamp. Rewriting the log would require rewriting both public anchors.

### Cross-check the public mirror

`epi witness check --mirror` compares the live witness against a mirror and
fails when history was rewritten:

```bash
# Against the hosted mirror (once it exists)
epi witness check --inbox-url https://cloud.epilabs.org/w/inb_abc \
  --mirror https://raw.githubusercontent.com/<owner>/epi-witness-checkpoints/main

# Against a local clone, or entirely offline
git clone https://github.com/<owner>/epi-witness-checkpoints
epi witness check --inbox-url https://cloud.epilabs.org/w/inb_abc \
  --mirror ./epi-witness-checkpoints
```

It fails — with a plain reason — when:

- a checkpoint the live witness serves differs from the mirrored one for the
  same day (`head_hash`, `count` or `signature`);
- a day present in the mirror is missing from the live witness, or changed
  there (history rewritten);
- the witness public key differs without a key-rotation entry
  (`previous_witness_ed25519_pub_hexes` on either side).

A day that exists **only** on the live side is fine: the mirror lags by up to a
day.

A separate public git mirror (`epi-witness-checkpoints`) is **planned but not
published** as of 23 Oct 2026 — the GitHub URL currently returns 404. Until it
exists, the signed `/w/{id}/checkpoints` endpoint plus Rekor are the public
record; do not tell customers to cross-check a repo that is not there. The
daily cron does **not** back up D1 — database exports are still a weekly
manual founder op (documented in the internal ops runbook).

**What changes when the mirror exists:** the `witness-mirror` workflow starts
pushing to it every day (it is already written, append-only and signature-checked;
it succeeds trivially while the secrets are unset), the two commands above become
the customer-facing cross-check, and this paragraph plus the "planned" note in
[docs/CLOUD.md](CLOUD.md) are updated to say it is live. Nothing else changes:
the mirror holds hashes only, never customer evidence.

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
  re-export of the same case that was never reported. When the case matches by
  goal (the vendor ran it again under a new workflow id), the same verdict is
  reported with the goal named: *"a different version of 'Adjudicate claim
  CLM-1001' was reported to you"*. The file's own seal may be valid; it is
  simply not what you were told about. Headline
  `✘ FAIL — NOT THE VERSION REPORTED TO YOU`, in every policy.

A second `Sequence:` line shows where the file sits in the vendor's chain
(`#57 of chain 3f2a…, log contiguous 1..412`). It is display-only: an old
file says `not present`, and a gap in the log does not change the verdict —
use `epi witness audit` for that, so the reason is named rather than folded
into a file verdict.

### In the browser, no install

`/verify` now takes **two** drops: the `.epi` file, and your `received.jsonl`
next to it. Same matching as the CLI — exact file/manifest hash, then the
content digest (a repacked file keeps it), then the case by goal:

- `Witness: matches your log` — what the vendor reported.
- `This is not the version your witness recorded.` — a re-sealed copy of a case
  you have a report for. Without the log, the same file looks valid, because
  every signature in it is real; that is the whole reason you keep the log.
- `This file is not in your witness log` — never reported.
- Signed logs (receipts) say **not confirmed** in the browser: it has no pinned
  witness key, so it will not call a stamp verified. Use
  `epi verify --witness-pubkey` for that.

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

## Over a period: the oversight report

One file answers "what did it decide?". A bank asks for a period: how many
decisions, by outcome; which model versions answered; who approved them; which
cases were reported but never delivered; which cases you expected that never
arrived. `epi oversight report` joins your files, this log and your expected-case
list into one page. See `docs/OVERSIGHT.md`.

```bash
epi oversight report --cases ./received --log received.jsonl \
  --since 2026-09-01 --until 2026-10-31 --expect cases.csv --out oversight.html
```

## Limits (read these)

- The witness proves **what was sent**, not what happened. A vendor can
  choose not to send a seal, and can only send seals for runs they record.
  Sequence numbers make a withheld **middle** seal visible, and the heartbeat
  makes a withheld **tail** visible — but only if the vendor's sealing path
  uses the ledger and the heartbeat actually runs. A vendor who never runs
  `epi witness heartbeat` can still hide the last few seals.
- Decisions that were never sealed at all are invisible except through the
  heartbeat's count (and the customer's own knowledge that a case happened).
  A vendor-declared burn is not verifiable: a dishonest vendor could call a
  withheld seal "burned", which is why `epi witness audit` reports burns as
  warnings and `--strict` fails them.
- Seals made in the browser with "Sign & seal" have no access to the local
  ledger and are **unsequenced**. They are listed as such, never as errors.
- It does not prove the agent behaved correctly, completely, or compliantly
  — only that these contents were sealed at (no later than) the recorded time.
- `sealed_at` is the vendor's clock; the independent time is the TSA
  `gen_time` inside `seal_timestamp` (checked offline by `epi verify`).
