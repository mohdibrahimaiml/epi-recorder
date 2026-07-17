# Free-tier keep-warm (no paid Render)

Render free instances **sleep** after idle. First request can take 10–60s.

## What we do (all free)

| Layer | Mechanism |
|-------|-----------|
| **GitHub Actions** | `.github/workflows/keep-warm.yml` pings every 10 minutes |
| **Website** | `website/js/auth-ui.js` hits `/api/ping` on every page load |
| **Account page** | Wakes API as soon as `/account` opens; multi-retry wake before GitHub redirect |
| **Endpoint** | `GET /api/ping` — ultra-cheap (no DB) |

## Enable the schedule

Scheduled workflows sometimes pause on inactive free repos.

1. GitHub → **Actions** → **Keep Render Warm**
2. Click **Run workflow** once (workflow_dispatch)
3. Confirm recent green runs every ~10 minutes

## Check cold vs warm

```bash
# Should be fast if warm
curl -s -w "\n%{time_total}\n" https://epi-verify-portal.onrender.com/api/ping
curl -s https://epi-verify-portal.onrender.com/api/auth/status
```

## Limits

- Free Render can still sleep under load or after idle gaps.
- Keep-warm reduces *frequency* of cold starts; it cannot eliminate them forever.
- If GitHub disables cron after inactivity, re-run **workflow_dispatch**.

## Not required

- Paid Render plan
- Paid disk (use Turso free for durable auth — see `FREE_AUTH_DB_SETUP.md`)
