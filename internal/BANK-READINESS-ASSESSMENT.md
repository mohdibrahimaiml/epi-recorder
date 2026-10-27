# Bank / Insurer Readiness Assessment

_Recorded 2026-10-26. Internal planning note, not a public claim._

**Short answer:** not yet ready for production use at a bank or insurer. Good enough for a pilot, if it's set up the right way.

## How a bank evaluates a tool like this

Three teams have to say yes, and each asks different questions:

1. **Security and procurement:** "Is this vendor safe to let in?"
2. **Risk and compliance:** "Does this evidence actually prove what we need?"
3. **Technology:** "Does it fit our systems and our key management?"

## 1. The `.epi` file

| What the bank checks | Status | |
|---|---|---|
| Can a change be detected? | Strong: hashes, signature, step chain, tested against attacks | ✅ |
| Can it be checked without trusting EPI? | Yes: offline, open-source verifier, two implementations (Python and browser) | ✅ |
| When was it sealed, and by which key? | Yes since #175 (key-bound timestamp) | ✅ |
| Does it state its own limits? | Yes: lists what it didn't capture | ✅ |
| **Is the signing key protected?** | **No.** The key sits on the same machine as the AI agent. If that machine is hacked, the attacker can sign fake records. Banks expect keys in a hardware or cloud key vault (HSM/KMS). | ❌ blocker |
| **Is "human approved" real?** | **No.** The approval step can just be the agent's own claim; no human signs it. | ❌ blocker for approvals |
| **Was everything captured?** | Partly. The gateway can't record streaming AI calls (it returns 501), and the SDK route can miss calls. | ⚠️ |
| **Can the file lie when opened?** | The double-click viewer can show "0 mismatches" on a tampered file. Fix in progress. | ⚠️ in progress |
| Tested by someone independent? | No. Only our own red team. | ❌ |

**Verdict:** the core idea and cryptography are sound. Two gaps would fail a serious review: **key protection** and **real human sign-off**.

## 2. epilabs.org/verify

| Check | Status |
|---|---|
| Works in a browser, nothing uploaded | ✅ |
| Shows what the AI decided (#185) | ✅ once merged |
| Can't confirm *who* signed (always amber in a browser) | ⚠️ by design, but confusing |
| Details section full of jargon | ⚠️ |

**Verdict:** fine for a reviewer's quick check. Banks will still run `epi verify` themselves for the real decision.

## 3. EPI Cloud

| What procurement asks | Status |
|---|---|
| SOC 2 or ISO 27001 certificate? | ❌ none |
| Independent penetration test? | ❌ none |
| Single sign-on for their staff? | ❌ none |
| Data kept in the EU or India? | ❌ no choice of region |
| Contracts: SLA, data agreement (DPA), list of subcontractors? | ❌ not ready |
| Who runs it? | One person, on Cloudflare's free plan |
| Is the witness independent? | ⚠️ EPI runs it itself. Public anchoring (Rekor) helps, but the public checkpoint mirror is missing. |
| Can anyone pay? | ❌ no billing |
| Privacy design | ✅ Strong: only fingerprints, never the content |

**Verdict:** not ready for a bank to depend on. Security procurement would stop it at the first questionnaire.

## The way through

Banks don't need to trust EPI Cloud for the first deal. The model that works today:

```
AI vendor runs epi-recorder in its OWN systems
   → files stay in the vendor's / bank's own storage
   → bank reviewer checks them offline with the open-source verifier
   → EPI Cloud used only for fingerprint witnessing (no client data)
```

With no client data leaving their systems, most of the procurement questions above don't apply. That's how to get a pilot. Cloud custody comes later, once there's revenue to pay for certification.

## What to fix, in order

| # | Fix | Why |
|---|---|---|
| 1 | **Sign with a key vault** (AWS KMS, Azure Key Vault, HSM) instead of a key file on the agent's machine | First question any bank security team asks |
| 2 | **Real human sign-off**: the approver signs the approval with their own key | Otherwise "human approved" can't be trusted |
| 3 | **Merge the viewer fix** | A display that lies is the first thing a red team finds |
| 4 | **Gateway records streaming calls** | Completeness is the second question a bank asks |
| 5 | **Publish the witness checkpoint mirror** | Proves EPI can't quietly rewrite history |
| 6 | **Independent pen test of the file format and verifier** | Turns "we tested ourselves" into proof |
| 7 | Later, once revenue covers it: SSO, data region, SOC 2 | Only needed when banks store files in EPI Cloud |

Items 1–5 are code. #1 and #2 matter most.

---

# Cost breakdown: what can be done for free

Most of it can be done for free. Only certification and independent testing truly need money.

## ✅ Free: coding agents can build it fully

| Fix | How, for free |
|---|---|
| **1. Key-vault signing** | Build a "signer" plug-in supporting AWS KMS, Azure Key Vault, Google KMS and HSMs (PKCS#11). Test for free with **SoftHSM** (free software HSM) and **moto** (free fake AWS). Banks bring their own vault, so we never pay for one. |
| **2. Real human sign-off** | The approver signs the approval with their own key: a **passkey in the browser** (WebAuthn, free) or a CLI key. Verify checks it's a real person's signature, not the agent's claim. |
| **3. Viewer fix** | Already in progress. Just merge it. |
| **4. Gateway records streaming calls** | Pure code. Test with fake OpenAI and Anthropic responses. |
| **5. Public witness checkpoint mirror** | Publish each day's signed checkpoint to a public GitHub repo with a GitHub Action (free) and add an `epi` command to check it. |
| **6. SSO for EPI Cloud** | Code is free (OIDC/SAML). Test with **Okta's free developer account** and **Microsoft Entra's free tier**. |
| **7. EU / India data region** | Cloudflare offers EU data storage for D1 and R2 on the free plan. India isn't available yet. |
| **8. Billing** | Paddle costs nothing to set up; it takes a cut only when we're paid. The repo already has Paddle skills for this. |
| **9. Verify page in plain language** | Remove the jargon and explain the amber identity warning simply. |
| **10. Second independent verifier** (e.g. a small one in Go or Rust) | Two implementations that must agree is how formats earn trust. |

## 🟡 Free, but needs founder time more than code

| Item | Free route |
|---|---|
| **Security documents** (security policy, incident response, backups, data agreement and SLA templates) | Agents can draft them. Founder decides and signs. A lawyer review costs money but can wait. |
| **SOC 2 / ISO 27001 *readiness*** | Free open-source tools (e.g. **Comp AI**, **Probo**) plus agent-written policies get us "ready". The actual audit can't be skipped. |
| **Outside red-teaming** | A public **"Break the seal" challenge** on GitHub with a hall of fame. Security people do this for credit, not pay. Not a formal pen test, but real outside evidence. |

## ❌ Needs money (later, when revenue exists)

| Item | Rough cost |
|---|---|
| SOC 2 Type I audit | $5–15k |
| Professional pen test | $5–20k |
| Cyber / E&O insurance | ~$1–3k a year |
| Lawyer review of contracts | ~$1–3k |
| Cloudflare paid plan (if the free limits are hit) | $5/month |

## Recommended order (all free)

1. **Merge the viewer fix**: already in progress.
2. **Key-vault signing**: removes the biggest blocker.
3. **Human sign-off with passkeys**: makes "approved" mean something.
4. **Checkpoint mirror**: small, and proves the witness is honest.
5. **Streaming capture**.
6. **Break-the-seal challenge**: outside testing at zero cost.

After these six, the only blockers left on the technical side are the paid audits, and everything a bank's technical reviewer would check is covered.
