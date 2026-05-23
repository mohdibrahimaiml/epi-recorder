# EPI Production Deployment Guide
## One Domain, One Platform, ~$5/month

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

**Platform**: Railway (one app, one custom domain)
**Cost**: ~$5/month (Railway Starter)

---

## Prerequisites

- Railway account (https://railway.app) — sign up with GitHub
- DNS access for `epilabs.org` (Cloudflare, Namecheap, etc.)
- Your local `~/.epi/keys/default.key` exists

---

## Step 1: Prepare Production Key

Run this locally to get your base64-encoded private key:

```bash
python scripts/prepare_production_key.py
```

**Copy the base64 string.** Treat it like a password. Never commit it.

---

## Step 2: Push Code to GitHub

```bash
# In epi-recorder repo
git push origin main
```

---

## Step 3: Deploy to Railway

### Create Project

1. Go to https://railway.app
2. Click **"New Project"**
3. Select **"Deploy from GitHub repo"**
4. Choose `epi-recorder`
5. Railway auto-detects `railway.toml`

### Set Environment Variables

In Railway → Project → Variables, add:

```
EPI_ATTESTATION_PRIVATE_KEY=<paste base64 from Step 1>
PORT=8000
```

### Add Custom Domain

In Railway → Project → Settings → Domains:
1. Click **"Custom Domain"**
2. Enter: `epilabs.org`
3. Railway gives you a CNAME target (e.g., `your-app.up.railway.app`)

### DNS Setup

In your DNS provider (Cloudflare/Namecheap):

```
CNAME epilabs.org → <railway-cname-target>
```

Wait 1–5 minutes for DNS propagation.

---

## Step 4: Verify Deployment

```bash
# Health check
curl https://epilabs.org/health

# DID document
curl https://epilabs.org/.well-known/did.json

# Trust registry
curl https://epilabs.org/.well-known/epi-trust-registry.json

# Verify a real .epi file
curl -F "file=@epi-recordings/demo_refund.epi" https://epilabs.org/api/verify | jq '.trust_level'

# Check tamper detection
curl -F "file=@tampered.epi" https://epilabs.org/api/verify | jq '.facts.integrity_ok'
# Expected: false
```

Open `https://epilabs.org/verify` in your browser to use the drag-drop UI.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `404` on DID | Files not in static dir | Check `verify_portal/static/.well-known/` exists in repo |
| `502` on verify | Railway app crashed | Check Railway logs for Python errors |
| `429` rate limited | Normal behavior | Wait 24h or upgrade Railway plan |
| Signature invalid | Wrong key in env var | Re-run `prepare_production_key.py` and update Railway variable |
| DNS not resolving | CNAME not propagated | Wait 5–10 minutes, check with `dig epilabs.org` |

---

## Rollback

If something breaks:

```bash
# Revert to previous commit
git revert HEAD
git push origin main

# Railway auto-deploys the revert
```

---

## Architecture Notes

### Why One Platform?

You only own `epilabs.org`. Using subdomains (`verify.epilabs.org`) requires:
- A second service (Vercel)
- A second DNS record
- More complexity

This architecture puts everything on Railway:
- `GET /` → landing page
- `GET /verify` → verify portal
- `POST /api/verify` → API
- `/.well-known/*` → DID + trust registry

### Scaling

The in-memory rate limiter (`_rate_limit_store`) is per-instance. If Railway scales horizontally, each instance tracks its own limits. For a solo founder pre-revenue, this is acceptable. Post-revenue, switch to Redis.

---

## Cost

| Service | Monthly Cost |
|---------|-------------|
| Railway (starter) | ~$5 |
| Domain (epilabs.org) | Already owned |
| **Total** | **~$5/month** |
