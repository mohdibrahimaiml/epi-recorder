# Coding-agent brief: make epilabs.org and epi-recorder enterprise-ready

You are the coding agent for **EPI Labs** (product: `epi-recorder`, site:
`epilabs.org`). This file is your complete operating manual: who you work for,
what to build, in which order, how to build it, how to prove it works, and when
to stop and ask. The exact technical specification of every work package (code
snippets, file paths, line numbers, acceptance tests) is in
**`plans/WEBSITE-ENTERPRISE-PLAN.md`**. Read both files fully before you change
anything. If they ever disagree, the plan wins for technical detail and this
brief wins for process.

---

## Part A. Context you need

### A1. What EPI is (one paragraph, do not change this meaning)
EPI seals each AI-agent run into a signed `.epi` file (Ed25519 signature,
SHA-256 hash chain, RFC 3161 timestamp). The customer who receives the file
verifies it **themselves, offline**, without trusting the vendor or EPI Labs:
`epi verify FILE --policy strict --witness-log received.jsonl --offline`.
A valid seal proves the file wasn't changed after sealing and, if the key is
pinned, who sealed it. It does **not** prove every action was captured or that
the decision was right.

### A2. Who the site is for (decided by the founder)
- **Buyer:** an AI-agent company selling into a regulated or high-stakes
  customer (financial services first; then insurance, healthcare, legal), whose
  deal stalls on "prove what your agent did".
- **Verifier:** that customer's risk/compliance/audit team. Use a **bank** as the
  lead example on the site.
- **Second audience: investors.** The founder is raising a pre-seed round
  through an agency. Investors will read the site. They must find: a focused
  target customer, a clear price ladder, honest claims they can check, and a
  bigger vision on its own page (`/vision`).

### A3. The founder
- Name: Mohd Ibrahim. Email: `mohdibrahim@epilabs.org`. Not a lawyer, not a
  security engineer: explain things to him in plain language, short sentences.
- No company is incorporated yet (see plan §7 D3). Never invent company facts.

### A4. State of the repo
- Latest release: **4.6.0** (PyPI and GitHub release, tag `v4.6.0`).
- `main` is the base branch. The plan lives on branch
  `claude/gifted-brown-ejhjag`; merge it into `main` first or branch from it.
- Website source of truth: **`website/`**. Mirrors generated from it by
  `python scripts/sync_website.py`: `site/`, `epi-official/`,
  `verify_portal/static/`. Never hand-edit a mirror.
- Cloudflare Pages Functions: `functions/` (`_proxy.js` proxies `/api/*` to Render).
- Backends on Render (`render.yaml`): `epi-verify` (`verify_portal`, URL
  `https://epi-verify-portal.onrender.com`, health `/health`) and `epi-mcp`
  (`epi_mcp`, `epi-mcp-http`).
- **Two website deploy paths exist:** `.github/workflows/deploy-website.yml`
  deploys `website/` to **GitHub Pages** on every push to `main` touching
  `website/**`, and Cloudflare Pages is configured to serve `site/`
  (`wrangler.toml`, `npm run build`). Step 0 below finds out which one actually
  serves `epilabs.org`.
- **Merging to `main` publishes the website.** Treat every merge as going live.

---

## Part B. Rules (non-negotiable)

1. **Never invent facts.** No customer names, logos, user counts, download
   numbers typed by hand, certifications, SLAs, uptime figures, company
   registration, addresses, LEI, legal claims, or regulatory claims that are not
   true today and checkable in this repo. Missing fact → write `TODO(founder): …`
   in the PR description (never on the live page) and ask.
2. **Never touch secrets.** Don't print, commit, or ask for tokens or passwords
   in chat. PyPI publishing moves to Trusted Publishing (WP-SUPPLY-1); no token
   is ever needed.
3. **Never publish a release yourself.** No `twine upload`, no tag push, no
   GitHub release. You prepare; the founder publishes.
4. **Never delete files you didn't create** unless a work package names them,
   and only after grepping that nothing references them. Never delete the
   founder's untracked local files (`.agents/`, `brag-output/`, `node_modules/`,
   `scripts/dataforge_epi_score.py`, `seal_aisent_*.py`,
   `tests/test_dataforge_epi_score.py`, anything not in git).
5. **Never skip, disable, or weaken a test** to get green. Never use
   `--no-verify`. Never force-push to `main`.
6. **Wording rules** (all pages, all docs you touch):
   - Banned words: "guarantee", "court-admissible", "tamper-proof", "compliant",
     "certified", "insurable", "forever", "trustless", "military-grade",
     "zero-knowledge" (unless literally true), "phone-home".
   - Use: "tamper-evident", "supports evidence for", "designed to verify without
     EPI Labs", "admissibility is decided by the court".
   - One verify command for banks/auditors/customers, everywhere:
     `epi verify FILE --policy strict --witness-log received.jsonl --offline`.
   - Use the approved text blocks in plan §6 verbatim.
7. **Real output only.** A terminal block shown as output must be pasted from a
   real run of the current release, not typed.
8. **One work package = one branch = one PR.** Don't mix packages. Don't widen
   a PR with "while I was here" changes; note them as follow-ups instead.
9. **🔒 gated packages** (WP-COPY-1, WP-COPY-2, WP-POS-1, WP-TRUST-1, WP-PAGES-1
   below): open the PR as a **draft**, post preview links + screenshots, and
   **do not merge** until the founder writes "approved" on that PR or in chat.
10. **Ungated packages** (all WP-SEC-*, WP-FIX-*, WP-A11Y-1, WP-SUPPLY-1 code,
    WP-OPS-1 code): you may merge yourself (squash merge) once **all** of Part E's
    checks pass and CI is green on the PR head. If the founder tells you he wants
    to merge everything himself, stop merging and just mark PRs ready.

---

## Part C. Approach (how to work)

**Order of priority: 1) stop real harm (security) → 2) stop embarrassment
(broken pages) → 3) stop overclaiming (honesty) → 4) tell one clear story
(positioning) → 5) earn trust (security page, signed releases) → 6) polish
(accessibility, speed, monitoring).** Never start a later phase while an earlier
phase has an open High item, except where Part D says items run in parallel.

Per work package, always the same loop:
1. `git fetch origin && git checkout -b wp/<id>-<short-name> origin/main`
2. Read the package in the plan. Open every file it names and confirm the
   problem still exists at the line given (line numbers are from commit
   `5930247`; they drift). If it's already fixed, say so and skip.
3. **Write the failing test first** (the plan names the test for each package).
   Run it, see it fail for the right reason.
4. Make the smallest change that fixes it. Match the surrounding code style.
5. `python scripts/sync_website.py` if you touched `website/`. Commit mirrors in
   the same PR.
6. Run Part E checks. Fix everything they find.
7. Re-read your own diff as a hostile reviewer: what would break? Any banned
   word? Any invented fact? Any mirror out of sync? Any new inline script that
   the CSP will block?
8. Push, open the PR with the template in Part F.
9. Wait for CI. If red: read the log, reproduce locally, fix, push. Repeat until
   green. "Flaky" is not a diagnosis.
10. Merge (ungated) or wait for approval (gated). After merge, check the live
    site (or the deploy log) for that change.

Commit messages: imperative, one line summary + a short body explaining why.

---

## Part D. The work, in order

### Step 0. Discovery (no code changes; report to founder, ~1 hour)
Run and report the results in one short message:
1. Environment:
   ```bash
   python -m pip install --upgrade pip setuptools wheel build twine
   python scripts/ci-install-deps.py
   pip install -e . && pip install pytest playwright axe-playwright-python
   npm install
   bash scripts/release-gate.sh python      # must be green before you start
   ```
   (Chromium: use a preinstalled one if present; otherwise `npx playwright install chromium`.)
2. **Which host serves epilabs.org:** `curl -sI https://epilabs.org/` → `server:
   cloudflare` + `cf-ray` means Cloudflare; `server: GitHub.com` means GitHub
   Pages (possibly behind Cloudflare DNS). Also `curl -sI
   https://epilabs.org/api/ping` (Functions only exist on Cloudflare Pages).
   **Why it matters:** `_headers` (WP-SEC-3) and `functions/` (WP-SEC-2) only work
   on Cloudflare Pages.
3. **Recommendation to give the founder:** serve the site from **one** host:
   Cloudflare Pages (supports `_headers`, Functions, preview deploys per branch).
   If GitHub Pages is live too, propose disabling `deploy-website.yml` (keep the
   file, switch it to `workflow_dispatch` only) **after** the founder confirms in
   the Cloudflare dashboard that the Pages project builds from `main` with build
   command `npm run build` and output `site`. Do not change DNS yourself.
4. Find the real Cloudflare Pages project name (for the CORS preview regex in
   WP-SEC-2) and whether branch preview deploys are on. If you can't see the
   dashboard, ask the founder for a screenshot of Pages → project → Settings.
5. Baseline numbers for the PR records: Lighthouse (desktop) on `/`, home page
   transfer size, axe violations on `/`, `/verify/`, `/plans`, console errors per page.

### Phase 1 — Security (ungated, do first, in this order)
| # | Package | One-line goal | Plan § |
|---|---|---|---|
| 1 | **WP-SEC-1** | No file-derived text ever reaches `innerHTML` unescaped (XSS) | §1 |
| 2 | **WP-SEC-2** | CORS only for exact epilabs.org origins + this project's previews | §1 |
| 3 | **WP-SEC-3** | `_headers` with HSTS, nosniff, frame-deny, CSP (Report-Only first, then enforce) | §1 |
| 4 | **WP-SEC-4** | Product: remote registry can never make a key trusted; strict never fetches it | §1 |
| 5 | **WP-SEC-5** | Shared-case page never shows green unless really verified | §1 |
| 6 | **WP-SEC-6** | `epi share` files really expire (7 days default, 30 max) + upload rate limit | §1 |

How-to notes on top of the plan:
- **SEC-1:** search all of `website/` for `innerHTML`, `outerHTML`,
  `insertAdjacentHTML`, `document.write`. Classify each as static (leave, add
  `// static-html`) or dynamic (wrap with `esc()` or switch to `textContent`).
  Build the two malicious test files in a test fixture, not by hand.
- **SEC-3:** do it in two PRs if needed: (a) move inline scripts and `onclick=`
  out + ship `Content-Security-Policy-Report-Only`; (b) after a clean Playwright
  run on every page, switch to enforcing. Paddle checkout must still open on
  `/plans` (test it in the Paddle sandbox if a sandbox token is configured;
  otherwise confirm the overlay script loads without CSP errors).
- **SEC-4 and SEC-6 are Python product changes.** Do them on separate branches,
  both with tests, both adding entries under `## [4.6.1]` in `CHANGELOG.md`.
  The version bump to `4.6.1` (in `pyproject.toml` and anywhere
  `tests/test_docs_release_consistency.py` requires it) goes in **one** final
  small PR "Release 4.6.1 prep" after both merge. Full suite must be green
  (`pytest -q -o addopts=""`; two environment-only failures are listed in plan §8).
  After deploy, the Render services pick up SEC-6 on the next deploy: tell the
  founder "Render → epi-verify → Manual Deploy → Deploy latest commit".
- **SEC-5:** if implementing the in-browser hash-chain check is large, ship the
  honest amber state first (`hashChain: null`, "not checked in browser") and
  open a follow-up issue for the full check.

### Phase 2 — Broken things (ungated)
| # | Package | Goal | Plan § |
|---|---|---|---|
| 7 | **WP-FIX-1** | Header/menu on all pages, JS syntax error gone, no dead links, link-checker test | §2 |
| 8 | **WP-FIX-2** | Version from one source (`pyproject.toml`), `SECURITY.md` + `security.txt` fixed | §2 |
| 9 | **WP-FIX-3** | No dev files deployed, small logo, self-hosted fonts, SW kill-switch, Paddle deferred | §2 |

How-to notes:
- **FIX-2 contact address:** use `mohdibrahim@epilabs.org` until the founder
  says "aliases work"; then switch to `security@epilabs.org`. Keep the address
  in **one** place that the build fills in, so the switch is one line. Ask the
  founder to enable GitHub private vulnerability reporting (repo Settings →
  Security); you can't toggle it yourself.
- **FIX-3:** exclusions must apply to **whichever** deploy path is live (Step 0).
  If GitHub Pages is still live, add the same exclusions to its upload step.
  Fonts: download the exact woff2 files currently used (check the CSS `@import`
  URLs), keep their licence files next to them.

### Phase 3 — Honesty (🔒 gated: draft PRs, founder approves)
| # | Package | Goal | Plan § |
|---|---|---|---|
| 10 | **WP-COPY-1** | Every overstated or false claim replaced (table in plan), banned-word test | §3 |
| 11 | **WP-COPY-2** | One pricing/refund/trial policy everywhere; price ladder (D1); mailto contact (D5); legal pages | §3, §7 D1/D3/D4/D5/D6 |

How-to notes:
- **COPY-1 hero terminal:** run `epi demo` (or seal a sample with the current
  release), then `epi verify` with the strict command, and paste the real output.
  Re-seal `website/assets/sample.epi` with the current release.
- **COPY-2 price ladder** (plan §7 D1): `/plans` shows six steps — Open source
  $0 · Hosted $199/mo (Beta) · Team $799/mo (Beta) · Evidence Sprint $1,500 ·
  Design-partner pilot $5,000/90 days · Enterprise from $25,000/yr. Feature lists
  must match `verify_portal/tier_gating.py` `PLAN_FEATURES` and
  `website/js/paddle-config.js` exactly. Don't change Paddle price IDs. First
  line of every tier: "Offline verification: unlimited, always free". Metered
  unit renamed to "hosted verification API calls". Home page names match (no
  more "Pro").
- **Privacy page retention table:** use plan §7 D6 exactly; publish the `epi
  share` row only after WP-SEC-6 is deployed. For "Server logs", check the actual
  retention in Render and Cloudflare docs/dashboards and write that figure, or
  ask the founder.
- **Terms:** "EPI Labs is currently operated by its founder, Mohd Ibrahim;
  incorporation in progress." Governing law / city: `TODO(founder)` in the PR,
  not on the page. Add the "hosted service is beta, no SLA unless signed" clause.

### Phase 4 — Positioning and new pages (🔒 gated)
| # | Package | Goal | Plan § |
|---|---|---|---|
| 12 | **WP-POS-1** | Home page tells one story: vendor seals → their customer verifies; "What the bank runs" section; insurer/government sections removed | §4 |
| 13 | **WP-PAGES-1** (new, below) | `/vision`, `/about`, design-partner section | §4, §7 D2/D7 |

**WP-PAGES-1 spec:**
- **`/vision` — "Where this goes".** Short intro: "Today EPI gives AI vendors
  proof their customers can check. Here is where that leads." Sections, each
  with a badge **Roadmap** or **Exploring** (never "Available"):
  1. Agentic payments and commerce — evidence for disputes about what an agent
     was told and did. (Exploring)
  2. AI-liability insurance — evidence for underwriting and claims. (Exploring)
  3. Agent-to-agent work — each party keeps a verifiable record of the other's
     actions. (Exploring)
  4. Auditors and regulators — a standard file format they can check with open
     tools. (Roadmap: link `docs/AUDITORS-GUIDE.md`)
  5. Org keys, hosted receipts, control plane. (Roadmap; reuse wording from the
     existing enterprise page's Roadmap column)
  Footer link "Vision". Add to `sitemap.xml`.
- **`/about` — founder and company.** Founder name, one paragraph "why I'm
  building EPI" (**FOUNDER writes it; leave a clearly marked placeholder in the
  draft PR and ask him**), photo (founder supplies), LinkedIn and GitHub links,
  the company-status sentence from plan §7 D3, contact `hello@` (or the founder
  address until aliases work). Traction shown **only as live badges**: PyPI
  downloads (pepy.tech badge), GitHub stars (shields.io badge), latest release
  (shields.io). No typed numbers.
- **Design-partner section** on home (after the pricing teaser) and `/plans`:
  heading "Design-partner program — 5 places"; body from plan §7 D7 (free
  90-day pilot normally $5,000; founder instruments one workflow; Team plan
  during pilot; 50% off year 1 after; in return feedback calls every two weeks,
  logo + case study they approve, one reference call, signed letter of intent);
  button `mailto:` with subject "Design partner" and a 3-line body template
  (company, what your agent does, who your regulated customer is). No "places
  left" counter.
- Logo strip of customers: **do not build** until a partner gives written
  permission.

### Phase 5 — Trust and supply chain
| # | Package | Goal | Plan § | Gate |
|---|---|---|---|---|
| 14 | **WP-TRUST-1** | `/security` hub + downloadable bank reviewer kit | §5 | 🔒 |
| 15 | **WP-SUPPLY-1** | PyPI Trusted Publishing workflow, SBOM, build provenance, Scorecard, Dependabot, CodeQL, `docs/RELEASING.md` | §5 | founder does the PyPI setting |

How-to notes:
- **TRUST-1 data-flow diagram:** inline SVG, no external library, readable in
  light and dark theme. The reviewer kit zip is built by a script
  (`scripts/build_reviewer_kit.py`) with a test that the zip contains the listed
  files and that the genuine sample verifies and the tampered one fails.
  Certifications section says "None yet" plainly.
- **SUPPLY-1:** write the workflow so it runs only on `release: published`, uses
  environment `pypi`, `permissions: id-token: write`, builds from a clean
  checkout, runs `twine check`, and uploads only `dist/*` for that version.
  Then give the founder the exact clicks (plan §5 step 2). **4.6.1 is released
  through this workflow**: after SUPPLY-1 merges and the founder has added the
  trusted publisher, tell him: "GitHub → Releases → Draft new release → tag
  `v4.6.1` on `main` → paste the CHANGELOG 4.6.1 section → Publish". Then check
  PyPI shows 4.6.1 with attestations, and the SBOM is attached.
- CodeQL / Scorecard findings rated High: fix in follow-up PRs (one per finding
  type), ungated.

### Phase 6 — Polish and operations (ungated)
| # | Package | Goal |
|---|---|---|
| 16 | **WP-A11Y-1** | Accessibility + SEO |
| 17 | **WP-OPS-1** | Real uptime monitoring + honest status page |

**WP-A11Y-1 spec** (the plan only names it; this is the full list):
1. axe-core: zero serious/critical violations on every page (Playwright +
   `axe-playwright-python`, or `@axe-core/playwright`). Add it as a test that
   runs against the local build.
2. Skip-to-content link; one `<main>` per page; `<nav>` and `<footer>` landmarks;
   `lang="en"` on `<html>`; headings in order (one `h1`).
3. Burger menu: a real `<button>` with `aria-expanded`, `aria-controls`, works
   with keyboard (Enter/Space/Escape), focus moves into the menu and back.
4. Visible focus style on all interactive elements (no `outline:none` without a
   replacement).
5. Colour contrast ≥ 4.5:1 for body text in **both** themes.
6. All images have meaningful `alt` (decorative ones `alt=""`); videos have
   captions or a transcript link.
7. `prefers-reduced-motion: reduce` disables particles, scroll reveals and
   animated counters. Content that "reveals on scroll" must be visible without
   JavaScript (default visible, JS adds the animation class).
8. SEO: unique `<title>` and meta description per page; `<link rel=canonical>`;
   Open Graph + Twitter tags using the new 1200×630 `og-image.png`; `sitemap.xml`
   lists every public page including `/security`, `/vision`, `/about`; `robots.txt`
   points to the sitemap; a real `404.html`; JSON-LD `Organization` with name
   "EPI Labs", URL, logo, `sameAs` GitHub — **no** legal name, address or founding
   facts until incorporation.
9. **Acceptance:** Lighthouse desktop on `/`: Performance ≥ 90, Accessibility ≥ 95,
   SEO ≥ 95, Best Practices ≥ 95. Record before/after in the PR.

**WP-OPS-1 spec:**
1. **FOUNDER (10 minutes, free):** create an UptimeRobot (or Better Stack) account
   with `mohdibrahim@epilabs.org`; add HTTP monitors every 5 minutes for
   `https://epilabs.org/`, `https://epi-verify-portal.onrender.com/health`, and
   the epi-mcp service `/health` (or `/` if no health route; find the public URL
   in the Render dashboard); turn on its free public status page; send you the
   status page URL. Five-minute checks also keep the free Render services from
   sleeping.
2. You: `website/status.html` stops measuring "uptime" from the visitor's browser.
   It shows the hosted services list, the "Beta · no SLA" statement, and a link
   (or embed, if CSP allows) to the public status page. No uptime numbers typed
   by hand.
3. Add `/api/ping` / `/health` routes to `epi-mcp` if missing (with a test).
4. Recommendation to give the founder (his decision): before the first paying
   Hosted/Team customer, move `epi-verify` from Render free to a paid instance
   (no cold starts). Don't change it yourself.
5. After 30 days with no incident on the status page, open a PR removing the
   "Beta · no SLA" badges (gated: founder approves).

---

## Part E. Checks before every PR (paste the output into the PR)

```bash
# Website
python scripts/sync_website.py
pytest -q -o addopts="" tests/test_website_sync.py tests/test_docs_release_consistency.py \
  tests/test_share_site_assets.py tests/test_website_links.py tests/test_website_xss.py
npm run build
npx wrangler pages dev site      # local server with Functions + _headers + _redirects
# Playwright against the local server:
#   every page: 0 console errors, 0 CSP violations, 0 failed requests (404/5xx)
#   screenshots at 1366x768 and 390x844 (light + dark) attached to the PR
#   axe: 0 serious/critical on /, /verify/, /plans, /security, /vision, /about
grep -rniE "guarantee|court-admissible|tamper-proof|insurable|forever|trustless|phone-home|offline from first run|courtroom" website/ \
  && echo "BANNED WORD FOUND" || echo "wording ok"

# Product (any change under epi_*/ or verify_portal/)
pytest -q -o addopts=""
bash scripts/release-gate.sh python
python -m build && twine check dist/*
```
Tests that don't exist yet (`test_website_links.py`, `test_website_xss.py`) are
created by WP-FIX-1 and WP-SEC-1; until then skip them.

If the CI on GitHub fails but local passes: read the CI log, find the
difference (OS, Python version, missing env var), reproduce it, fix it.

---

## Part F. PR template (use for every PR)

```
## WP-<ID>: <title>

**Problem** (1–3 sentences, plain language)
**What changed** (bullets; files)
**How I verified** (commands + pasted output; screenshots for visual changes)
**Before / after** (numbers where the plan asks: Lighthouse, size, axe)
**Not done / follow-ups** (anything out of scope you noticed)
**TODO(founder)** (facts or clicks only he can provide; empty if none)
**Gate:** ungated – will merge when CI is green  |  🔒 needs founder approval
```

---

## Part G. When to stop and ask the founder

Stop and ask (one short, plain message, with your recommendation first) when:
- a fact is missing (company details, governing law, founder bio/photo, log
  retention you can't verify, Cloudflare project name you can't see);
- a dashboard click is needed (Cloudflare, Render, PyPI, GitHub settings,
  UptimeRobot, email aliases);
- a 🔒 PR is ready for review;
- a fix would change product behaviour beyond what the plan describes;
- tests show a real bug outside the current package (open an issue, report it,
  continue with your package);
- anything would cost money.

Don't ask about things the plan or this brief already decide. Founder decisions
D1–D7 are final (plan §7).

## Part H. Founder's click-list (collect and send him these, at the moment each is needed)
1. Step 0: confirm which host serves the site; screenshot of Cloudflare Pages settings.
2. Email aliases (plan §7 D4): Cloudflare → epilabs.org → Email → Email Routing →
   `hello@`, `security@`, `privacy@`, `billing@` → `mohdibrahim@epilabs.org`; send
   a test to each; reply "aliases work".
3. GitHub → repo Settings → Security → enable Private vulnerability reporting.
4. After SEC-6 merges: Render → epi-verify → Manual Deploy → latest commit.
5. PyPI trusted publisher (plan §5 WP-SUPPLY-1 step 2), then delete all PyPI tokens.
6. Publish GitHub release `v4.6.1`.
7. UptimeRobot account + monitors + status page URL (WP-OPS-1).
8. `/about` text and photo; governing law/city for Terms.
9. Approve each 🔒 PR.

## Part I. Definition of done (whole project)
- Plan §9 checklist all ticked, plus:
- `/vision`, `/about`, `/security`, design-partner section live and approved.
- 4.6.1 on PyPI with attestations, released via Trusted Publishing, SBOM attached.
- Status page backed by real external monitoring.
- One deploy path for the website; it's documented in `docs/RELEASING.md`
  (or a short `docs/WEBSITE-DEPLOY.md`).
- Final report to the founder: a table of every package (PR link, merged/open,
  what changed in one line), the before/after numbers, and the open TODO(founder) list.

## Part J. How to report progress
After each merged or approval-ready PR, send the founder **three lines**:
what changed (plain words), the PR link, and what (if anything) he needs to do.
No long logs in chat; they go in the PR.
