# Free durable auth DB (no paid Render disk)

EPI login stores users, tokens, and plans in `auth.db`.

On **Render free**, the filesystem is wiped on redeploy — so local SQLite alone is not durable.

## Free solution: Turso (libSQL in the cloud)

Turso has a free tier. EPI talks to it over HTTPS (no paid disk, no native drivers).

### 1. Create a free Turso account

1. Go to https://turso.tech and sign up (GitHub login works).
2. Install CLI (optional but easy):

```bash
# Windows (PowerShell) — or use the Turso web dashboard instead
irm get.tur.so/install.ps1 | iex
turso auth login
```

### 2. Create a database

```bash
turso db create epi-auth
turso db show epi-auth --url
turso db tokens create epi-auth
```

Or in the Turso dashboard: **Create Database** → copy **URL** + create a **token**.

### 3. Set Render environment variables

In Render → your `epi-verify` service → **Environment**:

| Key | Value |
|-----|--------|
| `TURSO_DATABASE_URL` | `libsql://epi-auth-xxxxx.turso.io` (your URL) |
| `TURSO_AUTH_TOKEN` | the token you created |
| `GITHUB_CLIENT_ID` | (already set) |
| `GITHUB_CLIENT_SECRET` | (already set) |
| `EPI_FRONTEND_URL` | `https://epilabs.org` |
| `EPI_VERIFY_BASE_URL` | `https://epi-verify-portal.onrender.com` |

Aliases also accepted: `LIBSQL_URL` + `LIBSQL_AUTH_TOKEN`.

### 4. Redeploy

Manual deploy (or push any commit). Then check:

```text
https://epi-verify-portal.onrender.com/api/auth/status
```

Expect something like:

```json
{
  "ok": true,
  "oauth_configured": true,
  "db_backend": "turso",
  "db_durable": true,
  "turso_configured": true
}
```

### 5. Test login

1. Open https://epilabs.org/account  
2. Sign in with GitHub  
3. Redeploy Render (or restart)  
4. Sign in again — **same user / plan should still exist**

---

## Without Turso

If Turso env vars are **not** set, EPI uses local SQLite under `EPI_STORAGE_DIR` (default `./data`).

That works for development, but **accounts can reset** on free Render redeploys.

---

## Cost

| Piece | Cost |
|-------|------|
| GitHub Pages (website) | Free |
| Render free (API) | Free |
| Turso free DB | Free (within quota) |
| GitHub OAuth App | Free |

**Total: $0**
