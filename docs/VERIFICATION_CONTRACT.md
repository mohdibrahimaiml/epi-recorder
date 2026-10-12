# EPI Verification Contract

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

If `signature_valid` is `true`, the artifact is cryptographically intact. This is a **mathematical guarantee** — not a trust judgment.

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
| `KNOWN` | `KNOWN` | The signing key matches a key you pinned (`epi keys trust`, `--from-did`, trust bundle) or a resolved DID:WEB. |
| `LOCAL` | `LOCAL` | The key is on this computer, but not pinned. |
| `UNKNOWN` | `NOT_PINNED` | You have pinned no keys, and nothing else identifies the signer. The crypto is still valid; you just don't know who signed. |
| `UNKNOWN` | `NOT A KEY YOU TRUST (you have pinned: …)` | You have pinned at least one key and this file was sealed by a different one. The decision is FAIL under `standard` and `strict`. |
| `MISMATCH` | `MISMATCH` | Claimed identity does not match the signing key. |
| `REVOKED` | `REVOKED` | The key has been explicitly revoked. Do not trust. |

**Important:** `NOT_PINNED` is **not** a failure under the default policy. It means "I can verify the math, but I don't recognize the key." In a fresh environment with no pinned keys, every artifact shows it, and that's correct. Under `--policy strict` it is a FAIL. `NOT A KEY YOU TRUST` is different: you told EPI whose keys to expect, and this file is not one of them.

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
| `WARN` | Valid seal but not claim-ready under this policy (e.g. unknown/local sealer under `standard`). Do not treat as claim acceptance. |
| `FAIL` | Policy requirements not met (e.g. unknown sealer under `strict`, integrity failure). |

Sprint rule: external/claim use requires `--policy strict` (unknown sealer FAILs).
`epi verify` exits `1` on FAIL and `0` on PASS **or WARN**, so scripts that
gate on the exit code must use `--policy strict`.

### CLI headlines

The first line of the CLI report maps onto the decision and identity:

| Headline | Decision | When |
|----------|----------|------|
| `✔ SEAL · IDENTITY PINNED` | PASS | Identity `KNOWN`. |
| `✔ PASS` | PASS | Policy passed without a pinned identity (e.g. `permissive`). |
| `⚠ LOCAL SEALER · NOT ORG-PINNED` | WARN | Identity `LOCAL`. |
| `⚠ UNVERIFIED IDENTITY` | WARN | Identity `UNKNOWN` (`NOT_PINNED`) under `standard`. |
| `✘ SEAL FAIL — FILE ALTERED` | FAIL | `integrity_ok`, `chain_ok` or `sequence_ok` false. |
| `✘ SEAL FAIL — SIGNATURE INVALID` | FAIL | `signature_valid=false`. |
| `✘ FAIL — NOT A KEY YOU TRUST` | FAIL | Valid signature, identity `UNKNOWN`, other keys pinned. |
| `✘ FAIL — SEAL INTACT, REQUIREMENT NOT MET` | FAIL | Seal fine; another requirement failed (unpinned sealer under `strict`, `--require-timestamp` without a valid token, ...). `Reason:` names it. |

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
4. **Future-proofing:** EPI 4.0.2 uses Ed25519 and SHA-256. If these algorithms are broken in the future, old artifacts cannot be re-verified.

---

## The `signature_valid` Field

This is the most important field in the report. Here is exactly what each value means:

| Value | Meaning |
|-------|---------|
| `true` | The signature matches the manifest hash. The artifact is authentic. |
| `false` | The signature does not match. The artifact has been tampered with OR the signature is corrupted. |
| `null` | No signature is present. The artifact is unsigned. Integrity may still be valid. |

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

**What the seal timestamp does not bind:** in the normal `record()` flow the
file is first packed unsigned and signed on the second pack, so at stamping
time `imprinted_public_key` is `None` and the imprint's `public_key` field is
null. A `valid` seal timestamp therefore proves "these contents existed no
later than T" — not "this signing key sealed them by time T". The signing key
is covered only when `imprinted_public_key` is non-null (an explicit key was
passed at stamp time); the statement line deliberately claims contents-only
existence in the default flow.

**Seal statuses** (`timestamps.seal[]`, each `{url, status, gen_time,
tsa_subject, tsa_root, imprint_scheme}`):

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
was checked (never "created at"). If `manifest.created_at` is more than 10
minutes *after* `earliest_verified`, a clock warning is added (a creation
time later than the TSA's time is impossible for honest data).

**Opt-in strictness:** `epi verify --require-timestamp` FAILs unless at least
one seal-time token is `valid`. `VerificationPolicy.STRICT` does **not**
imply it (old strict artifacts carry no timestamps); pass the flag
explicitly when independent time attestation is required.

---

## Summary

> EPI tells you **what** was signed and **when** (by hash), and **who** claims to have signed it (by key / DID). It does not tell you **why** they signed it or **whether they should have**.
