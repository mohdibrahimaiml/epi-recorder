# EPI Cloud

**Status (v4.6.2):** private beta at `https://cloud.epilabs.org`.  
**Not:** a paywall on verification, a self-serve hosted-verification product, or a place that must hold every `.epi`.

Open-source `epi-recorder` stays complete without Cloud. Cloud is how a vendor **connects a computer**, **witnesses runs (hashes)**, and **shares selected files** with a customer reviewer.

## What Cloud holds vs what it does not

| Part | What EPI Cloud holds | What stays elsewhere |
|------|----------------------|----------------------|
| Witness | Hash-only receipts, ordered, signed; daily checkpoints | Full `.epi` bytes (unless you upload them) |
| Trust page | Metadata + files you attach to a share link | Reviewer's verification (browser or `epi verify`) |
| Evidence Room | Only runs the vendor *selects* (max 25 MB each) | Everything else |
| Customer bucket | Endpoint/bucket **metadata** and a vendor-reported health check | Credentials and objects — recorder-side only ([STORAGE.md](./STORAGE.md)) |
| Key registry | **Public** keys the vendor registered (`epi cloud keys push` accepts `*.pub` only) | Pins. A registry listing is informational. Reviewers still `epi keys trust` out of band |

The Worker never unzips an upload, never hashes a whole file in memory, and never sees customer bucket keys. Verification is always the reviewer's machine.

## Customer path (vendor → bank reviewer)

1. `epi cloud login` — terminal shows a short code; type it at `https://cloud.epilabs.org/auth/device` and pick the customer this computer records for. Saved to `~/.epi/cloud.json` (mode 0600). `epi auth login` is the same flow.
2. `epi demo` (or your own `record()` + `epi cloud push`) — seals and, when logged in, uploads a sample for that customer.
3. On the Cloud dashboard, create a **share / trust link scoped to that customer** and send it.
4. The reviewer opens the link (nothing to install) and/or downloads the evidence pack and runs `epi verify` offline.

Commands: [CLI.md](./CLI.md) (`epi cloud login|use|push|status`, `epi cloud keys …`, `epi cloud storage …`). Witness semantics: [WITNESS.md](./WITNESS.md).

## Plans (product, not a public checkout)

Public site: Cloud is private beta ([epilabs.org/plans](https://epilabs.org/plans)). Entitlements in code (`cloud/src/lib/plans.ts`):

| Plan | Customers | Stored runs | Retention |
|------|-----------|-------------|-----------|
| Free | 1 | 50 | 30 days |
| Startup | 3 | 1,000 | 1 year |
| Growth | 15 | 10,000 | 7 years |
| Design partner / Enterprise | as entitled | as entitled | as entitled |

Verification is never limited or charged. Speak in **customers**, not internal metric names.

Login for **epilabs.org Sign In** and the CLI is Cloud only.

Legacy hosted paths still on Render (not the account system, not required to record or verify): default `epi share` upload, MCP HTTP hosting, opt-in telemetry/pilot signup URLs, keep-warm cron, and some `/api/*` Cloudflare proxies. Cloud trust links are the customer path going forward.

---

# Ops (Cloudflare free-plan stack)

Source: `cloud/` (Worker `epi-cloud`). Verified against the Cloudflare docs on
2026-10-14; re-check before changing capacity assumptions.

## 1. Free-plan limits (real numbers)

| Need | Service | Free limit |
|---|---|---|
| API | Workers | 100,000 requests/day; **10 ms CPU per request** (I/O waits don't count) |
| Metadata | D1 | 5 GB total (max 500 MB per database); 5M row reads/day; 100k row writes/day — hard cutoff since 2026-09-01 (queries fail past cap until 00:00 UTC) |
| Witness log | Durable Objects (SQLite-backed) | 100,000 requests/day; 13,000 GB-s/day; SQLite rows 5M read / 100k written per day; 5 GB stored |
| Files | R2 | 10 GB-month; 1M Class A (write) ops/month; 10M Class B (read) ops/month; free egress. **Account needs a card on file (still $0 within limits)** |
| Jobs | Cron Triggers | free (daily checkpoint at 00:05 UTC) |
| Login | GitHub + Google OAuth | free |

Paid thresholds (only once revenue exists): Workers Paid $5/month; R2
$0.015/GB-month beyond 10 GB. `/admin/usage` shows usage vs limits; alert at 70%.

## 2. Capacity math

| Per event | Worker requests | D1 writes | DO writes | R2 |
|---|---|---|---|---|
| Witness receipt | 1 | 0 | 1 | 0 |
| Evidence Room upload (selected run) | 2 (init + put) | 2 (artifact + audit) | 0 | 1 write, ~0.5 MB |
| Trust page view | 2–5 | 1 (event) | 0 | reads only |

Free tier supports roughly ~50,000 witnessed runs/day across all customers
(DO request cap is the binding constraint) and ~20,000 files (10 GB) in
Evidence Rooms. Witness-first is what makes $0 viable.

## 3. Hard CPU rules (10 ms)

- Never buffer or hash a whole upload in the Worker. Stream the body straight to R2.
- Never unzip on the server. The client sends the manifest separately (M3).
- Only cheap server crypto: Ed25519 verify on a ≤4 KB manifest, HMAC on a ≤16 KB
  witness body, SHA-256 of small JSON.
- Never build zips on the server. Packs are built in the reviewer's browser (M6).
- Max Evidence Room file: 25 MB.

## 4. Founder setup (free)

> Run every `wrangler` command below from the repo root with
> `--config cloud/wrangler.toml`. Without it, wrangler picks up the repo-root
> `wrangler.jsonc` (a different Worker, `epi-recorder`) and your D1, R2, and
> secrets land in the wrong place. CI always passes `--config` explicitly.

1. Cloudflare account + card (R2 requires it; $0 within limits).
2. `wrangler --config cloud/wrangler.toml d1 create epi-cloud` → paste `database_id`
   into `cloud/wrangler.toml` (replaces the `TODO-...` placeholder), then
   `wrangler --config cloud/wrangler.toml d1 migrations apply epi-cloud --remote`.
   Never `d1 execute --file=` for schema: only `migrations apply` records what
   ran, and CI applies migrations before every deploy, so code never goes
   live ahead of its database.
3. `wrangler --config cloud/wrangler.toml r2 bucket create epi-cloud-room`.
4. OAuth apps: GitHub (Settings → Developer settings → OAuth Apps) and Google
   (Console → Credentials → OAuth client, web). Callbacks:
   `https://cloud.epilabs.org/auth/github/callback` and
   `https://cloud.epilabs.org/auth/google/callback`.
   Set client IDs/secrets via `wrangler --config cloud/wrangler.toml secret put`
   (never in git):
   `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`, `GOOGLE_CLIENT_ID`,
   `GOOGLE_CLIENT_SECRET`, `SESSION_KEY` (random 32 bytes hex),
   `INBOX_SECRET_KEY` (AES-GCM for inbox HMAC secrets, 32 bytes hex),
   `WITNESS_SIGNING_KEY` (Ed25519 witness key, 32 bytes hex — signs daily
   checkpoints), `ANCHOR_SIGNING_KEY` (P-256 key, 32 bytes hex — submits
   checkpoint hashes to Rekor only), `PADDLE_WEBHOOK_SECRET` (M7).
5. `FOUNDER_USER_IDS`: comma-separated user ids for the founder pages:
   `/admin/usage` and `/admin` (workspace list with owner email and usage,
   plus a plan picker - every plan change is written to the audit log).
   Never match on email: an unverified account can carry someone else's
   address, so the server also requires `email_verified = 1` for founder
   ids. Set it with `wrangler --config cloud/wrangler.toml secret put
   FOUNDER_USER_IDS` (a plain `[vars]` value in `wrangler.toml` works too,
   but a secret keeps the allowlist out of the config file). Find your user
   id after first login (D1: `SELECT id, email, email_verified FROM users`
   - use a row with `email_verified = 1`; GitHub and Google logins are
   separate rows). Open `https://cloud.epilabs.org/admin` while signed in
   as that user; the page shows who you are signed in as.
6. GitHub secret `CLOUDFLARE_API_TOKEN` (Workers/D1/R2 edit) for deploys.
7. Custom domain: attach `cloud.epilabs.org` to the worker after first deploy.
8. Create the empty public repo `epi-witness-checkpoints` (M1 mirror).

CI deploys only from `main` and skips while `database_id` is still the
`TODO-...` placeholder.

### 4b. Repairing a behind prod D1 (one-time)

Symptom: sign-in (or any new-feature call) returns
`{"error":{"code":"internal"}}` right after a deploy, and worker logs show
`no such column` / `no such table`. Cause: the schema was once created by
hand (`d1 execute --file=`), which records nothing, so later migrations
never ran. No customer data is at risk — repair is additive:

```bash
# 1. What does prod think ran?
wrangler --config cloud/wrangler.toml d1 migrations list epi-cloud --remote
# 2. Back up first (see §5).
wrangler --config cloud/wrangler.toml d1 export epi-cloud --remote --output=backup-$(date +%F).sql
# 3. Converge: 0001 is IF NOT EXISTS, so hand-created tables apply cleanly.
wrangler --config cloud/wrangler.toml d1 migrations apply epi-cloud --remote
# 4. Tripwire (same as CI smoke check): must print [] with no error.
wrangler --config cloud/wrangler.toml d1 execute epi-cloud --remote \
  --command "SELECT email_verified FROM users LIMIT 0" --json
wrangler --config cloud/wrangler.toml d1 execute epi-cloud --remote \
  --command "SELECT user_code FROM device_codes LIMIT 0" --json
```

If step 3 fails on an `ALTER TABLE ... ADD COLUMN` duplicate (0002 was
also hand-applied): the column already exists, so nothing is lost — note
which migration failed, apply the remaining files' statements by hand if
needed, and record the outcome in the PR. Then retry sign-in.

## 5. Backups

Weekly D1 backup to R2 (keep 4). Until the M1 cron ships, run by hand:

```bash
wrangler --config cloud/wrangler.toml d1 export epi-cloud --output=backup-$(date +%F).sql
# upload to R2 epi-cloud-room/backups/, keep the last 4
```

Restore: `wrangler --config cloud/wrangler.toml d1 execute epi-cloud --file=backup-<date>.sql`.
Document each restore in the PR that performs it.

## 6. Local dev

```bash
cd cloud
npm install
npm test          # vitest unit + route isolation (no Cloudflare account needed)
npm run typecheck
# --local needs no account; add --config when run from the repo root:
wrangler dev --local --config wrangler.toml
```

## 7. What the server never holds

Customer bucket credentials (BYO bucket is recorder-side, M4), customer
private keys, full `.epi` bytes in Workers memory. Tokens/keys are stored as
SHA-256; share tokens travel in the URL fragment + header only (M2).

## 8. Anchoring findings (M1, verified live 2026-10-15)

- Rekor v1 accepts `hashedrekord` with an **ECDSA P-256** key (x509/PEM,
  DER signature over the raw checkpoint bytes, HTTP 201 + inclusion proof).
  **Ed25519 keys are rejected** (`unsupported hash algorithm`), so anchoring
  uses a dedicated P-256 key and nothing else. Checkpoints stay Ed25519.
- Noble v2 ECDSA pre-hashes with sha256 by default: pass raw bytes, never a
  digest. It rejects high-S by default (ours are always low-S).
- The public mirror repo `epi-witness-checkpoints` is filled by
  `.github/workflows/witness-mirror.yml` (daily; needs `MIRROR_PAT`,
  `MIRROR_REPO`, `WITNESS_MIRROR_INBOXES` secrets - inboxes opt in).

## 9. Customer path

See the top of this file. Ops reminder: the Connect page is
`https://cloud.epilabs.org/auth/device`.
