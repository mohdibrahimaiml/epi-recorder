# Public website (`epilabs.org`)

**Source of truth:** the `website/` folder in this repo.  
**Live site:** https://epilabs.org, served by **Cloudflare Pages** from the
generated `site/` directory (`wrangler.toml`: `pages_build_output_dir = "site"`).  
**Version shown on the banner must match `pyproject.toml` (currently 4.9.0).**

This is the marketing and in-browser verify surface. It is **not** a substitute for the technical docs in this folder. Sign-in on the site is **EPI Cloud** (`cloud.epilabs.org`), not the old Render portal.

## What lives here

| Page | Role |
|------|------|
| `/` (`index.html`) | Product home |
| `/verify/` | In-browser verify (no upload in the default path) |
| `/how-it-works`, `/trust`, `/use-cases`, `/enterprise` | Explanatory pages |
| `/plans` | Pricing: open source free, one Decision File pilot (EUR 4,500, one workflow, 30 days), EPI Cloud **private beta** |
| `/login`, `/account` | Redirect / front door into EPI Cloud |
| `/status` | Health of EPI Cloud (not Render login) |
| `/standards` | EU AI Act Annex IV, AIUC-1, SCITT: evidence input, not a certificate |
| `/privacy`, `/terms`, `/refund` | Legal |

## Edit rules

| Consumer | How it uses `website/` |
|----------|-------------------------|
| **Cloudflare Pages (production, `epilabs.org`)** | `npm run build` copies `website/` → `site/`; `wrangler.toml` publishes `site/` |
| GitHub Pages (mirror/fallback) | `.github/workflows/deploy-website.yml` uploads `website/`; not the DNS origin for `epilabs.org` |
| Render verify portal static files | `python scripts/sync_website.py` → `verify_portal/static/` |
| `epi-official/` | Sync **target**, never a source |

**Always edit `website/` only**, then run:

```bash
python scripts/sync_website.py
```

Do not hand-edit `site/`, `verify_portal/static/*.html` marketing pages, or `epi-official/`. Those copies will be overwritten.

Portal-only extras that are **not** in `website/`:

- `verify_portal/static/auth/`
- `verify_portal/static/admin/`

## Claims the site is allowed to make

Match these or the page is wrong:

- Open-source record / seal / verify is MIT and free. No account required.
- Verification is never charged.
- EPI Cloud is **private beta**, not a self-serve hosted-verification subscription.
- The seal proves integrity **after sealing**, not completeness of capture.
- Accounts live on EPI Cloud.

Details next to the HTML: [`website/README.md`](../website/README.md).
