# DNS Setup for epilabs.org

Two-platform deployment: GitHub Pages for the marketing site, Render for the API.

## Domain: epilabs.org → GitHub Pages

1. Go to your domain registrar (where you bought epilabs.org)
2. Set these DNS records:

```
Type    Name    Value
CNAME   @       <username>.github.io
```

3. In GitHub repo → Settings → Pages:
   - Source: "GitHub Actions"
   - Custom domain: `epilabs.org`
   - Enforce HTTPS: yes

The website deploys automatically when `epi-official/**` changes on main.

## Subdomain: verify.epilabs.org → Render

1. At your domain registrar, add:

```
Type    Name     Value
CNAME   verify   epi-verify.onrender.com
```

2. In Render dashboard → epi-verify service → Settings → Custom Domain:
   - Add: `verify.epilabs.org`

## Subdomain: api.epilabs.org → Render

The same `epi-verify` Render service also hosts the opt-in telemetry and pilot-signup endpoints.

1. At your domain registrar, add:

```
Type    Name     Value
CNAME   api      epi-verify-portal.onrender.com
```

2. In Render dashboard → epi-verify service → Settings → Custom Domain:
   - Add: `api.epilabs.org`

## What lives where

| Domain | Hosting | Content |
|--------|---------|---------|
| epilabs.org | GitHub Pages | index.html, pricing, demo, docs, viewer |
| verify.epilabs.org | Render | /verify, /api/verify, /health, /.well-known/* |
| api.epilabs.org | Render | /api/telemetry/events, /api/telemetry/pilot-signups, /api/share |
