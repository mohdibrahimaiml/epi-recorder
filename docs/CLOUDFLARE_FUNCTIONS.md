# Cloudflare Pages Functions (API proxy)

Cloudflare Pages **cannot** use Netlify-style:

```
/api/* https://backend.example.com/api/:splat 200
```

That is why the build log said:

```
Proxy (200) redirects can only point to relative paths.
```

## Solution

Edge functions under `functions/` reverse-proxy to Render:

| Browser path | Function | Upstream |
|--------------|----------|----------|
| `/api/*` | `functions/api/[[path]].js` | `https://epi-verify-portal.onrender.com/api/*` |
| `/scitt/*` | `functions/scitt/[[path]].js` | same host |
| `/well-known/*` | `functions/well-known/[[path]].js` | maps to `/.well-known/*` |

Account pages still use absolute `API_BASE` as a fallback when Functions are unavailable (e.g. GitHub Pages only).

## Deploy

Functions live at the **repo root** (not inside `site/`).  
Cloudflare picks them up automatically on deploy from `main`.
