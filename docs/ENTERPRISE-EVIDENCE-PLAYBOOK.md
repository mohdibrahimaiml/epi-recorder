# Enterprise evidence playbook (one page)

**Audience:** security, platform, compliance.  
**Product rule:** same `.epi` bytes → same answer under policy.  
**Individuals** only need open + verify; this page is the **team process**.

---

## 1. What we keep

| Artifact | Keep | Why |
|----------|------|-----|
| `*.epi` sealed files | Yes — retention per policy | Portable evidence of the run |
| `epi verify --json` / `--report` output | Optional but recommended | Machine-readable audit trail |
| Signing private keys | Secrets manager / HSM path | Never in git |
| Trusted public keys | `~/.epi/trusted_keys/` or org bundle | Identity layer |

---

## 2. Seal every important agent run

```text
Agent / workflow completes
    → epi-recorder seals .epi (envelope-v2 + Ed25519)
    → store file next to job artifacts / object storage
```

CI sketch:

```yaml
# .github/workflows/epi-verify-samples.yml (see also examples/epi-verify.yml)
- run: pip install epi-recorder
- run: epi verify docs/assets/sample-hello.epi --policy standard
```

For your product pipeline: after tests that produce `.epi` files,

```bash
epi verify path/to/run.epi --policy standard
# exit non-zero on FAIL; WARN is intentional for unknown sealers
```

---

## 3. Know your sealers (identity)

Valid signature **does not** mean “our company” until the key is pinned.

**Once per sealer machine/org key:**

```bash
# From a known-good sealed file
epi keys trust path/to/prod-sealer-run.epi --name prod-sealer

# Or export/import a bundle of public keys only
epi keys bundle-export --out epi-trust-bundle.zip
# on auditor / CI runner:
epi keys bundle-import epi-trust-bundle.zip
```

Then:

```bash
epi verify path/to/run.epi --policy standard   # often PASS when sealer is known
epi verify path/to/run.epi --policy strict     # high assurance gate
```

| Policy | Typical use |
|--------|-------------|
| `standard` | Day-to-day: WARN if signer unknown but seal OK |
| `strict` | Release / regulated: unknown sealer fails |

**WARN on unknown sealer is intentional** — it forces a human process to pin keys, not a greenwash.

---

## 4. Share without losing the chain of custody

| Method | When |
|--------|------|
| Send the `.epi` file | Default — offline, no login |
| https://epilabs.org/verify | Counterparty has no install |
| `epi share` / portal | If you enable hosted collaboration |

Recipients should re-run `epi verify` (or hosted verify) on **the same bytes**.  
Do not treat embedded HTML alone as formal proof.

---

## 5. Incident / audit response (checklist)

1. Retrieve original `.epi` (not a screenshot).  
2. `epi verify file.epi --json --report verification_report.txt`  
3. Confirm integrity + signature.  
4. Confirm identity status (KNOWN vs UNKNOWN).  
5. Open timeline (`epi view` or forensic viewer) for what was decided.  
6. If disputed: third party re-runs verify; see [EVIDENCE-ALIGNMENT.md](EVIDENCE-ALIGNMENT.md).

---

## 6. Format contract

- Spec: [epi-spec SPEC v0.2](https://github.com/mohdibrahimaiml/epi-spec/blob/main/SPEC.md)  
- Alignment: [EVIDENCE-ALIGNMENT.md](EVIDENCE-ALIGNMENT.md)  
- Site deploy: [SITE.md](SITE.md)  
- Deeper trust docs: [ENTERPRISE-TRUST-PROFILE.md](ENTERPRISE-TRUST-PROFILE.md), [ENTERPRISE-TRUST-BUNDLE.md](ENTERPRISE-TRUST-BUNDLE.md)

---

## 7. What we deliberately do *not* claim

- That free-text “reviewer names” are government ID  
- That a valid seal proves the decision was *correct*  
- That browser self-check replaces CI or third-party audit  

We claim: **sealed, portable, re-checkable evidence of what was recorded.**
