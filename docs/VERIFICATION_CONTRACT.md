# EPI Verification Contract

**Product version:** 4.6.3. Product map: [README.md](./README.md).

## What This Document Is

This is the formal contract between EPI and anyone who verifies an `.epi` artifact. If you understand this document, you understand exactly what an EPI verification result means — and what it does **not** mean.

---

## The Three Tiers of Verification

EPI verification is layered. Each tier gives you a different guarantee.

### Tier 1 — Cryptographic (Always Available)
**What it needs:** The `.epi` file itself. Nothing else.

**What it proves:**
- The artifact has not been modified since it was signed.
- The signature was created by the private key corresponding to the public key embedded in the manifest.

**What it does NOT prove:**
- Who owns the private key.
- Whether the key has been compromised since signing.
- Whether the signer is trustworthy.

**How to check:**
```bash
epi verify artifact.epi --json
```

Look for:
```json
{
  "facts": {
    "signature_valid": true,
    "integrity_ok": true
  }
}
```

Cryptographically intact means **both** `integrity_ok` and `signature_valid` are `true`. `signature_valid` alone is not enough: an altered file can still show a valid signature over the unchanged manifest while `integrity_ok` is `false` (display-layer or payload hashes fail). Together those two facts are a **mathematical guarantee** about the sealed bytes — not a trust judgment about the signer.

---

### Tier 2 — Identity (Optional, Requires Network)
**What it needs:** The `.epi` file + a trust registry or DID:WEB resolver.

**What it proves:**
- The public key that signed the artifact is associated with a known identity (e.g., `did:web:example.com`).

**What it does NOT prove:**
- The identity is still valid (keys may have been rotated or revoked).
- The person operating the identity server is honest.

**Identity states** (JSON `identity.status`, and the `Status:` line the CLI prints):

| JSON status | CLI `Status:` line | Meaning |
|-------------|--------------------|---------|
| `KNOWN` | `KNOWN` | The signing key matches a key you pinned (`epi keys trust`, `--from-did`, trust bundle) or, under the standard policy only, a resolved DID:WEB. Strict never resolves DID:WEB: it needs a pin. |
| `LOCAL` | `LOCAL` | The key is on this computer, but not pinned. |
| `UNKNOWN` | `NOT_PINNED` | You have pinned no keys, and nothing else identifies the signer. The crypto is still valid; you just don't know who signed. |
| `UNKNOWN` | `NOT A KEY YOU TRUST (you have pinned: …)` | You have pinned at least one key and this file was sealed by a different one. The decision is FAIL under `standard` and `strict`. |
| `MISMATCH` | `MISMATCH` | Claimed identity does not match the signing key. |
| `REVOKED` | `REVOKED` | The key has been explicitly revoked (`epi keys revoke`). Revocation applies to the key, so every pin holding it shows `revoked` in `epi keys list`. Decision FAIL under `standard` and `strict`. Undo with `epi keys unrevoke <name>`. A *remote* revocation entry (public registry list) applies only to keys you have NOT pinned, and only under `standard` — strict never fetches the list. |

**Important:** `NOT_PINNED` is **not** a failure under the default policy. It means "I can verify the math, but I don't recognize the key." In a fresh environment with no pinned keys, every artifact shows it, and that's correct. Under `--policy strict` it is a FAIL. `NOT A KEY YOU TRUST` is different: you told EPI whose keys to expect, and this file is not one of them.

**Public registry listings are not pins.** EPI Labs publishes a public list of keys at `https://epilabs.org/.well-known/epi-trust-registry.json`, but that file is unsigned: anyone able to change it could add their own key. So a key that appears **only** there is reported as `LISTED … (informational; not a pin)`, its status stays `UNKNOWN` (WARN under `standard`, FAIL under `strict`), and `epi verify` prints `Registry: listed as "<name>" by epilabs.org (not a pin)`. Only keys you pinned yourself (or, under standard only, a resolved DID:WEB) count as `KNOWN`. A remote revocation entry is honoured only for keys you have NOT pinned, and only under `standard` (strict never fetches). `--policy strict` never fetches the list at all: strict is local-only and needs no network.

**`identity.pin_source` says where the trust came from.** `KNOWN` alone does not
tell you *how much* the verifier knows:

| `pin_source` | Meaning |
|---|---|
| `local_pin` | A key you pinned (`epi keys trust`, `--from-did`, trust bundle). A real pin. |
| `did_web` | The key appears in a `did:web` document **published by the file's own author** at their own domain. Self-assertion, not a pin. |
| `remote_registry` | The key appears in the unsigned public registry. Informational only. |
| `revoked` | Explicitly revoked. |
| `none` | Nothing recognised the key. |

Because `did:web` is self-assertion, `epi verify` does not describe it as
pinned. A DID-resolved identity prints:

```
✔ SEAL · SIGNER SELF-ASSERTED (DID)
  - Status:  SELF-ASSERTED (not pinned)
  - Trust:   The signer published this key in their own DID document at their
             own domain. That is self-assertion, not a pin you chose.
             Require an org pin with: epi verify --policy strict
```

The **policy decision** is unchanged by this: under `standard` a DID-resolved
identity is still `KNOWN` and the decision is still `PASS` (see the identity
table above). What changed is the wording — a green "IDENTITY PINNED" badge
for a signer who vouched for themselves was a false claim. Use
`--policy strict` when you need a pin you chose.

---

### Tier 3 — Policy (Optional, Human Layer)
**What it needs:** Everything above + a governance policy.

**What it proves:**
- The artifact meets the rules of your organization's policy (e.g., "must be signed by a key in the finance-team DID").

**What it does NOT prove:**
- The policy itself is correct or complete.

---

## Trust Levels

The CLI summarizes verification into a single `trust_level`
(`epi_core/trust.py` `build_verification_report`). Full list:

| Level | Condition | Meaning |
|-------|-----------|---------|
| `HIGH` | `integrity_ok=true` + `signature_valid=true` + `identity.status=KNOWN` | Cryptographically verified, sealer org-pinned. Claim-ready. |
| `MEDIUM` | `integrity_ok=true` + `signature_valid=true` + (`identity.status=LOCAL` or SCITT `transparency_ok=true` with unknown identity) | Seal OK; sealer is this machine's key (not org-pinned) or transparency-anchored but unpinned. Not claim-ready without a pin. |
| `LOW` | `integrity_ok=true` + `signature_valid=true` + `identity.status=UNKNOWN` | Valid signature but unknown sealer. Normal until `epi keys trust`. |
| `LOW` | `integrity_ok=true` + `signature_valid=null` (unsigned) | Integrity intact but unsigned. Ranks no higher than signed-unknown; anyone can strip a signature. Internal records only. |
| `NONE` | `integrity_ok=false` or `signature_valid=false` | Verification failed. Do not trust. |
| `FAIL` | `identity.status=MISMATCH` | Claimed identity does not match signing key — possible impersonation. Do not trust. |
| `INVALID` | `identity.status=REVOKED` | The signing key has been revoked. Do not trust. |

Policy decisions (`apply_policy`, `--policy`) are separate from trust:

| Policy `status` | Meaning |
|-----------------|---------|
| `PASS` | Meets the selected policy. |
| `WARN` | Valid seal but not claim-ready under this policy (e.g. unknown/local sealer, incomplete evidence such as a `tool.call` with no `tool.response`, or an absent step hash chain, under `standard`). Do not treat as claim acceptance. |
| `FAIL` | Policy requirements not met (e.g. unknown sealer or incomplete evidence under `strict`, integrity failure, revoked key, absent step hash chain under `strict`). |

### Sealed manifest: `policy_load_status` vs `policy`

Two manifest fields describe the sealed policy layer, and they mean different things:

- `policy_load_status` — **was a policy present at seal time?** `loaded` (a valid
  policy was found and used), `failed` (a policy file existed but was invalid),
  `absent` (no policy; heuristic-only run). It lets a verifier tell whether a run
  that *claims* policy enforcement actually had one.
- `policy` — the **formal evaluation** of the loaded policy: `policy_id`,
  `version`, `status` (`compliant` / `warning` / `violation`), the rule IDs
  evaluated, and `violation_count`. It is **present only when
  `policy_load_status == "loaded"`**; it is `null` for `absent` and `failed`.

### Low-severity observations are not faults

`analysis.json`'s `fault_detected` is `true` only for a **medium, high or
critical** primary finding. `low`/`info` findings (e.g. P11b "orphaned tool
call", P11c "unmatched LLM request") are **heuristic observations** — advisory
notes, not faults. All three surfaces agree on that: `analysis.json` reports
`fault_detected: false`, `epi analyze` prints "No anomalies detected" plus an
"Observations" line (never `FAULT DETECTED`), and the seal summary reports
"N low-severity observation(s) — not a fault" (never "no heuristic issues
flagged"). Issue #157 tracks the historical disagreement.

### VERIFY.txt states the sealing version

Every sealed `VERIFY.txt` names the **EPI version that produced the file**
(`producer_version`, read from the manifest) and the spec version, and gives the
correct command (`epi verify <file>`, with `python -m epi_cli verify <file>` as a
fallback) — never a hardcoded/stale version.

**The step hash chain is part of the claim.** `facts.chain_ok` is the chain
*check*; `facts.chain_present` says whether the steps carry any `prev_hash`
links at all. A file with no links is a **pre-chain** artifact: the chain
check passes *vacuously*, so nothing in it proves the recorded order — a
producer could reorder or drop steps and re-sign, and the file would still
verify. `strict` therefore FAILs such a file, and `standard` WARNs instead of
printing a clean PASS. Legacy pre-chain artifacts (spec < 4.4.x) are affected;
every current release seals a chained timeline.

Sprint rule: external/claim use requires `--policy strict` (unknown sealer FAILs).
`epi verify` exits `1` on FAIL and `0` on PASS **or WARN**, so scripts that
gate on the exit code must use `--policy strict`. The recommended
customer/bank/auditor command is:

```bash
epi verify FILE --policy strict --witness-log received.jsonl
# add --require-timestamp only if the vendor seals with a reachable timestamp service
```

### CLI headlines

The first line of the CLI report maps onto the decision and identity:

| Headline | Decision | When |
|----------|----------|------|
| `✔ SEAL · IDENTITY PINNED` | PASS | Identity `KNOWN`. |
| `✔ PASS` | PASS | Policy passed without a pinned identity (e.g. `permissive`). |
| `⚠ LOCAL SEALER · NOT ORG-PINNED` | WARN | Identity `LOCAL`. |
| `⚠ UNVERIFIED IDENTITY` | WARN | Identity `UNKNOWN` (`NOT_PINNED`) under `standard`. |
| `⚠ NOT IN YOUR WITNESS LOG · SIGNER PINNED` | WARN | Identity `KNOWN`; `--witness-log` given and this seal is not in it. |
| `⚠ SIGNER PINNED · SEE WARNING` | WARN | Identity `KNOWN`; another warning (e.g. clock) downgraded PASS. |
| `✘ SEAL FAIL — FILE ALTERED` | FAIL | `integrity_ok`, `chain_ok` or `sequence_ok` false. |
| `✘ SEAL FAIL — SIGNATURE INVALID` | FAIL | `signature_valid=false`. |
| `✘ FAIL — NOT A KEY YOU TRUST` | FAIL | Valid signature, identity `UNKNOWN`, other keys pinned. |
| `✘ FAIL — SEAL INTACT, REQUIREMENT NOT MET` | FAIL | Seal fine; another requirement failed (unpinned sealer under `strict`, revoked key (`Status: REVOKED`), incomplete evidence under `strict` (`Reason: Evidence incomplete (Strict Policy requires full telemetry coverage)`), `--require-timestamp` without a valid token, ...). `Reason:` names it. |

Real samples of each: [AUDITORS-GUIDE.md](./AUDITORS-GUIDE.md#real-samples).

### Browser verifier parity

Authoritative verify is `epi verify` (CLI). The browser verifier
(`website/js/epi-verify-core.js`) checks file hashes + Ed25519-over-manifest
only — no chain, SCITT, TSA validation, policy, `content_truncated`, or
header-transplant checks. Its labels map onto the CLI scale and must never
exceed the CLI result for the same bytes:

| Browser `trust_level` | CLI equivalent | Meaning |
|-----------------------|----------------|---------|
| `LOW` | `LOW` | Valid signature, identity unpinned. |
| `LOW` (unsigned, integrity ok) | `LOW` | Unsigned, integrity intact. Never above CLI. |
| `NONE` | `NONE` | Integrity/signature failed, or signature check could not run in this browser (pending — never a PASS). |

A browser `LOW` on an unsigned file equals CLI `LOW`, never above it.
Identity pinning (`KNOWN`) requires CLI key pin / trust bundle.

---

## Guarantees vs. Non-Guarantees

### Guaranteed
1. **Integrity:** If `integrity_ok=true`, no file inside the `.epi` archive has been modified.
2. **Authenticity:** If `signature_valid=true`, the manifest was signed by the holder of the corresponding private key.
3. **Offline verification:** Tier 1 works without network, without trust registries, and without the original signing machine.
4. **Deterministic hashing:** The same artifact always produces the same canonical hash (SHA-256 of JSON-canonicalized manifest).

### NOT Guaranteed
1. **Signer honesty:** EPI verifies that Alice signed it. It does not verify that Alice is telling the truth.
2. **Key security:** EPI does not know if the private key was stolen.
3. **Server availability:** DID:WEB resolution requires the server to be online. If the server is down, identity falls back to `UNKNOWN` — but the signature still verifies.
4. **Future-proofing:** EPI 4.6.3 uses Ed25519 and SHA-256. If these algorithms are broken in the future, old artifacts cannot be re-verified.

---

## The `signature_valid` Field

This is the most important field in the report. Here is exactly what each value means:

| Value | Meaning |
|-------|---------|
| `true` | The Ed25519 signature matches the **manifest hash**. That does not by itself prove the ZIP members or display layer are intact — check `integrity_ok` too. It also does not prove the signer is who you think; that is identity (pin the key). |
| `false` | The signature does not match the manifest hash. The manifest has been changed after signing, or the signature bytes are corrupted. |
| `null` | No signature is present. The artifact is unsigned. Integrity hashes may still be valid. |

---

## The `identity.status` Field

This is a **trust judgment**, separate from the cryptographic proof.

| Value | Meaning | Action |
|-------|---------|--------|
| `KNOWN` | The key is recognized by a trust registry or DID resolution. | Accept if you trust the registry. |
| `LOCAL` | The key matches a key on this machine, not an org pin. CLI `trust_level=MEDIUM`. | Internal use; pin for claims. |
| `UNKNOWN` (no pins; CLI prints `NOT_PINNED`) | The key is not recognized. The math is valid, but the signer is anonymous to this verifier. | Accept for internal use. Pin the sealer and use `--policy strict` for legal/regulatory use. |
| `UNKNOWN` (other keys pinned; CLI prints `NOT A KEY YOU TRUST`) | Valid signature by a key other than the one(s) you pinned. Decision FAIL under `standard` and `strict`. | Reject unless the vendor confirms a new key out of band and you pin it. |
| `MISMATCH` | Claimed identity does not match the signing key. CLI `trust_level=FAIL`. | Reject — possible impersonation. |
| `REVOKED` | The key has been explicitly revoked. | Reject. Do not trust. |

---

## Timestamps (`report["timestamps"]`)

`epi verify` checks RFC 3161 tokens **offline** against pinned TSA roots
(`epi_core/assets/tsa_roots/`, plus `--tsa-root` / `EPI_TSA_TRUST_ROOTS`
operator roots). No network fetch and no revocation (OCSP/CRL) check happen
during validation — a compromised TSA key or a revoked TSA certificate is
**not** detected; see Threat Model for the assumptions.

**What a `valid` token proves:** the exact bytes covered by the seal imprint
existed **no later than** `gen_time`, attested by a third party EPI Labs does
not control. It never proves "created at" — only an upper bound on existence.

**Seal imprint (`epi-tsa-imprint/v1`):** SHA-256 over JCS
`{scheme, workflow_id, created_at, public_key, files}`, where `files` is
`manifest.file_manifest` minus `viewer.html`, `VERIFY.txt`, `manifest.json`,
`mimetype` and the `artifacts/notarization|scitt|transparency/` prefixes
(`epi_core/notarize.py`). Seal time stamps this digest (not the canonical
manifest hash, which cannot be recomputed after sealing); the verifier
recomputes it from the final manifest. Tokens sealed before 4.6 carry no
`imprint_scheme` and report `legacy` (presence only, never a failure).

**Key binding:** `record()` takes the timestamp on its signed repack, after the
signing key exists, so the imprint's `public_key` field is the sealing key.
`notarization.json` records that key as `imprinted_public_key`; a `valid` seal
token then reads `sealed by key <fingerprint> no later than <gen_time>` and
`timestamps.key_binding` is `"key-bound"`.

Seals made before that change carry `imprinted_public_key: null`. Their token
still proves "these contents existed no later than T" and reports
`key_binding: "contents-only"`; they are not upgraded and never FAIL for it.

The recorded key is also checked against the file. If `imprinted_public_key`
differs from the manifest's `public_key` (or the file carries none), the seal
entry is `imprint_mismatch` — a key swapped after sealing cannot inherit the
timestamp, even when the swapped signature verifies.

**Seal statuses** (`timestamps.seal[]`, each `{url, status, gen_time,
tsa_subject, tsa_root, imprint_scheme, key_bound, imprinted_key_fingerprint}`):

| Status | Meaning | Decision effect |
|--------|---------|-----------------|
| `valid` | Imprint, CMS signature, critical timeStamping EKU, lifetime and chain to a pinned root all check out. | Sets `facts.timestamp_verified=true`. |
| `imprint_mismatch` / `bad_signature` / `cert_invalid` | Tampering (or a token that never covered these bytes). | **FAIL in every policy.** |
| `untrusted` | Signer chains to no pinned root. | Warning only; pin the root with `--tsa-root`. |
| `legacy` | Sealed before 4.6; imprint not recomputable. | Presence only; never changes the decision. |
| `absent` / `malformed` / `not_granted` | No usable token. | Neutral; never changes the decision. |

**Checkpoints** (`timestamps.checkpoints[]`, each `{index, event_count,
status, gen_time}`) validate the same way against the chain head each record
attests to. `imprint_mismatch` / `bad_signature` / `cert_invalid` prints
`CHECKPOINT TIMESTAMP INVALID` and FAILs; `untrusted` prints
`CHECKPOINT TIMESTAMP UNVERIFIED` as a warning.

**`earliest_verified`** is the oldest `gen_time` across valid seal and
checkpoint tokens. **`statement`** is one sentence exactly as strong as what
was checked (never "created at"): `sealed by key <fingerprint> no later than T`
when the imprint binds the signing key, `contents existed no later than T
(contents-only timestamp; signing key not bound)` for pre-change seals.
**`key_binding`** is `key-bound`, `contents-only` (valid token, no key
imprint) or `none`. If `manifest.created_at` is more than 10
minutes *after* `earliest_verified`, a clock warning is added (a creation
time later than the TSA's time is impossible for honest data).

**Opt-in strictness:** `epi verify --require-timestamp` FAILs unless at least
one seal-time token is `valid`. `VerificationPolicy.STRICT` does **not**
imply it (old strict artifacts carry no timestamps); pass the flag
explicitly when independent time attestation is required.

---

## Human approval (`report["human_approval"]`)

A `.epi` can carry a **human-signed approval**: a signed statement that a
specific person approved a specific decision, made with that person's own key.
Full details: [HUMAN-APPROVAL.md](./HUMAN-APPROVAL.md).

`human_approval.status` is one of:

| Status | Meaning |
|---|---|
| `verified` | A person approved what **this run** asked for: every sealed `agent.approval.request` has a human-signed `approve`, or (no sealed requests) a human-signed case-level approval covers the run. |
| `incomplete` | The run has sealed requests and at least one is not covered by a human-signed `approve` (and none was denied). The detail lists the missing ones. |
| `denied` | A human-signed approval **denied** one of the sealed requests. |
| `unverified` | Approvals exist but none counts: an unpinned key, the sealing key, an unsigned record, or an approval for a request not in this run when there are no sealed requests. |
| `none` | No approvals at all (any `agent.approval.response` steps are agent claims, and say so). |
| `failed` | At least one approval is `invalid`. Fail-closed: a tampered ledger blocks a run, it can never forge an approval. |

An approval whose `approval_id` is not a sealed `agent.approval.request` is
listed in `human_approval.approvals_not_in_run` and **never** makes the status
`verified` — it approves something this run did not ask for.
`human_approval.requests[]` carries each sealed request's `action` (taken from
the sealed step, not from the approval) and, when an approval covered it,
`approved_action` plus `action_mismatch` if the two differ.

Each entry in `human_approval.approvals` carries a `classification`:

| Classification | Meaning |
|---|---|
| `human_signed` | Valid signature; key pinned in **your** approver registry (`epi approvers add`) **with the `approver` role**; key ≠ the sealing key. |
| `signed_by_sealing_key` | Signed by the key that sealed the run — **not independent of the agent**. |
| `signed_unknown_key` | Valid signature, but the key is not a pinned approver. |
| `unsigned` | An approval is present with no signature. |
| `invalid` | Malformed, signature unverifiable, `review_hash`/`artifact_binding` mismatch, broken chain, or `approver.key_fingerprint` ≠ the signing key's fingerprint. |

`human_approval.requests` reports one result per sealed
`agent.approval.request` (`approved` / `denied` / `missing`).
`--require-human-approval` FAILs unless every request is `approved`, or the
latest human-signed **case-level** approval is `approve` with no request denied.
`human_approval.requirement_met` is `False` whenever the status is `failed` — a
tampered ledger can block a run, never satisfy it.

**What it proves:** a key you pinned as *that person's* approver signed this
exact artifact's decision. **What it does not prove:** that the person saw the
truth, that the key really belongs to the name you pinned, or that
`--policy strict` was satisfied — strict is about *who sealed*, not *who
approved*, and it deliberately does not imply `--require-human-approval`.

The identity shown is **your** registry entry for the signing key, not the name
written inside the file (a differing claim is printed as `(claimed: …)` with a
warning and does not invalidate the record).

---

## Summary

> EPI tells you **what** was signed and **when** (by hash), and **who** claims to have signed it (by key / DID). It does not tell you **why** they signed it or **whether they should have**.
