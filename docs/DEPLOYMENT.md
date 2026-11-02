# Deployment: one path per surface

Three deployables exist. Each has exactly one source directory and one config.
Do not run `wrangler deploy` from the repository root expecting a particular
target; pick the surface below.

| Surface | Source of truth | Build | Deploy |
|---|---|---|---|
| `epilabs.org` (marketing, `/verify`, `/t/`) | `website/` | `npm run build` copies it to `site/` and the `.well-known` files | Cloudflare Pages project `epilabs`, config `wrangler.toml` (`pages_build_output_dir = "site"`) |
| `cloud.epilabs.org` (accounts, witness, share) | `PRIVATE-EPI/cloud/` | `npm run typecheck && npx vitest run` | Cloudflare Worker `epi-cloud`, config in that repository |
| Legacy verify portal | `verify_portal/` | `pip install -e ".[gateway]"` | Render (`render.yaml`) or Railway (`railway.toml`); being retired |

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
5. **The legacy portal is not the account system.** Sign-in, witness and share
   links are Cloud. The portal remains only for old `epi share` fallbacks,
   MCP hosting and opt-in telemetry until those links are retired.

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
