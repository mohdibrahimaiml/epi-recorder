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
| Signing private keys | Secrets manager, or encrypted at rest with `EPI_KEY_PASSWORD` | Never in git; no HSM integration |
| Trusted public keys | `~/.epi/trusted_keys/` or org bundle | Identity layer |

---

## 2. Seal every important agent run

```text
Agent / workflow completes
    → epi-recorder seals .epi (envelope-v2 + Ed25519)
    → store file next to job artifacts / object storage
```

CI sketch (inline these steps in your own workflow file — there is no canned
`epi-verify-samples.yml` in this repo; the reusable unit is
`.github/actions/verify-epi`):

```yaml
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
# Public key from the sealer machine, handed over out of band
# (on the sealer: epi keys export > prod-sealer.txt; keep only the base64 key line)
epi keys trust prod-sealer.b64 --name prod-sealer
# or the sealer's did.json / PEM .pub file, or --from-did did:web:vendor.com

# Or export/import a bundle of public keys only
epi keys bundle-export --out epi-trust-bundle.zip
# on auditor / CI runner:
epi keys bundle-import epi-trust-bundle.zip
```

Then:

```bash
# Claim / insurer / bank / regulated acceptance (required):
epi verify path/to/run.epi --policy strict --witness-log received.jsonl
# add --require-timestamp only if the vendor seals with a reachable timestamp service

# Dev / local skim only (unpinned → WARN · UNVERIFIED IDENTITY, not claim-ready):
epi verify path/to/run.epi --policy standard
```

| Policy | Typical use |
|--------|-------------|
| `standard` | Day-to-day: WARN if signer unknown/local (valid seal · not org pin) |
| `strict` | Release / insurance / external audit: unknown sealer **FAIL** |

**WARN on unknown sealer is intentional** — it forces a human process to pin keys. Do not treat WARN as claim acceptance. `epi verify` exits `0` on WARN, so scripts must rely on the exit code only with `--policy strict`. Leave out `--witness-log` if the customer runs no witness receiver ([WITNESS.md](WITNESS.md)). Full re-sign forgery coverage: `tests/adversarial/test_resign_forgery.py`.

---

## 4. Share without losing the chain of custody

| Method | When |
|--------|------|
| Send the `.epi` file | Default — offline, no login |
| https://epilabs.org/verify | Counterparty has no install |
| `epi share` / portal | If you enable hosted collaboration |

Recipients should re-run `epi verify FILE --policy strict --witness-log received.jsonl` (or hosted verify for a quick look) on **the same bytes**.  
Do not treat embedded HTML alone as formal proof.

---

## 5. Incident / audit response (checklist)

1. Retrieve original `.epi` (not a screenshot).  
2. `epi verify file.epi --policy strict --witness-log received.jsonl --json --report verification_report.txt`  
3. Confirm integrity + signature.  
4. Confirm identity status (KNOWN vs UNKNOWN).  
5. Open timeline (`epi view` or forensic viewer) for what was decided.  
6. If disputed: third party re-runs verify; see [VERIFICATION_CONTRACT.md](VERIFICATION_CONTRACT.md).

---

## 6. Format contract

- Spec: [spec/EPI-SPEC.md](spec/EPI-SPEC.md)  
- Verify semantics: [VERIFICATION_CONTRACT.md](VERIFICATION_CONTRACT.md)  
- Site: [WEBSITE.md](WEBSITE.md)  
- Org keys: [IDENTITY-ONBOARDING.md](IDENTITY-ONBOARDING.md)

---

## 7. What we deliberately do *not* claim

- That free-text “reviewer names” are government ID  
- That a valid seal proves the decision was *correct*  
- That browser self-check replaces CI or third-party audit  

We claim: **sealed, portable, re-checkable evidence of what was recorded.**
