# EPI Cloud: build plan v2 ($0 hosting)

Status: ready for the coding agent · Owner: coding agent; founder approves 🔒 items ·
Base: `main` @ 546ce53 (4.6.1 released) · v2 supersedes v1 (changes listed in §12)

Read this whole file, then `plans/CODING-AGENT-BRIEF.md` (its process rules apply:
one work package = one PR, tests first, never invent facts, never publish a release,
🔒 = founder approval).

---

## 0. What we're building and why it wins

Everything that exists today stays **free forever**: recorder, sealing, `.epi`,
viewer, gateway, `epi verify`. We add **EPI Cloud**, which AI vendors pay for
because it gets their agents approved by banks, insurers and auditors **faster**.

### The three facts that shape the design
1. **Volume.** A production agent runs thousands of times a day. Storing every
   `.epi` (≈500 KB) for 7 years is terabytes per customer. A $0 stack fills in a week.
2. **Privacy kills sales cycles.** A sealed run contains customer data (names,
   amounts, messages). If EPI Cloud must hold it, every buyer needs a DPA,
   subprocessor approval and a security review **of EPI Labs**, which adds months.
   Hash-only needs none of that.
3. **Startup risk.** "What happens to our 7-year records if EPI Labs shuts down?"
   is the first question every CISO asks.

### So the product is **witness-first, customer-owned storage**
| Part | What EPI Cloud holds | Why |
|---|---|---|
| **Hosted Witness** (the core) | Hash-only receipt of **100%** of runs, ordered, signed, publicly anchored | Tiny, no PII, the part nobody can do alone: our moat |
| **Trust Page** | Metadata + the files the vendor chooses to share | The thing the bank actually looks at |
| **Evidence Room** (vault, selective) | Only runs the vendor *selects* (disputes, samples, audit requests) | Small, high-value, fits the free tier |
| **Customer storage** | Full retention of every `.epi` in **the customer's own S3/R2 bucket** | No PII at EPI, no startup risk, unlimited scale at $0 to us |
| **Evidence Pack** | Built **in the reviewer's browser** | $0 CPU, and the reviewer controls it |

Sales line (it's true): **"We hold no customer data. We witness every run.
Your files stay in your bucket. Your reviewer's own browser verifies everything.
If EPI Labs disappeared tomorrow, every record still verifies with open-source tools."**

### Design rule: the server trusts nothing and proves nothing
The server stores **claims** (hashes, manifests) and relays files. All real verification
runs on the reviewer's machine (browser or `epi verify`). A client that lies about a
hash only hurts itself: the reviewer's browser recomputes it and shows red.

---

## 1. $0 stack, real limits, capacity

**Cloudflare free plan only.** Never put Vault/Witness on Render free (it sleeps,
loses its disk on redeploy, and deletes its free DB after 30 days).

| Need | Service | Free limit to design for* |
|---|---|---|
| API | Workers | 100k requests/day; **~10 ms CPU per request** (I/O waits don't count) |
| Metadata | D1 | 5 GB; ~5M row reads/day; **~100k row writes/day** |
| Witness log | Durable Objects (SQLite-backed, free plan) | free-plan request/storage quota (check docs) |
| Files | R2 | **10 GB**; 1M writes/month; 10M reads/month; free egress. **Requires a card on the account (still $0 within limits)** |
| Jobs | Cron Triggers | free |
| Website/UI | Pages (existing) | free |
| Login | GitHub OAuth + **Google OAuth** | free |
| Public anchoring | **Sigstore Rekor** public transparency log + RFC 3161 (FreeTSA) + GitHub mirror repo | free |
| Payments | Paddle (existing) | % per sale only |

\* **Agent: check the current Cloudflare docs before M0 and write the real numbers
into `docs/CLOUD.md`.** Adapt if they differ, and tell the founder.

### 1.1 Capacity math (put this table in `docs/CLOUD.md` and on `/admin/usage`)
| Per event | Worker requests | D1 writes | DO writes | R2 |
|---|---|---|---|---|
| Witness receipt | 1 | 0 | 1 | 0 |
| Evidence Room upload (selected run) | 2 (init + put) | 2 (artifact + audit) | 0 | 1 write, ~0.5 MB |
| Trust page view | 2–5 | 1 (event) | 0 | reads only |

**Free tier supports roughly:** ~50,000 witnessed runs/day across all customers, and
~20,000 files (10 GB) in Evidence Rooms. Witness-first is what makes $0 viable.

**Paid thresholds** (only once revenue exists): Workers Paid $5/month (more CPU and
requests); R2 about $0.015/GB/month beyond 10 GB. Show usage vs. limits on `/admin/usage`
with an alert at 70%.

### 1.2 Hard CPU rules (10 ms)
- **Never** buffer or hash a whole upload in the Worker. Stream the body straight to R2.
- **Never** unzip on the server. The client sends the manifest separately (§6.4).
- Only cheap server crypto: Ed25519 verify on a ≤4 KB manifest, HMAC on a ≤16 KB
  witness body, SHA-256 of small JSON.
- **Never** build zips on the server (CRC-32 over MBs). Packs are built in the browser (§6.6).
- Max file size for Evidence Room uploads: **25 MB**.

---

## 2. Architecture

```
 Vendor (their infra)                        EPI Cloud (Cloudflare, $0)                       Customer's reviewer
 recorder / gateway
   ├─ witness report (hash only, HMAC) ────▶ POST /w/{inbox} ─▶ Durable Object (ordered, hash-chained)
   │                                          cron: daily checkpoint ─▶ sign ─▶ Rekor + RFC3161 + GitHub mirror
   ├─ every .epi ─▶ THEIR S3/R2 bucket (epi-recorder writes it; EPI Cloud never sees it)
   └─ selected .epi ─ epi cloud push ──────▶ /v1/.../artifacts/init + PUT ─▶ R2 (stream) + D1 (claims)
                                                                                         opens trust link
                                              /t/{slug}#k=…  (static page) ─────────────▶ browser:
                                              /v1/trust/... (token in header) ──────────▶  verifies files,
                                                                                            checks witness,
                                                                                            builds evidence pack
```

### 2.1 Repo layout (new)
```
cloud/
  wrangler.toml            # name "epi-cloud"; bindings DB (D1), ROOM (R2), WITNESS (DO); crons
  package.json             # hono, zod, aws4fetch (BYO bucket), vitest, @cloudflare/vitest-pool-workers
  src/index.ts             # router + middleware (auth, CSRF origin check, rate limit, errors, security headers)
  src/routes/              # auth.ts orgs.ts keys.ts agents.ts artifacts.ts witness.ts trust.ts storage.ts billing.ts admin.ts
  src/lib/manifest.ts      # canonical manifest hashing + Ed25519 verify (port from website/js/epi-verify-core.js)
  src/lib/crypto.ts        # sha256 (small inputs), HMAC, Ed25519, tokens
  src/lib/plans.ts         # plan limits (single source of truth)
  src/do/witness.ts        # WitnessInbox Durable Object
  migrations/0001_init.sql
  test/                    # unit + integration (miniflare); fixtures = website/assets/**/*.epi
website/app/               # dashboard UI (static, calls the API)
website/t/                 # trust page (static) + browser pack builder
epi_cli/cloud.py           # epi cloud login|push|status|inbox|storage
epi_core/storage_sink.py   # write every sealed .epi to the customer's own bucket (S3-compatible)
docs/CLOUD.md
.github/workflows/cloud.yml            # test + deploy worker
.github/workflows/witness-mirror.yml   # daily: copy signed checkpoints to the public repo
```
`verify_portal` (Render) stays untouched. Retiring it is out of scope.

---

## 3. Data model (D1) — `migrations/0001_init.sql`

```sql
CREATE TABLE orgs (id TEXT PRIMARY KEY, slug TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
  plan TEXT NOT NULL DEFAULT 'free', created_at TEXT NOT NULL);
CREATE TABLE users (id TEXT PRIMARY KEY, email TEXT, display_name TEXT, created_at TEXT NOT NULL);
CREATE TABLE identities (provider TEXT NOT NULL CHECK (provider IN ('github','google')),
  provider_user_id TEXT NOT NULL, user_id TEXT NOT NULL REFERENCES users(id),
  PRIMARY KEY (provider, provider_user_id));
CREATE TABLE memberships (org_id TEXT NOT NULL, user_id TEXT NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('owner','member','viewer')), PRIMARY KEY (org_id, user_id));
CREATE TABLE invites (id TEXT PRIMARY KEY, org_id TEXT NOT NULL, email TEXT NOT NULL, role TEXT NOT NULL,
  token_hash TEXT UNIQUE NOT NULL, expires_at TEXT NOT NULL, accepted_at TEXT);
CREATE TABLE sessions (id_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL, expires_at TEXT NOT NULL);
CREATE TABLE api_keys (id TEXT PRIMARY KEY, org_id TEXT NOT NULL, prefix TEXT NOT NULL,
  key_hash TEXT UNIQUE NOT NULL, scopes TEXT NOT NULL, created_by TEXT NOT NULL,
  created_at TEXT NOT NULL, last_used_at TEXT, revoked_at TEXT);
CREATE TABLE agents (id TEXT PRIMARY KEY, org_id TEXT NOT NULL, name TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'active', created_at TEXT NOT NULL, UNIQUE (org_id, name));
CREATE TABLE inboxes (id TEXT PRIMARY KEY, org_id TEXT NOT NULL, customer_label TEXT NOT NULL,
  hmac_secret_enc TEXT NOT NULL, created_at TEXT NOT NULL, closed_at TEXT);
CREATE TABLE checkpoints (inbox_id TEXT NOT NULL, day TEXT NOT NULL, count INTEGER NOT NULL,
  head_hash TEXT NOT NULL, signature TEXT NOT NULL, signed_at TEXT NOT NULL,
  rekor_uuid TEXT, rekor_log_index INTEGER, tsa_token_b64 TEXT, PRIMARY KEY (inbox_id, day));
CREATE TABLE artifacts (                      -- Evidence Room (selected runs only)
  id TEXT PRIMARY KEY, org_id TEXT NOT NULL, agent_id TEXT,
  claimed_sha256 TEXT NOT NULL,               -- client-supplied; browsers re-check
  claimed_crc32 INTEGER NOT NULL,             -- client-supplied; used only for browser zip packs
  size_bytes INTEGER NOT NULL, manifest_json TEXT NOT NULL,   -- ≤ 64 KB
  spec_version TEXT, workflow_id TEXT, goal TEXT, steps INTEGER, sealed_at TEXT,
  key_fingerprint TEXT, signature_check TEXT NOT NULL,         -- 'valid'|'invalid'|'unsigned'
  witness_status TEXT NOT NULL,                                -- 'witnessed'|'not_in_witness'|'different_version'|'no_inbox'
  reason TEXT,                                                 -- why selected: dispute|sample|audit_request|other
  object_key TEXT NOT NULL, upload_state TEXT NOT NULL DEFAULT 'pending',  -- pending|stored
  uploaded_at TEXT NOT NULL, retention_until TEXT NOT NULL, legal_hold INTEGER NOT NULL DEFAULT 0,
  deleted_at TEXT, UNIQUE (org_id, claimed_sha256));
CREATE INDEX artifacts_org_time ON artifacts(org_id, uploaded_at DESC);
CREATE TABLE org_keys (id TEXT PRIMARY KEY, org_id TEXT NOT NULL, public_key TEXT NOT NULL,
  fingerprint TEXT NOT NULL, label TEXT, valid_from TEXT NOT NULL, revoked_at TEXT, revoke_reason TEXT,
  UNIQUE (org_id, public_key));
CREATE TABLE share_links (id TEXT PRIMARY KEY, org_id TEXT NOT NULL, token_hash TEXT UNIQUE NOT NULL,
  label TEXT NOT NULL, scope TEXT NOT NULL, created_at TEXT NOT NULL, expires_at TEXT NOT NULL,
  revoked_at TEXT);
CREATE TABLE trust_events (id INTEGER PRIMARY KEY AUTOINCREMENT, share_link_id TEXT NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('opened','verified_file','downloaded_pack','downloaded_witness')),
  detail TEXT, at TEXT NOT NULL);           -- only from human actions (see §6.2)
CREATE TABLE storage_targets (org_id TEXT PRIMARY KEY, kind TEXT NOT NULL CHECK (kind IN ('s3','r2')),
  endpoint TEXT NOT NULL, bucket TEXT NOT NULL, region TEXT, prefix TEXT,
  last_check_at TEXT, last_check_ok INTEGER);  -- NO credentials stored here; see §6.5
CREATE TABLE audit_log (seq INTEGER PRIMARY KEY AUTOINCREMENT, org_id TEXT, actor TEXT NOT NULL,
  action TEXT NOT NULL, detail TEXT NOT NULL, at TEXT NOT NULL, prev_hash TEXT NOT NULL, entry_hash TEXT NOT NULL);
```
Witness entries live in each inbox's Durable Object SQLite, not in D1.

---

## 4. API

Auth: browser = session cookie (HttpOnly, Secure, SameSite=Lax); every state-changing
browser call checks `Origin`. CLI/gateway = `Authorization: Bearer epik_…`.
Trust page = `X-EPI-Share-Token` header (never in the URL query).

| Method & path | Who | What |
|---|---|---|
| `GET /auth/github` · `GET /auth/google` (+ callbacks) | anyone | OAuth login; the same email across providers links to one user only after a confirmed login with both |
| `POST /v1/orgs` · `POST /v1/orgs/{o}/invites` · `POST /v1/invites/{token}/accept` | user / owner | org + teammates (compliance/legal people use Google) |
| `POST/GET/DELETE /v1/orgs/{o}/api-keys` | owner | key shown once |
| `POST/GET/PATCH /v1/orgs/{o}/agents` | member | plan limit on active agents |
| `POST /v1/orgs/{o}/inboxes` · `GET` · `POST /{id}/close` | owner | create witness inbox; URL + secret shown once |
| `POST /w/{inbox}` | vendor recorder/gateway | **witness receive**: same protocol as `epi witness serve` (`X-EPI-Signature: sha256=<hmac>`, schema `epi-witness/v1`, body ≤16 KB) → 202 after the append commits |
| `GET /v1/inboxes/{id}/export.jsonl` | member / share token | byte-compatible with `received.jsonl` from `epi witness serve` |
| `GET /w/{inbox}/checkpoints` · `GET /.well-known/epi-witness-key.json` | public | signed checkpoints (+ Rekor/TSA references) · witness public keys |
| `POST /v1/orgs/{o}/artifacts/init` | API key `push` | body: `{manifest_json, claimed_sha256, claimed_crc32, size_bytes, agent, reason}` → server verifies the manifest signature, checks the witness, returns `{id, put_url}` |
| `PUT /v1/orgs/{o}/artifacts/{id}/content` | API key `push` | **streamed** straight to R2 (`env.ROOM.put(key, request.body)`); requires `Content-Length == size_bytes` |
| `GET /v1/orgs/{o}/artifacts` · `/{id}` · `/{id}/content` | member / share token | list · metadata · file (`Content-Disposition: attachment`) |
| `POST .../{id}/legal-hold` · `DELETE .../{id}` | owner | audit-logged; delete blocked during hold |
| `POST/GET/DELETE /v1/orgs/{o}/keys` (+ `/{id}/revoke`) · `GET /o/{slug}/keys.json` | owner · public | **public keys only** |
| `POST/GET/DELETE /v1/orgs/{o}/share-links` | owner | token shown once |
| `GET /v1/trust/{slug}` | share token header | trust page data |
| `POST /v1/trust/{slug}/events` | share token header | `opened` / `verified_file` / `downloaded_*`, **only from human clicks** |
| `PUT /v1/orgs/{o}/storage-target` · `POST .../storage-target/check` | owner | BYO bucket config (no secrets) + a health check reported by the vendor's recorder |
| `POST /billing/paddle/webhook` | Paddle | signature-verified |
| `GET /admin/usage` | founder (allowlisted ids) | usage vs free limits |

---

## 5. Plans 🔒 prices (founder decides)

| Plan | Agents | Witness inboxes | Evidence Room | Share links | BYO bucket | Price (proposal) |
|---|---|---|---|---|---|---|
| free | 1 | 1 | 50 files / 30 days | 1 | yes | $0 |
| design_partner (first 5) | 10 | 5 | 2,000 files / 7 yrs | 10 | yes | $500–1,000/mo, founding price locked |
| startup | 3 | 2 | 500 files / 1 yr | 3 | yes | ~$500/mo |
| growth | 10 | 10 | 5,000 files / 7 yrs | unlimited | yes | ~$2,000/mo |
| enterprise | custom | custom | custom | custom | yes + private deploy | $30–100k/yr |

Value metric = **agents in production**. Witnessing is unlimited within fair use.
**Verification is never limited or charged.**

---

## 6. Module specs

### 6.1 M0 — Skeleton, auth (GitHub + Google), orgs, invites, API keys
- Scaffold `cloud/`; D1 migration; deploy to `*.workers.dev`, then `cloud.epilabs.org`.
- GitHub and Google OAuth (state param; Google with PKCE). Session id: 32 random bytes; store sha256.
- Invites by link (copy-paste, **no email service needed**); roles owner/member/viewer.
- API keys `epik_…` (sha256 stored, shown once, scopes `push`, `read`).
- Rate limits (DO or D1 counters): login 10/min/IP, witness 600/min/inbox, push 60/min/key.
- Hash-chained `audit_log` helper used by every mutating route.
- **Acceptance:** GitHub *and* Google login → org → invite a second user → API key works;
  **tenant-isolation test suite** (org A can never read B, on every route); CI green.

### 6.2 M1 — Hosted Witness (build this before anything else: it's the moat and holds no PII)
- Inbox per customer relationship ("Acme Bank"). The vendor configures exactly what they
  already use: `--witness-url https://cloud.epilabs.org/w/{id} --witness-secret …`.
  **No product changes needed.**
- `POST /w/{id}`: HMAC check (constant time), schema check, size ≤16 KB → Durable Object
  appends `{seq, received_at, payload_raw, prev_hash, entry_hash}` with
  `entry_hash = sha256(prev_hash ‖ sha256(payload_raw) ‖ received_at)`; return 202 after commit.
- Export `export.jsonl` = raw payload lines in order (same as `received.jsonl`).
- **Daily checkpoint** (cron 00:05 UTC) per inbox with new entries: sign
  `{"inbox","day","count","head_hash"}` with the EPI Cloud witness Ed25519 key (Worker
  secret), then **anchor it three ways, all free**:
  1. **Sigstore Rekor** (public append-only transparency log run by the Linux Foundation):
     submit a `hashedrekord` entry for the checkpoint's sha256 signed by the witness key;
     store `rekor_uuid`/`log_index`. *Agent: confirm Rekor accepts this key type; if not,
     use an ECDSA P-256 key for anchoring only, and document it.*
  2. RFC 3161 timestamp from FreeTSA over the checkpoint.
  3. `.github/workflows/witness-mirror.yml` commits the checkpoints to the public repo
     `epi-witness-checkpoints`.
  Honest claim: *"rewriting the log would require rewriting a public transparency log, a
  public timestamp and public git history, and any reviewer can check all three."* Do not
  call GitHub alone "immutable".
- CLI: `epi witness check --inbox-url URL [--export FILE]` verifies the checkpoint
  signatures with the published key, the Rekor inclusion, and that the export's hash chain
  matches each day's `head_hash`. Reviewers can audit EPI Labs itself.
- **Acceptance (end to end with the real recorder against miniflare):** seal → report →
  export → `epi verify FILE --policy strict --witness-log export.jsonl --offline` gives
  WITNESSED; an unreported re-seal gives NOT IN WITNESS LOG; a different version gives
  DIFFERENT VERSION; editing, deleting or reordering any export line is caught by
  `epi witness check`; a burst of 1,000 reports stays strictly ordered.

### 6.3 M2 — Trust Page (bot-proof, token-safe)
- Link format: `https://epilabs.org/t/{slug}#k={token}`. The token is in the **fragment**,
  so it never reaches servers, corporate proxies or logs. The static page's JS reads it,
  removes it from the address bar (`history.replaceState`), and sends it as
  `X-EPI-Share-Token`.
- The first screen is a **gate**: vendor name + "Open evidence" button. Data loads only
  after the click. **No tracking on page load.** Email security scanners (Proofpoint,
  Mimecast, Defender) open links automatically; they must not create a "viewed" signal.
- Events recorded **only from human actions**: `opened` (gate click), `verified_file`,
  `downloaded_pack`, `downloaded_witness`. Vendor dashboard shows: "Acme Bank opened the
  evidence (Tue), verified 3 files, downloaded the witness log." That's a real sales signal.
- Page content: agents in scope; per agent over 30/90 days: runs **witnessed** (count from
  the inbox), runs in the Evidence Room, any `different_version` / `invalid` in red; key
  history; checkpoint status ("signed today 00:05 UTC · anchored in Rekor #…"); files with
  **"Verify in my browser"** (existing verifier, plus a check that the recomputed SHA-256 ==
  `claimed_sha256`, else red); "Verify yourself":
  `epi verify FILE --policy strict --witness-log received.jsonl --offline`.
- Headers: `noindex`, `Referrer-Policy: no-referrer`, CSP as the site. 🔒 copy approval.
- **Acceptance:** Playwright: a scanner-like headless load without a click creates **no
  event**; click → `opened`; verify a genuine file (amber unless pinned), a tampered file
  (red), a file whose bytes don't match `claimed_sha256` (red); an expired or revoked link
  shows a clear error; the token never appears in any server log line (test the log output).

### 6.4 M3 — Evidence Room (selected runs only)
- `epi cloud push FILE --agent NAME --reason dispute|sample|audit_request|other`. The CLI
  computes sha256 and crc32 locally, extracts `manifest.json` locally (it already can),
  calls `init`, then streams the file to `PUT …/content`.
- Server (`init`): verify the manifest signature (≤4 KB, cheap), compute the key
  fingerprint (same as `epi_core.keys.key_fingerprint()`), check `claimed_sha256` /
  content digest against the org's witness inboxes → `witness_status`, store the claims.
  `PUT`: stream to R2, check `Content-Length`, mark `stored`. **No server hashing or unzip.**
- Auto-select helpers (opt-in): `epi cloud push --sample 1%`, and the gateway option
  `--cloud-push-on review|policy_fail` to push runs flagged by policy or human review.
- Retention cron: delete past `retention_until` unless `legal_hold`; audit-log it.
- **"Export everything"** button: a list of signed download URLs + the witness export,
  so a customer can leave any time. Required for the startup-risk answer.
- **Acceptance:** every `.epi` under `website/assets/**` pushes with `signature_check=valid`;
  a tampered manifest gives `invalid`; a lie about `claimed_sha256` is caught by the trust
  page check; dedupe works; retention test with a fake clock; no Worker request exceeds
  the CPU budget in a load test with 25 MB files (measure with `wrangler dev` / tail).

### 6.5 M4 — Customer-owned storage (BYO bucket) ← answers "what if you shut down?"
- **The recorder writes, not EPI Cloud:** add `epi_core/storage_sink.py` so the vendor's
  own recorder/gateway uploads every sealed `.epi` directly to **their** S3-compatible
  bucket (AWS S3, Cloudflare R2, MinIO, GCS interop). Config via env
  (`EPI_STORAGE_URL=s3://bucket/prefix`, credentials from the standard AWS env/profile).
  Use a minimal SigV4 implementation or `boto3` as an optional extra (`pip install
  epi-recorder[storage]`). **EPI Cloud never holds those credentials.**
- Docs recommend S3 Object Lock (compliance mode) for WORM retention, and give the exact
  bucket policy for write-only access.
- The recorder reports a heartbeat to EPI Cloud (`storage-target/check`: last write ok,
  count, no file data), so the trust page can say "full records retained in customer
  storage (Object Lock: on/off, as reported by vendor)". Label it as vendor-reported.
- **Acceptance:** against MinIO in CI: 100 runs sealed → 100 objects in the bucket, with
  matching sha256; with the network off, uploads queue in a local outbox and flush later
  (reuse the witness outbox pattern); credentials never appear in logs.

### 6.6 M5 — Key Registry (public keys only)
- Register, rotate and revoke **public** keys (`epi cloud keys push` reads only `*.pub`; it
  refuses anything else). Public `GET /o/{slug}/keys.json`. Trust page shows the history.
- Informational only: never a pin (same rule as WP-SEC-4). `epi keys trust --from-cloud
  {slug}` still requires `--fingerprint` to match. Tests prove "registered ≠ pinned".

### 6.7 M6 — Evidence Pack (built in the reviewer's browser)
- On the trust page, "Download evidence pack" builds a zip **client-side** (fflate or the
  site's JSZip): selected files (fetched from R2), `artifacts.csv` with *browser-computed*
  hashes and verify results, `witness/received.jsonl`, `witness/checkpoints.json` + Rekor
  refs, `keys/history.json`, `README.html` (who, what, period, how to verify, scope disclaimer).
- `mapping/eu-ai-act-art12.md` and `mapping/bank-questionnaire.md` are **drafts** generated
  only from facts true for this org. 🔒 Founder (ideally with a compliance advisor) approves
  the templates before release. No "compliant" claims. **AIUC-1 mapping: not until the
  founder has the standard and has read it. Never invent control IDs.**
- **Acceptance:** unzip → `epi verify` each file with `--witness-log witness/received.jsonl`
  → matches `artifacts.csv`; pack works with 200 files in Chrome and Safari.

### 6.8 M7 — Plans & billing
- `plans.ts` limits enforced with clear upgrade messages; downgrade never deletes data.
- Port the Paddle webhook verification from `verify_portal/billing.py` (+ its tests).
  🔒 founder creates the new products; archive (don't delete) the old $199/$799 ones.
- `/admin`: the founder can set `design_partner` manually (invoice by hand at first).

---

## 7. Security requirements
- Secrets only via `wrangler secret put` (OAuth secrets, SESSION_KEY, INBOX_SECRET_KEY,
  WITNESS_SIGNING_KEY, PADDLE_WEBHOOK_SECRET). A CI grep blocks secret-looking strings.
- Tokens and keys stored as sha256; constant-time compares; share tokens only in the
  fragment/header; **a log-redaction test** proves no token, key or secret reaches logs.
- Tenant isolation tests on every route. Upload sniffing (must be an EPI container); files
  are always downloads, never rendered on our origin; the trust page never iframes the
  embedded viewer.
- Hash-chained audit log; weekly D1 backup to R2 (keep 4); restore steps in `docs/CLOUD.md`.
- Privacy page and `/security` updated 🔒: Witness = hashes only; Evidence Room = files the
  vendor selects; BYO bucket = EPI never sees it; host = Cloudflare; retention; deletion.

---

## 8. Build order (sell first, build behind it)

| When | Package | Outcome |
|---|---|---|
| Day 1 | **WP-PRICING-0** 🔒 | Remove the $199/$799 "hosted verification" plans. Add "Design Partner Program: 5 places, founding price" + "EPI Cloud: private beta" |
| Day 1–2 | **WP-DEMO-TRUST** 🔒 | **Static demo trust page** `epilabs.org/t/acme-demo` built from JSON + 3 real `.epi` files in `website/assets/`: gate button, witness counts, key history, "Verify in my browser", fake but clearly labelled **DEMO** data. **The founder starts outreach the same day with this link** |
| Week 1 | M0 | Login (GitHub + Google), orgs, invites, API keys |
| Week 2 | **M1 Witness** | The moat, live: vendors point `--witness-url` at EPI Cloud |
| Week 3 | **M2 Trust Page** (real data) | Design partners send real links to their customers |
| Week 4 | M3 Evidence Room | Selected runs, push, export-everything |
| Week 5 | M4 BYO bucket | "We hold no customer data; your files stay in your bucket" |
| Week 6 | M5 Keys · M6 Evidence Pack 🔒 mapping | Bank-review pack |
| Week 7 | M7 Billing | Self-serve upgrades |

One PR per package; tests first; Playwright on the trust page; preview deploy; the founder
approves 🔒.

## 9. Distribution and standards (non-code, but decides who wins)
- **Integrations already exist** (LangChain, LangGraph, OpenAI Agents, LiteLLM,
  OpenTelemetry, MCP). Each gets a 5-line "send witness receipts to EPI Cloud" snippet in
  its docs page plus a copy-paste example repo. That's where agent builders are.
- **Publish the specs**: `.epi` and `epi-witness/v1` as versioned open specs in `docs/spec/`
  (CC-BY), aligned with IETF SCITT terms. Being *the* evidence format is the long-term moat.
- **Channel, not competition:** "Export to Drata / Vanta / SafeBase" is later work; first
  get one AIUC-1 auditor or compliance consultant to accept EPI evidence in a real audit.
- **Every reviewer is a lead:** the trust page footer: "Reviewing an AI vendor? Ask them
  for an EPI trust link." (Free for reviewers, always.)

## 10. Founder setup (free)
1. Cloudflare: add a card (needed for R2; $0 within limits), create D1 `epi-cloud`, R2
   `epi-cloud-room`; later add the custom domain `cloud.epilabs.org` to the worker.
2. OAuth apps: GitHub (Developer settings → OAuth Apps) and Google (Cloud Console →
   Credentials → OAuth client, web), callbacks `https://cloud.epilabs.org/auth/{github|google}/callback`.
3. A Cloudflare API token (Workers/D1/R2 edit), saved as the GitHub secret `CLOUDFLARE_API_TOKEN`.
4. Create the empty public repo `epi-witness-checkpoints`.
5. Approve 🔒 PRs; set prices; create the Paddle products after M7.

## 11. Never do
- Charge for, meter or limit verification.
- Hold customer private keys, or customer bucket credentials.
- Buffer, hash or unzip whole uploads on the server; build zips on the server.
- Record "viewed" on page load; put share tokens in URL queries or logs.
- Claim "compliant", "certified", "guaranteed", "court-admissible" or "immutable".
- Treat cloud key registration as an identity pin.
- Make the open-source product depend on the cloud: everything still works offline.
- Present demo data as real: every demo screen is labelled **DEMO**.

## 12. Changes from v1 (and why)
| v1 | v2 | Why |
|---|---|---|
| Vault stores every run | **Witness 100% (hash-only); Evidence Room = selected runs; full retention in the customer's bucket** | Volume (free 10 GB fills in ~a week), privacy (no DPA needed), shutdown risk |
| D1 blob fallback | Removed: R2 only (card required, $0) | D1 size/write limits |
| Server hashes and unzips uploads | Client sends manifest + sha256 + crc32; server streams to R2 | 10 ms CPU limit |
| Server builds evidence-pack zip | Built in the reviewer's browser | CPU (CRC-32) and trust model |
| `?k=` token, view tracked on load | `#k=` fragment + header; events only on human clicks | Email scanners create fake views; tokens leak to proxy logs |
| GitHub login only | GitHub + Google + invite links | Compliance/legal staff don't use GitHub |
| GitHub mirror called immutable | Rekor + RFC 3161 + GitHub mirror, honest wording | Real third-party anchoring, still $0 |
| Vault first, witness 4th | **Witness first**, plus a static demo on day 1–2 | The moat ships first; selling starts before code |
