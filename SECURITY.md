# Security Policy

## 🔒 Reporting Security Vulnerabilities

**Please DO NOT report security vulnerabilities through public GitHub issues.**

Instead, please report them via email to:

**security@epilabs.org**

We take security seriously and will respond within 48 hours.

### What to Include

Please include as much information as possible:
- Type of vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)
- Your contact information

### Response Process

1. We'll acknowledge receipt within 48 hours
2. We'll investigate and provide an initial assessment within 7 days
3. We'll work on a fix and coordinate disclosure timing with you
4. Once fixed, we'll publish a security advisory

## 🛡️ Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 2.1.x   | ✅ Active support  |
| 2.0.x   | ❌ No longer supported |
| < 2.0   | ❌ No longer supported |

## 🔐 Security Features

EPI Recorder includes several security features:

### Cryptographic Signatures
- **Ed25519** digital signatures (same as Signal, SSH)
- All `.epi` files are cryptographically signed
- Tamper detection - any modification breaks the signature

### Automatic Secret Redaction
- API keys automatically redacted (OpenAI, Anthropic, AWS, etc.)
- Environment variables containing secrets masked
- Configurable redaction patterns

### Client-Side Verification
- Zero-knowledge verification in browser
- No server round-trips required
- Works offline and in air-gapped environments

## 🚨 Known Security Considerations

### API Interception
- EPI uses monkey-patching to intercept API calls
- This modifies library behavior at runtime
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
- **Serialization**: Canonical CBOR (RFC 8949)
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

### v2.1.3 (January 2026)
- Enhanced client-side verification
- Improved secret redaction patterns

### v2.1.2 (January 2026)
- Added browser-based cryptographic verification
- Bundled @noble/ed25519 for offline verification

### v2.1.0 (December 2025)
- Initial security hardening
- Automatic redaction system

## 📬 Contact

- **Security Issues**: security@epilabs.org
- **General Contact**: mohdibrahim@epilabs.org
- **GPG Key**: [Coming soon]

## 🙏 Acknowledgments

We thank security researchers who report vulnerabilities responsibly.

---

**Last Updated**: January 2026

