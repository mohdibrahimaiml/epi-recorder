# AIUC-1 Outreach Email Draft

---

## Subject
EPI Recorder — Reference Implementation for AIUC-1 Evidence Artifacts (Live Demo)

---

## Body

Hi [Name],

I'm reaching out regarding the AIUC-1 framework's need for verifiable technical evidence containers for AI agent audits.

We've built **EPI (Evidence Packaged Infrastructure)** — an open-source cryptographic evidence format specifically designed for AIUC-1's six trust domains. It is now live and ready for auditor evaluation.

**What EPI provides:**
- **Cryptographic integrity**: Every artifact is a signed ZIP with SHA-256 file manifests and Ed25519 signatures
- **Tamper evidence**: `prev_hash` chain linking every step; any modification breaks verification
- **Decentralized identity**: Signed artifacts anchor to `did:web:epilabs.org` — verifiable without trusting local config
- **SCITT transparency**: Optional inclusion receipts from append-only ledgers
- **AIUC-1 mapping**: Built-in `--aiuc1` flag maps evidence directly to your six domains (A-F)
- **GDPR redaction**: HMAC-SHA256 placeholders preserve audit value while protecting PII

**Live demo:**
- Verify artifacts in browser (no install): https://verify.epilabs.org
- Verify via CLI: `epi verify artifact.epi --aiuc1`
- DID identity: https://epilabs.org/.well-known/did.json
- Trust registry: https://epilabs.org/.well-known/epi-trust-registry.json

**What we'd like from AIUC-1:**
We noticed your website lists six trust domains but does not publish specific control IDs publicly. We'd love guidance on:
1. Which specific controls within each domain you'd want evidence artifacts to address
2. Whether a web-based verifier (no CLI install) meets Schellman auditor workflow needs
3. Any additional trust domain mappings you'd like to see

**Technical specs:**
- Repo: https://github.com/mohdibrahimaiml/epi-recorder
- License: MIT
- SCITT compatibility: IETF COSE_Sign1 with Ed25519
- DID method: W3C DID:WEB

We're targeting the July 15 framework update and would welcome your feedback on whether EPI can serve as a reference implementation for AIUC-1 evidence packaging.

Happy to jump on a call anytime that works for you.

Best,
[Your name]
[Your title]
https://epilabs.org

---

## Follow-Up (If No Response in 5 Days)

**Subject:** Re: EPI Recorder — Quick AIUC-1 domain mapping question

Hi [Name],

Quick follow-up — no pressure on timing.

One specific question that would help us align EPI with AIUC-1:

> Within your "Accountability & Transparency" domain, do you require evidence of:
> (a) human review sign-offs,
> (b) policy preservation, or
> (c) both?

EPI currently captures both in `review.json` and `policy.json`, but we want to ensure we're mapping to your actual requirements rather than guessing.

Thanks,
[Your name]

---

## Follow-Up (If No Response in 10 Days)

**Subject:** Re: EPI Recorder — One-line summary for your team

Hi [Name],

In one sentence: EPI is a free, open-source `.epi` file format that cryptographically seals AI agent execution traces so auditors can verify them without installing anything.

Live demo: https://verify.epilabs.org

If this isn't relevant for the July 15 update, no worries — just let us know if there's a better time to reconnect.

Best,
[Your name]
