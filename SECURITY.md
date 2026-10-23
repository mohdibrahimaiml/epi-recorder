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
- Optional at-rest encryption: set `EPI_KEY_PASSWORD` before `epi keys generate` / `epi keys import` to write encrypted PKCS#8 PEM. The same variable must be set for every load (sealing, signing, Cloud upload). There is no HSM integration and no recovery if the passphrase is lost.
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

### v4.6.3 (release pending)

- **Display-layer forgery no longer passes `epi verify` (red-team F-01).** The outer
  polyglot viewer region is byte-identical to the sealed `viewer.html` member, whose
  SHA-256 lives in the **signed** `file_manifest`. `epi verify` now checks the outer
  region against that signed value. Previously only the unsigned, self-referential
  `reserved_tail[0:32]` copy in the envelope header was checked: an attacker who
  edited the display layer could recompute that copy, and `epi verify` reported
  **PASS — including under `--policy strict`**. That contradicted the 4.6.2 release
  note, `docs/THREAT_MODEL.md` R1, `docs/KNOWN_LIMITATIONS.md` and the `VERIFY.txt`
  shipped inside every artifact. Legacy envelope-v2 artifacts whose signed
  `file_manifest` includes `viewer.html` are covered by the same check; artifacts
  whose manifest predates that entry have no signed binding for the display layer,
  and the verifier reports that instead of claiming coverage.
- **The viewer no longer paints a verdict it cannot support (red-team F-02).** The
  double-click polyglot page carries a pack-time *copy* of the manifest — taken
  before the archive's `manifest.json` was re-signed, so it is a stale pre-image —
  and the whole page is editable by whoever holds the file. A check against that
  copy is self-consistent by construction, yet it produced "INTEGRITY VERIFIED" and
  "SIGNATURE VALID". The viewer now requires the **shipped** manifest bytes (from
  the archive) before it reports a verdict, and otherwise shows a neutral
  **"INTEGRITY NOT VERIFIED HERE"**. `epi view` (which injects a context built from
  the CLI's own verification) still shows green for an intact file.
- **A `.epi` can no longer expand without limit (red-team F-22).** The container reader
  enforced no decompression budget: `epi verify` expanded **524,637,162 bytes out of a
  957,623-byte artifact (547x)**, enough to exhaust the disk of any machine that opens
  an untrusted file. `epi_core/container.py` now enforces a per-member, total and
  expansion-ratio budget, checked against the ZIP **central directory** so a bomb is
  refused before a single member is expanded. Operator-overridable via
  `EPI_MAX_EXPANDED_BYTES`, `EPI_MAX_MEMBER_BYTES`, `EPI_MAX_EXPANSION_RATIO`.
- **The reviewer trust page no longer forwards share tokens to an arbitrary origin
  (red-team W-01).** `website/t/app.js` honoured a `?api=<base-url>` override
  ("for local Playwright tests only") on **every** host. Every request that page
  makes carries the reviewer's share token in the `X-EPI-Share-Token` header, so a
  crafted link `https://epilabs.org/t/<slug>?api=https://attacker.example` would
  forward the victim's reviewer credential to the attacker — and let the attacker
  serve arbitrary content back as the trust page. The site's
  `Content-Security-Policy` is **Report-Only**, so nothing else stopped it. The
  override is now honoured **only on a local host**; on any public hostname it is
  ignored. Pinned by `tests/test_trust_page_api_override.py`, which reproduces the
  leak against the old code (`['https://evil.example/v1/trust/sh_test']`).
- **EPI Cloud: a machine API key could mint a whole-org trust link (red-team C-01).**
  `POST /v1/orgs/:orgId/export` accepted a **`push`-scoped** API key — the
  credential `epi cloud login` puts on a recorder machine — and minted a
  **7-day, scope-all** reviewer trust link (`agents:"all", inboxes:"all"`). It
  also skipped the `shareLinks` plan limit, and accepted a plain **member**
  session, while the sibling route `POST /v1/orgs/:orgId/share-links` is
  **owner-only**. A recorder machine could therefore escalate to reviewer read
  scope over the whole workspace. The route is now **owner-only**, enforces the
  same `shareLinks` plan limit as its sibling, and rejects API keys entirely.
  The previous Cloud test suite asserted the vulnerable behaviour as intended;
  `cloud/test/redteam.test.ts` now pins the boundary.
- **A self-asserted identity is no longer described as pinned (red-team F-19).**
  `manifest.governance.did` is written by whoever seals the file. Under the default
  (`standard`) policy the verifier resolves that DID, and if the resolved document
  lists the file's own key the identity becomes `KNOWN`. The red team produced a file
  that is **100% attacker-authored** — attacker's own key, attacker's own domain —
  and the report printed **`✔ SEAL · IDENTITY PINNED`, `DECISION: PASS`, exit 0**.
  The policy decision is a documented trade-off and is **unchanged**; the *words* were a
  false claim. A DID-resolved identity now prints
  **`✔ SEAL · SIGNER SELF-ASSERTED (DID)`** with `Status: SELF-ASSERTED (not pinned)`
  and a pointer to `--policy strict`, and `identity.pin_source` reports the trust
  source explicitly (`local_pin`, `did_web`, `remote_registry`, `revoked`, `none`).
- **Zip-slip guard added to the SCITT anchor path (red-team F-23).**
  `epi_recorder/auto_scitt.py` opened the artifact as a bare ZIP and called
  `extractall()` without a traversal check — bypassing the guard that
  `EPIContainer.unpack()` already had. The check is now applied there too.
- **`--policy strict` no longer certifies a file with no step hash chain
  (red-team F-13).** The `prev_hash` chain is what proves the recorded step order.
  An artifact whose steps carry no links at all made the chain check pass
  *vacuously*, and `--policy strict` reported **"All strict criteria met
  (Integrity, Identity, Completeness)"** — certifying a file whose order could be
  rewritten and re-signed without detection. `strict` now FAILs such a file and
  `standard` WARNs. `facts.chain_present` reports the distinction. Legacy
  pre-chain artifacts (spec < 4.4.x) are affected; current releases chain.

### v4.6.2
- **Viewer fail-closed on envelope tamper (#141 / #143).** Outer display-layer edits used to let the in-file viewer paint INTEGRITY VERIFIED. A baked envelope failure (`__envelope_header__` / `__polyglot_viewer__`) can no longer be upgraded to green. `epi verify` already caught this; the browser UI now matches.
- **Pack-time viewer carries VERIFY.txt; prohibition guards see original case (#145).**

### v4.6.1
- **Remote trust registry is informational only.** A key listed only at `epilabs.org/.well-known/epi-trust-registry.json` is not a pin. `--policy strict` never fetches the list.

### v4.6.0
- **RFC 3161 timestamps validated offline** by `epi verify` (imprint, CMS signature, timeStamping EKU, chain to pinned roots). Legacy tokens remain presence-only.


 