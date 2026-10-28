# EPI Cloud

**Status (v4.7.0):** private beta at `https://cloud.epilabs.org`.  
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

## Plans (product, not a public checkout)

Public site: Cloud is private beta ([epilabs.org/plans](https://epilabs.org/plans)). Entitlements in code (`cloud/src/lib/plans.ts`):

| Plan | Customers | Stored runs | Retention | Share links |
|------|-----------|-------------|-----------|-------------|
| Free | 1 | 50 | 30 days | 1 |
| Startup | 3 | 1,000 | 1 year | 3 |
| Growth | 15 | 10,000 | 7 years | unlimited |
| Design partner | 5 | 2,000 | 7 years | 10 |
| Enterprise | as entitled | as entitled | as entitled | as entitled |

Limits are per workspace and come from `PLAN_LIMITS` in
`cloud/src/lib/plans.ts`; a share link is a reviewer trust link, and expired
links do not count toward the limit. Verification is never limited or charged.
Speak in **customers**, not internal metric names.

Login for **epilabs.org Sign In** and the CLI is Cloud only.

Legacy hosted paths still on Render (not the account system, not required to record or verify): default `epi share` upload, MCP HTTP hosting, opt-in telemetry/pilot signup URLs, keep-warm cron, and some `/api/*` Cloudflare proxies. Cloud trust links are the customer path going forward.

---

## Founder ops (internal)

Setup, capacity, backups, and local dev are internal operator material. They are
deliberately not published on this site and are never linked from a public doc.
