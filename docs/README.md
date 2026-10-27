# EPI documentation

**Product version in this repo: 4.6.3** (see `pyproject.toml`).  
PyPI can lag the git tag — confirm with `pip index versions epi-recorder` or `epi --version`.

**License:** MIT (root `LICENSE`).  
**Not legal advice. Not a certificate.** A `.epi` file is evidence a third party can re-check. It does not, by itself, certify EU AI Act conformity, SOC 2, ISO 27001, or any other regulatory outcome.

**Normal user (install, record, verify, share a file):** [USER-GUIDE.md](./USER-GUIDE.md).

If you are evaluating EPI for a bank, insurer, or auditor, start here:

1. This page (what exists, what it proves, where to read).
2. [What verification means](./VERIFICATION_CONTRACT.md).
3. [What the product does not do](./KNOWN_LIMITATIONS.md).
4. [Auditor path](./AUDITORS-GUIDE.md) — offline, no account.

This folder has four kinds of files. Only the first kind is current product documentation.

| Kind | What it is | How to treat it |
|------------------|-----------------|-----------------|
| **Product docs** | Recorder, Cloud, website — kept at 4.6.3 | Canonical |
| **How-to** | pytest, local review, AGT, identity | Canonical if linked below |
| **Legacy hosted** | ChatGPT / Claude / MCP on Render | Real leftover services, **not** EPI Cloud |
| **Spec / RFC / design** | Wire format, frozen RFCs, design notes | Not a user guide; version in the file may be historical |

`docs/index.html` on GitHub Pages redirects to the **file-format spec**, not this index. Product reading starts here.

---

## Three products, one repo

| Product | What it is | Canonical docs |
|---------|------------|----------------|
| **epi-recorder** | Open-source Python SDK + `epi` CLI. Records an agent run, seals a portable `.epi` file, verifies it **offline**. MIT. No account required. | [USER-GUIDE.md](./USER-GUIDE.md), root [README.md](../README.md), [CLI.md](./CLI.md) |
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
| **Normal user / developer** | **[USER-GUIDE.md](./USER-GUIDE.md)** | Root [README.md](../README.md), [CLI.md](./CLI.md), [FRAMEWORK-INTEGRATIONS-5-MINUTES.md](./FRAMEWORK-INTEGRATIONS-5-MINUTES.md) |
| **Risk / compliance / bank reviewer** | [EPI_MASTER_DOCUMENTATION.md](./EPI_MASTER_DOCUMENTATION.md) | [VERIFICATION_CONTRACT.md](./VERIFICATION_CONTRACT.md), [KNOWN_LIMITATIONS.md](./KNOWN_LIMITATIONS.md), [AUDITORS-GUIDE.md](./AUDITORS-GUIDE.md) |
| **Independent auditor** | [AUDITORS-GUIDE.md](./AUDITORS-GUIDE.md) | [VERIFICATION_CONTRACT.md](./VERIFICATION_CONTRACT.md), [THREAT_MODEL.md](./THREAT_MODEL.md), [WITNESS.md](./WITNESS.md) |
| **Vendor sharing a run with a customer** | [CLOUD.md](./CLOUD.md) § customer path | [WITNESS.md](./WITNESS.md), [STORAGE.md](./STORAGE.md), [CLI.md](./CLI.md) (`epi cloud`) |
| **Self-hosting capture/review** | [SELF-HOSTED-RUNBOOK.md](./SELF-HOSTED-RUNBOOK.md) | [CONNECT.md](./CONNECT.md) |
| **Spec implementer** | [spec/README.md](./spec/README.md), [spec/EPI-SPEC.md](./spec/EPI-SPEC.md) | [standards/aiuc-1-evidence.md](./standards/aiuc-1-evidence.md), [standards/scitt-predicate.md](./standards/scitt-predicate.md) |
| **Website / epilabs.org editor** | [WEBSITE.md](./WEBSITE.md) | `website/README.md` |

---

## 1. Product docs (keep current)

### epi-recorder

| Doc | Purpose |
|-----|---------|
| [USER-GUIDE.md](./USER-GUIDE.md) | What it does, where to use it, how to record / verify / share (includes the command cheat sheet) |
| Root [README.md](../README.md) | 60-second path |
| [CLI.md](./CLI.md) | Command reference (includes `epi cloud`) |
| [POLICY.md](./POLICY.md) | Policy schema and authoring |
| [KNOWN_LIMITATIONS.md](./KNOWN_LIMITATIONS.md) | Honest product boundaries |
| [VERIFICATION_CONTRACT.md](./VERIFICATION_CONTRACT.md) | Exact meaning of a verify result |
| [HUMAN-APPROVAL.md](./HUMAN-APPROVAL.md) | What a human-signed approval proves (and doesn't) |
| [AUDITORS-GUIDE.md](./AUDITORS-GUIDE.md) | Offline independent check |
| [THREAT_MODEL.md](./THREAT_MODEL.md) | In-scope / out-of-scope attacks |
| [FILE-SAFETY.md](./FILE-SAFETY.md) | Is a `.epi` safe to open? (receiver guide) |
| [ENTERPRISE-EVIDENCE-PLAYBOOK.md](./ENTERPRISE-EVIDENCE-PLAYBOOK.md) | Org process around evidence |
| [SELF-HOSTED-RUNBOOK.md](./SELF-HOSTED-RUNBOOK.md) | Self-host gateway / connect |
| [FRAMEWORK-INTEGRATIONS-5-MINUTES.md](./FRAMEWORK-INTEGRATIONS-5-MINUTES.md) | SDK wrappers |
| [ACTIONS.md](./ACTIONS.md) | Composite GitHub Actions that actually exist in this repo |

### EPI Cloud

| Doc | Purpose |
|-----|---------|
| [CLOUD.md](./CLOUD.md) | Product claims, customer path ([founder ops](../internal/cloud-ops.md) is internal) |
| [WITNESS.md](./WITNESS.md) | Hash-only receipts (self-hosted endpoint or Cloud) |
| [STORAGE.md](./STORAGE.md) | Customer-owned bucket (credentials never leave the recorder) |
| [DPA.md](./DPA.md) | Data processing addendum, starting point (counsel review) |
| [SUBPROCESSORS.md](./SUBPROCESSORS.md) | Who touches customer data and what they see |
| [DATA-RETENTION.md](./DATA-RETENTION.md) | What is kept, for how long, how to delete |

### Website

| Doc | Purpose |
|-----|---------|
| [WEBSITE.md](./WEBSITE.md) | Source of truth, deploy, what not to edit |
| `website/README.md` | Same rules, next to the HTML |

---

## 2. How-to (same product, narrower job)

| Doc | When |
|------|------|
| [CONNECT.md](./CONNECT.md) | Local review workspace (`epi connect open`) |
| [IDENTITY-ONBOARDING.md](./IDENTITY-ONBOARDING.md) | Keys, DID, pinning |
| [KEY-CUSTODY.md](./KEY-CUSTODY.md) | Signing key in an HSM / AWS KMS / Google Cloud KMS (`epi keys link`) |
| [SHARE-A-FAILURE.md](./SHARE-A-FAILURE.md) | Hand a sealed failure to another engineer |
| [PYTEST-AGENT-REGRESSIONS.md](./PYTEST-AGENT-REGRESSIONS.md) | `pytest --epi` |
| [AGT-IMPORT-QUICKSTART.md](./AGT-IMPORT-QUICKSTART.md) | Import a Microsoft AGT export into `.epi` |
| [AGT-EXPORT.md](./AGT-EXPORT.md) | Export `.epi` to AGT-shaped JSON (read-only; does not change the seal) |
| [TELEMETRY-PRIVACY.md](./TELEMETRY-PRIVACY.md) | Opt-in telemetry (off by default) |
| [RELEASING.md](./RELEASING.md) | How a PyPI release is published (signed tags required) |
| [ROADMAP.md](./ROADMAP.md) | Committed vs considering vs out of scope (no dates) |
| [MIGRATION.md](./MIGRATION.md) | What old `.epi` files and old recorders do under 4.6.3 |
| [GOVERNANCE.md](./GOVERNANCE.md) | Who decides, how releases work, commercial terms map |
| [EPI_MASTER_DOCUMENTATION.md](./EPI_MASTER_DOCUMENTATION.md) | Bank / procurement briefing |
| [EPI-CODEBASE-WALKTHROUGH.md](./EPI-CODEBASE-WALKTHROUGH.md) | Engineers mapping the repo |

---

## 3. Evidence support for EU Annex IV (not a certificate)

These files describe **templates, schemas, and a packing CLI**. Filling them in does not make a system EU AI Act conformant.

| Doc | Purpose |
|-----|---------|
| [EU-AI-ACT-EVIDENCE-PREP.md](./EU-AI-ACT-EVIDENCE-PREP.md) | What a `.epi` can contribute to an evidence file, and what it cannot |
| [ANNEX-IV.md](./ANNEX-IV.md) | `epi annex` CLI: nine JSON section templates you author and can sign |
| [standards/aiuc-1-evidence.md](./standards/aiuc-1-evidence.md) | AIUC-1 evidence *grouping* (`epi verify --aiuc1`), not a certificate |

There is **no** 113-article “compliance matrix” and **no** CEN-CENELEC implementation claim in this repo. Those documents were removed because they read like certification.

---

## 4. Legacy hosted MCP (Render — not EPI Cloud)

Still running for ChatGPT / Claude connectors. Optional. Not required to record or verify. Not the Cloud account.

| Doc | Purpose |
|-----|---------|
| [EPI-MCP-CONTRACT.md](./EPI-MCP-CONTRACT.md) | Tools, honesty limits, what the host does not send |
| [CHATGPT-PLUGIN.md](./CHATGPT-PLUGIN.md) | ChatGPT connection / deploy notes |
| [CLAUDE-CONNECTOR.md](./CLAUDE-CONNECTOR.md) | Claude connector copy |

---

## 5. Spec, RFC, design (not the product front door)

| Path | What it is |
|------|------------|
| [spec/](./spec/) | Language-agnostic `.epi` wire format |
| [api/](./api/) | Generated gateway OpenAPI spec (regenerate, don't hand-edit) |
| [adr/](./adr/) | Architecture decision records (why, not just what) |
| [standards/scitt-predicate.md](./standards/scitt-predicate.md) | SCITT predicate notes |
| [rfcs/agt-portable-evidence-mapping.md](./rfcs/agt-portable-evidence-mapping.md) | Frozen community RFC (May 2026; names v4.1.0) |
| [design/org-trust-bundle.md](./design/org-trust-bundle.md) | Internal design note for org trust bundles |
| [epi-verifier/](./epi-verifier/) | Independent JS helper; file-integrity needs JSZip; step-chain check is not done |
| [assets/SAMPLES.md](./assets/SAMPLES.md) | Sample `.epi` files for `epi verify` |
| `dashboard-v2/` | Browser-test screenshots, not a user guide |

---

## Contributing to docs

1. Edit the **canonical** file for that topic (linked from this index).
2. Do not invent paid features or claim certification. Check [KNOWN_LIMITATIONS.md](./KNOWN_LIMITATIONS.md) and [website/plans.html](../website/plans.html).
3. Keep product-doc version numbers at **4.6.3** until the next release bumps `pyproject.toml`. Frozen RFCs may keep their original version; label them frozen.
4. Customer docs must not contain admin keys or Cloudflare wrangler secrets (those stay in [../internal/cloud-ops.md](../internal/cloud-ops.md)).
5. After structural changes, update this index.
6. Do not add sales talk tracks or article-by-article “compliance” tables.
