# EPI Cloud: build plan ($0 hosting)

Status: ready for the coding agent · Owner: coding agent; founder approves the 🔒 items ·
Base: `main` @ 546ce53 (4.6.1 released)

Read this whole file before writing code. Then read `plans/CODING-AGENT-BRIEF.md`
(the process rules there still apply: one work package = one PR, tests first,
never invent facts, never publish a release, 🔒 = founder approval).

---

## 0. The idea in one paragraph

Everything that exists today stays **free forever**: recorder, sealing, `.epi`
format, viewer, gateway, `epi verify`. We add **EPI Cloud**, a paid hosted service
that AI vendors pay for because it gets their agents approved by banks, insurers and
auditors. It has four parts:

1. **Evidence Vault**: stores sealed `.epi` files for the retention period the
   customer needs (1–7 years), searchable, exportable.
2. **Trust Page**: one private link the vendor sends to its customer's reviewer.
   It shows live, checkable evidence. **The reviewer's own browser verifies every
   file**, so the reviewer never has to trust EPI Labs.
3. **Hosted Witness**: a neutral inbox run by EPI Labs that receives the
   hash-only receipt of every sealed run (`epi-witness/v1`, already implemented
   in the product). Neither the vendor nor the customer can quietly delete receipts.
   Daily signed checkpoints are mirrored to a public GitHub repo.
4. **Evidence Pack**: one download that turns the evidence into what a reviewer
   asks for (verify instructions, witness export, key history, mapping to EU AI Act
   Art. 12 record-keeping and a bank questionnaire).

Plus a **Key Registry** (public keys only: rotation and revocation history) and
**plans/billing** by number of production agents.

**Design principle (also our sales line):** *the cloud never asks you to trust it.*
The cloud stores and relays; verification always happens on the reviewer's machine
(browser or `epi verify`). This is also what makes $0 hosting possible, because the
heavy CPU work runs on the client.

---

## 1. $0 hosting: stack and limits

Everything runs on **Cloudflare's free plan**, where the website already lives.
**Do not** build on Render free: it sleeps, loses its disk on every deploy, and
its free Postgres is deleted after 30 days. A vault can't live there.

| Need | Service (free plan) | Free limit to design for* | Notes |
|---|---|---|---|
| API / app server | **Cloudflare Workers** | 100k requests/day; ~10 ms CPU per request | Keep handlers light; no full re-verification on the server (see §6.2) |
| Database | **Cloudflare D1** (SQLite) | 5 GB; ~5M rows read/day, ~100k rows written/day | Plenty for 5–50 customers |
| File storage | **Cloudflare R2** | 10 GB storage; 1M writes/month; 10M reads/month; **no download fees** | ~20,000 files of 500 KB. Cloudflare may ask for a card to enable R2; within free limits it charges $0. Fallback without a card in §1.2 |
| Ordered witness log | **Durable Objects** (SQLite-backed, available on free plan) | free-plan quota | One object per witness inbox = one writer, so ordering is strictly correct |
| Scheduled jobs | Workers **Cron Triggers** | free | Retention purge, daily checkpoints |
| Website / UI | Cloudflare Pages (existing) | free | New pages under `website/app/` |
| Login | **GitHub OAuth App** | free | Vendor users sign in with GitHub. Reviewers need no account (secret link) |
| Payments | **Paddle** (existing) | no monthly fee, % per sale | Only costs money when you earn money |
| Public checkpoint mirror | **GitHub Actions + public repo** | free for public repos | Independent anchoring of witness checkpoints |
| Uptime | UptimeRobot free | 50 monitors | Already in plan WP-OPS-1 |
| Email (optional, later) | Resend free | 3,000/month | MVP needs no email at all |

\* Free-plan limits change. **The agent must check the current Cloudflare docs
before M0 and write the real numbers into `docs/CLOUD.md`.** If a limit differs
from this table, adapt the design and tell the founder.

### 1.1 When it stops being $0
- Workers Paid is $5/month: only needed above ~100k requests/day or for longer CPU time.
  That point is roughly 20+ active paying customers, who will pay for it many times over.
- R2 above 10 GB: about $0.015/GB/month.
- Write these thresholds into `docs/CLOUD.md`, and add an admin page that shows
  current usage against the free limits.

### 1.2 If R2 can't be enabled (no card)
Store `.epi` files in a D1 table `blobs(artifact_id, chunk_no, data BLOB)` in
≤1 MB chunks. Hide this behind one interface `BlobStore` with two
implementations (`R2BlobStore`, `D1BlobStore`), so switching later is one config
line. Max file size in this mode: 25 MB (same as the website verifier).

---

## 2. Architecture

```
 Vendor's machine                         EPI Cloud (Cloudflare, $0)                    Customer's reviewer
 ─────────────────                        ──────────────────────────                    ───────────────────
 epi-recorder / gateway                   Worker "epi-cloud"  (cloud.epilabs.org)
   seals run.epi ──── epi cloud push ───▶ /v1/artifacts  ──▶ R2 (files) + D1 (metadata)
   witness report ─── POST (HMAC) ──────▶ /w/{inbox_id}  ──▶ Durable Object (ordered log)
                                          Cron: daily checkpoint (Ed25519-signed)
                                                 │                                       opens Trust Page link
                                                 └──▶ GitHub repo (public mirror)        /t/{slug}?k=…
                                          /t/... serves metadata + files ─────────────▶ browser verifies each file
                                          /v1/packs/{id} evidence pack zip ───────────▶ epi verify --witness-log …
```

Rules:
- **Hash-only by default for the witness.** No run content ever reaches the
  witness. Content reaches EPI only if the vendor uploads files to the Vault.
- **Tenant isolation:** every row has `org_id`; every query filters by it; tests
  prove that org A can never read org B's data.
- **No customer private keys, ever.** The Key Registry stores public keys only.

### 2.1 Repo layout (new)
```
cloud/
  wrangler.toml            # name = "epi-cloud"; bindings: DB (D1), VAULT (R2), WITNESS (DO); crons
  package.json             # hono, zod, @noble/ed25519 (fallback), vitest, @cloudflare/vitest-pool-workers
  src/index.ts             # Hono router, middleware (auth, CSRF, rate limit, errors)
  src/routes/              # auth.ts orgs.ts keys.ts agents.ts artifacts.ts witness.ts trust.ts packs.ts billing.ts admin.ts
  src/lib/epi.ts           # ported from website/js/epi-verify-core.js: container detect, zip extract, manifest, signature
  src/lib/crypto.ts        # sha256, HMAC, Ed25519 sign/verify (WebCrypto), token generation
  src/lib/blobstore.ts     # BlobStore interface + R2/D1 implementations
  src/lib/plans.ts         # plan limits (single source of truth)
  src/do/witness.ts        # WitnessInbox Durable Object
  migrations/0001_init.sql ...
  test/                    # unit + integration (miniflare); fixtures = website/assets/**/*.epi
website/app/               # static UI: index (dashboard), vault, inboxes, keys, settings; t/ (trust page)
epi_cli/cloud.py           # `epi cloud login|push|status|inbox` commands
docs/CLOUD.md              # how it works, limits, security model, runbook
.github/workflows/cloud.yml            # test + deploy worker on main (wrangler, CF API token secret)
.github/workflows/witness-mirror.yml   # daily: fetch signed checkpoints → commit to public mirror repo
```

The existing `verify_portal` (Render) **stays running and untouched**. Later we
port its GitHub login and Paddle webhook logic into the Worker and retire it.
That is not part of this plan.

---

## 3. Data model (D1) — `migrations/0001_init.sql`

```sql
CREATE TABLE orgs (
  id TEXT PRIMARY KEY,               -- ulid
  slug TEXT UNIQUE NOT NULL,         -- url-safe, used in trust page
  name TEXT NOT NULL,
  plan TEXT NOT NULL DEFAULT 'free', -- free|startup|growth|enterprise|design_partner
  created_at TEXT NOT NULL
);
CREATE TABLE users (
  id TEXT PRIMARY KEY, github_id INTEGER UNIQUE NOT NULL, login TEXT NOT NULL,
  email TEXT, created_at TEXT NOT NULL
);
CREATE TABLE memberships (
  org_id TEXT NOT NULL REFERENCES orgs(id), user_id TEXT NOT NULL REFERENCES users(id),
  role TEXT NOT NULL CHECK (role IN ('owner','member')), PRIMARY KEY (org_id, user_id)
);
CREATE TABLE sessions (
  id_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL, expires_at TEXT NOT NULL
);
CREATE TABLE api_keys (
  id TEXT PRIMARY KEY, org_id TEXT NOT NULL, prefix TEXT NOT NULL,      -- shown: "epik_ab12…"
  key_hash TEXT UNIQUE NOT NULL,                                        -- sha256 of full key; full key shown once
  scopes TEXT NOT NULL,                                                 -- "push,read"
  created_by TEXT NOT NULL, created_at TEXT NOT NULL, last_used_at TEXT, revoked_at TEXT
);
CREATE TABLE agents (
  id TEXT PRIMARY KEY, org_id TEXT NOT NULL, name TEXT NOT NULL,        -- "refund-agent"
  status TEXT NOT NULL DEFAULT 'active', created_at TEXT NOT NULL,
  UNIQUE (org_id, name)
);
CREATE TABLE artifacts (
  id TEXT PRIMARY KEY, org_id TEXT NOT NULL, agent_id TEXT,
  file_sha256 TEXT NOT NULL, size_bytes INTEGER NOT NULL,
  spec_version TEXT, workflow_id TEXT, goal TEXT, steps INTEGER,
  sealed_at TEXT, key_fingerprint TEXT, public_key TEXT,
  server_check TEXT NOT NULL,         -- 'signature_ok'|'signature_bad'|'unsigned'|'unreadable'
  witness_status TEXT NOT NULL,       -- 'witnessed'|'not_in_witness'|'different_version'|'no_inbox'
  blob_key TEXT NOT NULL,
  uploaded_at TEXT NOT NULL, retention_until TEXT NOT NULL, legal_hold INTEGER NOT NULL DEFAULT 0,
  deleted_at TEXT,
  UNIQUE (org_id, file_sha256)
);
CREATE INDEX artifacts_org_time ON artifacts(org_id, uploaded_at DESC);
CREATE TABLE inboxes (                -- one hosted witness inbox per vendor→customer relationship
  id TEXT PRIMARY KEY, org_id TEXT NOT NULL,          -- vendor org that pays
  customer_label TEXT NOT NULL,                       -- "Acme Bank" (free text, vendor-entered)
  hmac_secret_hash TEXT NOT NULL,                     -- secret shown once; sha256 stored for display checks only
  hmac_secret_enc TEXT NOT NULL,                      -- secret encrypted with Worker secret (needed to verify HMAC)
  created_at TEXT NOT NULL, closed_at TEXT
);
CREATE TABLE checkpoints (
  inbox_id TEXT NOT NULL, day TEXT NOT NULL,          -- UTC date
  count INTEGER NOT NULL, head_hash TEXT NOT NULL,    -- hash of last entry of the day
  signature TEXT NOT NULL, signed_at TEXT NOT NULL,
  PRIMARY KEY (inbox_id, day)
);
CREATE TABLE org_keys (               -- PUBLIC keys only
  id TEXT PRIMARY KEY, org_id TEXT NOT NULL, public_key TEXT NOT NULL, fingerprint TEXT NOT NULL,
  label TEXT, valid_from TEXT NOT NULL, revoked_at TEXT, revoke_reason TEXT,
  UNIQUE (org_id, public_key)
);
CREATE TABLE share_links (
  id TEXT PRIMARY KEY, org_id TEXT NOT NULL, token_hash TEXT UNIQUE NOT NULL,
  label TEXT NOT NULL,                                -- "Acme Bank – vendor review"
  scope TEXT NOT NULL,                                -- json: {"agents":[...],"inbox":"...","artifacts":"all|selected"}
  created_at TEXT NOT NULL, expires_at TEXT NOT NULL, revoked_at TEXT, last_viewed_at TEXT
);
CREATE TABLE audit_log (              -- everything done in the cloud, hash-chained (we eat our own dog food)
  seq INTEGER PRIMARY KEY AUTOINCREMENT, org_id TEXT, actor TEXT NOT NULL,
  action TEXT NOT NULL, detail TEXT NOT NULL, at TEXT NOT NULL,
  prev_hash TEXT NOT NULL, entry_hash TEXT NOT NULL
);
```
The witness entries themselves live **inside the Durable Object's own SQLite**
(one object per inbox), not in D1. See §6.3.

---

## 4. API (all JSON; versioned under `/v1`)

Auth: browser = session cookie (HttpOnly, Secure, SameSite=Lax, 30 days);
CLI/gateway = `Authorization: Bearer epik_…`. Every state-changing browser
request checks `Origin` (CSRF). Errors: `{error:{code,message}}`.

| Method & path | Who | What |
|---|---|---|
| `GET /auth/github` → `GET /auth/github/callback` | anyone | GitHub OAuth login (state param, PKCE not needed for confidential client) |
| `POST /auth/logout` | user | |
| `GET /v1/me` | user | user + orgs |
| `POST /v1/orgs` | user | create org (becomes owner) |
| `POST /v1/orgs/{org}/api-keys` · `GET` · `DELETE /{id}` | owner | full key returned once |
| `POST /v1/orgs/{org}/agents` · `GET` · `PATCH /{id}` | member | plan limit enforced on active agents |
| `POST /v1/orgs/{org}/artifacts` | API key `push` / member | upload a `.epi` (raw body, ≤25 MB). Header `X-EPI-Agent: refund-agent` |
| `GET /v1/orgs/{org}/artifacts?agent=&from=&to=&cursor=` | member | list + filter |
| `GET /v1/orgs/{org}/artifacts/{id}` · `/download` | member | metadata · file |
| `POST /v1/orgs/{org}/artifacts/{id}/legal-hold` | owner | toggle |
| `DELETE /v1/orgs/{org}/artifacts/{id}` | owner | soft-delete (blocked during legal hold); audit-logged |
| `POST /v1/orgs/{org}/inboxes` · `GET` · `POST /{id}/close` | owner | create witness inbox; returns URL + HMAC secret once |
| `POST /w/{inbox_id}` | vendor's recorder/gateway | **witness receive**, protocol identical to `epi witness serve` (HMAC `X-EPI-Signature: sha256=…` over raw body; schema `epi-witness/v1`); 202 on accept |
| `GET /v1/orgs/{org}/inboxes/{id}/export.jsonl` | member / share link | the received payloads, one per line, **byte-compatible with `epi witness serve` output**, so `epi verify --witness-log` works on it |
| `GET /w/{inbox_id}/checkpoints` | public | signed daily checkpoints (JSON) |
| `GET /.well-known/epi-witness-key.json` | public | EPI Cloud witness public key(s) + validity |
| `POST /v1/orgs/{org}/keys` · `GET` · `POST /{id}/revoke` | owner | public key registry |
| `GET /o/{slug}/keys.json` | public | key history (for reviewers and the CLI) |
| `POST /v1/orgs/{org}/share-links` · `GET` · `DELETE /{id}` | owner | trust page links (token shown once) |
| `GET /t/{slug}?k={token}` (HTML) + `GET /v1/trust/{slug}` (JSON, token header) | reviewer | trust page data |
| `GET /v1/orgs/{org}/packs?from=&to=&agent=` (or via share link) | member/reviewer | evidence pack zip (§6.6) |
| `POST /billing/paddle/webhook` | Paddle | signature-verified; sets `orgs.plan` |
| `GET /admin/usage` | founder only (allowlisted GitHub id) | usage vs free-tier limits |

---

## 5. Plans (single source of truth: `cloud/src/lib/plans.ts`) 🔒 prices

| Plan | Active agents | Vault retention | Inboxes | Share links | Evidence packs |
|---|---|---|---|---|---|
| free (signed-up, unpaid) | 1 | 30 days, max 100 files | 1 | 1 | no |
| design_partner | 10 | 7 years | 5 | 10 | yes |
| startup | 3 | 1 year | 2 | 3 | yes |
| growth | 10 | 7 years | 10 | unlimited | yes |
| enterprise | custom | custom | custom | custom | yes |

Prices (founder decides; current proposal): startup ~$500/mo, growth ~$2,000/mo,
enterprise $30–100k/yr, design partner $1,000–2,000/mo for the first 5.
**Verification is never limited or charged anywhere.**

---

## 6. Module specs

### 6.0 M0 — Skeleton, auth, orgs, API keys
- `cloud/` scaffold, Hono, D1 migration, deploy to `epi-cloud.<account>.workers.dev`, then custom domain `cloud.epilabs.org` (founder adds route).
- GitHub OAuth (founder creates the OAuth App; client id/secret as Worker secrets).
- Sessions: random 32-byte id; store sha256(id) in D1; cookie holds the raw id.
- API keys: `epik_` + 32 random bytes base32; store sha256; show once; scopes.
- Rate limits: per IP and per key, counters in a Durable Object or D1 (window 1 min). Login 10/min, upload 60/min/key, witness 600/min/inbox.
- Security headers on every response (copy `website/_headers` policy; add `cloud.epilabs.org` to the website CSP `connect-src`).
- `audit_log` hash-chained writer used by every mutating route.
- **Acceptance:** login → create org → create API key → `curl` with the key works; tenant-isolation test suite (org A cannot read B) passes; `npm test` green in CI.

### 6.1 M1 — Evidence Vault
- `POST artifacts`: stream body to BlobStore while computing SHA-256 (WebCrypto digest over the buffered body is fine at ≤25 MB, the digest is native and cheap).
- **Server checks (cheap, within CPU limit):** detect container (envelope v2 / legacy zip), extract **only** `manifest.json`, verify the Ed25519 signature over the manifest (port `verifyManifestSignature` from `website/js/epi-verify-core.js`, same canonicalisation incl. pre-JCS specs), read spec_version/workflow_id/goal/steps/public_key, compute key fingerprint exactly like `epi_core.keys.key_fingerprint()`.
- **Do not** recompute every member hash on the server (CPU limit). The UI states plainly: *"Server checked: signature and witness. Full check runs in your browser,"* with a "Verify now" button that runs the existing browser verifier on the downloaded file.
- Witness match: if the org has inboxes, look up `file_sha256` / `content_digest` in the inbox log and set `witness_status` (same three verdicts as the CLI: witnessed / not in witness log / different version).
- Dedupe on `(org_id, file_sha256)`. Retention: `uploaded_at + plan retention`. Cron daily: delete blobs past `retention_until` unless `legal_hold`, mark `deleted_at`, audit-log it.
- CLI: `epi cloud login` (paste API key; stored in `~/.epi/cloud.json` with 0600 perms), `epi cloud push FILE... [--agent NAME]`, `epi cloud status`. Env `EPI_CLOUD_URL` (default `https://cloud.epilabs.org`), `EPI_CLOUD_KEY`. Gateway option `--cloud-push` to auto-upload after sealing (off by default).
- **Acceptance:** every `.epi` under `website/assets/**` uploads, gets `signature_ok`, and the browser "Verify now" result matches `epi verify --offline`; a tampered file gets `signature_bad`; the same file twice gives one row; retention purge test with a fake clock.

### 6.2 M2 — Trust Page  ← **first demo to design partners**
- Owner creates a share link (label, scope, expiry ≤ 180 days). URL: `https://epilabs.org/t/{slug}?k={token}` (static page on Pages; data from the Worker).
- Page shows: vendor name; agents in scope; for each agent, runs in the last 30/90 days (uploaded count, witnessed count, any `different_version` or `signature_bad`, in red); key fingerprints with history; witness checkpoint status ("last signed checkpoint: today 00:05 UTC ✓"); a list of artifacts with **"Verify in my browser"** per file (reuses the site verifier: downloads the file and runs `verifyEPI` locally); "Download evidence pack" (after M6); "Verify yourself" box with the exact command:
  `epi verify FILE --policy strict --witness-log received.jsonl --offline`.
- No login for reviewers in MVP; the unguessable token is the access. `noindex`, `Referrer-Policy: no-referrer`, token never logged, `last_viewed_at` recorded so the vendor sees "Acme viewed this yesterday" (a real sales signal).
- Wording uses the approved blocks in `plans/WEBSITE-ENTERPRISE-PLAN.md` §6 (scope disclaimer always visible). 🔒 founder approves page copy.
- **Acceptance:** Playwright: open link → see agents → click verify on a genuine file (amber "not changed, signer not pinned" unless pinned), a tampered file (red), an expired or revoked link (clear error page). Mobile layout works.

### 6.3 M3 — Hosted Witness (the moat)
- Owner creates an inbox per customer relationship ("Acme Bank"). The response gives `witness_url = https://cloud.epilabs.org/w/{inbox_id}` and a secret (once). The vendor sets these in their recorder/gateway exactly as for `epi witness serve` (`--witness-url`, `--witness-secret`), with **no product code changes needed** (that's the point: same protocol).
- `POST /w/{id}`: verify HMAC (`X-EPI-Signature: sha256=<hex>` over the raw body; constant-time compare); reject a missing/bad signature (401), a non-`epi-witness/v1` schema (400) or a body > 16 KB (413). Forward to the inbox's **Durable Object**, which appends `{seq, received_at, payload_raw, prev_hash, entry_hash}` with `entry_hash = sha256(prev_hash || sha256(payload_raw) || received_at)` in its own SQLite (single writer, so strict order). Return 202 **only after** the append commits.
- Export: `export.jsonl` = the raw payload lines in order, identical to what `epi witness serve` writes to `received.jsonl`. **Compatibility test:** seal a file with the real recorder pointed at a local Worker (miniflare), export, then run `epi verify FILE --policy strict --witness-log export.jsonl --offline`, expecting WITNESSED; an unreported re-seal gives NOT IN WITNESS LOG; a different version gives DIFFERENT VERSION.
- Daily checkpoint (cron 00:05 UTC): for each inbox with new entries, sign `{"inbox":id,"day":"YYYY-MM-DD","count":N,"head_hash":H}` with the EPI Cloud witness Ed25519 key (Worker secret `WITNESS_SIGNING_KEY`; public key at `/.well-known/epi-witness-key.json`). Store in `checkpoints`.
- Public mirror: `.github/workflows/witness-mirror.yml` runs daily, fetches all public checkpoints, and commits them to a **separate public repo** `epi-witness-checkpoints` (founder creates it). Rewriting history would then require rewriting a public git history that others have cloned, which is a strong, honest claim and free. Optional: also RFC 3161-timestamp each day's checkpoint file with FreeTSA.
- Add `epi witness check --inbox-url … FILE` (CLI) that downloads the checkpoints, verifies the signatures with the published key, and checks the export against the head hash. Reviewers can then audit EPI Labs itself.
- **Acceptance:** compatibility test above passes; reordering, deleting or editing any entry in an export is detected by `epi witness check`; HMAC tests; a 1,000-report burst keeps strict order; checkpoint signature verifies with the published key.

### 6.4 M4 — Key Registry (public keys only)
- Owner registers the org's signing public keys (paste the hex, or `epi cloud keys push` reads `~/.epi/keys/*.pub`, **never** the private key; the CLI refuses to read files without `.pub`).
- Rotation = add a new key; revocation = `revoked_at` + reason; history is never deleted.
- Public `GET /o/{slug}/keys.json` with fingerprints in the same format as `epi keys`. Trust page shows the history.
- Make it **informational, like the public registry after WP-SEC-4**: the CLI may *show* "registered at EPI Cloud as <org>", but **never** treats it as a pin. The reviewer still pins and phone-confirms. Add a test for this.
- `epi keys trust --from-cloud {slug}` prints fingerprints and requires `--fingerprint` to match (same rule as `.epi`-based pinning).
- **Acceptance:** register → rotate → revoke flows; a revoked key shows red on the trust page; CLI tests prove "registered" never equals "pinned".

### 6.5 M5 — Plans & billing
- `plans.ts` limits enforced in the routes (agents, inboxes, share links, retention, packs). Limit errors say exactly which limit was hit and how to upgrade.
- Port the Paddle webhook signature verification from `verify_portal/billing.py` (same algorithm, with tests from `tests/test_paddle_webhook_signature.py` ported). Map Paddle price IDs → plan. 🔒 founder creates the new Paddle products/prices; the old $199/$799 "hosted verification" products get archived (not deleted).
- Design partners: the founder can set `plan = design_partner` manually on `/admin` (no Paddle needed; invoice by hand).
- **Acceptance:** webhook with a valid signature upgrades the org; an invalid one gives 400; downgrade keeps data but blocks new uploads above the limit (never deletes data).

### 6.6 M6 — Evidence Pack v1
`GET …/packs` returns a zip built in the Worker (streamed, keep the CPU low: zip *store* mode, no compression of the `.epi` files themselves):
- `README.html`: one page with who, which agents, the period, counts, and how to verify (the exact command); the scope disclaimer from plan §6.3.
- `artifacts/` (the selected `.epi` files) + `artifacts.csv` (hash, agent, sealed_at, server check, witness status).
- `witness/received.jsonl` (export) + `witness/checkpoints.json` + `witness/epi-witness-key.json`.
- `keys/history.json`.
- `mapping/eu-ai-act-art12.md`: which EPI evidence field supports each Art. 12 logging element. 🔒 **Draft only; founder and, ideally, a compliance advisor review before it's offered. No claim of compliance; use the wording rules.**
- `mapping/bank-questionnaire.md`: answers to the common AI-vendor questions (logging, retention, human review, data exit, subcontractors) built only from facts true for this org. 🔒 same review.
- AIUC-1 mapping: **not in v1.** Add only after the founder obtains and reads the standard; never invent control IDs.
- **Acceptance:** unzip → run `epi verify` on every artifact with `--witness-log witness/received.jsonl` → results match `artifacts.csv`.

---

## 7. Security requirements (all modules)

- Secrets only via `wrangler secret put` (GITHUB_CLIENT_SECRET, SESSION_KEY, INBOX_SECRET_KEY, WITNESS_SIGNING_KEY, PADDLE_WEBHOOK_SECRET). Never in code, logs or the repo. A CI grep fails the build on anything secret-looking.
- All tokens and keys stored as sha256 hashes; compared in constant time.
- Every query includes `org_id`; tenant isolation tests for every route.
- Uploads: size limit, content sniffing (must be an EPI container), never execute or render uploaded HTML on our origin. Downloads use `Content-Disposition: attachment` and `Content-Type: application/vnd.epi+zip`. The trust page **never** iframes the embedded viewer.
- Rate limits as in M0. Request bodies for witness ≤16 KB.
- Audit log for every mutation, hash-chained; owners can view their org's audit log.
- Backups: weekly cron exports D1 → R2 (`backups/`), keep 4. Document the restore in `docs/CLOUD.md`.
- Privacy page and `/security` (WP-TRUST-1) updated: what EPI Cloud stores (Vault: full files; Witness: hashes only), where (Cloudflare), how long, and how to delete. 🔒

---

## 8. Build order and milestones

| # | Package | Size | Demo moment |
|---|---|---|---|
| 0 | **WP-PRICING-0** 🔒: pause $199/$799 "hosted verification" plans on the site, add "Design Partner Program (5 places)" + "EPI Cloud: in private beta" | S | Site stops selling something with no value |
| 1 | **M0** skeleton, auth, orgs, API keys | M | You can log in at cloud.epilabs.org |
| 2 | **M1** Vault + `epi cloud push` | M | Upload from the CLI, see the run in the dashboard |
| 3 | **M2** Trust Page | M | **Send a real link to a design partner.** Start selling here |
| 4 | **M3** Hosted Witness + checkpoints + public mirror + `epi witness check` | L | "Neither side can delete receipts": the moat demo |
| 5 | **M4** Key Registry | S | Key history on the trust page |
| 6 | **M5** Plans + Paddle | M | Self-serve upgrade |
| 7 | **M6** Evidence Pack v1 🔒 mapping | M | "Here's your bank review pack" |

With one coding agent: roughly 6–8 weeks to M6. **Start selling at step 3.** Do not
wait for everything.

Per package: branch, tests first, PR, CI green, deploy to the workers.dev preview,
Playwright run, then merge (ungated) or wait for approval (🔒). Same loop as
`CODING-AGENT-BRIEF.md` Part C.

---

## 9. Founder one-time setup (all free)

1. Cloudflare dashboard → Workers & Pages → create the D1 database `epi-cloud` and the R2 bucket `epi-cloud-vault` (add a card if R2 asks; charges stay $0 within limits; otherwise tell the agent to use the D1 fallback, §1.2).
2. Workers → add custom domain `cloud.epilabs.org` to the `epi-cloud` worker (after M0 deploys).
3. GitHub → Settings → Developer settings → OAuth Apps → New: homepage `https://epilabs.org`, callback `https://cloud.epilabs.org/auth/github/callback`. Give the agent the client ID; put the secret in with `wrangler secret put` yourself (or as a GitHub Actions secret).
4. Create a Cloudflare API token (Workers + D1 + R2 edit) and add it as the GitHub Actions secret `CLOUDFLARE_API_TOKEN`, so CI deploys.
5. Create the public repo `epi-witness-checkpoints` (empty).
6. After M5: create the new Paddle products at the prices you choose. 🔒
7. Approve every 🔒 PR (pricing copy, trust page copy, compliance mappings, privacy text).

---

## 10. Never do

- Never charge for, limit or meter verification.
- Never store customer private keys, or offer "we sign for you" in this plan.
- Never claim "compliant", "certified", "guaranteed" or "court-admissible" (wording rules in the brief).
- Never treat Cloud key registration or the trust page as an identity pin.
- Never show the trust page or pricing for features not live: label them **In pilot** or **Roadmap**.
- Never move the Vault or Witness to Render free or any host that can lose data on redeploy.
- Never make the product depend on the cloud: everything must keep working offline without it.

## 11. Definition of done (M0–M6)
- A design partner can: log in, create an org and an agent, push runs from the CLI or gateway, create a witness inbox for their customer, send a trust-page link, and download an evidence pack.
- Their customer's reviewer can: open the link, verify any file in their own browser, download the witness export and get `WITNESSED` from `epi verify --policy strict --witness-log … --offline`, and check EPI's checkpoints with `epi witness check`.
- Monthly hosting bill: **$0** at design-partner scale, with usage visible on `/admin/usage`.
