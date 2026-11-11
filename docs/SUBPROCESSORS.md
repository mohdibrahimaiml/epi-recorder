# EPI Labs sub-processors

**Product version:** 4.10.0. Last reviewed: 2026-10-22. Related:
[DPA](./DPA.md), [DATA-RETENTION](./DATA-RETENTION.md), [CLOUD](./CLOUD.md).

EPI Cloud runs on infrastructure EPI Labs rents. This page names every third
party that can touch customer data, what they see, and why. Open-source
record / seal / `epi verify` touch none of these — they run on your machine.

| Sub-processor | What it does for us | Customer data it can see |
|---|---|---|
| Cloudflare (Workers, D1, R2, Durable Objects, Pages) | Runs EPI Cloud: witness log, trust pages, Evidence Room, `epi share` uploads, login sessions | Witness receipts (hash-only), trust-link metadata, files you upload to the Evidence Room, `.epi` bytes you upload with `epi share` (that is what an upload is), OAuth account identifiers. The Worker never unzips an upload, never hashes a whole file in memory, and never sees customer bucket keys. |
| GitHub (repo, Actions, OAuth) | Source hosting, CI, release builds; one login option | OAuth profile identifiers at login; nothing from evidence files. CI builds release artifacts from public source. |
| Google (OAuth) | Alternative login option | OAuth profile identifiers at login only. |
| Paddle | Payment processing if you purchase | Purchase contact and billing data. Paddle never receives evidence files. Paid Cloud tiers are not sold through a public checkout yet. |
| Render (legacy) | Hosts legacy paths: the fallback `epi share` upload, MCP HTTP hosting, opt-in telemetry/pilot signup endpoints | **Full `.epi` bytes when an `epi share` upload falls back** (that is what an upload is); Cloud stores them by default. No account system - login moved to EPI Cloud. Offline verify never touches Render. |
| PyPI | Distributes `epi-recorder` | Nothing customer-specific. Downloads are public and anonymous. |

Customer-owned buckets (BYO storage) are **not** sub-processors: credentials
and objects stay recorder-side and EPI Labs never receives them
([STORAGE](./STORAGE.md)).

Changes: a new sub-processor is added here before it receives customer data.
Questions or objections: `mohdibrahim@epilabs.org`.
