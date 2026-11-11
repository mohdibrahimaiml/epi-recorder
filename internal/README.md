# Internal docs (not for partners)

Planning, operations and assessment docs are kept in a private repository,
not here. This repository is public: anything committed to it can be read by
anyone, so planning notes, capacity or pricing math, assessments, agent
prompts and operations runbooks do not belong in it.

What stays here is internal-but-harmless engineering material that public code
refers to. **Do not link it from the public site, the enterprise briefing, or
anything handed to a bank, insurer, or auditor.**

`docs/` is published as a website (`spec.epilabs.org`), so nothing internal may
live under it. `tests/test_docs_placement.py` enforces that, and that no public
doc links in here.

| Doc | What it is | Moved from |
|-----|------------|------------|
| [design/org-trust-bundle.md](./design/org-trust-bundle.md) | Org trust bundle v0 build spec (referenced by `epi_core/org_bundle.py`) | `docs/design/` |
| [website-copy-part2.md](./website-copy-part2.md) | Website Part 2 copy brief for the homepage and `/reviewers`; source text only, not linked from the public site | feature branch |

Sales qualification questions and the kill test are no longer in this repo. They
live in `PRIVATE-EPI/SALES-QUESTIONS.md`, which is git-ignored: everything under
`internal/` is still world-readable on GitHub, so private material goes outside
the tree entirely.
