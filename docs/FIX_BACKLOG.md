# EPI fix backlog (one by one)

We fix **one item fully**, verify, then move on.

| # | Item | Status |
|---|------|--------|
| 1 | Durable free auth DB (Turso optional, no paid disk) | **DONE** (Turso live in prod) |
| 2 | Login/logout E2E harden + live verify | **DONE** |
| 3 | Single website source of truth | **DONE** (`website/`) |
| 4 | Core loop: record→seal→verify→view reliability | **DONE** |
| 5 | Default secrets redaction (safe by default) | **DONE** |
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
