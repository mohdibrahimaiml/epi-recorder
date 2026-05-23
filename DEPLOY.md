# EPI Production Deployment Guide
## Zero-to-Live in 20 Minutes

---

## Prerequisites

- Railway account (https://railway.app) — sign up with GitHub
- Vercel account (https://vercel.com) — sign up with GitHub
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

## Step 2: Deploy Static Site (EPI-OFFICIAL Repo)

```bash
# In EPI-OFFICIAL repo
cp /path/to/epi-recorder/assets/well-known/did.json public/.well-known/
cp /path/to/epi-recorder/assets/well-known/epi-trust-registry.json public/.well-known/
git add public/.well-known/
git commit -m "Add DID:WEB and trust registry for EPI verification"
git push origin main
```

Then in Vercel dashboard:
1. Import `EPI-OFFICIAL` repo
2. Framework preset: `Other` (plain HTML)
3. Build command: leave empty
4. Output directory: `public`
5. Add custom domain: `epilabs.org`

Verify:
```bash
curl https://epilabs.org/.well-known/did.json
curl https://epilabs.org/.well-known/epi-trust-registry.json
```

---

## Step 3: Deploy Verify Portal (epi-recorder Repo)

```bash
# In epi-recorder repo
git add verify_portal/ railway.toml scripts/prepare_production_key.py DEPLOY.md
git commit -m "Add verify portal for epilabs.org"
git push origin main
```

Then in Railway dashboard:
1. Click "New Project"
2. Select "Deploy from GitHub repo"
3. Choose `epi-recorder`
4. Railway auto-detects `railway.toml`

### Set Environment Variables

In Railway → Project → Variables, add:

```
EPI_ATTESTATION_PRIVATE_KEY=<paste base64 from Step 1>
PORT=8000
```

### Add Custom Domain

In Railway → Project → Settings → Domains:
1. Click "Generate Domain" (or "Custom Domain")
2. Enter: `verify.epilabs.org`
3. Railway gives you a CNAME target

### DNS Setup

In your DNS provider (Cloudflare/Namecheap):

```
CNAME verify.epilabs.org → <railway-cname-target>
```

Wait 1-5 minutes for DNS propagation.

Verify:
```bash
curl https://verify.epilabs.org/health
```

---

## Step 4: End-to-End Test

```bash
# Test 1: Health check
curl https://verify.epilabs.org/health

# Test 2: Verify a real .epi file
curl -F "file=@epi-recordings/demo_refund.epi" https://verify.epilabs.org/verify | jq '.trust_level'

# Test 3: Check tamper detection
curl -F "file=@tampered.epi" https://verify.epilabs.org/verify | jq '.facts.integrity_ok'
# Expected: false
```

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `404` on DID | Wrong file path in Vercel | Ensure files are in `public/.well-known/` |
| `502` on verify | Railway app crashed | Check Railway logs for Python errors |
| `429` rate limited | Normal behavior | Wait 24h or upgrade Railway plan |
| Signature invalid | Wrong key in env var | Re-run `prepare_production_key.py` and update Railway variable |
| DNS not resolving | CNAME not propagated | Wait 5-10 minutes, check with `dig verify.epilabs.org` |

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

## Cost

| Service | Monthly Cost |
|---------|-------------|
| Vercel (static site) | $0 |
| Railway (starter) | ~$5 |
| Domain (epilabs.org) | Already owned |
| **Total** | **~$5/month** |
