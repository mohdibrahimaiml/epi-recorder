# Cloudflare Pages setup (epilabs.org)

The public site source of truth is **`website/`**.

## Why builds failed after the website consolidation

Cloudflare Pages was still configured for the old layout (repo root / `epi-official` / wrong output dir).  
We now ship an explicit build:

```bash
npm run build   # → copies website/ to dist/
```

## Required dashboard settings

Cloudflare → **Workers & Pages** → your **epilabs** project → **Settings → Builds & deployments**:

| Setting | Value |
|---------|--------|
| **Production branch** | `main` |
| **Root directory** | *(empty / repo root)* |
| **Framework preset** | **None** |
| **Build command** | `npm run build` |
| **Build output directory** | `dist` |

Or rely on repo `wrangler.toml`:

```toml
pages_build_output_dir = "dist"
```

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
