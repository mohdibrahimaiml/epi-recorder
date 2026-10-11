# Customer witness receiver (reference, not a product surface)

This folder is for the **vendor's customer**: a tiny server that receives
hash-only seal reports (`schema: epi-witness/v1`) and appends them to
`received.jsonl`. The vendor points their witness webhook at it:

```bash
# vendor side (or EPI_WITNESS_URL env)
record("run.epi", witness_url="http://customer-host:8099/", witness_secret="SHARED_SECRET")
```

## Run it (any small server, or localhost for a trial)

```bash
python examples/witness_receiver/receiver.py --port 8099 --secret SHARED_SECRET --out received.jsonl
```

Or point the webhook at your own system — it only needs to accept a JSON
POST, check the `X-EPI-Signature: sha256=<hex>` HMAC, stamp `received_at`,
and append the object to a `.jsonl` file.

## Check a file against your log

```bash
epi verify run.epi --witness-log received.jsonl
```

- `WITNESSED (received <time>)` — the file matches what the vendor reported.
- `NOT IN WITNESS LOG` — the customer was never told about this seal. For a
  case the customer knows happened, that absence is itself evidence.
- `MISMATCH` — the file differs from the sealed report (FAIL).

## Notes

- Entries are hashes and counts only — no content, no prompts, no step data.
- Optionally verify the `X-EPI-Seal-Signature: ed25519:<key>:<hex>` header
  against the vendor's pinned public key (no shared secret needed).
- Keep `received.jsonl` append-only in a system the vendor cannot edit.
  That independence is the whole point.
