# EPI fix backlog (one by one)

We fix **one item fully**, verify, then move on.

| # | Item | Status |
|---|------|--------|
| 1 | Durable free auth DB (Turso optional, no paid disk) | **DONE** (code) — needs your free Turso env vars on Render |
| 2 | Login/logout E2E harden + live verify | NEXT |
| 3 | Single website source of truth | pending |
| 4 | Core loop: record→seal→verify→view reliability | pending |
| 5 | Default secrets redaction | pending |
| 6 | README / golden-path focus | pending |
| 7 | `epi demo` magic | pending |
| 8 | Free keep-warm + cold-start UX | pending |

## How we work

1. Pick the next `#`  
2. Implement + tests  
3. Commit / push  
4. You verify (if env/config needed)  
5. Mark done, start next  

See also: [FREE_AUTH_DB_SETUP.md](./FREE_AUTH_DB_SETUP.md)
