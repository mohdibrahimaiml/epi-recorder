# EPI public website (single source of truth)

This folder is the **only** place to edit the public marketing site and account pages.

Canonical rules (same content, longer form): [docs/WEBSITE.md](../docs/WEBSITE.md).

| Consumer | How it uses `website/` |
|----------|-------------------------|
| **Cloudflare Pages (production, `epilabs.org`)** | `npm run build` copies this folder to `site/`; `wrangler.toml` publishes it |
| GitHub Pages (mirror/fallback) | `.github/workflows/deploy-website.yml` uploads this folder; not the `epilabs.org` DNS origin |
| **Render verify portal static files** | `python scripts/sync_website.py` → `verify_portal/static/` |

## Edit here

- `index.html`, `plans.html`, `account.html`, `login.html`, …
- `css/`, `js/`, `assets/`
- `_redirects` (API proxies only — no `/page → page.html` rewrites)

## Do not edit

- `site/` — generated copy for Cloudflare Pages
- `epi-official/` — sync **target**, not a source
- `verify_portal/static/*.html` marketing pages — synced from here

Portal-only extras (not in this folder):

- `verify_portal/static/auth/`
- `verify_portal/static/admin/`

## Sync

```bash
python scripts/sync_website.py
```

## Claims

Keep these true on every page:

- Banner version matches `pyproject.toml` (currently **4.6.3**).
- Sign In goes to EPI Cloud, not Render.
- Open-source record/seal/verify needs no account.
- Verification is never charged.
- EPI Cloud is private beta, not a self-serve hosted-verification subscription.
- The seal proves integrity after sealing, not completeness of capture.
