# Security Policy

## 🔒 Reporting Security Vulnerabilities

**Please DO NOT report security vulnerabilities through public GitHub issues.**

Instead, please report them via email to:

**mohdibrahim@epilabs.org**

(This matches `website/.well-known/security.txt`. A dedicated `security@`
address will replace it once mail forwarding is confirmed.)

We take security seriously and will acknowledge your report within 5 business days.

### What to Include

Please include as much information as possible:
- Type of vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)
- Your contact information

### Response Process

1. We'll acknowledge receipt within 5 business days
2. We'll investigate and provide an initial assessment within 7 days
3. We'll work on a fix and coordinate disclosure timing with you
4. Once fixed, we'll publish a security advisory

### Safe harbour

If you report in good faith, follow this policy, and avoid harm to users
(no data theft, no service disruption, no accessing other people's data),
EPI Labs will not take legal action against you for the research itself.
You may also report through GitHub private vulnerability reporting on this
repository, if it is enabled.

## 🛡️ Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 4.6.x   | ✅ Active support  |
| < 4.6   | ❌ No longer supported |

## 🔐 Security Features

EPI Recorder includes several security features:

### Cryptographic Signatures
- **Ed25519** digital signatures (RFC 8032) on the sealed manifest
- Default `record()` seals are signed; unsigned `.epi` files exist (`signature_valid` is `null`)
- Tamper detection is **integrity hashes plus the signature together**. A valid signature over an unchanged manifest does **not** mean the ZIP members or display layer are intact (`integrity_ok` can still be `false`). See [docs/VERIFICATION_CONTRACT.md](docs/VERIFICATION_CONTRACT.md).

### Automatic Secret Redaction
- API keys automatically redacted (OpenAI, Anthropic, AWS, etc.)
- Environment variables containing secrets masked
- Configurable redaction patterns

### Client-Side Verification
- Local verification in the browser (no proof system involved)
- No server round-trips required
- Works offline and in air-gapped environments

## 🚨 Known Security Considerations

### API Interception
- Current SDK integrations are **wrappers** (`wrap_openai`, `wrap_anthropic`, and the LangChain callback). They capture calls they wrap; they do not prove every model call in the process was captured.
- Only enable recording when needed
- Not recommended in security-critical contexts without review

### Data Handling
- Recorded data includes API requests/responses
- Ensure sensitive data is redacted before sharing `.epi` files
- Review redaction patterns for your use case

## 🔑 Cryptographic Details

### Signature Algorithm
- **Algorithm**: Ed25519 (RFC 8032)
- **Hash**: SHA-256
- **Canonicalization**: RFC 8785 JCS for 4.4.1+ artifacts (`rfc8785`). Pre-4.4.1 uses legacy `json.dumps(sort_keys=True)`. Spec `1.x` used CBOR. The verifier dispatches by `manifest.spec_version` — see [docs/KNOWN_LIMITATIONS.md](docs/KNOWN_LIMITATIONS.md).
- **Library**: Python `cryptography` package (industry standard)

### Key Management
- Private keys stored in `~/.epi/keys/`
- File permissions: 600 (owner read/write only)
- Never share private keys
- Public keys embedded in signed `.epi` files

## 🧪 Security Testing

We welcome security researchers to:
- Review our cryptographic implementation
- Test for vulnerabilities
- Suggest security improvements

Please follow responsible disclosure practices.

## 📝 Security Changelog

4.x only. Older 2.x notes are in git history, not current product truth.

### v4.6.2
- **Viewer fail-closed on envelope tamper (#141 / #143).** Outer display-layer edits used to let the in-file viewer paint INTEGRITY VERIFIED. A baked envelope failure (`__envelope_header__` / `__polyglot_viewer__`) can no longer be upgraded to green. `epi verify` already caught this; the browser UI now matches.
- **Pack-time viewer carries VERIFY.txt; prohibition guards see original case (#145).**

### v4.6.1
- **Remote trust registry is informational only.** A key listed only at `epilabs.org/.well-known/epi-trust-registry.json` is not a pin. `--policy strict` never fetches the list.

### v4.6.0
- **RFC 3161 timestamps validated offline** by `epi verify` (imprint, CMS signature, timeStamping EKU, chain to pinned roots). Legacy tokens remain presence-only.


 