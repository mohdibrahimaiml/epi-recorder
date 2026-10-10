# EPI evidence hardening plan (for the coding agent)

Owner: Mohd Ibrahim Afridi. Written 2026-10-10 against `main` at `211690d` (v4.5.0 docs, 4.4.8 on PyPI).

This plan turns five weaknesses into fixes. **Nothing here may cost money.** That means no paid
services, no paid hosting, and no paid APIs. Free public services (FreeTSA, DigiCert's public
timestamp server, Sigstore's public Rekor log, GitHub, Cloudflare Pages free tier, pypistats.org)
are allowed.

Read the whole plan before starting. Do the work packages (WP) in the order given in section 0.4.

---

## 0. Ground rules

### 0.1 How to work

- One work package per branch and per pull request. Branch names are given in each WP. Never push to `main`.
- Run the same checks CI runs before every push:
  ```bash
  python -m pytest tests/test_version_consistency_runtime.py tests/test_truth_consistency.py -q
  python -m pytest tests -m "not browser" -q --maxfail=20
  ```
  (This mirrors `scripts/release-gate.sh`.) If you add a dependency, run `pip install -e ".[dev]"` again first.
- Keep every existing `.epi` file verifiable. **Never** change what an old artifact's signature covers.
  New fields are optional and new behaviour is versioned. Old files must give the same verdict as before,
  or a clearly labelled "legacy" verdict.
- Every sample in `docs/assets/` and `examples/` that you re-seal must still pass `epi verify`.
- Update `CHANGELOG.md` under `Unreleased` in every PR.

### 0.2 Honesty rules (this project's main asset; do not weaken them)

- Never write a claim in code output, docs, README or the website that the code does not check.
  Wherever the text says "presence only" or "not validated", change it **only** in the same PR that adds the check.
- The repo has tests that enforce this honesty: `tests/test_tsa_presence_honesty.py` and
  `tests/test_truth_consistency.py`. Update them to the new truth. Do not delete them, and do not loosen them
  to make a build pass.
- `docs/KNOWN_LIMITATIONS.md` is the source of truth. When a limitation is fixed, move it to a
  "Fixed in X" section with the version. When you find a new one, add it.
- The browser viewer (`web_viewer/`, `epi_viewer_static/`) does **not** do the new checks unless you
  implement them in JS. Its text must keep saying that timestamp validation happens in `epi verify` only.

### 0.3 What "done" means for the whole plan

When WP1a, WP1b and WP3 have shipped, the website and README may truthfully say:

> "A sealed `.epi` proves it has not changed since sealing, **and** (when timestamps are present) that it existed no later than a time attested by an independent timestamp authority, checked offline by `epi verify`. With a customer witness configured, the customer holds an independent record of every seal."

Until then they may not.

### 0.4 Order

| # | Work package | Branch | Rough size |
|---|---|---|---|
| 1 | WP0: remove the public outreach file and fix stale dates | `fix/outreach-public-file` | 1 hour |
| 2 | WP1a: validate RFC 3161 timestamps offline | `feat/tsa-validation` | 2–3 days |
| 3 | WP1a-2: take checkpoint timestamping off the agent's hot path | `fix/checkpoint-async` | half a day |
| 4 | WP1b: customer witness on every seal | `feat/seal-witness` | 1–1.5 days |
| 5 | WP3: hash chain and capture-time checkpoints for gateway exports (issue #26) | `feat/gateway-export-chain` | 2–4 days |
| 6 | WP1c: did:web identity onboarding | `feat/did-web-onboarding` | half a day to 1 day |
| 7 | WP4: core vs experimental split (no code deleted) | `chore/core-vs-experimental` | 1 day |
| 8 | WP2.1: any-language docs | `docs/any-language` | 2 hours |
| 9 | WP2.2: gateway streaming (issue #31) | `feat/gateway-streaming` | 3–4 days |
| 10 | WP2.3: OTLP/HTTP trace receiver in the gateway | `feat/gateway-otlp` | 3 days |
| 11 | WP1d: Sigstore Rekor spike (time-boxed) | `spike/rekor` | 1 day maximum |
| 12 | WP5: launch assets (drafts only; nothing is posted by the agent) | `docs/launch-assets` | half a day |

---

## WP0. Remove the public outreach file and fix stale dates

**Why.** `website/outreach.md` is internal sales material (cold-email templates and target companies),
and it is **publicly deployed**: copies exist at `site/outreach.md`, `verify_portal/static/outreach.md` and
`epi-official/outreach.md`, and the site build ships them. It also says *"The EU AI Act's high-risk AI
provisions take full effect August 2, 2026"* (line 45). That date is wrong: Regulation (EU) 2026/1744 (the
Digital Omnibus, in force 27 July 2026) moved stand-alone (Annex III) high-risk obligations to
**2 December 2027**, and product-embedded (Annex I) ones to **2 August 2028**.

**Steps.**
1. `git rm` all four copies: `website/outreach.md`, `site/outreach.md`, `verify_portal/static/outreach.md`, `epi-official/outreach.md`.
2. Open `scripts/sync_website.py` and the `npm run build` script in `package.json`. Add an exclusion so any `*.md` file in `website/` other than `README.md` is never copied into the public outputs. Add a test in `tests/test_website_sync.py` asserting that no `outreach.md` exists in `site/`, `verify_portal/static/` or `epi-official/` after a sync.
3. Grep the public surfaces for stale AI Act dates and fix every hit:
   ```bash
   grep -rniE "august 2,? 2026|2 august 2026|aug(ust)? 2026" website docs README.md epi_core epi_cli --include=*.md --include=*.html --include=*.py | grep -v archive
   ```
   Replace with: "High-risk obligations for Annex III systems apply from 2 December 2027 (Regulation (EU) 2026/1744)". Docs under `docs/archive/` stay as they are, because they are labelled historical.
4. Check `docs/EU-AI-ACT-COMPLIANCE-MATRIX.md`, `docs/EU-AI-ACT-EVIDENCE-PREP.md` and `docs/ANNEX-IV.md` for the same date.

**Acceptance.**
- `grep -r outreach.md site verify_portal/static epi-official` returns nothing.
- There is no "August 2, 2026" in any non-archive public file.
- The tests pass.

**Note for the owner, not the agent:** keep sales templates in a private place (a private gist or notes app), not in this public repo.

---

## WP1a. Validate RFC 3161 timestamps offline

### Why

Today `epi verify` reports RFC 3161 tokens as "present; signature not validated" (`epi_cli/verify.py`
around line 1400). A token is only evidence once a verifier checks it.

When checked properly, it proves *"this exact data existed no later than time T, attested by a third
party that EPI Labs does not control"*. That is what stops a vendor fabricating or backdating a run after a
dispute starts. It is the single most important fix in this plan.

### What exists today (read these first)

- `epi_core/notarize.py`:
  - `DEFAULT_TSA_URL = https://freetsa.org/tsr`.
  - `_build_rfc3161_query` hand-builds a TimeStampReq with **no nonce and no certReq**.
  - `_submit_rfc3161` stores the **whole TimeStampResp** (not just the token).
  - `_parse_tsr_gen_time` byte-scans for a time string. This is a heuristic, not parsing.
  - `notarize_manifest` and `embed_notarization` write `artifacts/notarization/tsa_reply.tsr` and `notarization.json`.
- `epi_core/checkpoints.py`:
  - Heartbeat checkpoints submit the **hash-chain head** to the TSA and store `tsa_token_b64` in `artifacts/checkpoints/NNNNNN.json`.
  - `verify_checkpoints` recomputes chain heads and detects trimming, but never checks the token.
- `epi_core/container.py` around lines 1204–1250: seal-time notarization.

### Critical bug to fix first: the seal-time timestamp cannot currently be checked

In `container.py` the seal-time digest is `get_canonical_hash(manifest, exclude_fields=["signature"])`,
computed **before**:
- the notarization files are added to `file_manifest`;
- `VERIFY.txt` is added;
- `viewer.html` is added;
- `trust.payload_hash` is recomputed;
- the manifest is re-signed.

So the final manifest in the file is **not** what was timestamped, and a verifier can never recompute the
imprint. Validating that token today would always report a mismatch.

**Fix: define a recomputable imprint.** Add this to `epi_core/notarize.py`:

```python
IMPRINT_SCHEME = "epi-tsa-imprint/v1"
_IMPRINT_EXCLUDED_EXACT = {"viewer.html", "VERIFY.txt", "manifest.json", "mimetype"}
_IMPRINT_EXCLUDED_PREFIXES = ("artifacts/notarization/", "artifacts/scitt/", "artifacts/transparency/")

def compute_seal_imprint(workflow_id: str, created_at_iso: str, public_key_hex: str | None,
                         file_manifest: dict[str, str]) -> str:
    """SHA-256 hex over JCS({scheme, workflow_id, created_at, public_key, files}) where files
    is file_manifest minus display/notarization members. Recomputable from the final manifest."""
```

- Use `rfc8785.dumps` (already a dependency) for canonical JSON.
- In `container.py`, call it at the notarization point with the current `manifest.file_manifest`. At that moment it holds only the payload files, which is exactly the set the verifier will filter down to.
- Submit **that** digest to the TSA. Store it in `notarization.json` as:
  ```json
  {"imprint_scheme": "epi-tsa-imprint/v1", "imprinted_digest": "<hex>"}
  ```
  (alongside the existing fields).
- **Check the repack path.** `epi_recorder/api.py` around lines 1759–1784 re-packs with `EPI_NOTARIZE` suppressed ("first pack already notarized"). Write an end-to-end test: `record()` → final `.epi` → recompute the imprint from the final `manifest.file_manifest` → it must equal `imprinted_digest`.
  - If the repack changes any payload file hash, the imprint goes stale. In that case, either notarize on the **final** pack only, or compute the imprint over the files that do not change between packs. Pick whichever keeps the test green and document the choice in a code comment.
- Old artifacts have no `imprint_scheme`. The verifier must report them as **"legacy token: imprint not recomputable (sealed before 4.6); presence only"**. That is not a failure.

### New module `epi_core/tsa_verify.py`

**Dependency.** Add `asn1crypto>=1.5,<2` to `[project] dependencies` in `pyproject.toml` (pure Python, MIT
licence, free). Use it for parsing only. Use `cryptography` (already a dependency) for all signature
checks.

**API.**

```python
@dataclass
class TsaValidation:
    status: Literal["valid", "imprint_mismatch", "bad_signature", "untrusted", "cert_invalid",
                    "not_granted", "malformed", "absent"]
    gen_time: str | None          # UTC ISO-8601, from TSTInfo.genTime (parsed, not scanned)
    tsa_subject: str | None       # signer certificate subject
    tsa_root: str | None          # name of the pinned root it chained to
    serial: int | None            # TSTInfo.serialNumber
    policy_oid: str | None
    hash_algorithm: str | None    # messageImprint algorithm
    detail: str                   # one human sentence explaining the status

def validate_tsr(blob: bytes, expected_digest: bytes, *,
                 trust_roots: list[x509.Certificate] | None = None,
                 extra_certs: list[x509.Certificate] | None = None) -> TsaValidation: ...
def load_pinned_tsa_roots() -> list[tuple[str, x509.Certificate]]: ...
```

**Validation steps**, in this order. Stop at the first failure and return that status.

1. Parse `blob`. Accept both a full `tsp.TimeStampResp` (what we store) and a bare `cms.ContentInfo` token.
   - For a response, require `status` ∈ {`granted`, `granted_with_mods`}; otherwise return `not_granted`.
   - Any parse error returns `malformed`.
2. Get the `SignedData`. Require `encap_content_info.content_type == "tst_info"` (OID 1.2.840.113549.1.9.16.1.4). Parse `TSTInfo`.
3. **Imprint check.**
   - `message_imprint.hash_algorithm` must be sha256, sha384 or sha512.
   - `hashed_message` must equal `expected_digest` byte for byte; otherwise return `imprint_mismatch`.
4. **SignerInfo.**
   - Exactly one is expected. Locate the signer certificate by `sid` (issuer+serial or subject key identifier) among `signed_data["certificates"]`, then `extra_certs`, then the pinned TSA certificates.
   - Not found returns `untrusted`, with a detail saying the token carries no certificate (older tokens were requested without certReq).
5. **Signed attributes.**
   - `content-type` must be tst_info.
   - The `message-digest` attribute must equal `hash(signer digest_algorithm, eContent raw octets)`. The raw octets are the DER bytes of TSTInfo, taken from `encap_content_info["content"].contents` (the raw contents, not a re-encoding).
   - If an ESS `signing-certificate` or `signing-certificate-v2` attribute is present, its certificate hash must match the signer certificate.
6. **Signature.**
   - The signed bytes are the DER of `signed_attrs` re-tagged as a SET (`b"\x31" + der[1:]`).
   - Verify with the signer certificate's public key: RSA PKCS#1 v1.5, RSA-PSS (read the parameters) or ECDSA, using the signer's digest algorithm. Any exception returns `bad_signature`.
7. **Certificate checks.**
   - The signer certificate must have Extended Key Usage `timeStamping` (1.3.6.1.5.5.7.3.8); RFC 3161 requires it, and it should be critical.
   - `genTime` must fall inside the certificate's validity period.
   - Otherwise return `cert_invalid`.
8. **Chain to a pinned root.**
   - Build the path signer → intermediates (from the token's certificates or `extra_certs`) → a root in `trust_roots`, which defaults to `load_pinned_tsa_roots()`.
   - Check each link with `cert.verify_directly_issued_by(issuer)` (available in `cryptography` ≥ 40). Check each certificate's validity at `genTime`.
   - No path returns `untrusted`.
   - Do **not** do online revocation checks. Validation stays fully offline. Write that in the docstring and in `docs/VERIFICATION_CONTRACT.md`.
9. Return `valid` with all fields filled in.

### Pinned TSA roots (free, offline)

- Create `epi_core/assets/tsa_roots/` containing the PEM roots plus a `ROOTS.json` listing for each one: name, source URL, SHA-256 fingerprint, the date it was added, and the TSA URL it covers.
  - **FreeTSA:** the root from `https://freetsa.org/files/cacert.pem`. Also pin the signer certificate from `https://freetsa.org/files/tsa.crt` as an extra certificate, because old tokens were requested without certReq and carry no certificate.
  - **DigiCert public TSA** (`http://timestamp.digicert.com`, free, no account): request one token **with certReq**, read the chain inside it, and pin its root. As of 2025–2026 this is expected to be "DigiCert Trusted Root G4". Confirm the fingerprint against DigiCert's published root list at `https://www.digicert.com/kb/digicert-root-certificates.htm` before committing.
  - Record in `ROOTS.json` exactly how each fingerprint was checked.
- Make sure the package data ships these files: check `MANIFEST.in` and the `pyproject.toml` package-data settings, and add a test that `importlib.resources` can load them from an installed wheel.
- Let users add their own roots with the env var `EPI_TSA_TRUST_ROOTS=/path/a.pem:/path/b.pem` and the CLI flag `epi verify --tsa-root PATH` (repeatable).

### Request side changes (`notarize.py`)

- Replace the hand-built `_build_rfc3161_query` with an `asn1crypto.tsp.TimeStampReq` that sets:
  - `version=1`;
  - the message imprint (sha256);
  - a random 64-bit `nonce`;
  - **`cert_req=True`**, so future tokens carry their certificate chain.
- Keep the old function name as a thin wrapper so `checkpoints.py` keeps working.
- In `_submit_rfc3161`, parse the response and check that the returned nonce equals the one sent. On a mismatch, return `None` and record a gap, exactly like an outage.
- **Two independent TSAs.** Add `EPI_TSA_URLS` (comma-separated; default `https://freetsa.org/tsr,http://timestamp.digicert.com`). `EPI_TSA_URL` still works as a single-URL override.
  - **Seal time:** submit to every URL and store `artifacts/notarization/tsa_reply.tsr` (first success, kept for backward compatibility) plus `tsa_reply_<n>.tsr` for each additional success. List each one in `notarization.json` under `"tsa_tokens": [{"url": ..., "member": ...}]`.
  - **Checkpoints:** use the first URL and fall back to the next only if it fails. Never wait on both, to keep runs fast.
- Replace `_parse_tsr_gen_time`'s byte scanning with real parsing through `tsa_verify`. Keep the function name; it returns the parsed `genTime` or `None`.

### Verify side changes

- **`epi_core/checkpoints.py` → `verify_checkpoints`:**
  - For every record with a token, call `validate_tsr(token, bytes.fromhex(chain_head))`, *after* the existing recompute-head comparison.
  - Add the result to the record dict as `tsa_validation`.
  - An `imprint_mismatch`, `bad_signature` or `cert_invalid` result means tampering: set `ok=False` with the message `CHECKPOINT TIMESTAMP INVALID at index N: <detail>`.
  - `untrusted` (root not pinned) is a warning, not a failure, with a message telling the user to pin the root with `--tsa-root`.
- **`epi_cli/verify.py`:**
  - Replace the "presence only" notarization block (around lines 1400–1421) with real validation. Recompute the imprint with `compute_seal_imprint` from the final manifest; legacy files have no `imprint_scheme`.
  - Add `report["timestamps"]`:
    ```json
    {"seal": [{"url":..., "status":..., "gen_time":..., "tsa_subject":..., "tsa_root":..., "imprint_scheme":...}],
     "checkpoints": [{"index":..., "event_count":..., "status":..., "gen_time":...}],
     "earliest_verified": "<ISO or null>",
     "statement": "<one sentence, see below>"}
    ```
  - Add `facts["timestamp_verified"]` (bool).
  - Human output lines:
    - `Timestamp:  VERIFIED — existed no later than 2026-10-10T12:00:00Z (FreeTSA; chain to pinned root "FreeTSA Root CA")`
    - `Timestamp:  legacy token — imprint not recomputable (sealed before 4.6); presence only`
    - `Timestamp:  INVALID — <detail>` (shown in red)
    - `Timestamp:  none`
  - The statement must be exactly as strong as what was checked. For example: "Steps 1–50 existed no later than T1 (checkpoint 0); the sealed manifest existed no later than T2." Never say "created at".
  - **Policy:**
    - A new-scheme token that is `imprint_mismatch`, `bad_signature` or `cert_invalid` makes the decision **FAIL** in every policy.
    - Missing tokens or legacy tokens never change the decision by default.
    - Add `epi verify --require-timestamp`: FAIL unless at least one seal-time token is `valid`. Also turn it on in `VerificationPolicy.STRICT` if that does not break existing strict tests. If it does, leave STRICT alone and document that.
  - **Sanity check:** if `manifest.created_at` is more than 10 minutes *after* the earliest verified `genTime`, add a warning that the sealer's clock and the TSA disagree. (A creation time *later* than the TSA's time is impossible for honest data.)
  - Keep the `--json` output stable: add keys, never rename existing ones.
- **`epi verify --aiuc1`:** when timestamps are valid, add them as evidence under the Accountability (logging) domain, without claiming any AIUC-1 control is satisfied.

### Tests: `tests/test_tsa_validation.py` (offline, no network)

Build a throwaway TSA inside the test with `cryptography` and `asn1crypto`:
- a self-signed root CA;
- a TSA certificate with critical EKU `timeStamping`, signed by that root;
- a helper `make_tsr(digest, *, gen_time, include_certs=True, tamper=None, key=None)` that builds a real `TimeStampResp` and signs the signed attributes.

Cases:
1. A valid token with the root passed as `trust_roots` gives `valid`, and `gen_time` matches.
2. A different digest gives `imprint_mismatch`.
3. One byte flipped in TSTInfo (with the signature not redone) gives `bad_signature`.
4. A token signed by a key that does not match the certificate gives `bad_signature`.
5. A TSA certificate without the timeStamping EKU gives `cert_invalid`.
6. `gen_time` outside the certificate's validity gives `cert_invalid`.
7. An unknown root gives `untrusted`.
8. No certificates in the token, but the signer passed as `extra_certs`, gives `valid`.
9. A `rejection` status gives `not_granted`. Garbage bytes give `malformed`.
10. The ESS signing-certificate-v2 hash points at a different certificate: the token must not be `valid`.
11. **End to end:** `record()` with a monkeypatched `_submit_rfc3161` that returns test-TSA tokens. `epi verify --json` reports `timestamp_verified: true`, and the imprint recomputed from the final file matches.
12. **End to end, tampering:** edit the token bytes inside an artifact and re-sign the manifest with the same key (simulating a vendor who controls the key). Verify reports `INVALID` and the decision is FAIL.
13. **Legacy:** an existing sample in `docs/assets/` is reported as `legacy`, not FAIL, and its decision is unchanged from before the change.
14. **Checkpoints:** a checkpoint whose token imprints a different chain head gives `CHECKPOINT TIMESTAMP INVALID`.

Optional network test, marked `@pytest.mark.network` and skipped by default (register the marker in `pyproject.toml`): submit a real digest to FreeTSA and DigiCert and validate against the pinned roots. Run it manually once and paste the output into the PR description.

### Docs and copy to update in the same PR

- `ARCHITECTURE.md`: the RFC 3161 bullet.
- `docs/VERIFICATION_CONTRACT.md`: the new `timestamps` block, statuses, policy, and "offline, no revocation checks".
- `docs/THREAT_MODEL.md`: add "Backdating or fabrication after the fact" as an attack prevented *when a valid token is present*. Assumptions: the TSA's private key was not compromised and its clock was honest.
- `docs/KNOWN_LIMITATIONS.md`: move "RFC 3161 tokens stored but not validated" to Fixed. Add new limitations: no revocation checks; legacy tokens; the browser viewer does not validate.
- `README.md`, `website/trust.html`, `website/index.html`, `website/enterprise.html`: only now change the "not validated" wording, and only for `epi verify`.
- `docs/spec/EPI-SPEC.md`: the new optional `notarization.json` fields and the `epi-tsa-imprint/v1` definition, precise enough that someone could re-implement it.
- `tests/test_tsa_presence_honesty.py`: rewrite it to the new truth:
  - the viewer still says "not validated" (validation happens in the CLI);
  - `checkpoints.py` and `verify.py` no longer claim "presence only" for new-scheme tokens;
  - the website copy names `epi verify` as the place validation happens.
- Bump the version to 4.6.0 following the repo's version-consistency tests (`tests/test_version_consistency_runtime.py`).

**Acceptance.**
- All 14 tests pass.
- `epi demo --no-browser` with network shows `Timestamp: VERIFIED`; with network blocked it shows `none` and still PASSes.
- An old sample verifies with the same decision as before.

---

## WP1a-2. Take checkpoint timestamping off the agent's hot path

**Why.** `RecordingContext.add_step` in `epi_recorder/patcher.py` (around lines 195–233) calls
`create_checkpoint` **synchronously**, and that calls `httpx.post` with a timeout of up to 30 seconds. The
code comment says "never blocks", but it can block an agent's step for up to 30 seconds whenever the TSA is
slow.

**Steps.**
1. Add a small background submitter in `epi_core/checkpoints.py`: one daemon thread per recording context and a `queue.Queue`.
   - `add_step` only enqueues `(index, event_count, chain_head)`. The thread calls `create_checkpoint`.
   - Each checkpoint stays bound to the chain head at the moment it was enqueued, so the imprint is still correct.
2. In `finalize()` (before sealing), drain the queue and wait at most `EPI_CHECKPOINT_DRAIN_SECONDS` (default 10). Whatever is not finished is recorded as a runtime gap through the existing `append_runtime_gap`.
3. Keep the env switches `EPI_CHECKPOINTS_ENABLED`, `EPI_CHECKPOINT_INTERVAL_EVENTS` and `EPI_CHECKPOINT_INTERVAL_SECONDS` unchanged.

**Tests.**
- A fake `tsa_submit` that sleeps 2 seconds must not slow 100 `add_step` calls beyond normal.
- After `finalize`, every checkpoint file exists, or a gap is recorded for it.
- The existing `tests/test_checkpoints.py` still passes.

---

## WP1b. Customer witness on every seal

**Why.** Even with timestamps, the customer should hold their own copy of "a run with this hash was sealed
at this time", in a system the vendor cannot edit. This is free because the customer supplies the endpoint.

**Design.**
- **Config.**
  - `record(..., witness_url=None, witness_secret=None)`, with env fallbacks `EPI_WITNESS_URL` and `EPI_WITNESS_SECRET`.
  - Gateway settings with the same names in `GatewayRuntimeSettings` (`epi_gateway/main.py`), used on case export.
  - Several URLs are allowed (comma-separated) so a vendor can witness to more than one customer system.
- **Payload** (`schema: "epi-witness/v1"`), sent **after** the final `.epi` is written:
  ```json
  {"schema": "epi-witness/v1", "type": "epi.sealed",
   "workflow_id": "...", "goal": "<only if the caller sets witness_include_goal=True; default omitted>",
   "manifest_hash": "<canonical SHA-256 of the FINAL manifest, signature excluded>",
   "file_sha256": "<SHA-256 of the whole .epi file>",
   "public_key": "<hex>", "key_fingerprint": "<first 16 hex of sha256(pubkey hex), as in epi_core/trust.py>",
   "steps": <int>, "sealed_at": "<sealer clock, ISO>",
   "seal_timestamp": {"status": "...", "gen_time": "..."} }
  ```
  - Compute `manifest_hash` with the same function the verifier uses: `get_canonical_hash(manifest, exclude_fields=["signature"])` on the manifest read back from the final file.
  - **No content and no step data.** Only hashes and counts.
- **Signing.**
  - HMAC header `X-EPI-Signature: sha256=<hex>` when a secret is set (same format as today).
  - **Also** an Ed25519 signature of the body with the sealing key, in the header `X-EPI-Seal-Signature: ed25519:<keyname>:<hex>`, so the customer can verify it with the vendor's pinned public key.
- **Delivery.** Must never fail or slow the seal.
  - Move `send_signed_webhook` out of `epi_gateway/approval_notify.py` into `epi_core/webhook.py`, and re-export it from the old location so the gateway and its tests are unchanged.
  - Write each payload first to an outbox, `~/.epi/witness_outbox.jsonl` (respect `EPI_HOME`). Then deliver from a daemon thread.
  - On success, mark the entry `delivered_at`. On failure, leave it in the outbox.
  - At the end of `record()`, wait at most `EPI_WITNESS_TIMEOUT` (default 5 s) for delivery.
  - New CLI command `epi witness flush` retries everything undelivered; `epi witness status` lists pending, delivered and failed entries.
- **Verification side.**
  - `epi verify run.epi --witness-log received.jsonl`, where the log is the customer's file of received payloads, one JSON object per line. Each line may carry a receiver-added `received_at`.
  - It looks up `workflow_id` and compares `manifest_hash` and `file_sha256`. It reports one of:
    - `WITNESSED (received <received_at>)`
    - `NOT IN WITNESS LOG`
    - `MISMATCH`: the file differs from what the customer was told at seal time. This is a FAIL.
  - Add `report["witness"]`.
- **Reference receiver.** Not a new product surface: `examples/witness_receiver/receiver.py`, standard library only (`http.server`), about 60 lines. It checks the HMAC, adds `received_at`, and appends to `received.jsonl`. The README in that folder shows how a customer runs it for free on any small server, or points the webhook at their own system.

**Tests** (`tests/test_seal_witness.py`):
- A payload is sent with the correct hashes; use a local `http.server` on an ephemeral port.
- Both signatures verify.
- With the endpoint down, the seal still succeeds, the outbox has the entry, and `epi witness flush` delivers it once the server is up.
- `--witness-log` gives WITNESSED, NOT IN WITNESS LOG, and MISMATCH (when the file is altered and re-signed after the witness was sent).
- Nothing from steps or prompts appears in the payload: assert against a run containing a secret-looking string.

**Docs.**
- `docs/WITNESS.md`, one page aimed at the vendor's customer: "how to receive and keep witness records".
- Update `docs/THREAT_MODEL.md` with what the witness adds.
- Update `docs/KNOWN_LIMITATIONS.md`: the witness only proves what was sent, and the vendor can choose not to send it, but a missing witness entry for a case the customer knows happened is itself evidence.

---

## WP3. Hash chain and capture-time checkpoints for gateway exports (issue #26)

Read issue #26 in full first. It is the specification. Summary and concrete steps:

**Problem.** `build_case_payload_from_events` (`epi_core/case_store.py`, around line 518) projects capture
events to steps with **no `prev_hash`**, so gateway exports detect enforcement downgrades but not trimming.
Hashing only at export time proves nothing about history before the export.

**Step A: chain at export (detects trimming after export).**
1. Freeze the ordering **before** hashing. The `captured_at`/`event_id` sort and the synthetic `session.start` insert plus index renumbering (`case_store.py` around lines 508 and 593–608) must run first.
2. Then, for each projected step in order, set `prev_hash` (`CHAIN_START` for step 0) and compute `get_canonical_hash(StepModel(**step), format="json")`. This mirrors `RecordingContext.add_step` in `epi_recorder/patcher.py`.
3. Confirm the hash format matches what `epi verify` recomputes for the artifact's spec version (`canonical_format_for` and `epi_core/serialize.py`).
4. Old exports stay unchained forever, and the verifier's pre-chain path already handles them. Add a version note in `CHANGELOG.md`; no migration is needed.

**Step B: capture-time protection (the real fix).**
1. In `epi_gateway/worker.py` `EvidenceWorker`, maintain for each case a running chain over **raw capture events in the order they were accepted**:
   - `event_hash = sha256(JCS(event))`;
   - `head = sha256(prev_head || event_hash)`.
2. Persist `(case_id, event_count, head)` in the case store on every batch flush.
3. On flush, throttled per case (every `EPI_CHECKPOINT_INTERVAL_EVENTS` events or `EPI_CHECKPOINT_INTERVAL_SECONDS` seconds), submit the head to the TSA through the WP1a-2 background submitter. Store the token with the case.
4. On export:
   - include the raw events as `artifacts/capture/events.jsonl` (redacted exactly as the case already is; reuse whatever the capture manifest already records);
   - include the capture checkpoints as `artifacts/capture/checkpoints/NNNNNN.json`.
5. Extend `epi verify`:
   - recompute the raw-event chain from `artifacts/capture/events.jsonl`;
   - compare it to each capture checkpoint and validate each token (WP1a);
   - report `TRIMMED` when the export has fewer events than a checkpoint attests to.

   This is the design question the issue raises. The approach above is the recommended answer: it attests capture-time history without depending on how steps are projected. If you find a simpler way that meets the same acceptance test, document why in the PR.

**Acceptance** (from the issue):
- Deleting one event from a gateway case and exporting makes `epi verify` print `TRIMMED`.
- Reordering two events makes `epi verify` print a checkpoint mismatch.
- A large case (10,000 events) exports in a reasonable time; record the number in the PR.
- Close issue #26 from the PR.

---

## WP1c. did:web identity onboarding

**Why.** Today a fresh key verifies as "NOT_PINNED", and the verifier itself says *"anyone can re-sign a
rebuilt chain with a fresh key"*. A customer needs a one-time, free way to tie the vendor's key to the
vendor's domain.

**What exists.**
- `epi_core/did_web.py`: `resolve_did_web`, `extract_ed25519_key`, `generate_did_document`.
- `epi_core/trust.py` around line 341: `_verify_did_web` when `manifest.governance["did"]` is set.
- `epi keys trust` in `epi_cli/main.py` around line 1400.

**Steps.**
1. **`epi keys did --domain vendor.com [--path agents/claims] [--key default]`:** writes `did.json` with `generate_did_document` and prints:
   - the DID (`did:web:vendor.com` or `did:web:vendor.com:agents:claims`);
   - the exact URL to host it at (`https://vendor.com/.well-known/did.json`, or `https://vendor.com/agents/claims/did.json`);
   - the free hosting options (GitHub Pages, Cloudflare Pages).
2. **Recording:** `record(..., did="did:web:vendor.com")` and env `EPI_DID` set `manifest.governance["did"]` before signing. Grep first, because part of this may exist. The gateway gets the same through a setting.
3. **`epi keys trust --from-did did:web:vendor.com [--name vendor]`:** resolves once (network), extracts the Ed25519 key, pins it locally with the DID recorded, and prints the fingerprint for the user to confirm.
4. **Verify output:**
   - When pins exist **and** the file's key is not among them, show red: `IDENTITY: NOT A KEY YOU TRUST (you have pinned: vendor). This file was not sealed by a key you trust.`
   - When no pins exist at all, keep today's softer `NOT_PINNED` text.
   - When a DID is declared but `--offline` is set, show `DID declared (did:web:vendor.com), not resolved offline; pinned key matches/does not match`.
5. **Key rotation:** document listing several `verificationMethod` entries in `did.json`. The verifier must accept any listed Ed25519 key, so add a test.

**Tests:** mock resolution using the `_RequestsShim` patch point already in `did_web.py`. Cover each verify output above.

**Docs:** `docs/IDENTITY-ONBOARDING.md` with two sections, "for the vendor (5 minutes)" and "for the customer (2 minutes)".

---

## WP4. Core vs experimental split (no code deleted)

**Why.** About 78k lines across roughly 10 surfaces, maintained by one person. Focus the tests, docs and
claims on the core.

**Core (keep investing):**
- `epi_recorder` (SDK and integrations: OpenAI, Anthropic, LangChain, LangGraph, LiteLLM, OpenAI Agents SDK, OpenTelemetry)
- `epi_core`
- `epi_cli` (record, verify, view, keys, policy, witness)
- `epi_gateway` (capture, proxy, cases, review, export)
- `web_viewer` and `epi_viewer_static`
- `pytest_epi`
- `website/` (static, Cloudflare Pages free tier)

**Experimental (frozen: no new features until a paying user asks; bug fixes allowed):**
- `epi_mcp` (ChatGPT/Claude connector)
- `verify_portal` (hosted portal, auth, Paddle billing, tier gating)
- TRACE export (`epi_recorder/integrations/trace_exporter.py`)
- Microsoft AGT import/export (`epi_recorder/integrations/agt*`)
- `epi_guardrails`
- `website-v2/`
- remote SCITT service

**Steps.**
1. **README:** add a "Core" and "Experimental" table near the top of the project layout section. Each experimental item gets one line: "frozen; works as documented; not on the critical path."
2. **Tests:** register a marker `experimental` in `pyproject.toml`. Add `pytestmark = pytest.mark.experimental` to these files:
   `test_mcp_*.py`, `test_paddle_webhook_signature.py`, `test_tier_gating_plans.py`, `test_verify_portal*.py`,
   `test_trace_exporter_producer.py`, `test_trace_references.py`, `test_agt_*.py`, `test_embed_agt_pack.py`,
   `test_workspace_to_agt_exporter.py`, `test_policy_evaluation_agt_compat.py`, and any `test_*guardrail*` files.
   Check each file first, and keep any test that also covers core behaviour in the core run.
3. **CI:**
   - `scripts/release-gate.sh` and `release-gate.ps1` run `-m "not browser and not experimental"`.
   - Add a separate job in `.github/workflows/release-gate.yml` that runs `-m experimental` with `continue-on-error: true`.
4. **Render dependency:**
   - Make sure `epi demo`, the README's 60-second path and `epi verify` never call the hosted portal or Render. Grep for `onrender.com` and `epilabs.org/api` in core packages.
   - Disable the schedule in `.github/workflows/keep-warm.yml` (comment it out, with a note). Hiding cold starts is no longer needed once nothing core depends on Render.
   - Seal-time TSA calls are fine, but with no network they must fail fast. Set the demo's `EPI_TSA_TIMEOUT` to 5 seconds.
5. **`docs/SCOPE.md`:** the rule "no new surface until three external companies use the core", plus the list above.

**Acceptance.**
- CI is green.
- Core test time is recorded in the PR (before and after).
- With network blocked, `epi demo --no-browser` completes in under 15 seconds and PASSes.

---

## WP2.1. Any-language docs

**Why.** The gateway already accepts any language, but the docs undersell it.

**What exists.**
- `POST /capture` and `POST /capture/batch` accept generic events (`epi_core/capture.py`, `CaptureEventModel`).
- `POST /v1/chat/completions` and `POST /v1/messages` proxy OpenAI- and Anthropic-style APIs (non-streaming).
- The default local port is 8787 (`epi_cli/main.py` help text).

**Write `docs/ANY-LANGUAGE.md`** with:
1. **TypeScript (OpenAI SDK):** `new OpenAI({ baseURL: "http://localhost:8787/v1", apiKey })`, with a `stream: false` call. About 15 lines. Note that streaming is unsupported until WP2.2 ships.
2. **TypeScript (Anthropic SDK):** `baseURL: "http://localhost:8787"`.
3. **curl to `/capture`:** a minimal valid event built from the `CaptureEventModel` fields, so Go, Java and .NET users can send tool calls and decisions.
4. **How to export the case and verify it:** `POST /api/cases/{id}/export`, then `epi verify`.
5. **Smoke test:** add a `tests/` test that starts the gateway app with FastAPI's `TestClient` and posts the exact JSON shown in the doc, so the docs can't go stale.

Link the doc from the README integrations table, replacing the "Python only" framing.

---

## WP2.2. Gateway streaming (issue #31)

**Why.** Streaming calls get a 501 (`epi_gateway/main.py` around lines 1340 and 1407), which forces them onto
the weaker SDK path.

**Steps.**
1. In `epi_gateway/proxy.py`, add async streaming relays using `httpx.AsyncClient().stream("POST", ...)` (httpx is already a dependency). Leave the existing urllib non-streaming path unchanged.
2. In the two routes, when `stream=true`, return a FastAPI `StreamingResponse` that:
   - relays each upstream chunk to the client **unchanged and immediately**;
   - feeds each chunk to an assembler:
     - **OpenAI:** parse `data:` lines until `[DONE]`. Accumulate `choices[].delta.content`, `delta.tool_calls` (merge by index; concatenate `function.arguments`), `finish_reason` and `usage` (when `stream_options.include_usage` is set).
     - **Anthropic:** events `message_start`, `content_block_start`, `content_block_delta` (`text_delta`, `input_json_delta`), `content_block_stop`, `message_delta` (stop_reason, usage), `message_stop`.
   - after the stream ends, builds the same capture request the non-streaming path builds (`build_openai_proxy_capture_request` / `build_anthropic_proxy_capture_request`) from the assembled response, marked `"streamed": true`, and enqueues it.
3. **Fail-closed semantics.** Decide **before** opening the upstream stream: if the gateway is in fail-closed mode and the capture worker is not healthy, return 503 (same check as the non-streaming path). Once streaming has started, a capture failure at the end cannot be undone. Record a capture gap event and log it, and document this in `docs/KNOWN_LIMITATIONS.md`.
4. **Client disconnects mid-stream:** capture what was assembled, with `"stream_incomplete": true`.
5. Update the tests that pin the 501 (`tests/test_gateway_proxy.py`) to the new behaviour.

**Tests.**
- A fake upstream (an `httpx.MockTransport`, or a small local ASGI app) emitting realistic SSE for both providers, including tool calls split across chunks.
- The client receives a byte-identical stream.
- The captured case contains the full text and tool-call arguments.
- Disconnect handling, and fail-closed with an unhealthy worker giving 503.

Close issue #31 from the PR, and update the gateway known gaps in the capture manifest.

---

## WP2.3. OTLP/HTTP trace receiver

**Why.** The docstring of `epi_recorder/integrations/opentelemetry.py` says "any language", but
`EPISpanExporter` runs inside a Python process. A receiver in the gateway makes that claim true.

**Steps.**
1. Add `POST /v1/traces` to the gateway, accepting OTLP/HTTP **JSON** (`Content-Type: application/json`, the `ExportTraceServiceRequest` JSON mapping).
   - For `application/x-protobuf`, return 415 with a message saying to set the exporter to JSON. This avoids a new required dependency.
   - Optionally support protobuf if `opentelemetry-proto` is installed, as a new extra `otlp`.
2. Move the span-to-event mapping out of `opentelemetry.py` into `epi_core/otel_mapping.py`, so the gateway does not import the recorder. Map GenAI semantic-convention attributes (`gen_ai.system`, `gen_ai.request.model`, `gen_ai.operation.name`, prompt and completion events, `gen_ai.tool.name`, token usage) to capture events, and keep unknown attributes as metadata.
   - Group spans into cases by `traceId`. Order by `startTimeUnixNano`.
3. Apply the gateway's existing auth and redaction to these events, exactly as for `/capture`.
4. Return the OTLP success shape `{"partialSuccess": {}}`.
5. Fix the docstring in `opentelemetry.py` to describe the two paths honestly: an in-process Python exporter, or any language through the gateway's `/v1/traces`.

**Tests:** post a recorded JSON payload (write a realistic fixture by hand) and assert the resulting case
steps and redaction. Wrong content type gives 415.

**Docs:** add a section to `docs/ANY-LANGUAGE.md` with Node (`@opentelemetry/exporter-trace-otlp-http`, `url: "http://localhost:8787/v1/traces"`) and Go examples.

---

## WP1d. Sigstore Rekor spike (one day maximum, then stop)

**Goal.** Find out whether EPI can log a sealed artifact's hash in Sigstore's free public transparency log,
so the third-party log no longer depends on the Render free tier.

**Spike steps.**
1. Read the current Sigstore docs to find the live public Rekor API and its staging instance. Rekor v2 ("rekor-tiles") was rolling out in 2025–2026, so do not assume the v1 URLs are still current.
2. **Against staging only**, try in order:
   - (a) `hashedrekord` with an Ed25519 public key, where the artifact is a small JSON statement `{"workflow_id", "manifest_hash", "file_sha256"}` and its SHA-256 is the logged hash.
   - (b) if (a) is rejected because Ed25519 cannot sign a prehashed digest, the `rekord` type, or whatever entry type the current docs recommend for Ed25519, with the same small statement.
   - (c) if neither works with Ed25519, stop. Record the finding.
3. Write `plans/REKOR-SPIKE.md`: what worked, the exact request and response, how to verify the inclusion proof **offline** (which public key to pin), privacy notes, and a go/no-go decision.
   - **Privacy:** entries are public and permanent and reveal timing and the key fingerprint. They must therefore be **opt-in only** and never include goals or content.

**If it's a go** (separate PR, `feat/rekor-anchor`):
- Add `epi-register --rekor` and an env opt-in `EPI_REKOR=1` at seal time.
- Embed the entry under `artifacts/transparency/rekor_entry.json` following the existing SCITT embedding pattern in `epi_cli/scitt.py` (`_build_scitt_artifact`). Make sure the original seal verification still passes.
- Verify the signed entry timestamp and inclusion proof offline in `epi verify` against a pinned Rekor public key in `epi_core/assets/`.

**If it's a no-go:** WP1a plus WP1b already provide independent time attestation and a customer-held
record. Note this in `docs/KNOWN_LIMITATIONS.md` and move on.

---

## WP5. Launch assets (drafts only; the agent posts nothing)

Everything here is written to `plans/launch/` for the owner to review and post personally. The agent must
not post to GitHub issues, Hacker News, or other repositories.

1. **`plans/launch/show-hn.md`** (write it only after WP1a has shipped):
   - Title idea: "Show HN: Signed evidence files for AI agent runs, with timestamps you can check offline".
   - Body: what it proves, what it does **not** prove (quote `KNOWN_LIMITATIONS.md`), the 60-second demo, and a link to the threat model.
   - No marketing adjectives.
2. **`plans/launch/awesome-list-pr.md`:** the exact one-line entry and PR description for `systempromptio/awesome-ai-agent-governance` (audit trail section).
3. **`examples/langgraph_evidence/`:** a minimal, runnable LangGraph agent recorded with `epi_recorder.integrations.langgraph`, plus a `README.md` written so it could be proposed upstream as a community integration example. Add a smoke test that runs it with a fake LLM, no API key.
4. **`plans/launch/issue-76-reply.md`:** a draft public reply to issue #76 (Receipt Protocol) answering its three questions factually. Cover:
   - **files vs APIs:** both. A `.epi` is the portable unit, and the gateway is the API.
   - **what `epi-register` does:** check `epi_cli/scitt.py` and describe it exactly; it is not on-chain.
   - **how redaction works:** automatic regex patterns, on by default; see `epi_core/redactor.py`.

   Keep it collegial, cite code paths, and end with the repo's attribution footer only if the owner wants one.
5. **`scripts/dev/pypi_stats.py`:** fetches `https://pypistats.org/api/packages/epi-recorder/recent` and `/overall`, and prints last day, week and month, plus a CSV line to append to a local file. Standard library only. No scheduling and no telemetry changes.
6. **`plans/launch/metrics.md`:** what to track weekly, with no new telemetry:
   - PyPI downloads (script above);
   - GitHub stars and forks;
   - the number of distinct external `.epi` files verified on the static verify page, **only if** the existing opt-in telemetry already records verifies (check `docs/TELEMETRY-PRIVACY.md`; do not add tracking);
   - replies to outreach emails (counted manually by the owner).

---

## Appendix A. Facts the agent should not re-research

- EU AI Act after the Digital Omnibus (Regulation (EU) 2026/1744; Official Journal 24 July 2026; in force 27 July 2026):
  - Annex III high-risk obligations, including Art. 12 logging and Art. 26(6) deployer log retention of at least 6 months, apply from **2 December 2027**;
  - Annex I (product-embedded) obligations apply from **2 August 2028**.
- AIUC-1: control **E015 "Log AI system activity"** is mandatory. The next quarterly release is due 15 October 2026. EPI's `--aiuc1` report maps by domain and must not claim that any control is satisfied.
- FreeTSA: `https://freetsa.org/tsr`. DigiCert's free public TSA: `http://timestamp.digicert.com`. Plain HTTP is fine for both, because the token itself is signed.

## Appendix B. Allowed claims after each WP

| After | New claim allowed |
|---|---|
| WP1a | "`epi verify` checks RFC 3161 timestamps offline against pinned TSA roots: the record existed no later than the attested time." |
| WP1b | "Optionally, every seal is reported at seal time to an endpoint the customer controls." |
| WP3 | "Gateway exports are hash-chained and timestamped at capture time; deleting an event is detected." |
| WP1c | "A customer can bind a vendor's key to the vendor's domain once and get a clear failure for any other key." |
| WP2.2 / WP2.3 | "Any language: OpenAI/Anthropic-compatible proxy (including streaming) and OTLP/HTTP JSON traces." |

Never claim completeness of capture, correctness of the agent, or compliance with any regulation.
