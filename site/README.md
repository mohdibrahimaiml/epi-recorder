# EPI public website (single source of truth)

This folder is the **only** place to edit the public marketing site and account pages.

| Consumer | How it uses `website/` |
|----------|-------------------------|
| **GitHub Pages** (`epilabs.org`) | Deployed directly from this folder |
| **Render verify portal** | Synced into `verify_portal/static/` on app start + via `scripts/sync_website.py` |

## Edit here

- `index.html`, `pricing.html`, `account.html`, …
- `css/`, `js/`, `assets/`
- `_redirects` (API proxies only — no `/page → page.html` rewrites)

## Do not edit

- `site/` (removed / obsolete)
- Root-level `account.html` / `pricing.html` (obsolete copies)
- `epi-official/` by hand — it is a **sync target**, not a source
- `verify_portal/static/*.html` marketing pages by hand — synced from here

Portal-only extras (not in this folder):

- `verify_portal/static/auth/`
- `verify_portal/static/admin/`

## Sync manually

```bash
python scripts/sync_website.py
```

## Deploy targets

| Target | Path |
|--------|------|
| GitHub Pages | deploys website/ directly |
| Cloudflare Pages | uses generated mirror site/ (output dir) |
| Render portal | erify_portal/static/ via sync |

Always edit **website/** only, then run python scripts/sync_website.py.
