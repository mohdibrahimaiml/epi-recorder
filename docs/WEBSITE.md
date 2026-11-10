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
| `/decision-record` | The category page: what a Decision Record is, why not a log, ten-question checklist, real CLI output |
| `/plans` | Pricing: open source free; AI vendor review engagement (EUR 4,500 readiness assessment, EUR 9,500 founding / EUR 15,000 full engagement); EPI Cloud (USD): free workspace (1 customer relationship, 50 files/year, 30 days), Startup $500/month or $5,000/year, Growth $2,000/month or $20,000/year (upgraded in the dashboard), Enterprise from $40,000/year |
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
- EPI Cloud is a **free self-serve beta** (sign-in creates a workspace, no approval step), not a hosted-verification paywall. Startup and Growth are self-serve upgrades in the dashboard; Enterprise is invoiced directly.
- Cloud is priced per **customer relationship**, not per agent. Agents are fair use. The paid limits are customer relationships, Evidence Room files per year, retention and share links. Usage is not metered or blocked. Retention lasts while subscribed, and after cancelling the customer has 90 days to export everything.
- The seal proves integrity **after sealing**, not completeness of capture.
- Accounts live on EPI Cloud.

Details next to the HTML: [`website/README.md`](../website/README.md).
