# Zenjin v2 → epi-recorder migration

Status: plan only. Nothing in `C:\Users\dell\epi-recorder` has been modified.
Source of this plan: `website/` tree, `verify_portal/main.py` routes, `site/_redirects`,
`functions/_proxy.js`, `wrangler.toml`, `render.yaml` (read 2026-10-24).

## 1. Decision

The zenjin build becomes the new `website/` in the epi-recorder repo, on a branch,
and ships through the existing deploy pipeline:

```
branch site/zenjin-v2
  website/  (canonical)
    └─ python scripts/sync_website.py
         ├─ site/                    → Cloudflare Pages (epilabs.org)
         └─ verify_portal/static/    → FastAPI (verify/api.epilabs.org)
```

`site/` is generated. Never edit it by hand.

Production stays on `main` until the branch is reviewed and merged. Pushing a
branch produces a Pages **preview** (`*.epilabs.pages.dev`), not a production deploy;
Render only redeploys `main`.

## 2. Architecture (unchanged by this migration)

| Piece | Where | Role |
|---|---|---|
| Marketing site | Cloudflare Pages, project `epilabs`, output `site/` | static pages, `/assets` |
| `/api/*`, `/scitt/*`, `/.well-known/*` | Pages Functions (`functions/`) | proxy to `epi-verify-portal.onrender.com` |
| Verify portal | Render (`verify_portal/`) | `/api/verify`, `/api/contact`, billing, shares, telemetry, explicit page routes |
| EPI Cloud | Worker `epi-cloud` (`cloud/`) | auth, orgs, keys, artifacts, witness, shares, plans |
| Checkout | Paddle v2, client-side (`js/paddle-config.js`) | plans page |

The frontend already calls its own origin (`/api/...`); no backend change is needed.

## 3. Route matrix

Legend: **REDESIGN** = replaced by zenjin page · **KEEP** = copy production file unchanged
· **REDIRECT** = `_redirects` rule must survive · **API** = FastAPI route, file must exist.

| Route | Production file | Zenjin file | Notes | Action |
|---|---|---|---|---|
| `/` | index.html | index.html | | REDESIGN |
| `/how-it-works` | how-it-works.html | how-it-works.html | API route | REDESIGN |
| `/plans` | plans.html | plans.html | Paddle checkout | REDESIGN + port Paddle |
| `/trust` | trust.html | trust.html | | REDESIGN |
| `/verify/` | verify/index.html | verify/index.html | SW offline verifier | REDESIGN |
| `/pricing` | pricing.html | — | API route serves it; Pages 301 → `/plans` | KEEP + REDIRECT |
| `/account` | account.html | — | API route | KEEP |
| `/login` | login.html | — | nav rewrites to cloud | KEEP |
| `/terms` | terms.html | — | API route, legal | KEEP |
| `/privacy` | privacy.html | — | API route, legal | KEEP |
| `/refund` | refund.html | — | API route, legal | KEEP |
| `/portal` | portal.html | — | API route | KEEP |
| `/use-cases` | use-cases.html | — | linked from old pages | KEEP |
| `/enterprise` | enterprise.html | — | `/enterprise/` → `/enterprise` 301 | KEEP + REDIRECT |
| `/integrations` | integrations.html | — | | KEEP |
| `/status` | status.html | — | | KEEP |
| `/welcome` | welcome.html, welcome/index.html | — | | KEEP |
| `/cases/` | cases/index.html | — | | KEEP |
| `/t/*` | t/app/index.html, t/app.js, t/acme-demo/* | — | trust pages; rewrite rules | KEEP + REDIRECT |
| `/viewer` | viewer.html, viewer/app.js | — | 301 → `/verify/` | KEEP + REDIRECT |
| `/epi-viewer` | epi-viewer/app.js | — | API routes | KEEP |
| `/verify` | verify.html (redirect stub) | — | `/verify` → `/verify/` 301 | KEEP + REDIRECT |
| `/assets/viewer.html` | assets/viewer.html | — | | KEEP |
| `/agt`, `/aiuc1` | (fallback index) | — | API `_static_page(..., fallback_index=True)` | no file needed |
| `/auth/success` | — | — | API falls back to `/account` | no file needed |

## 4. Files to carry into `website/`

**Plumbing (must exist or production breaks):**

- `_headers` — HSTS, nosniff, frame deny, CSP (Report-Only, sha256 hashes)
- `_redirects` — `/pricing`, `/viewer`, `/verify`, `/enterprise/`, `/t/*`
- `_routes.json` — `{"version":1,"include":["/*"],"exclude":[]}`
- `functions/` — `_proxy.js`, `api/[[path]].js`, `scitt/`, `.well-known/`, `v1/`, `_middleware.js`
- `sw.js` — bump `CACHE_NAME` (`epi-verifier-v9` → `v10`)
- `manifest.json`, `robots.txt`, `sitemap.xml`, `CNAME`, `LICENSE`, `README.md`
- `.well-known/epi-trust-registry.json`, `.well-known/security.txt` — byte-identical to zenjin copies
- `favicon.ico`, `_nav.html`

**Legacy pages/assets (keep both CSS systems during transition):**

- `css/site.css`, `css/meridian.css`, `css/aos.css`, `css/contact.css`
- `js/theme.js`, `js/aos.js`, `js/wow.js`, `js/particles.js`, `js/terminal.js`,
  `js/terminal-demo.js`, `js/app.js`, `js/instrument-nav.js`, `js/contact.js`,
  `js/paddle-config.js`, `js/sprint-checkout.js`
- `assets/demo/*`, `assets/epi-*.png`, `assets/icons.svg`, `assets/logo.*`

**Zenjin additions:**

- `css/zenjin-epi.css` (imports Bunny fonts — already allowed by CSP `style-src`/`font-src`)
- `js/zenjin-epi.js`
- `assets/epi-walkthrough.mp4` (5.3 MB), `epi-walkthrough-poster.jpg`,
  `epi-walkthrough-og.jpg`, `epi-launch.vtt`
- `assets/logo-white.png`, `logo-trimmed.png`, `logo-black.png`, `epilabs-org-avatar-white-1024.png`

**Verified identical between production and zenjin (no drift):**

`js/jszip.min.js`, `js/epi-manifest-preimage.js`, `js/epi-verify-core.js`,
`js/home-verify.js`, `js/auth-ui.js`, `js/contact.js`, `assets/sample.epi`,
`.well-known/epi-trust-registry.json`.

## 5. Integration fixes (before merge)

1. **Contact** — `js/contact.js` must POST to `/api/contact` with
   `{name, email, company, tier, use_case}`.
   Zenjin currently sends `{name, email, company, role, interest, message}`;
   map `interest → tier`, `role + "\n" + message → use_case`. The backend ignores
   unknown fields, so today the message is silently lost.
2. **Waitlist** — do **not** post to `/api/telemetry/pilot-signups` (requires
   `schema_version: "pilot-signup/v1"`, `consent_to_contact`, and an allowed
   `use_case`; it is install telemetry, not marketing). Either add `/api/waitlist`
   to `verify_portal`, or send through `/api/contact` with `tier: "waitlist"`.
3. **Checkout** — port `js/paddle-config.js` + `js/sprint-checkout.js` and the
   Paddle v2 script tag into the zenjin plans page. Keep the same price IDs/env.
4. **Auth** — leave `cloud.epilabs.org/session` as-is. It only allows
   `epilabs.org`/`www.epilabs.org`; previews will show "Sign In". Expected.
5. **CSP** — move the inline GSAP timeline in `index.html` to `/js/film-timeline.js`,
   then run `scripts/build_csp_hashes.py`. Do not enable enforcing CSP until the
   hashes match. JSON-LD is not executable and needs no hash.
6. **Contact storage** — Render free plan writes `contact_submissions/*.json` to
   ephemeral disk; submissions vanish on restart unless SMTP is configured.
   Fix before calling the form production-ready (Turso or email-only).

## 6. Risks

- **Mixed design during transition.** Kept pages still use `site.css` and the old
  nav. Acceptable only while the new nav does not link them.
- **CSP.** Inline timeline will be blocked if CSP moves from Report-Only to
  enforcing without new hashes.
- **Service worker.** Network-first HTML means stale HTML is unlikely; shared JS
  is byte-identical, so the cache is safe. Still bump `CACHE_NAME` so old caches
  are dropped.
- **FastAPI file routes.** Missing `account.html`/`terms.html`/`privacy.html`/
  `refund.html`/`pricing.html` returns 404 on `api.epilabs.org` even when Pages
  works.
- **Legal pages** must ship; they are linked from checkout and the footer.
- **Paddle.** Wrong env/price IDs silently break checkout; test with sandbox first.
- **Sitemap/robots** must be regenerated for new URLs; old URLs stay valid.

## 7. Branch procedure

```powershell
cd C:\Users\dell\epi-recorder
git status                     # must be clean
git checkout -b site/zenjin-v2

# 1. copy zenjin pages + assets into website/ (keep every existing file)
#    - index.html, how-it-works.html, plans.html, trust.html, verify/index.html
#    - css/zenjin-epi.css, js/zenjin-epi.js
#    - assets/epi-walkthrough.*, epi-launch.vtt, logo-white.png, logo-trimmed.png
#    - MIGRATION.md (this file)
# 2. do NOT copy: _headers, _redirects, sw.js, manifest.json, robots.txt, sitemap.xml
# 3. apply integration fixes (§5)
python scripts/sync_website.py
git add website site verify_portal/static epi-official
git commit -m "site: zenjin v2 frontend (home, how-it-works, plans, trust, verify)"
git push -u origin site/zenjin-v2
```

Preview: Cloudflare Pages builds the branch → `https://<branch-alias>.epilabs.pages.dev`.
Render is untouched. Merge to `main` only after §8 passes.

## 8. Acceptance checklist (run on the preview, then production)

- [ ] `/`, `/how-it-works`, `/plans`, `/trust`, `/verify/` render zenjin design, desktop + mobile
- [ ] film: poster, play, sound, captions (CC), 60.2 s
- [ ] in-page verifier accepts `sample.epi`; `/verify/` still verifies offline
- [ ] contact form → 200 from `/api/contact`; submission visible in Render logs
- [ ] waitlist → 202/200 from its endpoint
- [ ] Paddle checkout opens (sandbox), price IDs correct
- [ ] `/account`, `/login`, `/terms`, `/privacy`, `/refund`, `/portal` load
- [ ] `/use-cases`, `/enterprise`, `/integrations`, `/status`, `/t/acme-demo/`, `/cases/` load
- [ ] `/pricing` → 301 `/plans`; `/verify` → 301 `/verify/`; `/viewer` → 301 `/verify/`
- [ ] headers present: HSTS, `X-Frame-Options: DENY`, CSP report-only
- [ ] `sw.js` cache name bumped; no stale asset errors in console
- [ ] `sitemap.xml` / `robots.txt` list the new URLs
- [ ] Lighthouse: no console errors, LCP sane with the video preload=metadata

## 9. Rollback

- Branch: delete branch; `main` untouched.
- After merge: `git revert` the merge commit; Cloudflare Pages redeploys the old
  `site/` from `main`; Render restarts and re-syncs `website/`.

## 10. Open decisions

1. Which legacy page gets redesigned next — `/use-cases` (best argument fit) or
   legal pages (lowest risk)?
2. Waitlist: new `/api/waitlist` endpoint, or reuse `/api/contact` with `tier`?
3. Keep both CSS systems indefinitely, or set a date to retire `site.css`
   after the legacy pages are redesigned?
