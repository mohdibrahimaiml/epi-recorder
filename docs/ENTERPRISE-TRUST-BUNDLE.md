# Enterprise trust bundle (org sealer + auditors)

Minimal ops path so `epi verify --policy strict` can **PASS** for known sealers,
and browser/CLI reviews verify with `epi verify --review`.

## Sealer machine (once)

```bash
epi keys generate --name org-seal
# Private: ~/.epi/keys/org-seal.key  (protect; never ship)
# Public:  ~/.epi/keys/org-seal.pub

# Export public keys only for auditors (preferred):
epi keys bundle-export --out org-trust-bundle.zip
# Or: epi keys bundle-export org-seal --out org-trust-bundle.zip
```

Record/seal workflows with that key as the default (or configured) sealer.

Optional air-gapped seal:

```bash
# Windows PowerShell
$env:EPI_NOTARIZE = "0"
```

## Auditor / CI machines

```bash
epi keys bundle-import org-trust-bundle.zip
# equivalent older path:
# epi keys trust path/to/org-seal.pub --name org-seal

epi verify artifact.epi --policy strict
```

Expected when the artifact was sealed with `org-seal` and completeness is OK:

- Integrity: Verified  
- Signature: Valid  
- Identity: KNOWN (`org-seal`)  
- DECISION: PASS  

Without trust, **standard** policy correctly yields **WARN** (unknown signer).

## Human review (additive)

Browser (`epi view` → Sign & Seal) or CLI review attaches a **separate** review signature.
Original org seal stays on the manifest.

```bash
epi verify artifact_reviewed.epi --review
```

Expect binding valid + review signature valid when untampered.

To treat a review key as known, trust its public key the same way (export from
`review_signature` / `ed25519:<pub>:<sig>` or generate a dedicated review PEM).

## See also

- `docs/ENTERPRISE-TRUST-PROFILE.md` — full claims, gaps, modes  
- `docs/EPI-CANONICAL-HASH.md` — hash algorithm (JCS-style)  
