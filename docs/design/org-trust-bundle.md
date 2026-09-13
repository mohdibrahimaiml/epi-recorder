# Org Trust Bundle Lifecycle — Design (approved, v0 build spec)

Status: approved with amendments. Implements the auditor story: an offline
auditor holding a company artifact from years ago answers (1) did this come
from that company, and (2) was the sealing key legitimately the company's key
at sealing time — with no network, no account, no relationship with us.

Amendments folded in after review (see §10):
- A1: `epi enterprise bootstrap` no longer generates customer key material
  (done, own commit). The bundle design's central claim is now structural.
- A2: TSA corroboration of sealing time is opportunistic, never mandatory,
  and required only under `--policy strict`.
- A3: first-contact root authenticity procedure specified (§8).
- A4: successor-root generation is mandatory in bootstrap, not recommended.
- A5: open question recorded (§11): one org identity vs per-department/system.

## 0. What already exists

- `epi enterprise bootstrap` scaffolds org keys, pins, bundle, policy, CI
  recipe. **As of the A1 fix it accepts `--org-pubkey` (public only) and
  refuses otherwise** — generation happens on customer hardware.
- `epi keys bundle-import` imports public keys into a local trust dir.
- `epi_core/keys.py`: `trust_key`, `revoke_key` (undated `<name>.revoked`
  markers — local-only, no timestamps, unusable for historical verification),
  `export_trust_bundle` (`epi-trust-bundle-v1` zip: README + manifest.json +
  `keys/*.pub`; no versions, windows, signatures, or timestamps).
- `epi_core/trust.py`: `TrustRegistry.verify_key_trust` checks local
  `.revoked`, local `.pub`, DID:WEB (network), remote registry URL
  defaulting to `https://epilabs.org/.well-known/epi-trust-registry.json`
  (network, with offline fallthrough).
- `epi_core/did_web.py`: full DID:WEB resolve + Ed25519 extract, stdlib-only.
  **Excluded from the v0 offline path** — resolution is an HTTPS fetch.
  Optional online hint only, never on the critical path.
- `epi_core/serialize.py` + `MANIFEST_OMIT_NONE_FROM_HASH` (currently
  `{"content_truncated", "policy_load_status"}`): any new optional
  `ManifestModel` field that is `None` on old artifacts must be registered
  here or the frozen 4.3.0/4.4.0 goldens break (`tests/test_legacy_preimage.py`
  enforces this mechanically). Three JS verifiers mirror the rule
  (`website/js`, `site/js`, `epi-official/js` `epi-manifest-preimage.js`).
- `epi_core/local_scitt.py` + `scitt.py`: file-based transparency service
  (independent Ed25519 service key, append-only JSONL ledger, RFC 6962
  Merkle leaves, inclusion proofs). Anchoring substrate; nothing new to build.

## 1. Five failure modes and preventions

1. **Retroactive revocation destroys the archive.** Prevention: revocation is
   timestamped and never retroactive; validity is evaluated at sealing time
   (§4).
2. **Bundle rollback** (auditor handed v2 missing the v4 revocation).
   Prevention: monotonic `version` + `issued_at` in the signed envelope;
   horizon rule (§5.4): a bundle older than the artifact yields UNKNOWN,
   never a verdict; bundle version hashes anchored in SCITT (§7) make forked
   histories detectable.
3. **Stale auditor bundle** (key added in v4, auditor holds v2). Prevention:
   same horizon rule — UNKNOWN with the precise reason, never a guess. False
   negatives are always preferred over false positives.
4. **Accidental network fetch.** Prevention: the v0 verifier takes
   `(artifact_bytes, bundle_bytes)` and nothing else — no sockets, no env
   vars, no local key dirs. DID:WEB and remote-registry paths are
   unreachable from it.
5. **Manifest change breaks legacy preimages.** Prevention: **zero manifest
   changes** (§6) — everything rides the existing free-form `governance`
   dict, which old artifacts lack. Goldens green by construction.

## 2. Bundle format (`epi-org-bundle-v1.json`)

Single JSON file (emailable, readable, diffable):

```json
{
  "format": "epi-org-bundle-v1",
  "bundle_id": "acme-corp",
  "version": 5,
  "issued_at": "2028-03-14T09:00:00Z",
  "issuer_root_fingerprint": "<hex sha256 of root pub>",
  "root_public_key": "<64-hex root pub — required: envelope verification needs the key itself, the fingerprint alone cannot verify a signature>",
  "keys": [
    {"key_id": "seal-2026", "public_key": "<64-hex>",
     "not_before": "2026-01-05T00:00:00Z", "not_after": null,
     "status": "active", "role": "sealing"}
  ],
  "signatures": [{"key_id": "root-2024",
    "signature": "ed25519:<hex over canonical bundle body, signatures field excluded>"}]
}
```

Rules: `version` strictly increasing per `bundle_id`; `issued_at`
non-decreasing; per-key validity windows; revocation is a state transition
that **adds** `revoked_at`/`not_after`/`revocation_reason` — entries are
never deleted (the history is the product). Timestamps ISO-8601 UTC, second
precision (matches manifest normalization). v0 carries windows but no
revocation timestamps (no anchoring, no network — §9).

## 3. Signer: the customer, never us

The envelope is signed by the **customer's root key**, generated on customer
hardware. Root-of-trust distribution needs no third party: the root public
key (fingerprint) is embedded in each artifact's `manifest.governance`
(`governance.org_root`) **at seal time**, covered by the artifact's own
manifest signature. The artifact names its root; the bundle is signed by
that root. No trust in EPI Labs is required at any point — our code is only
the calculator.

Why not us-signing: it would make EPI Labs a certificate authority every
auditor must trust — a single compromise point whose disappearance voids
all evidence, contradicting the product spine. Customer signing keeps the
"survives us" property intact.

## 4. Revocation semantics (core rule)

**Validity is evaluated at sealing time. Revocation ends a window; it never
rewrites history.** For artifact sealed at `T_seal` and key window
`[not_before, revoked_at ‖ not_after ‖ ∞)`: valid ⟺
`not_before ≤ T_seal < window_end`. The alternative — void-on-revoke —
turns every employee departure into archive destruction and is rejected.

**Unknown compromise time:** `revoked_at` is set by the customer as their
best-supported compromise boundary (e.g. last clean audit), recorded with a
`revocation_reason` stating the uncertainty in the clear. We refuse to pick
silently in either direction: silent "now" leaves forged artifacts valid;
silent "forever ago" nukes the archive. Uncertainty belongs to the customer,
in writing, in the bundle.

**`T_seal` (amendment A2):** taken as `manifest.created_at`, opportunistically
corroborated downward by an embedded TSA timestamp or SCITT registration if
present (`min(manifest.created_at, earliest independent anchor)`). No
network call is ever made to obtain corroboration — a mandatory seal-time
network call would contradict the product's offline discipline. Absence of
corroboration produces a clear warning, never a failure — except under
`--policy strict`, which requires an independent anchor. **Residual risk,
stated explicitly:** `created_at` is self-asserted; a forger holding a
stolen-but-unrevoked key can backdate into the validity window, and neither
TSA (which only closes backdating) nor any offline check detects *use* of a
legitimately-valid key by the wrong hands. Full elimination needs mandatory
anchoring (v2), not v0.

## 5. Verification algorithm (bundle v5, key valid in v1)

Inputs: `artifact_bytes`, `bundle_bytes`. Nothing else.

1. Parse artifact → manifest, manifest signature, `T_seal`.
2. Parse bundle → require `format == "epi-org-bundle-v1"`.
3. Verify envelope signature against `manifest.governance.org_root`. Fail →
   `INVALID (bundle signature)`, stop.
4. **Horizon check:** `bundle.issued_at < T_seal` → `UNKNOWN (bundle predates
   artifact)`; key id absent → `UNKNOWN (key not in bundle)`. Never a guess.
5. Window check: `not_before ≤ T_seal < window_end` (v0: windows only).
   Else `INVALID` naming the violated boundary.
6. Verify manifest signature against the validated key (existing
   `verify_embedded_manifest_signature` path, key injected — no trust dirs).

Worked example: artifact sealed 2026-06-01 under `seal-2024` (window to a
2027 revocation); bundle v5 issued 2028 holds the full history. Horizon ok,
window ok, signature ok → **VALID**, noted "sealing key since revoked;
validity evaluated at sealing time."

## 6. Manifest changes: none

`governance.org_root` (+ optional `governance.org_key_id`) ride the existing
free-form `governance` dict (`schemas.py:199`). Old manifests lack them →
omitted from preimage exactly as today. `MANIFEST_OMIT_NONE_FROM_HASH`
untouched, JS verifiers untouched, goldens green by construction. (If a
future version promotes these to model fields: `Optional`/default-`None` +
register in the set + mirror in all three JS preimage files, per
`tests/test_legacy_preimage.py`.)

## 7. Transparency anchoring (v2, not v0)

Anchor `sha256(canonical bundle body)` per issued version in the existing
local SCITT log. Gain over the signed bundle alone: **equivocation
detection**. A signature proves *this* bundle came from the root; it cannot
prove it is the *only* v5. Brief root access could sign an alternate v5
with an attacker's key, and the signature would check out. An anchored,
append-only, Merkle-committed version history makes the fork visible (two
v5 hashes = proof of misbehavior, checkable offline against a log
snapshot) — the Certificate-Transparency threat model, deliberately.

## 8. First-contact root authenticity (amendment A3)

"How does the auditor learn Acme's real root fingerprint?" Out-of-band, and
the procedure must say so: publish the fingerprint in the signed customer
contract / MSA exhibit, on company letterhead, or in a DNSSEC-signed
`_epi.<domain>` TXT record the auditor was given during procurement — pick
per engagement and **record which channel in the bundle's provenance note**.
The design makes forgery detectable, never trust automatic. Any claim
beyond that would repeat the receipts mistake.

## 9. Failure modes

- **Lost root:** no new bundles/rotations/revocations; everything issued
  still verifies forever against the last bundle. Recovery: the
  **mandatory** successor root generated at setup (amendment A4 — bootstrap
  refuses to finish without one, sealed offline by the customer), activated
  by a pre-signed succession statement. Skipped setup ⇒ PGP-master-key-grade
  pain, survivable, never retroactive.
- **Compromised sealing key:** new bundle version, `revoked_at` at best
  compromise boundary; pre-boundary artifacts valid; post-boundary fail
  closed. Archive intact by construction.
- **Bundle rollback:** monotonic version + horizon rule → downgrades to
  UNKNOWN at worst, never manufactures VALID.
- **Stale bundle:** UNKNOWN with precise reason (§5.4).
- **Departed signer:** ordinary revocation, `reason: departure`,
  `revoked_at` = exit date. Administratively boring, as intended.

## 10. Out of scope for v1

Dashboard, SSO, self-serve signup, role management, key escrow (we must
never be *able* to seal as the customer), automated root-rotation ceremony
(documented procedure only), remote bundle hosting, DID:WEB on the verify
path.

## 11. Open question (recorded, not designed)

Does a company want one org identity, or per-department/per-system
identities with different scopes? The schema supports multiple key entries
with `role` fields, which keeps both futures open — but no scope semantics
are specified in v0. Expect to learn this from the first customer.

## 12. Build sequence (v0)

Smallest shippable answering both auditor questions: bundle schema +
`epi org bundle issue` (local-only root handling) + `epi org bundle verify
artifact bundle` (§5 steps 1–6) + `governance.org_root` at seal. No
revocation timestamps, no anchoring, no network. Frozen goldens green
throughout (guaranteed by §6; gated by `tests/test_legacy_preimage.py`).
