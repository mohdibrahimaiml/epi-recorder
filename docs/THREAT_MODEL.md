# EPI Threat Model

## What This Document Is

This threat model describes what attacks EPI prevents, what attacks it does **not** prevent, and what assumptions the system relies on. If you are evaluating EPI for security, regulatory, or legal use, read this first.

---

## Assumptions

EPI's security guarantees depend on these assumptions being true:

1. **Ed25519 and SHA-256 remain secure.** If either algorithm is broken, signatures and integrity hashes become unreliable.
2. **The private key was not compromised at the time of signing.** EPI cannot detect a stolen key.
3. **The verifier checks the signature.** An unsigned artifact provides only integrity, not authenticity.
4. **The DID:WEB server is honest (when DID is used).** A malicious server can return any key it wants.

---

## Attacks Prevented

### 1. Payload Tampering
**Attack:** An attacker modifies `steps.jsonl`, `environment.json`, or any other file inside the `.epi` archive.

**Prevention:** The manifest contains SHA-256 hashes of every file. `epi verify` recomputes these hashes. Any mismatch fails integrity verification.

**Test:** Change one byte in `steps.jsonl` → `integrity_ok=false`.

---

### 2. Manifest Tampering
**Attack:** An attacker modifies `manifest.json` (e.g., changes `goal`, `created_at`, or `workflow_id`).

**Prevention:** The manifest is part of the signed payload. Changing any field invalidates the Ed25519 signature.

**Test:** Change `goal` in manifest → `signature_valid=false`.

---

### 3. Signature Replay
**Attack:** An attacker copies a valid signature from Artifact A onto Artifact B.

**Prevention:** The signature covers the SHA-256 hash of the specific manifest. A signature for Manifest A will not verify against Manifest B.

**Test:** Copy signature from one artifact to another → `signature_valid=false`.

---

### 4. Timestamp Forgery
**Attack:** An attacker changes `created_at` to make an artifact appear older or newer.

**Prevention:** `created_at` is included in the signed manifest hash. Any change invalidates the signature.

**Test:** Change `created_at` → `signature_valid=false`.

---

### 5. Private Key Leakage into Artifact
**Attack:** A bug causes the private key to be serialized into the `.epi` file.

**Prevention:** The signing code only embeds the **public** key. The private key never leaves the `~/.epi/keys/` directory. Automated tests scan artifact bytes for private key material.

---

### 6. Secret Leakage in Steps
**Attack:** An LLM prompt or API key is accidentally recorded in `steps.jsonl`.

**Prevention:** The redactor automatically detects and replaces:
- API keys (`sk-...`)
- Bearer tokens
- Email addresses
- Phone numbers
- SSNs and credit card numbers

**Limitation:** The redactor is regex-based. Novel secret formats may slip through.

---

### 7. Revoked Key Abuse
**Attack:** An attacker uses a stolen or retired key to sign a new artifact.

**Prevention:** The trust registry checks `~/.epi/trusted_keys/*.revoked`. If the public key is on the revocation list, `identity.status=REVOKED` and `trust_level=INVALID`.

---

## Attacks NOT Prevented

### 1. Compromised Signing Key
**Attack:** The signer's private key is stolen. The attacker creates a perfectly valid, signed artifact.

**Why EPI cannot prevent this:** EPI verifies that a signature is mathematically valid. It cannot know whether the person holding the private key is the legitimate owner.

**Mitigation:** Key rotation, HSM storage, revocation lists.

---

### 2. Malicious Signer
**Attack:** A legitimate signer creates an artifact with fabricated steps (e.g., fakes an LLM response).

**Why EPI cannot prevent this:** EPI proves **authenticity** (who signed it) and **integrity** (nothing changed after signing). It does not prove **accuracy** (whether the content is true).

**Mitigation:** Organizational policy, human review, cross-referencing with external logs.

---

### 3. DID:WEB Server Compromise
**Attack:** An attacker compromises the web server hosting the DID document and replaces the public key.

**Why EPI cannot fully prevent this:** DID:WEB resolves to a web server. If the server is compromised, the resolver returns the attacker's key, making the attacker's artifact appear as `KNOWN`.

**Mitigation:** Monitor DID documents for unexpected changes. Use local trusted keys as a fallback.

---

### 4. Algorithm Degradation
**Attack:** In 20 years, quantum computers break Ed25519. Old artifacts can no longer be trusted.

**Why EPI cannot prevent this:** All cryptographic systems have a shelf life. EPI 4.0.1 uses industry-standard algorithms that are secure today.

**Mitigation:** Re-sign important artifacts with newer algorithms as standards evolve.

---

### 5. Social Engineering
**Attack:** An attacker tricks a legitimate user into running `epi record` on malicious code.

**Why EPI cannot prevent this:** EPI records what happened. It does not judge whether it *should* have happened.

**Mitigation:** Training, approval workflows, policy enforcement.

---

## Trust Boundaries

```
+---------------------------------------------+
|  Attacker Controls                          |
|  - The .epi file (can try to tamper)        |
|  - The network (can try to intercept DID)   |
+---------------------------------------------+
              |
              v
+---------------------------------------------+
|  EPI Verifier Controls                      |
|  - Private keys (never leaves ~/.epi/keys)  |
|  - Trust registry (~/.epi/trusted_keys/)    |
|  - DID cache (~/.epi/cache/did_web/)        |
+---------------------------------------------+
              |
              v
+---------------------------------------------+
|  Guarantees                                 |
|  - Tampering is detected                    |
|  - Signature is mathematically valid        |
|  - Identity is resolved (if DID provided)   |
+---------------------------------------------+
```

---

## Summary Table

| Attack | Prevented? | Mechanism |
|--------|-----------|-----------|
| Payload tampering | Yes | SHA-256 file manifest |
| Manifest tampering | Yes | Ed25519 signature |
| Signature replay | Yes | Manifest-bound signature |
| Timestamp forgery | Yes | Signed `created_at` |
| Private key leak | Yes | Public key only in artifact |
| Secret leakage | Partial | Regex redaction |
| Revoked key reuse | Yes | Revocation list |
| Compromised key | No | Out of scope |
| Malicious signer | No | Out of scope |
| DID server compromise | Partial | Local fallback |
| Algorithm degradation | No | Time-bound guarantee |
| Social engineering | No | Out of scope |
