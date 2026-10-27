# Internal docs (not for partners)

Everything here is operator truth: founder setup, capacity and pricing math,
execution plans, agent prompts and internal design notes. **Do not link it from
the public site, the enterprise briefing, or anything handed to a bank, insurer,
or auditor.**

`docs/` is published as a website (`spec.epilabs.org`), so every file in it is
world-readable — that is why this tree lives at the repo root rather than under
`docs/internal/`. `tests/test_docs_placement.py` enforces both halves: nothing
internal under `docs/`, and no public doc linking in here.

**Be aware of what "internal" means here.** This tree is inside a *public*
repository: it is not served as a web page and not linked, but anyone reading
the repo can open it. Treat it as unlisted, not secret. A document that must
stay genuinely private (credentials, customer names, incident post-mortems)
does not belong in this repository at all.

| Doc | What it is | Moved from |
|-----|------------|------------|
| [cloud-ops.md](./cloud-ops.md) | EPI Cloud founder setup, limits, backups, local dev | `docs/CLOUD.md` |
| [scope.md](./scope.md) | Investment rule: what the repo staffs vs freezes | `docs/SCOPE.md` |
| [BANK-READINESS-ASSESSMENT.md](./BANK-READINESS-ASSESSMENT.md) | Where the product falls short of bank diligence | `docs/internal/` |
| [BANK-READINESS-EXECUTION-PLAN.md](./BANK-READINESS-EXECUTION-PLAN.md) | Step-by-step bank-readiness plan and PR status | `docs/internal/` |
| [swallow-audit.md](./swallow-audit.md) | Swallowed-exception audit / red-team prep | `docs/internal/` |
| [design/org-trust-bundle.md](./design/org-trust-bundle.md) | Org trust bundle v0 build spec | `docs/design/` |
| [prompts/](./prompts/) | Coding-agent prompt for each bank-readiness step | `docs/internal/prompts/` |
