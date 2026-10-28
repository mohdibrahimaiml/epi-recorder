# Key custody: signing with an HSM or cloud KMS

By default `epi` signs with an Ed25519 key file in `~/.epi/keys/`. That is fine for a laptop. In production it means anyone who takes over the machine running the agent can also sign records.

This guide moves the signing key into a **hardware security module (HSM) or cloud key vault**. The private key never leaves the vault: EPI asks the vault to sign, and the vault returns only the signature.

**Nothing changes for whoever checks the files.** Vault-held keys produce standard Ed25519 signatures, byte for byte the same format as a key file. `epi verify`, the browser verifier and every older verifier accept them unchanged.

## Supported vaults

| Vault | Works? | Key type to create | URI |
|---|---|---|---|
| Any PKCS#11 HSM (Thales Luna, Entrust nShield, Utimaco, YubiHSM 2, AWS CloudHSM, SoftHSM) | ✅ | Ed25519 (`CKK_EC_EDWARDS`, mechanism `CKM_EDDSA`) | `pkcs11:token=<label>;object=<label>?module-path=<lib.so>` |
| AWS KMS | ✅ | Key spec `ECC_NIST_EDWARDS25519`, usage `SIGN_VERIFY` | `awskms:<key id, ARN or alias/name>[?region=<region>]` |
| Google Cloud KMS | ✅ | Algorithm `EC_SIGN_ED25519` | `gcpkms:projects/<p>/locations/<l>/keyRings/<r>/cryptoKeys/<k>/cryptoKeyVersions/<n>` |
| Azure Key Vault / Managed HSM | ❌ | Azure Key Vault has no Ed25519 key type. Use an HSM over PKCS#11 instead. | n/a |

Install the matching extra:

```bash
pip install "epi-recorder[pkcs11]"    # PKCS#11 HSMs
pip install "epi-recorder[aws-kms]"   # AWS KMS (boto3)
pip install "epi-recorder[gcp-kms]"   # Google Cloud KMS
```

## Set it up

### 1. Create an Ed25519 key in the vault

```bash
# AWS KMS
aws kms create-key --key-spec ECC_NIST_EDWARDS25519 --key-usage SIGN_VERIFY \
  --description "EPI evidence signing"
aws kms create-alias --alias-name alias/epi-signing --target-key-id <key-id>

# Google Cloud KMS
gcloud kms keys create epi-signing --keyring epi --location global \
  --purpose asymmetric-signing --default-algorithm ec-sign-ed25519

# PKCS#11 (example: SoftHSM for a test; a real HSM uses its own admin tool)
softhsm2-util --init-token --free --label epi --pin "$PIN" --so-pin "$SO_PIN"
pkcs11-tool --module /usr/lib/softhsm/libsofthsm2.so --token-label epi --login --pin "$PIN" \
  --keypairgen --key-type EC:edwards25519 --label epi-signing
```

### 2. Link it to an EPI key name

```bash
epi keys link --name default --uri awskms:alias/epi-signing?region=eu-west-1
```

This step:
- fetches the public key from the vault and asks the vault to sign once, to prove the setup works;
- writes `default.pub` and `default.signer` in the keys folder. `default.signer` holds only the URI and the public key. **Nothing secret is written to disk.**
- prints the key **fingerprint**.

`link` refuses to run while a `default.key` file exists, because it won't silently replace a key you already use. Move or delete that file first, or link the vault key under another name. A gateway uses `EPI_GATEWAY_SIGNING_KEY_NAME`.

From then on, `epi record`, `record()`, the gateway, `epi review`, the witness report and every other signing path sign through the vault.

### 3. Credentials and the PIN

| Vault | Where credentials come from |
|---|---|
| PKCS#11 | `EPI_PKCS11_PIN` (the user PIN). The PIN is **never** accepted in the URI. The library path comes from `?module-path=` or `EPI_PKCS11_MODULE`. |
| AWS KMS | The normal AWS credential chain: an IAM role, `AWS_PROFILE`, environment variables. Grant only `kms:Sign` and `kms:GetPublicKey` on this key. |
| Google Cloud KMS | Application Default Credentials. Grant `roles/cloudkms.signerVerifier` on this key version only. |

### 4. Enforce it (recommended)

```bash
export EPI_REQUIRE_EXTERNAL_KEY=1
```

With this set, EPI **refuses to sign with any key file on disk**. Only linked vault keys are accepted, so a forgotten or planted `.key` file can't be used.

## Safety checks EPI does on every signature

- **Swap guard.** The public key the vault reports must match the one pinned when you ran `link`. If someone repoints the alias or swaps the key, EPI refuses to sign and tells you to re-link on purpose (`--overwrite`).
- **Self-check.** Each signature is verified against the vault's public key before EPI uses it. A key set up for the wrong algorithm (for example prehashed Ed25519ph) fails at seal time, not later in a customer's check.
- **No export.** A vault signer has no `private_bytes()`. Any code path that tries to export the key fails loudly.

## How a reviewer confirms the key is in the vault

The `.epi` file can't prove where its key was stored. A file that said "signed by an HSM" would only be the signer's own claim. Instead, the reviewer compares fingerprints:

1. `epi verify file.epi` prints the signer's fingerprint.
2. The vendor's key administrator shows the vault's public key:
   ```bash
   aws kms get-public-key --key-id alias/epi-signing --query PublicKey --output text \
     | base64 -d | openssl pkey -pubin -inform DER -outform PEM > vault.pub
   epi keys trust vault.pub --name vendor-hsm   # prints the same fingerprint
   ```
   For a PKCS#11 HSM, read the public key with the HSM's own tool, for example
   `pkcs11-tool --module <lib.so> --token-label epi --read-object --type pubkey --label epi-signing -o vault.pub`
   (recent OpenSC versions write PEM directly).
3. If the fingerprints match, the signing key is the one inside the vault. The vault's own audit log (CloudTrail, Cloud Audit Logs, HSM audit) then lists every signature it made.

## Limits

- **AWS KMS** signs at most 4096 bytes per request. EPI's manifest and witness signatures are well under that. A larger payload (for example a very large Annex IV section) is refused with a clear error instead of being signed some other way.
- **Speed.** Each seal makes one network call to the vault (tens of milliseconds for a cloud KMS). Sessions are reused inside a process.
- **Approvals.** A vault key protects the *system's* signature. It doesn't make a human approval real. That's a separate signature from the approver's own key (see the roadmap).
