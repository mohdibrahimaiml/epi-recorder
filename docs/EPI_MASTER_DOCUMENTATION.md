# EPI — enterprise briefing (v4.6.2)

**Product:** `epi-recorder` (open source) + optional **EPI Cloud** (private beta) + public site **epilabs.org**.  
**Container:** EPI Evidence Format (see [spec/EPI-SPEC.md](./spec/EPI-SPEC.md)).  
**Name:** EPI = **Evidence Packaged Infrastructure**.

This is the document to hand a bank, insurer, or auditor. If anything here disagrees with [VERIFICATION_CONTRACT.md](./VERIFICATION_CONTRACT.md) or [KNOWN_LIMITATIONS.md](./KNOWN_LIMITATIONS.md), those two files win.

It is **not** a certificate, a legal opinion, or a claim that EPI “makes you compliant.”

---

## 1. What you would be buying / adopting

### epi-recorder (always available)

A Python SDK and `epi` CLI that turns an AI agent run into a **portable `.epi` file**: a sealed, signed container a third party can verify **offline**, with no EPI account and no EPI server.

```
Agent workflow  →  epi-recorder (record, redact, seal)  →  recording.epi
                                                              │
                         epi verify / browser viewer  ←───────┘
                         (local; no upload required)
```

### EPI Cloud (optional, private beta)

A hosted layer at `https://cloud.epilabs.org` for vendors who need to **show a customer a run** without mailing files around:

- **Witness:** hash-only receipts of runs (not the full `.epi` by default).
- **Trust page:** a link a reviewer opens in a browser.
- **Evidence Room:** only the files the vendor *selects* to share (25 MB max per file).
- **Customer-owned storage:** full `.epi` retention can stay in the vendor’s own S3-compatible bucket. EPI Cloud does not receive those bucket credentials.

Open-source sealing and verification stay free. Cloud is not a paywall on `epi verify`.

### Website

`https://epilabs.org` — product site, in-browser verify, plans, legal. Accounts on the site sign in through EPI Cloud. Source: `website/` only ([WEBSITE.md](./WEBSITE.md)).

---

## 2. What a verify result means

Layered. Do not collapse them into one green check.

| Layer | Needs | Proves | Does not prove |
|-------|--------|--------|----------------|
| Integrity + signature | The `.epi` file only | Bytes unchanged since seal; signature matches the embedded public key | Who holds the private key; that capture was complete |
| Identity | File + **pinned** public key (`epi keys trust`) | That key is one you already accepted out of band | The person operating the key is honest forever |
| Policy / analysis | File + `epi_policy.json` / sealed analysis | The run against *those* rules | That the rules are the right rules |
| Witness (optional) | Witness log + pinned witness key | A third party recorded a hash at a time | That the original capture was complete |

Customer / auditor command:

```bash
pip install epi-recorder
epi verify case.epi --policy strict --witness-log received.jsonl
```

Rely on the exit code only with `--policy strict` (WARN exits 0 under the default policy). First-run **LOCAL / NOT_PINNED** identity is expected until the receiver pins the sender’s key. Full contract: [VERIFICATION_CONTRACT.md](./VERIFICATION_CONTRACT.md). Auditor walkthrough: [AUDITORS-GUIDE.md](./AUDITORS-GUIDE.md).

---

## 3. What we do not claim

Say these out loud in a security review. They are product facts, not caveats hidden in a footer.

- EPI does **not** prove that every LLM call, tool call, or human action was captured. The seal covers what was written into the file. Instrumentation gaps stay gaps. See [KNOWN_LIMITATIONS.md](./KNOWN_LIMITATIONS.md).
- EPI does **not** certify EU AI Act, SR 11-7, SOC 2, or any other regime. [EU-AI-ACT-EVIDENCE-PREP.md](./EU-AI-ACT-EVIDENCE-PREP.md) and [ANNEX-IV.md](./ANNEX-IV.md) are **evidence-support** (templates and packing), not mappings that claim coverage of the regulation.
- A listing in a public key registry is **not** a pin. Reviewers pin keys themselves.
- `epi-register` without `--service` embeds a **local, self-issued** SCITT receipt, not an independent ledger entry.
- Browser viewer crypto checks integrity/signature in-page; RFC 3161 timestamp **validation** is done by `epi verify`, not by the viewer (the viewer says so).
- EPI Cloud in 4.6.2 is **private beta**. Public plans page does not sell a hosted-verification subscription.
- Default `record()` timestamps attest that **contents existed no later than T**. They do not bind the signing key unless `imprinted_public_key` is present ([KNOWN_LIMITATIONS.md](./KNOWN_LIMITATIONS.md)).

---

## 4. Architecture (as shipped)

| Component | Role |
|-----------|------|
| `epi_recorder/` | SDK: `record()`, wrappers (`wrap_openai`, …) |
| `epi_core/` | Container, canonical hash, Ed25519, redaction, policy/fault analysis, TSA verify |
| `epi_cli/` | `epi` command: record, verify, view, policy, keys, witness, **cloud** |
| `web_viewer/` + `epi_viewer_static/` | Offline case UI baked into the file |
| `epi_gateway/` | Optional **self-hosted** capture/review (`epi gateway serve`) |
| `cloud/` | EPI Cloud Worker (Cloudflare): auth, witness, shares, artifacts, keys, storage target |
| `website/` | epilabs.org |
| `verify_portal/` | Legacy hosted verify/share API on Render. Login moved to Cloud. Still used for some `epi share` / MCP / telemetry paths ([CLOUD.md](./CLOUD.md)). |

Integrity model (short):

1. `record()` writes `steps.jsonl`; each step carries `prev_hash` of the previous step (`CHAIN_START` on step 0).
2. Seal writes member files, SHA-256 per file in `manifest.json`, embeds the viewer.
3. Manifest (public key included, signature field excluded) is hashed canonically and signed Ed25519.
4. `epi verify` recomputes hashes, chain, and signature locally.

Authoritative detail: [ARCHITECTURE.md](../ARCHITECTURE.md), [spec/EPI-SPEC.md](./spec/EPI-SPEC.md).

Typical members of a sealed file (names can vary with options; the spec is the contract):

```
recording.epi
├── manifest.json
├── steps.jsonl
├── environment.json
├── policy.json / policy_evaluation.json   (when policy ran)
├── analysis.json                          (when analysis ran)
├── review.json                            (when a human reviewed)
└── viewer.html                            (offline UI)
```

Do not treat example JSON in older slides as the wire format. Use the spec.

---

## 5. Policy and fault analysis

- Rulebook: `epi_policy.json`, created with `epi policy init`.
- Sealed evaluation is inspectable in the file; recount failures from `results`, not from a summary header (see known limitation on older 4.4.1–4.4.6 files).
- Heuristic fault passes are **diagnostics**, not a regulatory control set.
- Guide: [POLICY.md](./POLICY.md).

---

## 6. Sharing a run with a bank reviewer

Vendor:

```bash
epi cloud login          # device code at cloud.epilabs.org/auth/device
epi demo                 # or record your own workflow, then epi cloud push
```

Then create a **customer-scoped** share/trust link on the Cloud dashboard. The reviewer opens the link (nothing to install) or downloads the evidence pack and runs `epi verify` offline.

Witness receipts are hash-only. Full files in the Evidence Room are only what the vendor uploaded. Customer-bucket credentials never go to EPI Cloud ([STORAGE.md](./STORAGE.md), [CLOUD.md](./CLOUD.md)).

Free Cloud plan: **1 customer**. Paid plan numbers (when entitled): Startup 3 customers / 1,000 stored files (1-year retention); Growth 15 / 10,000 (7-year). Verification is not metered. Cloud checkout is not self-serve on the public site.

---

## 7. Developer integration (minimum)

```python
from epi_recorder import record, get_current_session

with record("demo.epi", goal="show the golden path"):
    s = get_current_session()
    s.log("tool.call", tool="lookup", id="A-1")
    s.log("tool.response", ok=True, balance=250)
    s.log("decision", action="approve", reason="within limit")
```

```bash
epi verify demo.epi --policy strict
epi view demo.epi
```

Secrets are redacted by default (`redact=True`). Everyday how-to: [USER-GUIDE.md](./USER-GUIDE.md). Command reference: [CLI.md](./CLI.md).

---

## 8. Where to go next

| Need | Doc |
|------|-----|
| Docs map | [README.md](./README.md) |
| Exact verify semantics | [VERIFICATION_CONTRACT.md](./VERIFICATION_CONTRACT.md) |
| Honest gaps | [KNOWN_LIMITATIONS.md](./KNOWN_LIMITATIONS.md) |
| Threat model | [THREAT_MODEL.md](./THREAT_MODEL.md) |
| Cloud ops / CPU / D1 | [CLOUD.md](./CLOUD.md) |
| Website editing | [WEBSITE.md](./WEBSITE.md) |
| EU evidence support (not a certificate) | [EU-AI-ACT-EVIDENCE-PREP.md](./EU-AI-ACT-EVIDENCE-PREP.md), [ANNEX-IV.md](./ANNEX-IV.md) |
