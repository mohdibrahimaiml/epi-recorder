# EPI support and service levels

**Product version:** 4.6.2. Private beta status: [docs/CLOUD.md](./docs/CLOUD.md).

This page says what is supported, how to get help, and what to expect. It is
not a legal SLA with penalties — EPI Cloud is in private beta and there is no
paid tier with contractual uptime yet.

## What is supported

| Surface | Status | Help channel |
|---|---|---|
| `epi-recorder` open source (record / seal / `epi verify` / viewer) | Supported, MIT | GitHub issues |
| EPI Cloud (witness, trust links, Evidence Room) | **Private beta** — works, but expect changes | Email (below) + GitHub issues |
| Legacy hosted paths (`epi share` default upload, MCP on Render) | Best-effort, frozen | GitHub issues |
| Spec implementers (`docs/spec/`) | Supported via test vectors | GitHub issues |

## Response targets

| Channel | Target |
|---|---|
| Security reports (`SECURITY.md`) | Acknowledge in 5 business days, assessment in 7 |
| Founder contact (sales / pilot / deletion requests) | 1 business day (`website/plans.html` contact form or `mohdibrahim@epilabs.org`) |
| GitHub issues (bugs) | Triaged on a best-effort basis; security first, then data-loss, then features |

## What is not promised (beta honesty)

- No contractual uptime for EPI Cloud. Capacity math is public
  ([internal/cloud-ops.md](./internal/cloud-ops.md) is operator detail; limits
  are Cloudflare free-plan limits).
- No data-loss warranty on beta storage: keep your own copies of sealed `.epi`
  files. The sealed file is self-contained and verifiable offline — that is the
  durability story, not our servers.
- Legacy Render paths can cold-start and have no SLA
  ([docs/KNOWN_LIMITATIONS.md](./docs/KNOWN_LIMITATIONS.md)).

## Data requests

Deletion / export requests while there is no self-serve checkout: email
`mohdibrahim@epilabs.org` with the workspace name. See
[docs/DATA-RETENTION.md](./docs/DATA-RETENTION.md) for what is kept and for
how long.

## Escalation

If a private-beta issue blocks a regulated-customer deal, say so in the
subject line. Deal-blockers jump the queue — that is the point of the beta.

## Automated guards (free, always on)

- **Secret scanning + push protection** — on for this repo. Leaked keys are
  flagged; pushes containing secrets are blocked.
- **Dependabot security updates** — on. Vulnerable dependencies get PRs.
- **CodeQL** (Python + JavaScript) and **OpenSSF Scorecard** — run weekly via
  Actions; findings land in Security > Code scanning. The score is public;
  fix top findings before claiming posture.
