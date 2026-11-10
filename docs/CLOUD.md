# EPI Cloud

**Status (v4.9.0):** free self-serve workspace at `https://cloud.epilabs.org`.  
**Not:** a paywall on verification, a self-serve hosted-verification product, or a place that must hold every `.epi`.

Open-source `epi-recorder` stays complete without Cloud. Cloud is how a vendor **connects a computer**, **witnesses runs (hashes)**, and **shares selected files** with a customer reviewer.

## What Cloud holds vs what it does not

| Part | What EPI Cloud holds | What stays elsewhere |
|------|----------------------|----------------------|
| Witness | Hash-only receipts, ordered, signed; daily checkpoints | Full `.epi` bytes (unless you upload them) |
| Trust page | Metadata + files you attach to a share link | Reviewer's verification (browser or `epi verify`) |
| Evidence Room | Only runs the vendor *selects* (max 25 MB each) | Everything else |
| Customer bucket | Endpoint/bucket **metadata** and a vendor-reported health check | Credentials and objects — recorder-side only ([STORAGE.md](./STORAGE.md)) |
| Key registry | **Public** keys the vendor registered (`epi cloud keys push` accepts `*.pub` only) | Pins. A registry listing is informational. Reviewers still `epi keys trust` out of band |

The Worker never unzips an upload, never hashes a whole file in memory, and never sees customer bucket keys. Verification is always the reviewer's machine.

## Customer path (vendor → bank reviewer)

1. `epi cloud login` — terminal shows a short code; type it at `https://cloud.epilabs.org/auth/device` and pick the customer this computer records for. Saved to `~/.epi/cloud.json` (mode 0600). `epi auth login` is the same flow.
2. `epi demo` (or your own `record()` + `epi cloud push`) — seals and, when logged in, uploads a sample for that customer.
3. On the Cloud dashboard, create a **share / trust link scoped to that customer** and send it.
4. The reviewer opens the link (nothing to install) and/or downloads the evidence pack and runs `epi verify` offline.

Commands: [CLI.md](./CLI.md) (`epi cloud login|use|push|status`, `epi cloud keys …`, `epi cloud storage …`). Witness semantics: [WITNESS.md](./WITNESS.md).

## Plans (pricing note v3)

Public site: [epilabs.org/plans](https://epilabs.org/plans). Signing in creates
a free workspace; there is no approval step. We charge per **customer
relationship**, not per AI agent: agents are fair use on every plan.

| Plan | Price | Customer relationships | Evidence Room files | Retention | How |
|------|-------|------------------------|---------------------|-----------|-----|
| Free | $0 | 1 | 10 / year | 30 days | self-serve, 7-day share links |
| Design Partner (first 5) | $750 / month, locked 24 months, or $7,500 upfront | 5 | 2,000 / year | 7 years while subscribed | invoiced |
| Startup | $500 / month or $5,000 / year | 3 (+$150/month each, up to 6) | 1,000 / year | 1 year | Paddle |
| Growth | $2,000 / month or $20,000 / year | 15 (+$100/month each) | 10,000 / year | 7 years while subscribed | Paddle |
| Enterprise | from $40,000 / year | unlimited | custom | custom | annual contract |

Prices are USD and exclude taxes. Startup and Growth are paid by card in
**Billing** in the dashboard (Paddle); Design Partner, Enterprise and add-on
relationships are invoiced directly. Limits are per workspace. A share link is
a reviewer trust link and does not count toward the relationship limit.

Retention lasts while the subscription is active. After cancelling, the customer
has **90 days to export everything**; downgrading to Free applies that 90-day
window to existing files and never deletes them immediately. Evidence Room files
are counted per rolling year.

Usage is fair use: witnessed runs are reported in the dashboard and founder
usage, but there is no per-run limit and no 402 for usage. The witness route is
never gated; a report is always accepted and chained.

Verification is never limited or charged, and reviewers never pay.

The entitlement code lives with the hosted service. It is deliberately not in
this repository, so plan names, limits and pricing can change without a public
commit. The `epi cloud` client here only consumes the API.

Login for **epilabs.org Sign In** and the CLI is Cloud only.

Legacy hosted paths still on Render (not the account system, not required to record or verify): the one-shot fallback for `epi share` uploads, MCP HTTP hosting, opt-in telemetry/pilot signup URLs, keep-warm cron, and some `/api/*` Cloudflare proxies. `epi share` defaults to `https://cloud.epilabs.org`, which now serves `POST /api/share`; the fallback exists for clients older than the current release. Cloud trust links are the customer path going forward.

---

## Founder ops (internal)

Setup, capacity, backups, and local dev are internal operator material. They are
deliberately not published on this site and are never linked from a public doc.
