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
- `blog/` — generated from `blog/posts/*.md` by `python scripts/build_blog.py`; edit the Markdown and templates, not the HTML

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

- Banner version matches `pyproject.toml` (currently **4.10.0**).
- Sign In goes to EPI Cloud, not Render.
- Open-source record/seal/verify needs no account.
- Verification is never charged.
- EPI Cloud has a free self-serve workspace (1 customer, 1 share link, 50 runs,
  30 days). Signing in creates it; verification itself is never charged.
- Paid Team and Business plans exist as product tiers but are not sold through a
  public checkout yet.
- The seal proves integrity after sealing, not completeness of capture.
