# EPI Threat Model

**Product version:** 4.6.3. Product map: [README.md](./README.md).

## What This Document Is

This threat model describes what attacks EPI prevents, what attacks it does **not** prevent, what assumptions the system relies on, and what risks a **receiver** takes when opening a file they did not create. If you are evaluating EPI for security, regulatory, or legal use, read this first — and if your question is "is this file safe to open?", start with [FILE-SAFETY.md](./FILE-SAFETY.md).

---

## Assumptions

EPI's security guarantees depend on these assumptions being true:

1. **Ed25519 and SHA-256 remain secure.** If either algorithm is broken, signatures and integrity hashes become unreliable.
2. **The private key was not compromised at the time of signing.** EPI cannot detect a stolen key.
3. **The verifier checks the signature.** An unsigned artifact provides only integrity, not authenticity.
4. **The DID:WEB server is honest (when DID is used).** A malicious server can return any key it wants.
5. **Recording does not depend on external timestamp authorities per call.** Per-call TSA anchoring was attempted and abandoned: a network round-trip to an outside authority in the path of every model call would make recorder reliability hostage to that authority's uptime. Forward security comes from heartbeat checkpoints (periodic TSA timestamps of the hash-chain head) plus seal-time notarization instead.

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

### 4. Post-Seal Timestamp Tampering
**Attack:** An attacker changes `created_at` **after sealing** to make an artifact appear older or newer.

**Prevention:** `created_at` is included in the signed manifest hash. Any change after sealing invalidates the signature.

**Scope — what this does NOT prevent:** a dishonest signer can write any `created_at` they like *before* signing. The signature proves the field was not altered after sealing; it does not prove the value was honest when written. Independent time evidence is the RFC 3161 token (next item) or a customer witness. Also note the 128-byte envelope header carries a redundant **unsealed** copy of the timestamp; authoritative readers use the signed manifest value ([KNOWN_LIMITATIONS.md](./KNOWN_LIMITATIONS.md)).

**Test:** Change `created_at` → `signature_valid=false`.

---

### 5. Backdating or Fabrication After the Fact
**Attack:** After a dispute starts, a vendor fabricates a run or backdates one — sealing data now but claiming it existed months ago.

**Prevention (only when a valid RFC 3161 token is present):** `epi verify` checks the seal-time and checkpoint tokens offline against pinned TSA roots. A valid token proves the imprinted bytes existed no later than the TSA's `gen_time`, attested by a third party the vendor does not control. A freshly fabricated run can only obtain a *new* timestamp — it cannot backdate one.

**Assumptions:** the TSA's private key was not compromised and its clock was honest (validation performs no revocation checks). Pre-4.6 artifacts carry legacy tokens that attest nothing checkable.

**Test:** `tests/test_tsa_validation.py` (tampered token → `bad_signature` → FAIL; re-signed payload drift → `imprint_mismatch` → FAIL).

### 6. Silent Re-seal After the Fact
**Attack:** A vendor seals a run, then quietly alters the file and re-signs it with the same key (which they control) before handing it over — the signature is valid, so nothing looks wrong.

**Prevention (only with a customer witness configured):** every seal is reported at seal time to an endpoint the customer controls (`epi-witness/v1`: workflow id, manifest and file hashes). `epi verify --witness-log` compares the handed-over file against the customer's independent record: a re-sealed copy that reuses a reported workflow id reports `DIFFERENT VERSION` and FAILs; one that was never reported shows `NOT IN WITNESS LOG` (WARN, FAIL under `--policy strict`).

**Limitation:** the witness only proves what was sent — the vendor can choose not to send a seal. A missing entry for a case the customer knows happened is itself evidence.

**Test:** `tests/test_seal_witness.py` (altered + re-signed file → `MISMATCH` → FAIL).

---

### 7. Private Key Leakage into Artifact
**Attack:** A bug causes the private key to be serialized into the `.epi` file.

**Prevention:** The signing code only embeds the **public** key. Automated tests scan artifact bytes for private key material.

**Where the key rests (two paths):**
- **CLI signing** (`epi record`, which seals on pack) loads the private key from `~/.epi/keys/` and never copies it into the artifact.
- **Browser Sign & seal** generates or imports a key *in the browser*: by default a 32-byte Ed25519 seed stored as plain-text hex in `localStorage` (`epi.viewer.signingSeed.v1`), or a user-pasted unencrypted PKCS#8 PEM. The seed is **never written into the `.epi`**, but at rest it is weaker than a permission-protected CLI key — see Receiver-side threat R4 and [FILE-SAFETY.md](./FILE-SAFETY.md).

The guarantee that holds for both paths: **no private key material is serialized into the artifact.** The weaker guarantee is *where the browser seed rests while you use it* — that is a key-custody risk (R4), not an artifact-leakage risk.

---

### 8. Secret Leakage in Steps
**Attack:** An LLM prompt or API key is accidentally recorded in `steps.jsonl`.

**Prevention:** The redactor automatically detects and replaces:
- API keys (`sk-...`)
- Bearer tokens
- Email addresses
- Phone numbers
- SSNs and credit card numbers

**Limitation:** The redactor is regex-based. Novel secret formats may slip through.

---

### 9. Revoked Key Abuse
**Attack:** An attacker uses a stolen or retired key to sign a new artifact.

**Prevention:** The trust registry checks `~/.epi/trusted_keys/*.revoked`. If the public key is on the revocation list, `identity.status=REVOKED` and `trust_level=INVALID`.

---

### 10. Agent Self-Approval (mitigated)

**Attack:** the agent (or whoever runs it) writes `agent.approval.response`,
`record(approved_by=...)`, or a review signed with its own sealing key, and a
screen presents that as "a person approved this".

**Defence:** an approval counts as `human_signed` only when it is signed with a
key pinned in the verifier's **approver** registry (`epi approvers add`) **and**
that key differs from the run's sealing key. An approval signed by the sealing
key is reported `signed_by_sealing_key` — "not independent of the agent" — and
an unpinned key is `signed_unknown_key`. The sealing-key rule is checked before
the registry, so pinning the agent's key as an approver does not help. Agent
approval steps are labelled "reported by the agent (not signed by a person)"
wherever the CLI prints them. The gateway approval link (a URL click) is
likewise unsigned and is not a human-signed approval. See
[HUMAN-APPROVAL.md](./HUMAN-APPROVAL.md).

**Residual:** a person who pins the wrong key pins the wrong identity — pinning
is a human step. And a pinned approver who is coerced still signs.

### 11. Step Reordering / Timeline Tampering
**Attack:** A producer (or a re-signing attacker) reorders the recorded steps,
or drops one, so the evidence no longer reflects what actually happened.

**Prevention:** Each step carries `prev_hash`, the canonical hash of the
previous step; step 0 carries the genesis marker `CHAIN_START`. Verification
recomputes the whole chain, so a reordered, dropped or altered step breaks it
(`chain_ok=false` → `SEAL FAIL`). A genesis marker at an index > 0 is reported
as a chain restart (possible truncation).

**Scope:** the chain only helps if there **is** one. A pre-chain artifact — one
whose steps carry no links at all — makes the check pass *vacuously*, and
nothing in it proves the order. `facts.chain_present` reports this, `--policy
strict` FAILs such a file, and `standard` WARNs rather than printing a clean
PASS. Current releases always seal a chained timeline.

**Test:** `tests/adversarial/test_chain_policy.py`,
`tests/adversarial/test_completeness.py`, `tests/adversarial/test_integrity.py`.

---

## Attacks NOT Prevented

### 1. Compromised Signing Key
**Attack:** The signer's private key is stolen. The attacker creates a perfectly valid, signed artifact.

**Why EPI cannot prevent this:** EPI verifies that a signature is mathematically valid. It cannot know whether the person holding the private key is the legitimate owner.

**Mitigation:** Keep the key in an HSM or cloud KMS so it can't be copied off the agent host ([KEY-CUSTODY.md](./KEY-CUSTODY.md): `epi keys link`, `EPI_REQUIRE_EXTERNAL_KEY=1`). An attacker on the host can still ask the vault to sign while they hold access, so the vault's own audit log is the record of what was signed. Key rotation and revocation lists cover the rest.

---

### 2. Malicious Signer
**Attack:** A legitimate signer creates an artifact with fabricated steps (e.g., fakes an LLM response).

**Why EPI cannot prevent this:** EPI proves **authenticity** (who signed it) and **integrity** (nothing changed after signing). It does not prove **accuracy** (whether the content is true).

**Mitigation:** Organizational policy, human review, cross-referencing with external logs.

---

### 3. DID:WEB Server Compromise
**Attack:** An attacker controls the web server hosting the DID document and
replaces the public key — or simply publishes their own DID document.

**Why EPI cannot fully prevent this:** DID:WEB resolves to a web server. The
server is chosen by the *file's author*, not by the verifier. Under the
default (`standard`) policy a DID-resolved key makes `identity.status = KNOWN`,
and a file that is entirely attacker-authored therefore verifies as
**PASS / KNOWN**.

The red team measured this end to end: an artifact signed with an
attacker-generated key, declaring `did:web:attacker.example`, whose DID
document lists that same key, produced

```
✔ SEAL · IDENTITY PINNED      DECISION: PASS      exit code 0
```

**Fixed (wording).** The *policy* decision is unchanged — it is a documented
trade-off in `docs/VERIFICATION_CONTRACT.md` — but the report no longer
describes a self-asserted identity as pinned:

```
✔ SEAL · SIGNER SELF-ASSERTED (DID)
  - Status:  SELF-ASSERTED (not pinned)
  - Trust:   The signer published this key in their own DID document at their
             own domain. That is self-assertion, not a pin you chose.
             Require an org pin with: epi verify --policy strict
```

`identity.pin_source` now reports the source explicitly (`local_pin`,
`did_web`, `remote_registry`, `revoked`, `none`) so machine consumers can
tell a real pin from self-assertion.

**Residual:** `--policy strict` remains the defence, and it never resolves a
DID at all (strict is local-only). Two further notes:

- Under `standard`, resolving a DID makes an **outbound request to a host the
  file chose**. There is no host allowlist, so a malicious artifact can point
  the verifier at an arbitrary destination (verifier IP/UA disclosure, and an
  SSRF pivot towards internal ranges).
- `strict` forces `registry.offline`, but the SCITT service key fetch is
  *not* covered by that flag — see the SCITT entry below.

---

### 4. Algorithm Degradation
**Attack:** In 20 years, quantum computers break Ed25519. Old artifacts can no longer be trusted.

**Why EPI cannot prevent this:** All cryptographic systems have a shelf life. EPI 4.6.3 uses Ed25519 and SHA-256, which are industry-standard algorithms that are secure today.

**Mitigation:** Re-sign important artifacts with newer algorithms as standards evolve.

---

### 5. Social Engineering
**Attack:** An attacker tricks a legitimate user into running `epi record` on malicious code.

**Why EPI cannot prevent this:** EPI records what happened. It does not judge whether it *should* have happened.

**Mitigation:** Training, approval workflows, policy enforcement.

---

## Receiver-Side Threats (you received a file you did not create)

The sections above cover **sender-side** attacks (tampering with a real file).
A receiver faces a different set: the file itself may be the weapon. Read
[FILE-SAFETY.md](./FILE-SAFETY.md) for the full receiver guide; the threat
model summary is:

### R0. Malicious or lookalike `.epi` file (start here as a receiver)

**Threat:** the file itself is the weapon. An envelope-v2 `.epi` is a
polyglot: double-clicking it renders attacker-controlled HTML/JavaScript in
the reviewer's browser. A lookalike can also be fully "valid" — anyone can
seal a plausible file and sign it with their own key.

**What to do instead of opening it:**

- **Do not trust rendering.** The in-file viewer paints its own verdict (see
  R1) and its scripts run in your browser. Verify **before** you render — or
  never render: `epi verify` parses the ZIP members in memory and never
  executes the file's HTML or JavaScript. The CLI needs no browser and no
  network (Tier 1 offline).
- **Pin the sender's key out of band.** A signature from an unknown key is
  math, not trust. An attacker-signed lookalike verifies cryptographically;
  only a pinned key plus `epi verify --policy strict` tells it apart from the
  real sender's file (DID-resolved `KNOWN` under `standard` is self-assertion,
  not a pin).
- **Extraction is guarded.** `EPIContainer.unpack` refuses decompression bombs
  before extracting anything (expansion budget checked against the ZIP central
  directory: `epi_core/container.py::_check_expansion_budget`) and rejects
  path-traversal members (`../` escapes raise instead of writing).
- **Display spoofing fails verification.** The outer viewer region is
  byte-identical to the sealed `viewer.html` member whose SHA-256 sits in the
  **signed** `file_manifest`, so editing the display layer of a real file
  fails `epi verify` even when the attacker also recomputes the unsigned
  header copy. The signed display binding shipped in 4.6.3; 4.6.2's #141/#143
  fixed only envelope tamper and still trusted the unsigned header copy for the
  viewer. The viewer itself refuses to paint a verdict it cannot support.
- **The shipped viewer makes no network calls.** Scanned the current 4.6.3
  artifact (`docs/assets/demo-banking-aml.epi`): zero external scripts, fetches,
  or sockets in the outer or inner viewer; every library is inlined. Reproduce it
  with the script in [FILE-SAFETY.md](./FILE-SAFETY.md) §2. Honest boundary:
  there is no Content-Security-Policy enforcing that, and no independent
  penetration test yet ([issue #153](https://github.com/mohdibrahimaiml/epi-recorder/issues/153)) —
  so files from untrusted senders still deserve HTML-attachment caution, or the
  data-only form (`epi migrate --legacy-zip`, `epi export agt|trace`).

Full receiver guide: [FILE-SAFETY.md](./FILE-SAFETY.md). Detail on each
sub-threat: R1–R4 below.

### R1. Attacker-crafted file with a fake "VERIFIED" viewer
**Attack:** An attacker builds a `.epi`-shaped file whose embedded HTML viewer
paints "VERIFIED / PASS" no matter what — or edits the display layer of a real
file.

**Why the viewer alone cannot be trusted:** the verdict chrome lives inside the
file being judged. A wholly fabricated file carries no signature from a key you
pinned, so it fails `epi verify` — but only if you run `epi verify` instead of
believing the colours.

The outer polyglot viewer (the HTML a double-click renders) is byte-identical to
the sealed `viewer.html` member, whose SHA-256 sits in the **signed** manifest.
Editing the display layer therefore breaks verification: the signed
`file_manifest` no longer matches, and the artifact fails even if the attacker
also recomputes the unsigned `reserved_tail[0:32]` copy in the envelope header.
That header copy is self-referential and, on its own, only detects naive
corruption.

The viewer itself also refuses to paint a verdict it cannot support: when it
does not hold the signed manifest bytes (the double-click polyglot case), it
shows a neutral **"INTEGRITY NOT VERIFIED HERE"** rather than green. Only
`epi view` (which injects a context built from the CLI's own verification) or
an in-page check against the shipped archive may show green.

**Mitigation:** never trust the in-file viewer. Verify with the CLI
(`epi verify --policy strict`), pin the sender's key out of band, and consult
the witness log when one exists.

### R2. Malicious recorded content executing in the viewer (stored XSS)
**Attack:** A hostile run's steps contain `</script>` breakouts or event-handler
payloads that execute when the victim opens the viewer.

**Status:** the shipped viewer HTML-escapes recorded values in text positions
and embeds sealed JSON script-safely (`_html_safe_json_dumps`), and a scan of a
4.6.3 seal shows no network primitives for exfiltrated data to reach — but there
is **no Content-Security-Policy** enforcing that, and the viewer has had **no
independent penetration test**. Treat this as defense-in-depth, not a proven
boundary.

**Mitigation:** verify-before-render (CLI first), open files from untrusted
senders with normal HTML-attachment caution, prefer the data-only form
(`epi migrate --legacy-zip`, `epi export agt|trace`) when the shell is not
needed. CSP hardening is tracked in
[issue #153](https://github.com/mohdibrahimaiml/epi-recorder/issues/153).

### R3. Decompression bomb
**Attack:** A crafted ZIP payload expands to exhaust memory or disk when the
victim verifies or opens it.

**Status: mitigated (red-team F-22).** The container reader now enforces an
expansion budget, checked against the ZIP *central directory* so nothing is
expanded to make the decision: a per-member uncompressed cap, a total
uncompressed cap, and a total expansion-ratio cap
(`epi_core/container.py::_check_expansion_budget`). The red team measured
`epi verify` expanding **524,637,162 bytes out of a 957,623-byte artifact
(547x)** before the guard; afterwards the same file is refused before a
single member is expanded.

The limits are operator-overridable (`EPI_MAX_EXPANDED_BYTES`,
`EPI_MAX_MEMBER_BYTES`, `EPI_MAX_EXPANSION_RATIO`) and are deliberately
generous: legitimate artifacts are text/JSON and compress well under 50x.

**Residual:** the guard is a policy, not a format limit. A receiver that
raises the caps, or a reader that bypasses `epi_core` (the legacy Render
`/api/verify` path historically did) is not covered by it.

### R4. Browser signing-seed theft
**Attack:** Malware, or another local HTML file opened in the same browser
profile, reads the browser's stored signing seed and signs artifacts as you.

**Status:** browser Sign & seal keeps a 32-byte Ed25519 seed as **plain-text
hex in `localStorage`** (`epi.viewer.signingSeed.v1`), or holds a user-pasted
unencrypted PEM in memory. In Chromium-based browsers, `file://` pages share one
`localStorage` area, so another local HTML file opened in the same profile can
read it. CLI keys (`~/.epi/keys/`) are not affected.

**Mitigation:** seal real evidence with CLI keys; treat browser-signed identity
as low-assurance. Hardening options (non-extractable WebCrypto keys,
session-only seed, passphrase wrapping) are tracked in
[issue #153](https://github.com/mohdibrahimaiml/epi-recorder/issues/153).

---

## Trust Boundaries

```
+---------------------------------------------+
|  Attacker Controls                          |
|  - The .epi file (can try to tamper)        |
|  - The network (can try to intercept DID)   |
|  - A crafted file's viewer (paints its own  |
|    verdict — never trust in-file chrome)    |
+---------------------------------------------+
              |
              v
+---------------------------------------------+
|  EPI Verifier Controls                      |
|  - CLI private keys (~/.epi/keys/)          |
|  - Browser seed (localStorage, weaker — R4) |
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
|  - Pre-seal honesty is NOT guaranteed       |
|    (signer chose created_at; capture may    |
|    be incomplete — see items 4–5, R1)       |
+---------------------------------------------+
```

---

## Summary Table

| Attack | Prevented? | Mechanism |
|--------|-----------|-----------|
| Payload tampering | Yes | SHA-256 file manifest |
| Manifest tampering | Yes | Ed25519 signature |
| Signature replay | Yes | Manifest-bound signature |
| Post-seal timestamp tampering | Yes | Signed `created_at` (pre-seal honesty NOT covered — see item 4) |
| Backdating / fabrication after the fact | Yes, when a valid RFC 3161 token is present | Offline TSA validation against pinned roots |
| Silent re-seal after the fact | Yes, with customer witness configured | Independent witness log + `--witness-log` |
| Private key leak into artifact | Yes | Public key only in artifact (browser seed rest is weaker — see R4) |
| Secret leakage | Partial | Regex redaction |
| Revoked key reuse | Yes | Revocation list |
| Agent self-approval | Yes | Approver registry (`epi approvers add`) + sealing-key rule + `--require-human-approval` |
| Compromised key | No | Out of scope |
| Malicious signer | No | Out of scope |
| DID server compromise | Partial | Local fallback |
| Algorithm degradation | No | Time-bound guarantee |
| Social engineering | No | Out of scope |
| Fake-verdict crafted file (receiver) | No — verify, don't trust chrome | CLI verify + key pinning (R1) |
| Viewer stored-XSS (receiver) | Partial | Output escaping; no CSP, no pen-test (R2) |
| Decompression bomb (receiver) | Partial — expansion budget enforced, caps are operator-overridable | Central-directory expansion guard (R3) |
| Browser seed theft (receiver) | No | localStorage is plain text (R4) |
