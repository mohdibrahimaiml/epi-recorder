# Website source of truth

## Canonical tree

**`website/`** is the only tree you should edit for the public marketing site and `/verify/`.

Deployed by `.github/workflows/deploy-website.yml` → **GitHub Pages** with:

```yaml
path: website
```

`CNAME` in `website/` → **epilabs.org**.

## Mirrors (generated / kept in sync)

Do **not** hand-edit these for content changes. Refresh from `website/`:

```bash
python scripts/sync_website.py
```

| Path | Why it exists |
|------|----------------|
| `verify_portal/static/` | Render / FastAPI static + portal (preserves `auth/`, `admin/`) |
| `epi-official/` | Legacy tree name; kept identical for old docs and local habits |
| `site/` | Cloudflare Pages output directory (mirror of `website/`) |

## Verify engine

| File | Role |
|------|------|
| `website/js/epi-verify-core.js` | **Canonical** browser verifier (`window.verifyEPI`) |
| `website/verify/index.html` | Hosted verify UI |

After editing either, run `python scripts/sync_website.py` so mirrors match.

Root `js/epi-verify-core.js` is a **compat copy** of `website/js/epi-verify-core.js` (some historical paths load `/js/...` from repo root layouts). Prefer `website/js/` as the edit target, then sync.

## Rule

1. Edit **`website/`** only.  
2. Run **`python scripts/sync_website.py`**.  
3. Commit **`website/` + mirrors + root `js/` copy** together when hashes change.  
4. Never “fix only epi-official” — it will drift and confuse the next person.

## Alignment with the product

Hosted verify must agree with `epi verify` on integrity and signature for the same `.epi` bytes. See `docs/EVIDENCE-ALIGNMENT.md` once Phase 4 lands; until then, smoke with a golden sample after each verify-core change.
