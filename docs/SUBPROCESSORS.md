# EPI Labs sub-processors

**Product version:** 4.6.2. Last reviewed: 2026-10-22. Related:
[DPA](./DPA.md), [DATA-RETENTION](./DATA-RETENTION.md), [CLOUD](./CLOUD.md).

EPI Cloud runs on infrastructure EPI Labs rents. This page names every third
party that can touch customer data, what they see, and why. Open-source
record / seal / `epi verify` touch none of these — they run on your machine.

| Sub-processor | What it does for us | Customer data it can see |
|---|---|---|
| Cloudflare (Workers, D1, R2, Durable Objects, Pages) | Runs EPI Cloud: witness log, trust pages, Evidence Room, login sessions | Witness receipts (hash-only), trust-link metadata, files you upload to the Evidence Room, OAuth account identifiers. The Worker never unzips an upload, never hashes a whole file in memory, and never sees customer bucket keys. |
| GitHub (repo, Actions, OAuth) | Source hosting, CI, release builds; one login option | OAuth profile identifiers at login; nothing from evidence files. CI builds release artifacts from public source. |
| Google (OAuth) | Alternative login option | OAuth profile identifiers at login only. |
| Paddle | Payment processing if you purchase | Purchase contact and billing data. Paddle never receives evidence files. Checkout is not self-serve while Cloud is in private beta. |
| Render (legacy) | Hosts legacy paths: default `epi share` upload, MCP HTTP hosting, opt-in telemetry/pilot signup endpoints | **Full `.epi` bytes when a vendor uses the default `epi share` upload** (that is what an upload is). No account system — login moved to EPI Cloud. Offline verify never touches Render. |
| PyPI | Distributes `epi-recorder` | Nothing customer-specific. Downloads are public and anonymous. |

Customer-owned buckets (BYO storage) are **not** sub-processors: credentials
and objects stay recorder-side and EPI Labs never receives them
([STORAGE](./STORAGE.md)).

Changes: a new sub-processor is added here before it receives customer data.
Questions or objections: `mohdibrahim@epilabs.org`.
