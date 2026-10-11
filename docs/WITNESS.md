# Customer witness

One page for the vendor's customer: how to receive and keep witness records.

## What it is

When the vendor seals a run with a witness configured, their system POSTs a
small hash-only report to an endpoint **you** control, at seal time:

```json
{"schema": "epi-witness/v1", "type": "epi.sealed",
 "workflow_id": "...", "manifest_hash": "<sha256>", "file_sha256": "<sha256>",
 "content_digest": "<sha256>",
 "public_key": "<hex>", "key_fingerprint": "<16 hex>",
 "steps": 12, "sealed_at": "<vendor clock>", "seal_timestamp": {"status": "present", "gen_time": "..."}}
```

No content, no prompts, no step data — hashes and counts only. The vendor
cannot edit your copy afterwards.

`content_digest` covers the sealed evidence: every manifest field and file
hash except the signature and transparency receipts added after sealing.
If the vendor later runs `epi-register`, the file is re-packaged (new
`file_sha256`), but `epi verify --witness-log` still reports WITNESSED
because the evidence you were told about is unchanged. Any change to the
evidence itself is a MISMATCH.

Verify with `epi verify run.epi --witness-log received.jsonl --require-timestamp`:
a file without a valid timestamp otherwise still passes.

## How to receive (5 minutes)

1. Run the reference receiver (stdlib only) on any small server:
   `python examples/witness_receiver/receiver.py --port 8099 --secret SHARED_SECRET`.
   Agree the secret with the vendor out of band. Or point the webhook at
   your own system: accept the POST, check
   `X-EPI-Signature: sha256=<hex>` (HMAC-SHA256 of the raw body), stamp
   `received_at`, append to `received.jsonl`.
2. Optionally check `X-EPI-Seal-Signature: ed25519:<key>:<hex>` against the
   vendor's pinned public key — authenticated without any shared secret.
3. Keep `received.jsonl` append-only, backed up, in a system the vendor
   cannot write to. That independence is the whole point.

## How to check a file

```bash
epi verify run.epi --witness-log received.jsonl
```

- `WITNESSED (received <time>)` — the file is byte-identical to what the
  vendor reported at seal time.
- `NOT IN WITNESS LOG` — you were never told about this seal. For a case
  you know happened, that absence is itself evidence: ask the vendor why.
- `MISMATCH` — the file differs from the sealed report. Verification FAILs.

## Limits (read these)

- The witness proves **what was sent**, not what happened. A vendor can
  choose not to send a seal, and can only send seals for runs they record.
- It does not prove the agent behaved correctly, completely, or compliantly
  — only that these bytes were sealed at (no later than) the recorded time.
- `sealed_at` is the vendor's clock; the independent time is the TSA
  `gen_time` inside `seal_timestamp` (checked offline by `epi verify`).
