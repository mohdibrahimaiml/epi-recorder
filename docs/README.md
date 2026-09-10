# EPI documentation

**Start here** if you opened the `docs/` folder.  
Product version in this repo: **4.4.5**. PyPI may lag — check with `pip index versions epi-recorder` or pin git (see [PILOT.md](./PILOT.md)).

**License:** MIT (see root `LICENSE`).  
**Not legal advice:** evidence files support audits; they do not certify regulatory compliance by themselves.

---

## Start by role

| You are… | Read first | Then |
|----------|------------|------|
| **New developer** | Root [README.md](../README.md) (60-second path) | [USAGE_GUIDE.md](./USAGE_GUIDE.md), [CLI.md](./CLI.md) |
| **Policy & fault analysis** | **[POLICY-AND-FAULT-ANALYZER.md](./POLICY-AND-FAULT-ANALYZER.md)** | [POLICY.md](./POLICY.md) |
| **Enterprise / customer pilot** | **[PILOT.md](./PILOT.md)** | [ENTERPRISE-15-MINUTES.md](./ENTERPRISE-15-MINUTES.md), [ENTERPRISE-CAPABILITY.md](./ENTERPRISE-CAPABILITY.md) |
| **Auditor / independent verifier** | [AUDITORS-GUIDE.md](./AUDITORS-GUIDE.md) | [VERIFICATION_CONTRACT.md](./VERIFICATION_CONTRACT.md), [THREAT_MODEL.md](./THREAT_MODEL.md) |
| **EPI Labs operator** (hosted plans) | [OPERATOR-RUNBOOK.md](./OPERATOR-RUNBOOK.md) | [KNOWN_LIMITATIONS.md](./KNOWN_LIMITATIONS.md) |
| **Spec / standards** | [spec/README.md](./spec/README.md), [spec/EPI-SPEC.md](./spec/EPI-SPEC.md) | [standards/aiuc-1-evidence.md](./standards/aiuc-1-evidence.md), [standards/scitt-predicate.md](./standards/scitt-predicate.md) |
| **Integrations** | [FRAMEWORK-INTEGRATIONS-5-MINUTES.md](./FRAMEWORK-INTEGRATIONS-5-MINUTES.md) | [AGT-IMPORT-QUICKSTART.md](./AGT-IMPORT-QUICKSTART.md) |

---

## Pilot pack (curated)

For a guided pilot, use **only**:

1. [PILOT.md](./PILOT.md) — scope, install pin, success criteria  
2. Root [README.md](../README.md) — golden path  
3. [ENTERPRISE-15-MINUTES.md](./ENTERPRISE-15-MINUTES.md) — customer engineer path  
4. [ENTERPRISE-CAPABILITY.md](./ENTERPRISE-CAPABILITY.md) — honest shipped vs not shipped  
5. Optional: [AUDITORS-GUIDE.md](./AUDITORS-GUIDE.md)  
6. Operator only: [OPERATOR-RUNBOOK.md](./OPERATOR-RUNBOOK.md)

Full narrative (internal / investor): [COMPLETE-PRODUCT-GUIDE.md](./COMPLETE-PRODUCT-GUIDE.md).

---

## Canonical product docs (Tier A)

| Doc | Purpose |
|-----|---------|
| [USAGE_GUIDE.md](./USAGE_GUIDE.md) | Day-to-day install, record, verify |
| [POLICY-AND-FAULT-ANALYZER.md](./POLICY-AND-FAULT-ANALYZER.md) | How users use policy + fault analysis |
| [CLI.md](./CLI.md) | Command reference (v4.4.5) |
| [KNOWN_LIMITATIONS.md](./KNOWN_LIMITATIONS.md) | Honest product boundaries |
| [POLICY.md](./POLICY.md) | Policy schema and authoring detail |
| [ANNEX-IV.md](./ANNEX-IV.md) | Annex IV tooling |
| [ACTIONS.md](./ACTIONS.md) | GitHub Actions |
| [ENTERPRISE-TRUST-BUNDLE.md](./ENTERPRISE-TRUST-BUNDLE.md) | Org trust bundles |
| [ENTERPRISE-EVIDENCE-PLAYBOOK.md](./ENTERPRISE-EVIDENCE-PLAYBOOK.md) | Org process for evidence |
| [SELF-HOSTED-RUNBOOK.md](./SELF-HOSTED-RUNBOOK.md) | Self-host paths |
| [archive/SITE.md](./archive/SITE.md) | Public site source of truth (`website/`) |

---

## Optional deep dives

| Doc | When |
|------|------|
| [COMPLETE-PRODUCT-GUIDE.md](./COMPLETE-PRODUCT-GUIDE.md) | Journeys, tiers, pitch narrative |
| [DEMO-SCRIPT.md](./DEMO-SCRIPT.md) | Live demo talk track |
| [EU-AI-ACT-COMPLIANCE-MATRIX.md](./EU-AI-ACT-COMPLIANCE-MATRIX.md) | Regulatory mapping (evidence support, not a certificate) |
| [EPI-CANONICAL-HASH.md](./EPI-CANONICAL-HASH.md) | Hash details |
| [TELEMETRY-PRIVACY.md](./TELEMETRY-PRIVACY.md) | Telemetry opt-in |
| [CONNECT.md](./CONNECT.md) | Connect / review workspace |
| [SHARE-A-FAILURE.md](./SHARE-A-FAILURE.md) | Sharing sealed failures |

---

## Archive and historical (do not use for install)

| Path | Status |
|------|--------|
| [archive/](./archive/) | Historical reports and old checklists only |
| [archive/junk-docs/](./archive/junk-docs/) | **Ignore** for product decisions |
| Files with large “master / pivot / strategy” titles | Often **historical**; prefer this index |

If a file has a banner **“historical / not current”**, treat it as non-canonical.

---

## Website

| Path | Role |
|------|------|
| `website/` | **Production** public site source (`epilabs.org`) |
| `website-v2/` | **Sandbox redesign** — not deployed by default |
| [archive/SITE.md](./archive/SITE.md) | Sync rules (`python scripts/sync_website.py`) |

---

## Contributing to docs

1. Edit the **canonical** file for that topic (link from this index).  
2. Do not invent paid features; check [ENTERPRISE-CAPABILITY.md](./ENTERPRISE-CAPABILITY.md) and [KNOWN_LIMITATIONS.md](./KNOWN_LIMITATIONS.md).  
3. Keep **customer** docs free of admin keys and Render ops (those stay in OPERATOR-RUNBOOK).  
4. After structural changes, update this index.
