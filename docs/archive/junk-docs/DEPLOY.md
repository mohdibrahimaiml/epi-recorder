# EPI Free Deployment Guide
## Zero Cost — Render Free Tier

---

## What You're Deploying

| URL | What it serves |
|---|---|
| `https://epilabs.org` | Landing page |
| `https://epilabs.org/verify` | Verify portal (drag-drop UI) |
| `https://epilabs.org/api/verify` | Verification API (POST) |
| `https://epilabs.org/.well-known/did.json` | DID document |
| `https://epilabs.org/.well-known/epi-trust-registry.json` | Trust registry |
| `https://epilabs.org/health` | Health check |

**Platform**: Render (free tier — $0)
**Limitation**: Sleeps after 15 min inactivity (wakes in ~30 sec on next request)

---

## Prerequisites

- Render account (https://render.com) — sign up with GitHub (no credit card required)
- DNS access for `epilabs.org`

---

## Step 1: Push Code to GitHub

```bash
cd /c/Users/dell/epi-recorder
git push origin main
```

---

## Step 2: Deploy on Render

### Create Blueprint

1. Go to https://dashboard.render.com/blueprints
2. Click **"New Blueprint Instance"**
3. Connect your GitHub repo: `epi-recorder`
4. Render reads `render.yaml` and sets up the service automatically

### Or Manual Setup

1. Go to https://dashboard.render.com/
2. Click **"New +"** → **"Web Service"**
3. Connect `epi-recorder` repo
4. Settings:
   - **Name**: `epi-verify-portal`
   - **Runtime**: Python 3
   - **Build Command**: `pip install -e ".[gateway]"`
   - **Start Command**: `python -m verify_portal.main`
   - **Plan**: Free
5. Click **Create Web Service**

---

## Step 3: Add Secret Key

In Render dashboard → your service → **Environment**:

```
EPI_ATTESTATION_PRIVATE_KEY = p4c0FFSbCFvetlNhT9nOPz4Q7+y0cpVas8p9ONvqo3k=
```

Click **Save Changes**. Render redeploys automatically.

---

## Step 4: Add Custom Domain

In Render dashboard → your service → **Settings** → **Custom Domains**:

1. Click **"Add Custom Domain"**
2. Enter: `epilabs.org`
3. Render gives you a CNAME target (e.g., `epi-verify-portal.onrender.com`)

### DNS Setup

In your DNS provider:

```
CNAME epilabs.org → epi-verify-portal.onrender.com
```

Wait 2–5 minutes for propagation.

---

## Step 5: Verify

```bash
# Health check
curl https://epilabs.org/health

# DID document
curl https://epilabs.org/.well-known/did.json

# Verify a real .epi file
curl -F "file=@epi-recordings/demo_refund.epi" https://epilabs.org/api/verify
```

Open `https://epilabs.org/verify` in your browser.

---

## Free Tier Limits

| Limit | Value |
|---|---|
| RAM | 512 MB |
| Disk | 0.5 GB |
| Bandwidth | 100 GB/month |
| Uptime | Sleeps after 15 min inactivity |
| Cost | **$0** |

**When someone visits after sleep**: First request takes ~30 seconds to wake up. All subsequent requests are fast.

**Upgrade later**: Render Starter plan is $7/month (always-on, more resources).

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `502 Bad Gateway` | App crashed — check Render logs |
| First request slow | Normal — free tier sleeps after 15 min |
| `429 Too Many Requests` | Rate limiting working correctly |
| DNS not resolving | Wait 5–10 min, check CNAME record |

---

## Alternative Free Hosts

| Host | Free Tier | Custom Domain | Notes |
|---|---|---|---|
| **Render** ✅ | Yes | Yes | Sleeps after 15 min |
| Koyeb | Yes | Yes | 2 apps free |
| Fly.io | Yes | Yes | Requires credit card |
| Vercel | Yes | Yes | Only static/serverless; body limit 4.5MB |
