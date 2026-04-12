# Hosted Insurance Pilot Runbook

This runbook is the supported deployment and smoke-test path for the hosted insurance design-partner flow:

- `epilabs.org` is served from [C:/Users/dell/epi-recorder/epi-official-site](C:/Users/dell/epi-recorder/epi-official-site)
- `api.epilabs.org` runs the existing gateway from [C:/Users/dell/epi-recorder/epi_gateway/main.py](C:/Users/dell/epi-recorder/epi_gateway/main.py)
- the canonical demo flow uses [C:/Users/dell/epi-recorder/examples/starter_kits/insurance_claim](C:/Users/dell/epi-recorder/examples/starter_kits/insurance_claim)

## 1. Publish The Official Site

Use `EPI-OFFICIAL` as the only public site repo.

Required public pages:

- `/verify/`
- `/cases/`
- `/claim-denial-evidence.html`

This repo now includes:

- a GitHub Pages workflow in `.github/workflows/deploy-pages.yml`
- `CNAME` for `epilabs.org`
- `.nojekyll` so static assets are served as-is

Deployment behavior:

- pushes to `main` publish the site
- docs and `epi-video/` do not block the Pages deploy
- the site artifact excludes `.git`, `.github`, `docs/`, `epi-video/`, and wheel files

## 2. Deploy The Gateway

Build and run the existing gateway Docker image from [C:/Users/dell/epi-recorder/epi_gateway/Dockerfile](C:/Users/dell/epi-recorder/epi_gateway/Dockerfile).

Minimum runtime configuration:

```text
EPI_GATEWAY_SHARE_ENABLED=true
EPI_GATEWAY_SHARE_SITE_BASE_URL=https://epilabs.org
EPI_GATEWAY_SHARE_API_BASE_URL=https://api.epilabs.org
EPI_GATEWAY_SHARE_MAX_UPLOAD_BYTES=5242880
EPI_GATEWAY_SHARE_DEFAULT_EXPIRY_DAYS=30
EPI_GATEWAY_SHARE_MAX_EXPIRY_DAYS=30
EPI_GATEWAY_SHARE_RATE_LIMIT_PER_HOUR=10
EPI_GATEWAY_SHARE_QUOTA_BYTES_PER_30D=104857600
EPI_GATEWAY_SHARE_IP_HMAC_SECRET=<secret>
EPI_GATEWAY_SHARE_S3_ENDPOINT=<r2-endpoint>
EPI_GATEWAY_SHARE_S3_REGION=auto
EPI_GATEWAY_SHARE_S3_BUCKET=<bucket>
EPI_GATEWAY_SHARE_S3_ACCESS_KEY_ID=<key>
EPI_GATEWAY_SHARE_S3_SECRET_ACCESS_KEY=<secret>

EPI_GATEWAY_ALLOWED_ORIGINS=https://epilabs.org

EPI_APPROVAL_BASE_URL=https://api.epilabs.org
EPI_APPROVAL_WEBHOOK_URL=<pilot-webhook-url>
EPI_APPROVAL_WEBHOOK_SECRET=<secret>
EPI_APPROVAL_WEBHOOK_TIMEOUT_SECONDS=10
```

Optional SMTP fallback:

```text
EPI_SMTP_HOST=<smtp-host>
EPI_SMTP_PORT=587
EPI_SMTP_USER=<smtp-user>
EPI_SMTP_PASSWORD=<smtp-password>
EPI_SMTP_FROM=<from-address>
```

Operational defaults:

- keep the R2 bucket private
- add a 30-day lifecycle rule for shared artifacts
- do not store approval secrets in `epi_policy.json`
- do not enable extra workspace/auth work for this pilot unless the customer blocks on it

## 3. Run The Local Hosted Smoke Test

Run the local rehearsal before touching production:

```powershell
.venv-release\Scripts\python.exe scripts\smoke_insurance_hosted_flow.py
```

What it validates:

- the official site pages are servable from `epi-official-site`
- the gateway starts with hosted sharing enabled
- the insurance starter kit generates a real `.epi`
- `epi share` uploads it to the gateway and returns a hosted URL
- share `meta` and artifact download endpoints respond correctly
- an approval-request workflow triggers the configured webhook
- `POST /api/approve/{workflow_id}/{approval_id}` records the human response
- crash recovery marks an orphan session as recovered/blocked
- the Decision Record export is generated from the insurance artifact

The local smoke path uses the share service's filesystem object store fallback so it does not need real R2 credentials.

## 4. Production Smoke Checklist

After deploying `epilabs.org` and `api.epilabs.org`, verify all of these in order:

1. `https://epilabs.org/verify/` loads and drag-drop verification works
2. `https://epilabs.org/cases/?id=<share_id>` loads a hosted case
3. `https://api.epilabs.org/health` returns OK over TLS
4. `POST /api/share` returns a live hosted URL
5. `GET /api/share/{id}/meta` and `GET /api/share/{id}` work cross-origin from the hosted page
6. an `agent.approval.request` triggers the pilot webhook or email path
7. clicking approve/deny records `agent.approval.response`
8. exported Decision Record matches the case story shown in the browser

## 5. After Smoke Passes

Freeze feature work and switch to sales execution:

- capture three screenshots:
  - Decision Summary
  - approval flow
  - Decision Record
- use the insurance starter kit and `claim-denial-evidence.html` as the only public demo story
- send the first 10 insurance/compliance outreach messages before starting any new non-blocking feature branch
