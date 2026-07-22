# EPI Enterprise Trust Profile

**Status:** Normative product profile for enterprise use of `.epi` evidence  
**Scope:** What EPI *actually* proves today (code-backed), what it does *not* prove,  
and a gap checklist for “evidence layer for AI agents / systems.”  
**Version:** 1.0 · **Date:** 2026-07-22 · **Code baseline:** epi-recorder v4.3.0 (+ local viewer/seal fixes)

This document is **descriptive of the current implementation**, not a marketing brief.  
Where something is incomplete, it is marked **PARTIAL** or **NOT IMPLEMENTED**.

Related (may be outdated in places): `docs/AUDITORS-GUIDE.md`, `docs/EPI-ENTERPRISE-REPORT.md`  
(the latter still describes some pre–envelope-v2 details — prefer this profile + source).

---

## 1. What a `.epi` file is (and is not)

### 1.1 Definition (accurate)

A `.epi` file is a **portable evidence container** for a recorded AI/agent workflow:

| Layer | Reality in code | Code reference |
|-------|-----------------|----------------|
| Outer container | **envelope-v2** (magic `<!--`, 128-byte header) wrapping a ZIP payload; or **legacy-zip** | `epi_core/container.py` (`EPI_CONTAINER_FORMAT_*`, `_EPI_ENVELOPE_HEADER_STRUCT`) |
| Inner ZIP | First entry `mimetype` = `application/vnd.epi+zip` (stored uncompressed) | `EPI_LEGACY_MIMETYPE` |
| Catalog | `manifest.json` (Pydantic `ManifestModel`) with `file_manifest` SHA-256 map | `epi_core/schemas.py` |
| Evidence body | Members hashed in `file_manifest` (e.g. `steps.jsonl`, env, analysis, …) | packing / `verify_integrity` |
| Authenticity | Optional Ed25519 signature on **canonical manifest hash** (excl. `signature`) | `epi_core/trust.py` `sign_manifest` / `verify_signature` |
| Time (optional) | RFC 3161 `.tsr` + `notarization.json` under `artifacts/notarization/` | `epi_core/notarize.py`; seal gated by `EPI_NOTARIZE` |
| Human review (optional) | `review.json` and/or `reviews/*` ledger | `epi_core/review.py`; browser Sign & Seal in `web_viewer/app.js` |
| Viewer | Offline HTML (packaged / `epi view`) | `web_viewer/*`, `epi_core/viewer_assets.py` |

### 1.2 What EPI **does** prove (when checks pass)

Given a verifier that implements the same algorithms:

1. **Integrity of listed members** — bytes of each path in `manifest.file_manifest` match the recorded SHA-256 (`EPIContainer.verify_integrity`).
2. **Authenticity of the manifest** — if `signature` + `public_key` present and valid: the signed fields (including that hash map and metadata) were signed by the private key corresponding to `public_key` (`verify_embedded_manifest_signature`).
3. **Structural / forensic facts** (when `epi verify` runs full pipeline) — sequence, step chain (`prev_hash`), completeness heuristics, optional SCITT receipt check (`epi_cli/verify.py` + `create_verification_report`).
4. **Known sealer identity (only if configured)** — `public_key` matches a key in the **local** trust registry `~/.epi/trusted_keys/*.pub` (or remote registry / DID hooks when used) → `identity.status == "KNOWN"` → `trust_level == "HIGH"` when integrity + sig also OK.

### 1.3 What EPI does **not** prove (even on HIGH / PASS)

| Claim | Why it is out of scope |
|-------|-------------------------|
| Free-text reviewer name is a real employee | Browser/CLI review stores a string; no IdP binding required |
| The agent “did the right thing” ethically | EPI records what was **captured**, not moral truth |
| Complete capture of all side effects | Only steps/files that were recorded and hashed exist |
| Seal-time wall clock is true absolute time | Unless notarization token is present **and** independently validated against a trusted TSA CA (viewer currently **displays** token time; full TSA PKI validation is not the same as display) |
| Browser Sign & Seal reuses the original org sealer | Default path uses a **device-local** Ed25519 seed (`localStorage`); private key never enters the `.epi`, but identity is a new key unless PEM is imported |
| Original file was updated when user signed in the viewer | Design: original is **immutable**; Sign & Seal **downloads** a new `*_reviewed.epi` |

---

## 2. Cryptographic and hash profile (precise)

### 2.1 Manifest signature

| Property | Value | Source |
|----------|--------|--------|
| Algorithm | Ed25519 | `cryptography` / noble-ed25519 in viewer |
| Signed preimage | SHA-256 of JCS-**style** canonical JSON of manifest **excluding** `signature` | `get_canonical_hash(..., exclude_fields={"signature"})` |
| Wire format | `ed25519:{derived_key_name}:{sig_hex}` | `sign_manifest` |
| `derived_key_name` | `sha256(utf8(public_key_hex))[:16]` | binds name to key material |
| `public_key` field | 32-byte raw public key as hex | embedded in manifest |

Canonical JSON is **JCS-compatible (RFC 8785-style)** via  
`json.dumps(..., sort_keys=True, separators=(',', ':'), ensure_ascii=False)` —  
**not** a claim of full RFC 8785 library compliance. See `docs/EPI-CANONICAL-HASH.md`.

### 2.2 Envelope-v2 header (128 bytes)

Struct (`epi_core/container.py`):

```text
<4s BB H Q 16s Q 32s 56s
magic="<!--" version=2 payload_format=0x01 flags=0
payload_length (ZIP only) | uuid | created_at_micros | payload_sha256 | reserved
```

Polyglot optional: after header, ` -->\n` + HTML + `\n<!-- EPI_ZIP_PAYLOAD_START -->\n` + ZIP.  
`payload_sha256` covers **ZIP bytes only**.

### 2.3 Review binding (CLI / Python path — stronger)

`ReviewRecord` v1.1 (`epi_core/review.py`):

- `artifact_binding` includes:
  - `workflow_id`
  - `manifest_sha256`
  - `manifest_signature` / `manifest_public_key`
  - `sealed_evidence_sha256` (hash over sorted `file_manifest` member digests; **excludes** mutable review/viewer-oriented treatment per docstring)
  - `container_format`
- `review_hash` over canonical review payload  
- optional `review_signature`: `ed25519:{pub_hex}:{sig_hex}` over `review_hash` bytes  
- append-only chain via `previous_review_hash` + `reviews/` members  

### 2.4 Review from browser Sign & Seal (Model A — additive)

`web_viewer/app.js` / `viewer/app.js` `buildReviewedArtifactBytes` (Model A):

- Requires full original `.epi` bytes (`archive_base64` / `archiveBytes` from `epi view`)
- Builds v1.1 `ReviewRecord` with `artifact_binding`, `review_hash`, `review_signature`
- Writes `reviews/<review_id>.json`, `review.json`, `review_index.json`
- **Does not** re-sign or rewrite `manifest.json` (org execution seal preserved)
- Review key: device-local seed or optional PEM (`epiResolveSigningSeed`)
- Verifiable with `epi verify <file> --review` (`verify_review_trust`)

Still not employee IdP identity — free-text `reviewed_by` is a claim; crypto binds the **review key**.

---

## 3. Trust levels and verify policies (code-accurate)

### 3.1 Trust registry

| Store | Default path | Contents |
|-------|--------------|----------|
| Signing keys | `~/.epi/keys/` (`EPI_KEYS_DIR` override) | `{name}.key` PEM PKCS#8, `{name}.pub` |
| Trusted identities | `~/.epi/trusted_keys/` | `{name}.pub` as **hex raw** public key (`KeyManager.trust_key`) |
| Revocation | same dir | `{name}.revoked` containing hex key |

CLI: `epi keys generate`, `epi keys trust <name-or-path>`, revoke via key manager APIs.

`TrustRegistry.verify_key_trust` order (exact, `epi_core/trust.py`):

1. Local `*.revoked`  
2. Local `*.pub`  
3. If `governance.did` is `did:web:…` → **network** DID resolution  
4. If `registry_url` set (default `https://epilabs.org/.well-known/epi-trust-registry.json` or `EPI_TRUSTED_REGISTRY_URL`) → **network** GET; failures are ignored (fall through)  
5. Else UNKNOWN  

**Accuracy note:** integrity + signature checks are offline. **Identity** may attempt network (DID / remote registry). Offline-only identity = rely on local `trusted_keys` and avoid DID-only trust.

### 3.2 `trust_level` (from `create_verification_report`)

| `trust_level` | Conditions (all must hold as stated) |
|---------------|--------------------------------------|
| **FAIL** | Identity status **MISMATCH** (impersonation heuristic) |
| **INVALID** | Identity **REVOKED** |
| **HIGH** | `integrity_ok` ∧ signature valid ∧ identity **KNOWN** |
| **MEDIUM** | integrity ∧ valid sig ∧ SCITT `transparency_ok` (unknown identity), **or** integrity ∧ **unsigned** (`signature_valid is None`) |
| **LOW** | integrity ∧ valid signature ∧ identity **UNKNOWN** (no SCITT upgrade) |
| **NONE** | Integrity failed and/or invalid signature path |

Note: **MEDIUM** is overloaded (unsigned-but-intact **or** signed+SCITT). Read `facts` + `identity`, not only the label.

### 3.3 Decision policies (`apply_policy`, default **`standard`**)

| Policy | PASS when | WARN / FAIL highlights |
|--------|-----------|-------------------------|
| **permissive** | Integrity OK (and not earlier hard fails) | Does not require trusted identity |
| **standard** (default) | Integrity OK; not revoked/mismatched; if signed+UNKNOWN → **WARN** | Unknown signer cannot silent-PASS |
| **strict** | Integrity OK + identity **KNOWN** + `completeness_ok` | Unknown identity → FAIL |

CLI: `epi verify file.epi --policy standard|strict|permissive`

### 3.4 Enterprise acceptance recommendation

| Use case | Recommended command | Accept if |
|----------|---------------------|-----------|
| Internal CI smoke | `epi verify --policy permissive` or `standard` | Integrity (+ sig if present) |
| Vendor / partner evidence | `epi verify --policy standard` | **PASS** only; **WARN** = do not accept without key exchange |
| Regulated / external audit | `epi verify --policy strict` + org trust store | **PASS** + document signer name from registry |
| Court / high assurance | strict + independent TSA validation + org key ceremony docs | Beyond single CLI exit code |

**First-run demo WARN is expected:** valid self-signature without `epi keys trust` → identity UNKNOWN → standard policy **WARN**. That is correct security behavior, not a product bug.

---

## 4. Operational modes (seal network / offline)

| Mode | How to run | Network at **seal** | Network at **verify/view** | Notarization |
|------|------------|---------------------|----------------------------|--------------|
| **Air-gapped seal** | `EPI_NOTARIZE=0` (and no remote SCITT/registry) | None required for core seal | None | Absent |
| **Default seal (current code)** | `EPI_NOTARIZE` defaults to **on** (`"1"`) in `container.py` | May POST to TSA (`EPI_TSA_URL`, default `https://freetsa.org/tsr`); OTS if CLI installed | None for core verify/view | `artifacts/notarization/*` if success |
| **Custom TSA** | `EPI_TSA_URL=https://…` | Org TSA | None | Same layout |
| **Demo fast path** | `epi demo` sets `EPI_NOTARIZE=0` | Offline-friendly | None | Off |

**Accurate product language:**

- **View** is offline-capable (local HTML).  
- **Verify integrity + signature** are offline-capable.  
- **Verify identity** may use network (DID:WEB, default remote trust registry URL) unless only local keys are used and remote fetch fails open to UNKNOWN.  
- **Seal** is **not** fully offline when notarization default is on.  
- Failure to reach TSA is non-fatal at seal (`Notarization unavailable … sealing without timestamp anchor`).

Viewer: §1 shows notarization **only if** data present (`web_viewer` + `epi_cli/view.py` injection). Display ≠ full TSA certificate chain validation.

---

## 5. Evidence lifecycle (immutable record + additive review)

```text
[record workspace] → pack/seal → signed .epi (execution evidence)
                              ↓
              optional notarization files inside ZIP
                              ↓
         human review (CLI v1.1 ledger OR browser Sign & Seal)
                              ↓
         NEW artifact or in-place review members (CLI paths)
         browser: NEW *_reviewed.epi download (original unchanged)
```

**Immutable rule (design intent):** sealed execution members listed in `file_manifest` are what integrity covers; reviews are **additive** metadata (`review.py` docstring: reviews do not rewrite original sealed execution files).

---

## 6. Implementation status checklist

Legend: **DONE** = present and usable · **PARTIAL** = present but incomplete for enterprise · **GAP** = needed for enterprise evidence layer

### 6.1 Core evidence object

| ID | Requirement | Status | Notes |
|----|-------------|--------|-------|
| E1 | Portable single-file container | **DONE** | envelope-v2 + legacy |
| E2 | Member integrity map | **DONE** | `file_manifest` |
| E3 | Offline integrity verify | **DONE** | `epi verify` / portal client-side |
| E4 | Ed25519 seal | **DONE** | `sign_manifest` |
| E5 | Canonical hash spec documented accurately | **DONE** | JCS-style, divergences listed |
| E6 | Single viewer/seal implementation | **PARTIAL** | `web_viewer` vs `viewer` still dual; CLI packs `web_viewer` |

### 6.2 Organizational identity

| ID | Requirement | Status | Notes |
|----|-------------|--------|-------|
| I1 | Generate org keys | **DONE** | `epi keys generate` |
| I2 | Local trust store | **DONE** | `epi keys trust` → `~/.epi/trusted_keys` |
| I3 | Revocation markers | **DONE** | `*.revoked` |
| I4 | Verify → HIGH for trusted keys | **DONE** | when registry configured |
| I5 | Default enterprise path = org key + trust on all verifiers | **PARTIAL** | Works if ops do it; not enforced by product defaults |
| I6 | HSM / non-exportable keys | **GAP** | File PEM / optional password only |
| I7 | IdP-bound human reviewer (SSO/OIDC) | **GAP** | Free-text / optional PEM in browser |
| I8 | Org key distribution package (trust bundle) | **PARTIAL** | Manual copy of `.pub` files |

### 6.3 Human attestation

| ID | Requirement | Status | Notes |
|----|-------------|--------|-------|
| R1 | Case-level Approve/Reject/Escalate UX | **DONE** | `web_viewer` attestation |
| R2 | Human-readable status in `review.json` | **DONE** | `status` + `notes` after Item 1 fix |
| R3 | Original artifact immutable on browser seal | **DONE** | download new file |
| R4 | Review bound to sealed evidence digest | **DONE** | Python v1.1 + browser Model A (`epiBuildArtifactBinding` / `epiBuildSignedReviewRecord`); original manifest signature preserved |
| R5 | Append-only multi-review ledger | **PARTIAL** | Python `reviews/` + chain; browser single `review.json` |
| R6 | Review crypto verify in `epi verify` | **PARTIAL** | review trust report paths exist; depends on v1.1 shape |

### 6.4 Time and transparency

| ID | Requirement | Status | Notes |
|----|-------------|--------|-------|
| T1 | RFC 3161 embed at seal | **DONE** | default on |
| T2 | Air-gapped seal switch | **DONE** | `EPI_NOTARIZE=0` |
| T3 | Viewer displays notarization | **DONE** | Item 2 |
| T4 | Full TSA token PKI validation in verify | **GAP** / **PARTIAL** | token present; not same as trusted CA validation productization |
| T5 | OTS/Bitcoin | **PARTIAL** | if `opentimestamps-client` installed |
| T6 | SCITT transparency | **PARTIAL** | code + governance fields; ops-dependent |

### 6.5 Completeness / decision-grade content

| ID | Requirement | Status | Notes |
|----|-------------|--------|-------|
| C1 | Step stream + kinds | **DONE** | `steps.jsonl` |
| C2 | Strict policy completeness gate | **DONE** | `completeness_ok` in strict |
| C3 | Published “Enterprise Evidence Profile” for required step kinds | **GAP** | this doc starts trust; content profile still open |
| C4 | Default secret redaction | **DONE** | redactor on by design in recorder paths |
| C5 | Integration coverage matrix (LangChain, etc.) vs profile | **PARTIAL** | integrations exist; not scored against a frozen profile |

### 6.6 Operations / legal

| ID | Requirement | Status | Notes |
|----|-------------|--------|-------|
| O1 | Offline verify/view | **DONE** | |
| O2 | Machine-readable verify JSON | **DONE** | `epi verify --json` |
| O3 | Legal hold / retention product | **GAP** | filesystem responsibility |
| O4 | Multi-artifact case file product | **PARTIAL** | connect/gateway; not core `.epi` atom |
| O5 | Threat model doc | **DONE** | `docs/THREAT_MODEL.md` (review for currency) |

---

## 7. Enterprise golden path (commands that match the code)

### 7.1 Org sealer setup (one-time per environment)

```bash
epi keys generate --name org-seal
# Distribute only the public material to verifiers:
epi keys trust org-seal
# On every auditor/CI machine that must get DECISION PASS under standard/strict:
#   copy org-seal.pub into process, then: epi keys trust ./org-seal.pub --name org-seal
```

### 7.2 Record + seal (air-gapped)

```bash
set EPI_NOTARIZE=0   # Windows PowerShell: $env:EPI_NOTARIZE="0"
# record via API/CLI → produces signed .epi when signing key present
epi verify artifact.epi --policy strict
# Expect PASS only if sealer key is trusted and completeness OK
```

### 7.3 Record + seal (with public/internal TSA)

```bash
set EPI_NOTARIZE=1
set EPI_TSA_URL=https://freetsa.org/tsr   # or enterprise TSA
epi verify artifact.epi --policy standard
epi view artifact.epi   # §1 Notarization panel if tokens embedded
```

### 7.4 Human attestation

**Preferred for enterprise binding:** Python/CLI review that uses `ReviewRecord.bind_to_artifact` + sign.

**Browser Sign & Seal:** fine for portable review UX; treat as **new artifact** + **possibly new key**; run:

```bash
epi verify *_reviewed.epi --policy standard
# Trust browser key pub (from manifest.public_key) only if that key is an accepted review key
```

---

## 8. Claims language (use in contracts and security reviews)

**Allowed (accurate):**

- “EPI produces a portable, hash-integrity-protected evidence file.”  
- “Ed25519 signatures bind a sealer public key to the manifest and file digests.”  
- “Verification of integrity and signature can be performed offline with open-source tooling.”  
- “Unknown signers yield WARN under the default standard policy.”  
- “Human review can be attached without rewriting the original sealed execution bytes (CLI design / browser download model).”

**Disallowed (inaccurate):**

- “EPI is fully RFC 8785 JCS compliant” (it is **JCS-style**; see hash doc).  
- “Sign & Seal updates the original file in place.”  
- “Approve is stored as cryptographic org identity of the named person.”  
- “Default seal requires no network” (notarization default on).  
- “HIGH trust without configuring trusted keys.”

---

## 9. Priority backlog (precision-ordered)

Derived only from **GAP/PARTIAL** above — not a wishlist.

| Priority | ID | Work item | Why |
|----------|-----|-----------|-----|
| **P0** | I5, I8 | Documented + scripted org trust bundle for CI/auditors | Without this, enterprise always sees WARN/LOW |
| **P0** | R4 | Align browser Sign & Seal with v1.1 `artifact_binding` + `review_hash` | Same assurance as CLI review |
| **P0** | E6 | Single seal/view source of truth; generate mirrors | Prevent dual-bug regressions |
| **P1** | T2 messaging | Product modes matrix in README/CLI help (done partially) | Procurement clarity |
| **P1** | T4 | Optional `epi verify` path: validate RFC 3161 against configurable TSA trust anchors | Time claims become evidence-grade |
| **P1** | C3 | Frozen “decision-grade” step/content profile + integration scores | Completeness is content, not only crypto |
| **P2** | I6 | HSM/PKCS#11 or cloud KMS sealer | Enterprise key custody |
| **P2** | I7 | IdP-bound reviewer claims | Human attestation identity |
| **P2** | O3–O4 | Retention/hold + multi-artifact case packaging | Legal ops |

---

## 10. Verification of this document against code

When updating this profile after code changes, re-check:

1. `epi_core/trust.py` — `create_verification_report`, `apply_policy`, `VerificationPolicy`  
2. `epi_core/container.py` — envelope constants, `EPI_NOTARIZE` default  
3. `epi_core/notarize.py` — `DEFAULT_TSA_URL`, embed paths  
4. `epi_core/review.py` — `build_artifact_binding`, ledger version  
5. `epi_core/serialize.py` / `docs/EPI-CANONICAL-HASH.md` — hash algorithm claims  
6. `web_viewer/app.js` — Sign & Seal + notarization UI behavior  
7. `epi_cli/verify.py` — default `--policy standard`  

---

## 11. Summary

**EPI’s `.epi` atom is the right architecture for an enterprise AI evidence layer:** portable, integrity-protected, offline-verifiable, with optional time and human review.

**Enterprise readiness is not “file format complete.”** It is:

1. **Known org keys** on every verifier (HIGH / strict PASS),  
2. **Review bound to sealed evidence** (CLI-class, not name-only),  
3. **Honest modes** (offline seal vs notary),  
4. **Content completeness** for decision-grade captures,  
5. **One implementation path** for seal/view.

Use §6–§9 as the living gap list; do not claim DONE items as GAP or vice versa without re-reading the cited modules.
