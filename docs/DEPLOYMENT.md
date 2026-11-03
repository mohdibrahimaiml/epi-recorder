# Deployment: one path per surface

Three deployables exist. Each has exactly one source directory and one config.
Do not run `wrangler deploy` from the repository root expecting a particular
target; pick the surface below.

| Surface | Source of truth | Build | Deploy |
|---|---|---|---|
| `epilabs.org` (marketing, `/verify`, `/t/`) | `website/` | `npm run build` copies it to `site/` and the `.well-known` files | Cloudflare Pages project `epilabs`, config `wrangler.toml` (`pages_build_output_dir = "site"`) |
| `cloud.epilabs.org` (accounts, witness, share) | `PRIVATE-EPI/cloud/` | `npm run typecheck && npx vitest run` | Cloudflare Worker `epi-cloud`, config in that repository |
| Legacy verify portal | `verify_portal/` | `pip install -e ".[gateway]"` | Render (`render.yaml`) or Railway (`railway.toml`); being retired |
| `verify.epilabs.org` | `PRIVATE-EPI/cloud/src/index.ts` | same Worker build as Cloud | Route on the `epi-cloud` Worker: browsers get **301** to `epilabs.org/verify/`; legacy API paths proxy to Render until sunset |

## Rules

1. **One config per directory.** The public repo keeps `wrangler.toml` for
   Pages only. The old `wrangler.jsonc` Worker (name `epi-recorder`, assets
   `docs/`) is retired in `attic/wrangler-docs-worker.jsonc.retired`. It was
   never part of the customer path and made a root deploy ambiguous.
2. **`website/` is the only place to edit page copy.** `site/`,
   `epi-official/`, `verify_portal/static/` and `assets/` are generated copies.
   Run `python scripts/sync_website.py` after editing `website/`.
3. **`.well-known` is committed, not generated at deploy time.** Trust anchors
   live in `website/.well-known/` and are copied to every mirror.
4. **Cloud changes are deployed from `PRIVATE-EPI`, not from this repo.**
   `cloud/src` is not present here; a public deploy cannot touch the Worker.
   Merges to `PRIVATE-EPI/main` apply D1 migrations and deploy through
   `.github/workflows/cloud.yml` using the scoped `CLOUDFLARE_API_TOKEN`.
5. **The legacy portal is not the account system.** Sign-in, witness and share
   links are Cloud. The portal remains only for old `epi share` fallbacks,
   MCP hosting and opt-in telemetry until those links are retired.

## Daily checks

`.github/workflows/production-smoke.yml` runs at 06:17 UTC and checks the live
Pages pages, the trust anchors, Cloud health, and the `verify.epilabs.org`
redirect. A failure is a real outage signal, not a build warning.

## Checking what is deployed

```powershell
# Static site (Pages)
curl.exe -sI https://epilabs.org/ | Select-String "HTTP/"

# Cloud Worker
curl.exe -s https://cloud.epilabs.org/health

# Share upload path (expects 201)
curl.exe -s -o NUL -w "%{http_code}`n" -X POST https://cloud.epilabs.org/api/share
```

The last command only checks that the route exists; a real upload is exercised
by `tests/test_share_fallback.py` and the release checklist.

## Retiring the docs Worker

`attic/wrangler-docs-worker.jsonc.retired` is kept for history. If a Worker
named `epi-recorder` still exists in the Cloudflare account and is not serving
traffic, delete it in the dashboard. Nothing in the product references it.
