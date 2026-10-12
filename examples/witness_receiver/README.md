# Customer witness receiver (reference)

The receiver ships with `epi-recorder`: run **`epi witness serve`**. This
folder keeps `receiver.py`, the original reference script, for reference; it
is now a thin wrapper around the same code (`epi_core.witness_receiver`).

The receiver is for the **vendor's customer**: a tiny server that receives
hash-only seal reports (`schema: epi-witness/v1`) and appends them to
`received.jsonl`. The vendor points their witness webhook at it:

```bash
# vendor side (or EPI_WITNESS_URL / EPI_WITNESS_SECRET env)
record("run.epi", witness_url="http://customer-host:8099/", witness_secret="SHARED_SECRET")
```

## Run it (any small server, or localhost for a trial)

```bash
pip install epi-recorder
EPI_WITNESS_SECRET=SHARED_SECRET epi witness serve --port 8099 --out received.jsonl
```

It prints the URL to give the vendor and the log path for
`epi verify --witness-log`.

| Flag | Default | Meaning |
|------|---------|---------|
| `--host` | `127.0.0.1` | Interface to listen on. For a vendor on another network use `0.0.0.0` **behind a TLS-terminating reverse proxy** and give the vendor the `https://` URL. |
| `--port` | `8099` | Port to listen on. If it is taken the receiver exits with a one-line error. |
| `--out` | `received.jsonl` | Append-only log to write. |
| `--secret` | `EPI_WITNESS_SECRET` env | Shared HMAC secret. Required: without one `epi witness serve` refuses to start. |
| `--insecure-no-secret` | off | Run with the HMAC check off (local trial only). |

Reports with a bad or missing HMAC get HTTP 401 and a log line on stderr
(`rejected: bad or missing X-EPI-Signature HMAC ...`). `--help` lists all flags.

The reference script takes the same `--host/--port/--out/--secret` flags
(`python examples/witness_receiver/receiver.py --help`); unlike the CLI it
runs with the HMAC check off when no secret is given.

Or point the webhook at your own system — it only needs to accept a JSON
POST, check the `X-EPI-Signature: sha256=<hex>` HMAC, stamp `received_at`,
and append the object to a `.jsonl` file.

## Check a file against your log

```bash
epi verify run.epi --policy strict --witness-log received.jsonl
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
