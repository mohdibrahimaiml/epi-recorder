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

| Flag | Default | Meaning |
|------|---------|---------|
| `--host` | `127.0.0.1` | Interface to listen on. For a vendor on another network use `0.0.0.0` **behind a TLS-terminating reverse proxy** and give the vendor the `https://` URL. |
| `--port` | `8099` | Port to listen on. If it is taken the receiver exits with a one-line error. |
| `--out` | `received.jsonl` | Append-only log to write. |
| `--secret` | `EPI_WITNESS_SECRET` env | Shared HMAC secret. Without one, the HMAC check is off. |

Reports with a bad or missing HMAC get HTTP 401 and a log line on stderr
(`rejected: bad or missing X-EPI-Signature HMAC ...`). `--help` lists all flags.

Or point the webhook at your own system — it only needs to accept a JSON
POST, check the `X-EPI-Signature: sha256=<hex>` HMAC, stamp `received_at`,
and append the object to a `.jsonl` file.

## Check a file against your log

```bash
epi verify run.epi --witness-log received.jsonl
```

- `WITNESSED (received <time>)` — the file's sealed contents match what the
  vendor reported (`content_digest`). A file re-packaged later (e.g. by
  `epi-register`) still matches; it is not a byte-for-byte comparison.
- `NOT IN WITNESS LOG` — the customer was never told about this seal. For a
  case the customer knows happened, that absence is itself evidence.
- `MISMATCH` — the file differs from the sealed report (FAIL).

## Notes

- A re-run of a case is a new, separately witnessed seal. Look for several
  entries for the same case. Details: [docs/WITNESS.md](../../docs/WITNESS.md).
- Entries are hashes and counts only — no content, no prompts, no step data.
- Optionally verify the `X-EPI-Seal-Signature: ed25519:<key>:<hex>` header
  against the vendor's pinned public key (no shared secret needed).
- Keep `received.jsonl` append-only in a system the vendor cannot edit.
  That independence is the whole point.
