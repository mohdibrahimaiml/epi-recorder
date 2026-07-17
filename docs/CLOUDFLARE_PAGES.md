# Cloudflare Pages setup (epilabs.org)

The public site source of truth is **`website/`**.

## Why builds failed

Log:

```text
Error: Output directory "site" not found.
```

Cloudflare is configured with **output directory = `site`** and **no build command**.  
We moved the source of truth to `website/` and deleted the old `site/` tree, so CF failed.

## Fix in the repo

1. **`website/`** remains the only place you edit.
2. **`site/`** is a **generated mirror** of `website/` (for Cloudflare).
3. `python scripts/sync_website.py` copies `website/` → `site/`, `verify_portal/static/`, `epi-official/`.
4. `npm run build` also copies `website/` → `site/` and `dist/`.

## Dashboard settings (match what you already have)

| Setting | Value |
|---------|--------|
| **Production branch** | `main` |
| **Root directory** | *(empty)* |
| **Framework preset** | **None** |
| **Build command** | *(empty)* **or** `npm run build` |
| **Build output directory** | **`site`** |

If build command is empty, `site/` **must exist in git** (kept in sync from `website/`).

## After changing settings

1. **Retry deployment** of the latest commit (or push an empty commit).
2. Confirm deploy status is **Success**.
3. Check `https://epilabs.org/account` and `https://epilabs.org/`.

## What not to set

- Do **not** set root directory to `epi-official` or `site` (obsolete).
- Do **not** add `/page → page.html` rewrites in `_redirects` (causes 308 loops).
- Do **not** use SPA `/* /index.html 200` for this multi-page site.

## Related

- Site source: `website/`
- Sync to Render static: `python scripts/sync_website.py`
- GitHub Pages: `.github/workflows/deploy-website.yml` (also uses `website/`)
