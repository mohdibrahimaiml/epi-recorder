# EPI Usage Guide

## Quick Start

### 1. Install
```bash
pip install epi-recorder
```

### 2. Generate Keys (One-Time)
```bash
epi keys generate
```

This creates:
- `~/.epi/keys/default.key` — your private key (keep safe)
- `~/.epi/keys/default.pub` — your public key (can be shared)

### 3. Record a Workflow
```bash
epi record --out refund.epi -- python process_refund.py
```

Or programmatically:
```python
from epi_recorder.api import EpiRecorderSession

with EpiRecorderSession(output_path="refund.epi", goal="Process refund REF-100") as epi:
    epi.log_step("llm.request", {"model": "gpt-4", "prompt": "Should we approve?"})
    epi.log_step("llm.response", {"output": "Yes, under $500 threshold."})
```

### 4. Verify an Artifact
```bash
epi verify refund.epi
```

Output:
```
VERIFIED ✓
Trust Level: HIGH
Integrity Check:  PASSED — 4 files verified (SHA-256)
Signature Check:  VALID — Ed25519, signed by key 'default'
```

For machine-readable output:
```bash
epi verify refund.epi --json
```

---

## Verification Results — How to Read Them

### Exit Codes
| Exit Code | Meaning |
|-----------|---------|
| `0` | Verification passed. |
| `1` | Verification failed (tampering, bad signature, revoked key). |

### JSON Report Fields
```json
{
  "facts": {
    "integrity_ok": true,
    "signature_valid": true,
    "has_signature": true,
    "mismatches": {}
  },
  "identity": {
    "status": "UNKNOWN",
    "name": "default",
    "detail": "UNKNOWN: Identity not found in any trusted registry"
  },
  "trust_level": "HIGH",
  "decision": {
    "status": "PASS",
    "policy": "standard",
    "reason": "Integrity verified and identity not revoked"
  }
}
```

#### What Each Field Means

**`facts.integrity_ok`**
- `true` — All files inside the `.epi` archive match their SHA-256 hashes. Nothing was modified.
- `false` — One or more files were tampered with. Check `mismatches` for details.

**`facts.signature_valid`**
- `true` — The manifest was signed by the private key matching the embedded public key.
- `false` — The signature does not match. The manifest was altered after signing.
- `null` — No signature exists. The artifact is unsigned.

**`identity.status`**
- `KNOWN` — The signing key is recognized (via DID:WEB or local trust registry).
- `UNKNOWN` — The key is not recognized, but the signature is mathematically valid.
- `REVOKED` — The key has been revoked. Do not trust.

**`trust_level`**
- `HIGH` — Signed and intact. Suitable for legal/regulatory evidence.
- `MEDIUM` — Intact but unsigned. Good for internal records.
- `NONE` — Failed verification. Do not trust.
- `INVALID` — Key revoked. Do not trust.

**`decision.status`**
- `PASS` — The artifact meets the verification policy.
- `FAIL` — The artifact violates the policy (e.g., revoked key, integrity failure).

---

## DID:WEB Identity Binding (Optional)

Bind your artifact to a web identity so third parties can verify who signed it.

### 1. Host a DID Document
Create `https://yourcompany.com/.well-known/did.json`:
```json
{
  "id": "did:web:yourcompany.com",
  "verificationMethod": [
    {
      "id": "did:web:yourcompany.com#key-1",
      "type": "Ed25519VerificationKey2020",
      "publicKeyHex": "2152f8d19b791d24453242e15f2eab6cb7cffa7b6a5ed30097960e069881db12"
    }
  ]
}
```

Get your public key hex:
```bash
epi keys export default --format hex
```

### 2. Record with DID
```python
with EpiRecorderSession(
    output_path="refund.epi",
    did_web="did:web:yourcompany.com",
    auto_sign=True,
) as epi:
    ...
```

### 3. Verify
```bash
epi verify refund.epi
```

If the DID resolves, the output shows:
```
Identity: KNOWN (did:web:yourcompany.com)
```

If the server is offline, the output shows:
```
Identity: UNKNOWN
Signature: VALID
```

The artifact still verifies cryptographically — the identity is just unconfirmed.

---

## Common Scenarios

### "I got an .epi file from someone else. How do I verify it?"
```bash
epi verify their_file.epi --json
```

If `signature_valid=true` and `integrity_ok=true`, the file is authentic and unmodified. `identity=UNKNOWN` is normal if you don't have their key in your trust registry.

### "I want to check if a key has been revoked"
Create a revocation file:
```bash
echo "<public_key_hex>" > ~/.epi/trusted_keys/bad_actor.revoked
```

Any artifact signed by that key will now show `trust_level=INVALID`.

### "I need to verify offline"
```bash
epi verify artifact.epi
```

Offline verification works automatically. The only thing you lose is DID:WEB resolution (falls back to `UNKNOWN`).

### "I want a human-readable report file"
```bash
epi verify artifact.epi --report-out report.txt
```

---

## Troubleshooting

| Problem | Cause | Solution |
|---------|-------|----------|
| `signature_valid=false` | Manifest or payload was modified. | Re-create the artifact. Do not hand-edit `.epi` files. |
| `integrity_ok=false` | A file inside the archive was changed. | Re-create the artifact. |
| `identity=UNKNOWN` | No trust registry entry or DID resolution failed. | Normal for third-party artifacts. Add the public key to `~/.epi/trusted_keys/` if you trust the signer. |
| `trust_level=INVALID` | The key is on the revocation list. | Do not trust the artifact. Investigate why the key was revoked. |
| `No signature present` | The artifact was created with `auto_sign=false` or no key was available. | Sign it: `epi sign artifact.epi` |
