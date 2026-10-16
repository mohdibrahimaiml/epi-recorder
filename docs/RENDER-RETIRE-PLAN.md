# Render dependencies still live (do NOT delete yet) — one account system plan

Single account system is now EPI Cloud (`https://cloud.epilabs.org`).
Website Sign In (`/account`, `/login`, nav) points to the cloud front door.
`epi auth login` is an alias of `epi cloud login` (device flow).

The old Render server (`epi-verify-portal.onrender.com`) is retired for login,
but these still depend on it. Proposal for each (no deletion in this change):

| Still on Render | Where | Proposal |
|---|---|---|
| `epi share` hosted upload (`POST /api/share`) | `epi_cli/share.py` `DEFAULT_SHARE_API_URL`, `EPI_SHARE_API_URL` | Keep working until Evidence Room share-links replace it. Next: `epi share` gains `--cloud` flag that mints a cloud trust link (`/v1/orgs/:org/share-links`) and uploads via `/v1/orgs/:org/artifacts/*`; then flip default and deprecate Render path. |
| `epi auth` local token file (`~/.epi/auth.json`) | `epi_cli/auth_cmd.py` `save_auth/load_auth`, `epi_core/telemetry.py` `DEFAULT_TELEMETRY_URL` | Kept read-only for `--local` dev sessions. Cloud auth uses `~/.epi/cloud.json`. Next: remove Render token refresh; keep `auth.json` only for `--local`. |
| Telemetry + pilot signups | `epi_core/telemetry.py` `DEFAULT_TELEMETRY_URL`, `DEFAULT_PILOT_SIGNUP_URL` | Keep (opt-in, offline-first). Next: point to cloud `/v1/telemetry` or drop if unused; never required for core flows. |
| Keep-warm cron | `.github/workflows/keep-warm.yml` (`BASE: https://epi-verify-portal.onrender.com`, `epi-mcp.onrender.com`) | Keep until Render retired. Next: replace with cloud `/health` check or delete when Render sunsets. |
| Cloudflare `_proxy` / `functions/_proxy.js` (`BACKEND = ...onrender.com`) | `functions/_proxy.js`, `docs/archive/CLOUDFLARE_FUNCTIONS.md` | Keep for old `/api/*` share/verify paths. Next: proxy to `cloud.epilabs.org` for trust/verify, then remove. |
| Static copies of old account/status pages | `site/`, `verify_portal/static/`, `epi-official/`, `js/auth-ui.js` | Build artifacts / archives. Next: re-sync from `website/` (single source) or delete generated copies; do not hand-edit. |
| Old billing webhook (`verify_portal`, `/api/paddle/webhook`, `/api/plan/features`, `/api/keys`) | `verify_portal/`, `website/js/paddle-config.js` | Retired for login; billing stays as-is until cloud plans (M7 paddle) ship. Next: M7 replaces with cloud entitlements. |
| Docs referencing Render/MCP on Render | `docs/*`, `plans/*`, `render.yaml` | Docs only. Next: update after share + billing migrate. |

No Render code was deleted in this change. Website `/api/auth/*` calls were
removed from `website/` (only share `/api/share/*` in `website/cases/` remains,
intentionally, until the cloud share-link migration lands).
