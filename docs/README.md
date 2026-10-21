# EPI documentation

**Product version in this repo: 4.6.2** (see `pyproject.toml`).  
PyPI can lag the git tag — confirm with `pip index versions epi-recorder` or `epi --version`.

**License:** MIT (root `LICENSE`).  
**Not legal advice. Not a certificate.** A `.epi` file is evidence a third party can re-check. It does not, by itself, certify EU AI Act conformity, SOC 2, ISO 27001, or any other regulatory outcome.

If you are evaluating EPI for a bank, insurer, or auditor, start here:

1. This page (what exists, what it proves, where to read).
2. [What verification means](./VERIFICATION_CONTRACT.md).
3. [What the product does not do](./KNOWN_LIMITATIONS.md).
4. [Auditor path](./AUDITORS-GUIDE.md) — offline, no account.

---

## Three products, one repo

| Product | What it is | Canonical docs |
|---------|------------|----------------|
| **epi-recorder** | Open-source Python SDK + `epi` CLI. Records an agent run, seals a portable `.epi` file, verifies it **offline**. MIT. No account required. | Root [README.md](../README.md), [USAGE_GUIDE.md](./USAGE_GUIDE.md), [CLI.md](./CLI.md) |
| **EPI Cloud** | Optional hosted layer at `https://cloud.epilabs.org`. Witness (hash-only receipts), trust pages, Evidence Room for files you *choose* to share. **Private beta** — not a self-serve hosted-verification subscription. Verification stays free. | [CLOUD.md](./CLOUD.md), [WITNESS.md](./WITNESS.md), [STORAGE.md](./STORAGE.md) |
| **Website** | Public site `https://epilabs.org`. Marketing, in-browser verify, plans, legal. Source of truth is `website/` only. | [WEBSITE.md](./WEBSITE.md) |

How the pieces fit: [ARCHITECTURE.md](../ARCHITECTURE.md).  
Enterprise briefing (CISO / risk / procurement): [EPI_MASTER_DOCUMENTATION.md](./EPI_MASTER_DOCUMENTATION.md).

Login for the website and the CLI is **EPI Cloud**. Older Render login is retired. Some legacy hosted paths (`epi share` default upload, MCP on Render, telemetry) still exist — see [CLOUD.md](./CLOUD.md). They are **not** the account system and **not** required to record or verify.

---

## What a `.epi` file proves — and what it does not

A sealed `.epi` proves: after sealing, these bytes were not altered, and they were signed by the private key that matches the public key in the manifest.

It does **not** prove: that every model call or tool call was captured, that the signer is who they claim until you pin their key, that policy rules are complete, or that a regulation is satisfied.

Seal, identity, and policy are three different checks. Details: [VERIFICATION_CONTRACT.md](./VERIFICATION_CONTRACT.md).

---

## Start by role

| You are… | Read first | Then |
|----------|------------|------|
| **Developer integrating the recorder** | Root [README.md](../README.md) | [USAGE_GUIDE.md](./USAGE_GUIDE.md), [CLI.md](./CLI.md), [FRAMEWORK-INTEGRATIONS-5-MINUTES.md](./FRAMEWORK-INTEGRATIONS-5-MINUTES.md) |
| **Risk / compliance / bank reviewer** | [EPI_MASTER_DOCUMENTATION.md](./EPI_MASTER_DOCUMENTATION.md) | [VERIFICATION_CONTRACT.md](./VERIFICATION_CONTRACT.md), [KNOWN_LIMITATIONS.md](./KNOWN_LIMITATIONS.md), [AUDITORS-GUIDE.md](./AUDITORS-GUIDE.md) |
| **Independent auditor** | [AUDITORS-GUIDE.md](./AUDITORS-GUIDE.md) | [VERIFICATION_CONTRACT.md](./VERIFICATION_CONTRACT.md), [THREAT_MODEL.md](./THREAT_MODEL.md), [WITNESS.md](./WITNESS.md) |
| **Vendor sharing a run with a customer** | [CLOUD.md](./CLOUD.md) § customer path | [WITNESS.md](./WITNESS.md), [STORAGE.md](./STORAGE.md), [CLI.md](./CLI.md) (`epi cloud`) |
| **Self-hosting capture/review** | [SELF-HOSTED-RUNBOOK.md](./SELF-HOSTED-RUNBOOK.md) | [CONNECT.md](./CONNECT.md) |
| **Spec / standards** | [spec/README.md](./spec/README.md), [spec/EPI-SPEC.md](./spec/EPI-SPEC.md) | [standards/aiuc-1-evidence.md](./standards/aiuc-1-evidence.md), [standards/scitt-predicate.md](./standards/scitt-predicate.md) |
| **Website / epilabs.org editor** | [WEBSITE.md](./WEBSITE.md) | `website/README.md` |

---

## Canonical docs (keep these current)

### epi-recorder

| Doc | Purpose |
|-----|---------|
| Root [README.md](../README.md) | 60-second path |
| [USAGE_GUIDE.md](./USAGE_GUIDE.md) | Install, record, verify |
| [CLI.md](./CLI.md) | Command reference (includes `epi cloud`) |
| [POLICY.md](./POLICY.md) | Policy schema and authoring |
| [KNOWN_LIMITATIONS.md](./KNOWN_LIMITATIONS.md) | Honest product boundaries |
| [VERIFICATION_CONTRACT.md](./VERIFICATION_CONTRACT.md) | Exact meaning of a verify result |
| [AUDITORS-GUIDE.md](./AUDITORS-GUIDE.md) | Offline independent check |
| [THREAT_MODEL.md](./THREAT_MODEL.md) | In-scope / out-of-scope attacks |
| [ANNEX-IV.md](./ANNEX-IV.md) | Annex IV *tooling* (evidence support, not a certificate) |
| [ACTIONS.md](./ACTIONS.md) | GitHub Actions |
| [ENTERPRISE-EVIDENCE-PLAYBOOK.md](./ENTERPRISE-EVIDENCE-PLAYBOOK.md) | Org process around evidence |
| [SELF-HOSTED-RUNBOOK.md](./SELF-HOSTED-RUNBOOK.md) | Self-host gateway / connect |
| [FRAMEWORK-INTEGRATIONS-5-MINUTES.md](./FRAMEWORK-INTEGRATIONS-5-MINUTES.md) | SDK wrappers |
| [AGT-IMPORT-QUICKSTART.md](./AGT-IMPORT-QUICKSTART.md) | Microsoft AGT import |

### EPI Cloud

| Doc | Purpose |
|-----|---------|
| [CLOUD.md](./CLOUD.md) | Product claims, customer path, founder ops |
| [WITNESS.md](./WITNESS.md) | Hosted and self-hosted witness |
| [STORAGE.md](./STORAGE.md) | Customer-owned bucket (credentials never leave the recorder) |

### Website

| Doc | Purpose |
|-----|---------|
| [WEBSITE.md](./WEBSITE.md) | Source of truth, deploy, what not to edit |
| `website/README.md` | Same rules, next to the HTML |

---

## Optional depth

| Doc | When |
|------|------|
| [EPI_MASTER_DOCUMENTATION.md](./EPI_MASTER_DOCUMENTATION.md) | Bank / procurement briefing |
| [EPI-CODEBASE-WALKTHROUGH.md](./EPI-CODEBASE-WALKTHROUGH.md) | Engineers mapping the repo |
| [DEMO-SCRIPT.md](./DEMO-SCRIPT.md) | Live demo talk track |
| [EU-AI-ACT-COMPLIANCE-MATRIX.md](./EU-AI-ACT-COMPLIANCE-MATRIX.md) | Regulatory *mapping* (not a certificate) |
| [TELEMETRY-PRIVACY.md](./TELEMETRY-PRIVACY.md) | Opt-in telemetry |
| [CONNECT.md](./CONNECT.md) | Local review workspace |
| [SHARE-A-FAILURE.md](./SHARE-A-FAILURE.md) | Sharing sealed failures |
| [IDENTITY-ONBOARDING.md](./IDENTITY-ONBOARDING.md) | Keys, DID, pinning |
| [RELEASING.md](./RELEASING.md) | How a release is published |

---

## Contributing to docs

1. Edit the **canonical** file for that topic (linked from this index).
2. Do not invent paid features or claim certification. Check [KNOWN_LIMITATIONS.md](./KNOWN_LIMITATIONS.md) and [website/plans.html](../website/plans.html).
3. Keep version numbers at **4.6.2** until the next release bumps `pyproject.toml`.
4. Customer docs must not contain admin keys or Cloudflare wrangler secrets (those stay in [CLOUD.md](./CLOUD.md) founder setup).
5. After structural changes, update this index.
