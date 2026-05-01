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

**Identity states:**

| Status | Meaning |
|--------|---------|
| `KNOWN` | The signing key matches a resolved DID:WEB or local trusted key. |
| `UNKNOWN` | No trust registry entry or DID resolution succeeded. The crypto is still valid — you just don't know who the signer is. |
| `REVOKED` | The key has been explicitly revoked. Do not trust. |

**Important:** `UNKNOWN` is **not** a failure. It means "I can verify the math, but I don't recognize the key." In a fresh environment with no trust registry, every artifact shows `UNKNOWN` — and that's correct.

---

### Tier 3 — Policy (Optional, Human Layer)
**What it needs:** Everything above + a governance policy.

**What it proves:**
- The artifact meets the rules of your organization's policy (e.g., "must be signed by a key in the finance-team DID").

**What it does NOT prove:**
- The policy itself is correct or complete.

---

## Trust Levels

The CLI summarizes verification into a single `trust_level`:

| Level | Condition | Meaning |
|-------|-----------|---------|
| `HIGH` | `integrity_ok=true` + `signature_valid=true` | Cryptographically verified and intact. Suitable for regulatory or legal submission. |
| `MEDIUM` | `integrity_ok=true` + `signature_valid=null` (unsigned) | Integrity intact but artifact is unsigned. Good for internal records, not for external evidence. |
| `NONE` | `integrity_ok=false` or `signature_valid=false` | Verification failed. Do not trust. |
| `INVALID` | `identity.status=REVOKED` | The signing key has been revoked. Do not trust. |

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
4. **Future-proofing:** EPI 4.0.1 uses Ed25519 and SHA-256. If these algorithms are broken in the future, old artifacts cannot be re-verified.

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
| `UNKNOWN` | The key is not recognized. The math is valid, but the signer is anonymous to this verifier. | Accept for internal use. Investigate for legal/regulatory use. |
| `REVOKED` | The key has been explicitly revoked. | Reject. Do not trust. |

---

## Summary

> EPI tells you **what** was signed and **when** (by hash), and **who** claims to have signed it (by key / DID). It does not tell you **why** they signed it or **whether they should have**.
