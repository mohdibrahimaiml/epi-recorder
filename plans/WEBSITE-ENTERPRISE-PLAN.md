# epilabs.org → enterprise-grade: implementation plan

Status: ready to execute · Baseline: `main` @ `5930247` (v4.6.0 released) · Owner: coding agent, founder approves gated items.

This plan comes from three audits of `website/` (claims-vs-code, technical/UX in a real
browser with axe-core, and enterprise buyer research). Every High item below was
re-checked in the code. Work top to bottom. **Do not skip the gates.**

---

## 0. Read this first: rules for the agent

1. **Source of truth.** Edit only `website/` (the site), `functions/` (Cloudflare
   Pages Functions), `scripts/cf-pages-build.mjs`, and, for WP-SEC-4, `epi_core/`
   and `epi_cli/`. Never hand-edit the mirrors `site/`, `epi-official/` or
   `verify_portal/static/`. Regenerate them with `python scripts/sync_website.py`
   after every website change and commit the result in the same PR.
2. **Tests must stay green.** Run
   `pytest -q tests/test_website_sync.py tests/test_docs_release_consistency.py tests/test_share_site_assets.py`
   after every website PR, and the full suite (`pytest -q -o addopts=""`) for the
   product change in WP-SEC-4.
3. **One PR per work package** (WP), with a branch named after it. In the PR body,
   say what changed and how you verified it, including screenshots for visual
   changes. Don't mix packages.
4. **Never invent facts.** No customer names, logos, numbers, certifications,
   SLAs, legal entity details or regulatory claims that aren't true today. If a
   step needs a fact you don't have (company registration, address, LEI),
   **stop and ask the founder** (see §7 "Decisions needed").
5. **Wording rules (all pages):**
   - Never write "guarantee", "court-admissible", "tamper-proof", "compliant",
     "certified", "insurable", "forever" or "trustless".
   - Use "tamper-evident", "supports evidence for", "designed to verify without
     EPI Labs", and "admissibility is decided by the court".
   - Use **one recommended verify command** everywhere it is aimed at a bank,
     auditor or customer:
     `epi verify FILE --policy strict --witness-log received.jsonl --offline`
   - Use **one network sentence** everywhere network behaviour is described (§6.1).
6. **Real output only.** Any terminal block labelled as output must be pasted from
   running `epi-recorder==4.6.0`, not typed by hand.
7. **Gated items** (marked 🔒) need the founder's written OK before merging: copy and
   positioning changes, pricing and plans, legal pages.

---

## Execution order

| Order | Work package | Size | Gate |
|---|---|---|---|
| 1 | WP-SEC-1 XSS fix in verifier pages | S | – |
| 2 | WP-SEC-2 CORS allowlist in `functions/_proxy.js` | XS | – |
| 3 | WP-SEC-3 security headers (`_headers`, CSP) | M | – |
| 4 | WP-SEC-4 **product 4.6.1**: remote registry never grants trust | M | – |
| 5 | WP-SEC-5 shared-case page: honest verdict badge | S | – |
| 6 | WP-FIX-1 broken pages: header/menu on 3 pages, JS syntax error, dead links | S | – |
| 7 | WP-FIX-2 version single-source, `SECURITY.md`, `security.txt` | S | – |
| 8 | WP-FIX-3 remove public cruft, logo weight, fonts, Paddle defer | M | – |
| 9 | WP-COPY-1 honesty pass (network claims, fake output, overclaims) | M | 🔒 |
| 10 | WP-COPY-2 pricing/trial/refund/privacy/terms consistency | M | 🔒 + facts |
| 11 | WP-POS-1 one story: vendor → bank (home, how-it-works, enterprise, trust) | L | 🔒 |
| 12 | WP-TRUST-1 `/security` trust hub + reviewer kit | M | 🔒 + facts |
| 13 | WP-SUPPLY-1 signed releases (PyPI Trusted Publishing, SBOM, Scorecard) | M | founder does PyPI setting |
| 14 | WP-A11Y-1 accessibility + SEO polish | M | – |
| 15 | WP-OPS-1 real uptime monitoring + status page | S | founder creates monitor account |

Packages 1–8 are safe, mechanical and urgent: do them first, in this order. Packages 9–12 change what
the company says; draft them, then wait for approval.

---

## 1. Security (do first)

### WP-SEC-1: XSS in the "verify a file" flow (HIGH, confirmed)
**Problem:** a crafted `.epi` runs script in the visitor's browser, on the same
origin as the login token in `localStorage`.
`website/js/home-verify.js:500` builds `'Invalid mimetype: '+mtNorm` from file
content, and `showResult()` writes it with `dr.innerHTML=msg` (line ~614). Other
paths do the same with `f.name` and `e.message` (lines ~463, 489, 491, 508, 510),
and `set()` at line 58 does it with `text`.

**Do:**
1. Add a single helper `function esc(s){return String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}`.
2. Every place that inserts **file-derived or error-derived** text into HTML must
   use `esc()` or `textContent`. Grep for `innerHTML` in `website/js/home-verify.js`,
   `website/js/epi-verify-core.js`, `website/cases/index.html`,
   `website/verify/index.html` and `website/assets/viewer.html`, and review each one.
   Static HTML literals may stay.
3. Prefer `textContent` and `createElement` for new code.

**Acceptance:**
- Add `tests/test_website_xss.py`. It scans those files, and every `innerHTML=`
  assignment whose right-hand side concatenates a variable must go through `esc(`
  (or carry an allow-list comment `// static-html`).
- Manual check: build a zip whose `mimetype` entry is
  `<img src=x onerror="window.__pwn=1">` and a file named `"><img src=x onerror=alert(1)>.epi`.
  Load both in `/verify/` and on the home page (Playwright, see §8). `window.__pwn`
  stays undefined and no alert fires.

### WP-SEC-2: CORS allowlist (HIGH, confirmed)
**Problem:** `functions/_proxy.js:54` uses
`origin.endsWith("epilabs.org") || origin.includes("pages.dev")`, with
credentials. That also matches `evilepilabs.org` and any `*.pages.dev`.

**Do:** replace it with an exact allowlist:
```js
const ALLOWED = new Set(["https://epilabs.org", "https://www.epilabs.org"]);
const PREVIEW = /^https:\/\/[a-z0-9-]+\.epi-recorder\.pages\.dev$/; // this project's previews only
function allowedOrigin(o){ return o && (ALLOWED.has(o) || PREVIEW.test(o)) ? o : null; }
```
- Emit `Access-Control-Allow-Origin` and `Access-Control-Allow-Credentials` only when
  `allowedOrigin()` returns a value. Do the same in the preflight handler.
- Add `Vary: Origin`.
- Check the actual Pages project name in the Cloudflare dashboard or `wrangler.toml`
  (the preview URLs seen so far are `*.epi-recorder.pages.dev`).

**Acceptance:** a small Node test, or a documented `curl` run against
`wrangler pages dev`, showing that origin `https://evilepilabs.org` gets no ACAO
header and `https://epilabs.org` gets it.

### WP-SEC-3: security headers (HIGH)
**Do:** create `website/_headers`:
```
/*
  Strict-Transport-Security: max-age=31536000; includeSubDomains
  X-Content-Type-Options: nosniff
  Referrer-Policy: strict-origin-when-cross-origin
  Permissions-Policy: camera=(), microphone=(), geolocation=(), payment=(self "https://*.paddle.com")
  X-Frame-Options: DENY
  Content-Security-Policy: default-src 'self'; script-src 'self' https://cdn.paddle.com; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; font-src 'self'; connect-src 'self' https://*.paddle.com https://epi-verify-portal.onrender.com; frame-src https://*.paddle.com; frame-ancestors 'none'; base-uri 'self'; form-action 'self'
```
- **Before enabling the CSP,** move every inline `<script>` into files under
  `website/js/`, and replace `onclick=` attributes with `addEventListener`.
  `account.html` has five of them. The theme pre-paint script can stay inline only
  if you add its `'sha256-…'` hash to `script-src`. Generate the hash; don't guess it.
- Fonts must be self-hosted first (WP-FIX-3), or add `https://fonts.bunny.net` to
  `style-src` and `font-src` until then.
- **Roll out in two steps:** first ship it as
  `Content-Security-Policy-Report-Only`, check the browser console on every page
  (Playwright), then switch it to enforcing.
- Make sure `scripts/cf-pages-build.mjs` copies `_headers` into the output.

**Acceptance:** Playwright loads all pages with zero CSP violations in the console.
`curl -I` on the preview deploy shows the headers.

### WP-SEC-4: product 4.6.1, the remote registry must never grant trust (HIGH, confirmed)
**Problem:** `epi_core/trust.py:498-516`. Without `--offline`, `epi verify` fetches
`https://epilabs.org/.well-known/epi-trust-registry.json` (unsigned JSON) and
returns `True` (KNOWN identity) for any key listed there. KNOWN satisfies
`--policy strict`. Anyone who controls that static file can make every verifier
in the world accept their key as a trusted identity.

**Do (smallest correct change):**
1. In `TrustRegistry.verify_key_trust`, a key found in the remote registry
   returns a new non-trusting status. Use `(False, name, "LISTED: in EPI Labs public registry (informational; not a pin)")`,
   or add an identity status `LISTED` that `apply_policy` treats like `UNKNOWN`:
   WARN under standard, FAIL under strict.
2. Remote `revoked_keys` may still downgrade a key (revocation is safe to honour).
3. In verify output, show the line `Registry: listed as "<name>" by epilabs.org (not a pin)`.
4. Make `epi verify` skip the remote fetch whenever `--policy strict` is used, so
   strict is always local-only and needs no network.
5. Update `docs/VERIFICATION_CONTRACT.md`, `docs/AUDITORS-GUIDE.md`,
   `website/trust.html` (disclosure) and `CHANGELOG.md` (`## [4.6.1]`), and bump the
   version in `pyproject.toml`.

**Tests** (in `tests/test_release_ux.py` or a new file):
- Monkeypatch the registry fetch to list the file's key. Standard policy gives
  WARN, never PASS. Strict gives FAIL (exit 1). A local pin of the same key gives PASS.
- Under `--policy strict`, no HTTP request is made: patch `requests.get` to raise.
- A remote revocation still turns a pinned key into REVOKED.

**Acceptance:** the full suite is green, the 4.6.1 wheel is built, and
`twine check` passes. The founder publishes it the same way as 4.6.0 (a clean
worktree build, see `plans/RELEASE-4.6.0.md`; or WP-SUPPLY-1 once it exists).

### WP-SEC-5: shared-case page must not show a false green (HIGH)
**Problem:** `website/cases/index.html:282-283` shows "Verified case" whenever the
signature result is not `false`, including `undefined`, which means not verified.
`website/js/epi-verify-core.js:398` returns `hashChain: true` without checking
anything. Line 381 also loads `/js/nav.js`, which returns 404.

**Do:**
1. Show green only if `signature === true` **and** the chain was actually
   recomputed. Otherwise show amber: "Not fully verified in the browser. Run
   `epi verify FILE --policy strict --witness-log received.jsonl --offline`."
2. Implement the chain check: recompute each step's `prev_hash` the way the CLI
   does (`epi_cli/verify.py` `_verify_step_chain`, with JCS canonicalisation). If
   that's too large for this PR, set `hashChain: null` with the label "not checked
   in browser" instead of `true`.
3. Even when everything is valid, an unpinned signer shows "Seal valid · signer not
   pinned", never a plain "Verified".

**Acceptance:** Playwright checks with a valid file, a tampered file and a file
with a stripped signature give green-with-caveat, red and amber respectively.

---

## 2. Broken things and hygiene (mechanical)

### WP-FIX-1: broken pages
1. **Header and menu on `/status`, `/refund`, `/cases/`.**
   - These pages load only `css/meridian.css` but use the `site.css` nav markup.
     Add `<link rel="stylesheet" href="/css/site.css?v=16">`, or port them to the
     `site.css` template (preferred).
   - Their burger menu does nothing: `cases/index.html:381` loads a missing
     `/js/nav.js`. Use the same burger script as the other pages.
   - Remove the duplicate `instrument-nav.js` include in `status.html` (lines 151 and 156).
2. **JS syntax error on 7 pages** (how-it-works, trust, use-cases, enterprise,
   integrations, terms, privacy). The theme pre-paint script contains Python
   f-string escapes, `}}catch(e){{}}`. Replace it with the working one from
   `assets/viewer.html`: `(function(){try{…}catch(e){}})();`
3. **Dead documentation links (404).** These files moved to `docs/archive/`:
   - `enterprise.html` lines ~69, 109, 111: ENTERPRISE-15-MINUTES, ENTERPRISE-CAPABILITY, ENTERPRISE-TRUST-BUNDLE
   - `how-it-works.html` lines ~84, 85, 87: COMPLETE-PRODUCT-GUIDE, POLICY-AND-FAULT-ANALYZER, PILOT
   - `use-cases.html` line ~66: PILOT

   Point each to a **current** doc (`docs/AUDITORS-GUIDE.md`,
   `docs/IDENTITY-ONBOARDING.md`, `docs/WITNESS.md`, `docs/POLICY.md`,
   `docs/SELF-HOSTED-RUNBOOK.md`). Don't link to archive pages from marketing pages.
4. `portal.html` sends users to `/verify/?mode=server`, which doesn't exist. Send
   them to `/verify/`.
5. `welcome/index.html` says "Subscription confirmed" even after a one-time sprint
   purchase. Make the text match what was bought, or say "Payment received".

**Acceptance:** add `tests/test_website_links.py`. It parses every `href` and `src`
in `website/**/*.html` and checks that each internal target exists (honouring
`_redirects` and pretty URLs) and that each GitHub `blob/` link points at a path
that exists in the repo. It must pass. A Playwright run on all pages shows zero
console errors.

### WP-FIX-2: version and security contact
1. **One version source.**
   - Add `website/js/version.js` (`window.EPI_VERSION="4.6.0"`) and render the
     version into elements with a `data-epi-version` attribute.
   - Or have `scripts/sync_website.py` / `cf-pages-build.mjs` replace a
     `{{EPI_VERSION}}` token from `pyproject.toml` at build time. **Preferred:** it
     also works without JS.
   - Replace all 12 files that say `v4.5.0`.
   - Add a test asserting that the site version equals the `pyproject.toml` version.
2. **`SECURITY.md`:**
   - The supported-versions table lists 2.x. Make it `4.6.x ✅ / < 4.6 ❌`.
   - Use one contact address, identical to `security.txt`. **Ask the founder which:**
     `security@epilabs.org` needs a working mailbox.
   - Use a realistic response time: "acknowledge within 5 business days".
   - Remove "zero-knowledge" and "same as Signal/SSH".
   - Add a safe-harbour paragraph, and offer GitHub private vulnerability reporting
     (enable it in the repo settings: Security → Private vulnerability reporting).
3. **`website/.well-known/security.txt`:**
   - Use the same Contact as SECURITY.md.
   - Add `Preferred-Languages: en`.
   - Keep `Expires` under a year ahead and add a calendar reminder.
   - Fix the stale `functions/well-known` comment in `_redirects`.

### WP-FIX-3: weight, cruft and performance
1. **Stop shipping dev files.** In `scripts/cf-pages-build.mjs`, exclude
   `**/_*.py`, `**/*.py`, `assets/demo/_*`, `assets/demo/verify_out.txt`,
   `assets/demo/_verify_js_extract.txt`, `assets/demo/frames/`, `README.md`,
   `_nav.html`, and the unused `js/terminal.js`, `js/terminal-demo.js`,
   `js/particles.js`, `js/app.js`, `epi-viewer/app.js`, `sw.js` and `manifest.json`
   (see step 4). Better still, delete the unused files from `website/` entirely.
   Keep only demo `.epi` files that a page links to.
2. **Unreferenced large images:** `cryptographic_visual.png` 713 KB,
   `trust_network.png` 620 KB, `verification_icon.png` 435 KB, `verifier-logo.png`,
   `epi-logo.png`, and the duplicate `epi-walkthrough.mp4`. Delete them after
   grepping to confirm they're unused.
3. **Logo.** `/assets/logo.png` is 293 KB and shows about 40 px tall on every page.
   Use `logo.svg` (it exists) or a PNG of about 280×112 under 10 KB. Make a separate
   1200×630 `og-image.png` for social cards.
4. **Service worker.** It isn't registered anywhere, but returning visitors may
   still have an old one. Ship a kill-switch `sw.js`, delete `manifest.json`, and
   remove the old purple-brand references:
   ```js
   self.addEventListener('install',()=>self.skipWaiting());
   self.addEventListener('activate',e=>e.waitUntil((async()=>{for(const k of await caches.keys())await caches.delete(k);await self.registration.unregister();for(const c of await self.clients.matchAll())c.navigate(c.url);})()));
   ```
5. **Fonts.**
   - Self-host the woff2 files in `website/fonts/` with `font-display:swap`.
   - Remove the `@import` of fonts.bunny.net (site.css) and Google Fonts
     (meridian.css). Google Fonts on EU visitors is a GDPR issue.
6. **Paddle.**
   - Add `defer` to `paddle.js` and `paddle-config.js` on `/plans`.
   - Initialise Paddle only once: it's currently called inline at plans.html ~512
     **and** in `sprint-checkout.js:52`. Pick one.
   - Don't load Paddle on the home page unless it has a checkout button.
7. **Functions routing.** `_routes.json` should be
   `{"version":1,"include":["/api/*","/scitt/*"],"exclude":[]}`, so static
   requests don't go through Functions. Delete the pass-through `_middleware.js`
   if nothing needs it.
8. **`cases/`** uses jszip from cdnjs. Use the local `/js/jszip.min.js`.

**Acceptance:**
- The deployed output contains no `.py` or `.txt` files other than `robots.txt` and
  `security.txt`.
- Home page transfer size drops by at least 250 KB.
- Lighthouse performance on `/` is at least 90 (desktop) on the preview deploy.
  Record the before and after numbers in the PR.

---

## 3. 🔒 Honesty pass (draft → founder approves)

### WP-COPY-1: remove false and overstated claims
Replace each item with the approved wording in §6. The line numbers are from `5930247`.

| Where | Current | Replace with |
|---|---|---|
| `index.html` ~80 | "✓ Offline from first run" | "✓ Verify offline (`--offline`)" |
| `index.html` ~189 | "No vendor key escrow, no phone-home" | §6.1 network sentence |
| `index.html` ~169, `how-it-works.html` ~54 | "Optional RFC 3161 token" | "RFC 3161 timestamp by default (hash only; `EPI_NOTARIZE=0` to turn off)" |
| `index.html` ~129 | "0 servers required to verify" | "0 servers needed: `epi verify --offline`" |
| `index.html` ~88-112 hero terminal, labelled "Real output" | 4.5-era mock | **Real** 4.6.0 output of `epi verify` on a freshly sealed demo file (re-seal `assets/sample.epi` with 4.6.0 first) |
| `index.html` ~175-179, ~584-589 | strict shows WARN/LOCAL; "CHAIN 142/142" | Real strict output: unpinned → `✘ FAIL — SEAL INTACT, REQUIREMENT NOT MET`, exit 1; pinned and witnessed → `✔ SEAL · IDENTITY PINNED`, `Witness: WITNESSED` |
| `index.html` ~131 | "1 byte breaks the seal… That is the entire trust model" | "Any change to a sealed member fails verification. Seal, identity and policy are checked separately." |
| `index.html` ~165 | "each file carries a manifest… what wasn't" | "Files sealed with 4.x carry a capture manifest stating what was and wasn't captured." |
| `index.html` ~300 | "Cryptographic continuity from the run to the courtroom" | "A tamper-evident record you can hand to the other side. Admissibility is decided by the court." |
| `index.html` title/meta/JSON-LD/footer ~6,7,22,489,511 | "makes AI agents insurable" | "Tamper-evident evidence for AI agent decisions" (until a carrier partner exists) |
| `index.html` ~210 "Three guarantees"; ~413 "Verifiable in 5 years… forever" | | "Three checks"; "Designed to verify without EPI Labs, using MIT-licensed open tools. Format compatibility: `docs/VERIFICATION_CONTRACT.md`." |
| `privacy.html` ~58 | "The CLI collects no telemetry" | "The CLI has **opt-in** telemetry, off by default (`docs/TELEMETRY-PRIVACY.md`). It creates a random install ID on first run." |
| `privacy.html` ~62 | "Analytics… (Plausible)" | Remove (no analytics script exists), or add Plausible for real |
| `plans.html` ~111 | gateway "manifest-declared" | "hash-chained on both the SDK and gateway paths" |
| `plans.html` ~129 | "3 slots / mo" | delete |
| `refund.html` ~62 | "Standard enterprise agreements include a 30-day termination clause…" | "Enterprise terms are agreed per contract." |
| `account.html` ~206-207 | `export EPI_API_KEY` + `epi verify` "uses hosted volume" | A real HTTP example against the portal API (see `verify_portal/`). **Verify the endpoint and header name in the code before writing it.** |
| Demo pages `assets/demo/demo-*.html` | mocked runs presented as real; "execution appears compliant"; "CFPB Qualified Mortgage statutory cap of 43.0%" | Re-seal with 4.6.0. Add a top banner: **"SIMULATED: model responses are mocked for demonstration."** Rename the rule to "Example DTI threshold (illustrative)". Verdict wording: "No policy rule fired". |

Also everywhere:
- Use the §6.2 command wherever a bank, auditor or customer is told how to verify.
- Remove every other variant: plain `--policy strict`, or no `--witness-log`.

**Acceptance:**
- `grep -rniE "phone-home|offline from first run|courtroom|insurable|guarantee|forever|tamper-proof|court-admissible|3 slots" website/` returns nothing.
- Add a test that fails if any of those strings come back.

### WP-COPY-2: pricing, trial, refund and legal consistency (🔒 + facts from founder)
**Decide first (founder, see §7 D1):** pause the self-serve Hosted ($199) and Team
($799) tiers, or keep them labelled **"Beta · no SLA"**. They currently run on
free-tier Render with cold starts and no monitoring (`status.html` says so).

Then make one policy and use it on every page (`plans`, `account`, `refund`, `terms`, home):
- **Trial:** "No free trial." Delete "7-day free trial" (`account.html` ~176) and
  "14-day Enterprise pilot is free" (`refund.html` ~77), unless the founder decides otherwise.
- **Refund and cancellation:** "Cancel anytime in the Paddle customer portal; refunds within
  14 days of purchase via Paddle (merchant of record)." Add an explicit line for the
  **$1,500 sprint**.
- **Enterprise starting price:** one number on every page. The home page says
  "From $1,500" (that's the sprint) and plans says "From $5K". Use "Pilots from $5K;
  Evidence Sprint $1,500".
- **One name per tier.** The home page says "Pro"; plans says "Hosted".
- **What the paid tiers deliver:** an HTTP verify API quota, `epi share` links and
  remote SCITT. State plainly that **you don't need a paid plan to verify files.**
- **Footer.** Every page, `/plans` especially, links Terms · Privacy · Refund ·
  Status · Security. Paddle requires the legal links to be reachable.
- **`terms.html`:** legal entity name, registered address, governing law and courts,
  limitation of liability, billing/renewal/cancellation, acceptable use, and the
  status of the hosted service (beta, no SLA unless signed). **Use the founder's
  real entity details (§7 D3). If there's no company yet, say "operated by
  <founder name>, <city, country>" and get these terms reviewed by a lawyer before
  taking enterprise payments.**
- **`privacy.html`:** list the processors and what each receives: Paddle (billing),
  Cloudflare (hosting/CDN), Render (verify and MCP backend), GitHub (sign-in), the
  RFC 3161 timestamp services (receive only a SHA-256 hash), and the font host if
  any remains. Give retention periods: `epi share` uploads (say how long), MCP
  artifacts (24 h), account data. Disclose the localStorage auth token.
- **Contact and waitlist forms post nowhere** (`js/contact.js:9`
  `EPI_CONTACT_ENDPOINT=""`). Either wire them to a real endpoint (a Pages
  Function that emails via a provider the founder chooses) or replace them with a
  plain `mailto:` link. Remove "reply within one business day" unless the founder
  commits to it.

---

## 4. 🔒 Positioning: one story (WP-POS-1)

**The buyer:** an AI-agent startup selling into banks and fintechs, whose deal
stalls on "prove what your agent did". **The verifier:** that bank's risk,
compliance or audit team. The site currently tells three stories (insurers,
enterprise audit, developer tool), and "witness" doesn't appear on it once.

### Home page structure (keep the current hero line; it's right)
1. **Hero:** "Your agent's deal is stuck on 'prove it.' Hand them a file." Subline:
   "EPI seals each agent run into a signed `.epi` file the bank verifies itself,
   offline, without trusting you or us." CTAs: `pip install epi-recorder` ·
   "See what the bank runs ↓".
2. **The problem** (keep, tighten): vendor logs are self-reported and editable.
3. **What the vendor does (3 steps, real code):**
   - `record()` or the gateway seals each run.
   - `witness_url` reports a hash of every seal to the bank as it happens.
   - `epi keys did --domain` publishes the vendor's identity.
4. **NEW: "What the bank runs" (3 steps):**
   1. `epi witness serve --out received.jsonl` (the bank's own record of every
      seal, hashes only).
   2. Pin the vendor key with `epi keys trust --from-did did:web:vendor.com`, or
      from their `did.json`, then confirm the fingerprint by phone.
   3. `epi verify FILE --policy strict --witness-log received.jsonl --offline`.

   Then show the real outcomes table: genuine → PASS; altered → FILE ALTERED;
   other key → NOT A KEY YOU TRUST; re-run not reported → FAIL; different version →
   NOT THE VERSION REPORTED TO YOU.
5. **Worked example:** "A disputed refund decision, end to end." Link to a page or
   doc built from `docs/DEMO-DISPUTE-CASE.md` (plan WP-DEMO).
6. **What it does NOT prove:** that every action was captured, that the decision
   was right, or legal admissibility. Link KNOWN_LIMITATIONS.
7. **Open source and trust:** the MIT verifier, `/security`, and the threat model.
8. **Pricing teaser:** free to use and verify, sprint, pilot.

**Remove from home:** the insurer/underwriting section, the government/AI-safety
audiences, and particles and other decorative animation that hides content
without JS (see WP-A11Y-1).

### Other pages
- **`how-it-works`:** add the bank-side flow and the witness; keep the technical depth.
- **`enterprise`:** retitle it **"For banks verifying an AI vendor"** + "For vendors
  selling to banks". Fix the dead links. Keep the honest Shipped / Services /
  Roadmap split (it's good). Add `epi witness serve` and key pinning.
- **`trust`:** explain seal / identity / policy in plain language, each with its
  real verify line. Disclose the remote registry behaviour (after WP-SEC-4: "listed,
  informational, never a pin"), the timestamp services, and the "what it doesn't
  prove" box.
- **`use-cases`:** lead with "Vendor → bank disputes" (refund, loan decision, AML
  alert closure). Mark every demo as SIMULATED.

**Acceptance:** the founder approves the copy in a preview deploy. Ask a 3-second
test question of someone who doesn't know EPI: "Who is this for?" The answer
should be "AI companies selling to banks".

---

## 5. 🔒 Trust hub and supply chain

### WP-TRUST-1: `/security` page (new) + bank reviewer kit
One URL a vendor can paste into a bank questionnaire. Sections:
1. **Where your data goes (the biggest procurement win). Write it as a table:**

   | Mode | What EPI Labs receives | Subprocessor? |
   |---|---|---|
   | Library/CLI, self-hosted gateway | **Nothing.** Sealing sends a SHA-256 hash to two public RFC 3161 timestamp services (FreeTSA, DigiCert); off with `EPI_NOTARIZE=0` or your own TSA via `EPI_TSA_URLS`. Witness reports go to the **bank's** server, not to EPI. | No |
   | `epi verify --offline` | Nothing (no network) | No |
   | Hosted verify / `epi share` / MCP connector | The uploaded file, kept for N hours/days | Yes (see list) |

   Include a simple data-flow diagram (SVG, no external libraries).
2. **Threat model:** publish `docs/THREAT_MODEL.md` content or link it, plus the
   "what a .epi does NOT prove" box and `KNOWN_LIMITATIONS.md`.
3. **Vulnerability disclosure:** `security.txt`, SECURITY.md, and GitHub private reporting.
4. **Subprocessors:** Cloudflare, Render, Paddle, GitHub (sign-in), and the
   timestamp services (hash only). State "none when self-hosted".
5. **Company facts:** legal name, country, registration number, contact, and LEI
   status (§7 D3). DORA requires an LEI for non-EU ICT providers in a bank's register.
6. **Certifications:** "None yet. Roadmap: CSA STAR Level 1 self-assessment (free)
   [date]; SOC 2 Type I for the hosted service once it has paying users." Say "none
   yet" plainly; don't leave it out.
7. **Release integrity:** link to the signed releases and SBOM (after WP-SUPPLY-1).
8. **Download: "Bank reviewer's kit"** (`/security/reviewer-kit.zip`, built by a
   script in `scripts/`):
   - a genuine sample `.epi` sealed by 4.6.0, plus a tampered copy;
   - a sample `received.jsonl`;
   - the one-page verify instructions (§6.2 command, pinning, and what each verdict means);
   - the threat model (PDF or MD);
   - the data-flow statement;
   - a one-page "How to list EPI in your vendor-risk / DORA register answer".

   The founder fills in the company facts.

Add `/security` to the main nav or the footer, and to `sitemap.xml`.

### WP-SUPPLY-1: signed releases (also removes the PyPI-token problem)
1. Add `.github/workflows/publish-pypi.yml`:
   - Trigger: `on: release: types: [published]`.
   - Build in a clean checkout, run `twine check`, and upload the 4.6.x files only.
   - Use `pypa/gh-action-pypi-publish@release/v1` with
     `permissions: id-token: write`, inside a GitHub environment `pypi`.
   - No token: this uses **PyPI Trusted Publishing**, and PEP 740 attestations are
     on by default.
2. **Founder, once:**
   - pypi.org → epi-recorder → Settings → Publishing → Add GitHub publisher:
     owner `mohdibrahimaiml`, repo `epi-recorder`, workflow `publish-pypi.yml`,
     environment `pypi`.
   - Then delete all PyPI API tokens.
3. Generate a CycloneDX SBOM (`cyclonedx-py`) and attach it to the GitHub release.
4. Add `actions/attest-build-provenance` for the wheel, sdist and `.exe`.
5. Add the OpenSSF Scorecard action (`ossf/scorecard-action`), Dependabot
   (`.github/dependabot.yml` for pip + github-actions) and CodeQL (python, javascript).
   Fix anything High it reports.
6. Document the release process in `docs/RELEASING.md`:
   draft GitHub release → publish → the workflow uploads to PyPI → the installer
   workflow attaches the `.exe`.

**Acceptance:** cut `4.6.1` (WP-SEC-4) through this workflow. PyPI shows
"Attestations ✓" on the files, and the release has the SBOM attached.

---

## 6. Approved wording blocks (use verbatim)

### 6.1 Network sentence
> Verifying never needs EPI Labs: `epi verify --offline` makes no network calls.
> When sealing, EPI sends only a SHA-256 hash to two public RFC 3161 timestamp
> services (switch off with `EPI_NOTARIZE=0`, or use your own with `EPI_TSA_URLS`).
> If you configure a witness, a hash-only report also goes to **your customer's**
> witness server.

### 6.2 The bank's command
```
epi verify FILE --policy strict --witness-log received.jsonl --offline
```
"Rely on the exit code only with `--policy strict`; WARN exits 0."

### 6.3 Scope disclaimer (keep near every verify example)
> A valid seal proves the file has not changed since it was sealed, and who sealed
> it if you pinned their key. It does not prove every action was captured, or that
> the decision was correct.

### 6.4 Legal disclaimer (footer of compliance-related pages)
> EPI produces evidence files. It is not a compliance certification or legal advice.
> Whether evidence meets a regulatory or legal standard is for your auditor, regulator
> or court to decide.

### 6.5 Regulatory facts (only if regulation is mentioned at all; no fines or fear copy)
- EU AI Act, Art. 12 (automatic logging) and Art. 19 (providers keep logs ≥ 6
  months). High-risk obligations apply from **2 Dec 2027** (Annex III) / **2 Aug
  2028** (Annex I) after the Digital Omnibus.
- Do **not** cite SR 11-7 (rescinded Apr 2026; SR 26-2 excludes generative/agentic
  AI), CFPB Circular 2022-03 (withdrawn May 2025), or €35M/7% fines (prohibited
  practices only).

---

## 7. Decisions needed from the founder (ask, don't guess)

| # | Decision | Needed for | Recommendation |
|---|---|---|---|
| D1 | Self-serve Hosted $199 / Team $799: **pause** or keep as **"Beta · no SLA"**? | WP-COPY-2 | Pause; lead with the $1,500 sprint and design-partner pilots |
| D2 | Remove the insurer/underwriting and government sections from the home page? | WP-POS-1 | Yes, until there's a customer in those segments |
| D3 | Company facts: legal entity name, country, registration no., registered address, LEI (yes / applying / no) | Terms, `/security` | Fill in real data; apply for an LEI (~€50–100/yr) before bank conversations |
| D4 | Security contact address (one, monitored) | WP-FIX-2 | `security@epilabs.org`, forwarded to the founder |
| D5 | Contact form: real endpoint (which email provider?) or `mailto:` | WP-COPY-2 | `mailto:` now; a form later |
| D6 | Retention period for `epi share` uploads / hosted verify | Privacy, `/security` | State the real value from `verify_portal` config |
| D7 | Design-partner offer: number of slots, what's free, what you ask in return | POS/TRUST | 3 slots: free pilot plus a bank-reviewer session, in exchange for feedback and a reference |

---

## 8. How to verify each PR (the agent runs this)

```bash
# 1. sync mirrors + site tests
python scripts/sync_website.py
pytest -q -o addopts="" tests/test_website_sync.py tests/test_docs_release_consistency.py tests/test_share_site_assets.py tests/test_website_links.py tests/test_website_xss.py

# 2. local serve that mimics Cloudflare Pages (pretty URLs + _redirects)
npm run build            # scripts/cf-pages-build.mjs → output dir
npx wrangler pages dev site   # or the build output dir; serves Functions + _headers too

# 3. browser checks (Playwright; Chromium is preinstalled in CI images)
#    - every page: zero console errors, zero CSP violations, no 404 requests
#    - 1366x768 and 390x844 screenshots attached to the PR
#    - axe-core: zero "serious/critical" violations on /, /verify/, /plans, /security
```
For the product change (WP-SEC-4), run the full suite: `pytest -q -o addopts=""`.
Two failures are known to be environment-only and are acceptable:
`test_flag_unwritable_doesnt_crash` (fails when run as root) and
`test_analytics_engine_module` (pandas missing).

---

## 9. Done means

- [ ] No High or Medium item from §1–2 is left open; the XSS, CORS and header checks are verified on the preview deploy
- [ ] 4.6.1 released through the signed workflow, with remote registry = informational only
- [ ] The grep in WP-COPY-1 returns nothing; real CLI output only; one verify command sitewide
- [ ] One pricing/trial/refund policy on every page; legal links in every footer; real terms and privacy
- [ ] Home page tells the vendor → bank story; "What the bank runs" section live
- [ ] `/security` live, with the data-flow table, threat model, subprocessors, company facts, "certifications: none yet", and the reviewer kit
- [ ] Lighthouse at least 90 performance, at least 95 accessibility on `/`; no axe serious/critical violations
- [ ] Every claim on the site can be checked against the code or a doc in the repo
