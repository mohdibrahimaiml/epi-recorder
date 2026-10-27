# Bank Readiness: Execution Plan

_Companion to [BANK-READINESS-ASSESSMENT.md](BANK-READINESS-ASSESSMENT.md). Started 2026-10-26._

One step at a time. Each step ships as its own reviewed PR with tests before the next one starts.

| # | Step | Status |
|---|---|---|
| 1 | Viewer must not show a pass it didn't compute | ✅ Done ([#186](https://github.com/mohdibrahimaiml/epi-recorder/pull/186), plus [#185](https://github.com/mohdibrahimaiml/epi-recorder/pull/185) for the verify page) |
| 2 | Key-vault signing (HSM / KMS) | ✅ Built on `claude/optimistic-turing-lusdoj` (awaiting PR review) |
| 3 | Real human sign-off (approver signs with their own key / passkey) | 🚧 3a merged ([#188](https://github.com/mohdibrahimaiml/epi-recorder/pull/188)); 3b (gateway link) in review ([#190](https://github.com/mohdibrahimaiml/epi-recorder/pull/190)); 3c (browser labels) next |
| 4 | Public witness checkpoint mirror | ⏳ |
| 5 | Gateway records streaming calls | ⏳ |
| 6 | "Break the seal" public challenge | ⏳ |

---

## Step 2: Key-vault signing

### Problem
`KeyManager.load_private_key()` reads an Ed25519 PEM from `~/.epi/keys/<name>.key` on the same machine as the agent. Whoever compromises that machine can sign fake records. Banks expect the key to stay inside an HSM or cloud KMS and never be exportable.

### Key design decision: keep Ed25519, so the file format doesn't change
The `.epi` signature is `ed25519:<keyname>:<hex>` over the canonical manifest hash. Both verifiers (Python and browser) accept only Ed25519. Ed25519 keys can be held in:

| Backend | Ed25519? | How EPI uses it |
|---|---|---|
| PKCS#11 HSMs (Thales Luna, Entrust nShield, YubiHSM 2, AWS CloudHSM, SoftHSM for tests) | ✅ `CKM_EDDSA` | `pkcs11:` URI |
| AWS KMS | ✅ key spec `ECC_NIST_EDWARDS25519`, algorithm `ED25519_SHA_512`, `MessageType=RAW` (pure Ed25519) | `awskms:` URI |
| Google Cloud KMS | ✅ `EC_SIGN_ED25519` (pure, `data` field) | `gcpkms:` URI |
| Azure Key Vault / Managed HSM | ❌ no Ed25519 key type | Documented gap: use Azure Cloud HSM via PKCS#11, or another backend |

Because the signature stays pure Ed25519, **every existing `.epi` verifier accepts HSM-signed files unchanged.** No format change and no verifier change.

### Design
1. **`epi_core/signers.py`.** Each external signer behaves like `Ed25519PrivateKey` for signing: `.sign(data) -> 64 bytes` and `.public_key() -> Ed25519PublicKey`. Every existing signing path (manifest, review, SCITT, annex, notify, org bundle) works without edits. `private_bytes()` raises a clear error: the key can't leave the vault.
   - Every signature is checked against the vault's public key before it is returned. This catches a misconfigured key (for example Ed25519ph instead of pure Ed25519) at seal time, not in a customer's verify.
2. **Linking a key.** `epi keys link --name default --uri <uri>` fetches the public key from the vault and writes `<name>.pub` (as today) plus `<name>.signer` (the URI and pinned public key; nothing secret). `load_private_key()` returns the external signer when `<name>.signer` exists.
   - **Swap guard:** if the vault's live public key ever differs from the pinned one, signing is refused.
3. **Policy switch:** `EPI_REQUIRE_EXTERNAL_KEY=1` makes `load_private_key()` refuse any key file on disk. A bank can enforce "no signing keys on agent hosts".
4. **Fix the 3 places that export raw key bytes** (witness seal-signature header in the SDK, the CLI and the gateway). They now pass the signer object instead of raw bytes.
5. **No-overwrite rule:** `epi keys generate` refuses a name that is linked to a vault.
6. **Optional dependencies:** `epi-recorder[pkcs11]`, `[aws-kms]`, `[gcp-kms]`. The core install is unchanged.
7. **Docs:** `docs/KEY-CUSTODY.md`, with setup per backend and how a bank checks the key fingerprint against its own vault (`aws kms get-public-key`, etc.).

### Tests (all free)
- **Real SoftHSM** (skipped when `libsofthsm2.so` is absent): link, seal a real `.epi`, `epi verify` passes, the swap guard triggers on a different key.
- **AWS / GCP:** an injected fake client that signs with a real Ed25519 key, so the request shape (`MessageType=RAW`, `ED25519_SHA_512`, `data=`) is asserted.
- Misbehaving backend (wrong signature) → refused.
- `EPI_REQUIRE_EXTERNAL_KEY=1` blocks file keys.
- The witness header is signed through an external signer.

### Out of scope for step 2
Claiming "HSM-backed" inside the manifest. That would be a self-declared claim, the kind the assessment criticises. The bank's proof is comparing the fingerprint in `epi verify` with the public key in its own vault.

---

## Step 3: Real human sign-off — DONE (3a merged, 3b merged, 3c in review)
- An approval is a separate signed statement over (manifest hash, decision, approver identity, time) made with the **approver's** key, not the agent's.
- Approver keys: a CLI key (`epi review sign`) or a WebAuthn passkey in the browser.
- `epi verify` reports an approval as *human-signed* only when that signature verifies against a key pinned as an approver. It never reports it from an agent-written step.

### Step 3 follow-up: fault_analyzer still accepts an agent-reported approval

`epi_core/fault_analyzer.py` lets an `agent.approval.response` step satisfy a
policy's "approval required" rule. That is a **policy-compliance** claim about
the run (did the workflow do what the rulebook says), not an **identity** claim
(who signed). Changing it now would flip existing policy results, so it is
deliberately out of scope for 3a.

**Resolved in 3b:** `epi_core/fault_analyzer.py` now splits the approval-source
policy — `gateway_link_authenticated` and legacy `gateway_human` still satisfy
"approval required" but carry an explicit P6b note that this is the recording's
claim, and `gateway_link_unsigned` is treated as self-reported. The only
cryptographic proof remains `epi verify --require-human-approval`.

---

## Step 4: Checkpoint mirror — CODE DONE, WAITING ON THE PUBLIC REPO
- Done: `epi witness check --mirror <URL|dir>` (cross-checks the mirror against
  the live witness: changed day, deleted day, or a key change without a rotation
  entry all fail; a day only on the live side is fine), an append-only
  signature-verified mirror script that exits non-zero on "history change
  detected", a dormant-safe workflow that cross-checks before pushing,
  `mirror-template/` to copy into the new repo, and a
  [docs/WITNESS.md](../../docs/WITNESS.md) section.
- Waiting on the founder: create the public `epi-witness-checkpoints` repo from
  `mirror-template/`, create a fine-grained PAT (contents:write on that repo
  only), and set the `MIRROR_PAT`, `MIRROR_REPO`, `EPI_CLOUD_URL` and
  `WITNESS_MIRROR_INBOXES` secrets.

## Step 5: Streaming capture — PAUSED
- The gateway proxies SSE for OpenAI and Anthropic and stores the assembled response plus the chunk hashes. The 501 goes away.
- **Paused on purpose:** no pilot is blocked on it, and the SDK already captures streaming. Do not start it before a pilot needs the gateway path.

## Step 6: Break the seal — DONE, WAITING ON KEY CUSTODY
- Done: `CHALLENGE.md` (credit-only, exact criteria a–e, safe harbour),
  `challenge/challenge-original.epi` with published signing/approver keys,
  `challenge/check_submission.py` (BREAK / NO BREAK for a–d) and
  `scripts/make_challenge_artifacts.py`.
- Waiting on the founder: move the generated private keys offline (or destroy
  them — recommended, since the published artifact is reproducible and a leaked
  key would invalidate criterion b), and turn on GitHub private vulnerability
  reporting if it is off.

## Pilot kit — DONE
- `examples/pilot_kit/` (`agent.py`, `run_pilot_demo.sh` / `.py`, CI workflow)
  and `docs/PILOT-GUIDE.md` + `docs/BANK-REVIEWER-BRIEF.md`.
