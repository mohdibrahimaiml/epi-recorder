# Changelog

All notable changes to EPI Recorder are documented here.

## [4.7.0] - 2026-10-28

### Added

- **Pilot kit: run the whole story end to end.** `examples/pilot_kit/` holds a
  LangGraph refund agent that runs with **no API key** (deterministic scripted
  graph; `--openai` optional), records two approval requests, and a demo script
  that walks vendor → approver → bank in three separate `EPI_HOME` dirs: seal
  with a vault key, approve both requests with the approver's own key, then have
  the bank pin both fingerprints and run
  `epi verify run.epi --policy strict --require-human-approval`. It also proves
  the failure paths (one byte tampered → non-zero; one approval missing →
  `INCOMPLETE`) and that the bank's home holds no private key. Run it with
  `bash examples/pilot_kit/run_pilot_demo.sh`. Two new documents:
  [docs/PILOT-GUIDE.md](docs/PILOT-GUIDE.md) for the vendor and
  [docs/BANK-REVIEWER-BRIEF.md](docs/BANK-REVIEWER-BRIEF.md) for the bank's
  reviewer, whose every command is run by the demo and asserted by a test. A CI
  workflow runs the demo on changes to the code it depends on, so it cannot rot.

- **"Break the seal" public challenge (credit-only).** `CHALLENGE.md` states
  exactly what counts as a break (an intact+signed file whose steps differ from
  the published original; `--require-human-approval` passing without the
  approver's key; a tampered file shown as intact in the browser; a wrong signer
  fingerprint; a verifier crash/hang/code execution), what does not (stolen keys,
  social engineering, attacks on hosted infrastructure), and the safe-harbour
  rules (private report first, 90-day disclosure). `challenge/` holds the
  published artifact sealed and approved with challenge keys whose private halves
  are held offline, `challenge/check_submission.py` prints BREAK / NO BREAK for
  criteria a–d locally, and `scripts/make_challenge_artifacts.py` regenerates
  everything (writing private keys only to a temp dir outside the repo).
  [GOVERNANCE.md](GOVERNANCE.md) still says no bug bounty: this is credit only.

- **Cross-check the public witness mirror (`epi witness check --mirror`).**
  Compare the live witness against the public `epi-witness-checkpoints` mirror
  (a raw.githubusercontent.com base URL or a local clone; `--offline` works with
  local files). It fails with a plain reason when a mirrored day differs on the
  live side (`head_hash`, `count` or `signature`), when a mirrored day is
  missing from the live witness (history rewritten), or when the witness key
  changed without a key-rotation entry. A day that exists only on the live side
  is fine — the mirror lags by up to a day. The mirror script is now
  append-only: it verifies every checkpoint signature with the published key,
  never rewrites an existing day, and exits non-zero with "history change
  detected" so the workflow fails instead of rewriting history.
  `mirror-template/` holds the README and `checkpoints/` placeholder to copy
  into the new public repo; the workflow cross-checks the mirror before pushing
  and still succeeds trivially while the secrets are unset. See
  [docs/WITNESS.md](docs/WITNESS.md).

- **Honest approval labels in every browser screen (step 3c).** The public
  `/verify/` page and the offline viewers no longer present an approval as a
  verified human decision. An in-run `agent.approval.response` reads
  "Agent-reported: <reviewer> approved <action>"; a gateway link reads
  "Gateway link click (not a signed approval)" (or "by a logged-in user", or
  "older gateway"); a client-claimed label reads "Agent-reported (claimed X; the
  gateway did not accept it)". The page decision line is labelled
  "Decision (agent-reported)" and never painted green from an agent step.
  A 1.2.0 signed approval is verified **in the browser** where it can be
  (canonical `review_hash`, Ed25519 signature, `artifact_binding`), and shows
  "Signed approval (approve|deny) for <id>, key fingerprint XXXX XXXX XXXX XXXX
  … pin approvers with `epi approvers add` and run
  `epi verify --require-human-approval` to confirm who"; a record that fails any
  check shows "Invalid signed approval (does not match this file)" and never
  the name; one signed by the sealing key says so. The embedded approver name is
  only ever shown as "(claimed name: …)". The fingerprint matches
  `epi_core.keys.key_fingerprint`, asserted in Chromium for three keys.

- **Human-signed approvals (`epi approvers`, `epi review approve`,
  `epi verify --require-human-approval`).** A `.epi` can now prove "a specific,
  known person approved this exact decision" with a signature from **that
  person's own key**. The verbatim format, the approval block inside the
  existing `reviews` list, the 1.2.0 review version, the five honest
  classifications, and the per-request `--require-human-approval` rule are
  documented in [docs/HUMAN-APPROVAL.md](docs/HUMAN-APPROVAL.md).
  - New `epi_core/approvers.py` + `epi approvers add|list|remove|keygen|link`.
    Approver keys live in `EPI_APPROVER_KEYS_DIR` (default
    `~/.epi/approver_keys/`), never the agent keys dir; the approver registry is
    separate from the trusted *signer* registry, so pinning a vendor's sealing
    key cannot make it an approver. `epi approvers add` refuses a key that is a
    local agent key or a pinned signer unless `--force` (with a warning).
  - `epi review <file.epi> approve --approval-id <id> --decision approve|deny
    --as <name>` verifies first, shows what is being signed, refuses
    self-approval (the sealing key), refuses an unknown `approval_id`, and signs
    only with a key from the approver keys dir.
  - `epi verify` gains a `human_approval` report field and a single
    `Human approval:` line that summarises the run's sealed requests
    (`VERIFIED` / `INCOMPLETE` / `DENIED`), and `--require-human-approval` FAILs
    unless every sealed approval request has a human-signed approval (or a
    case-level approval). `--policy strict` deliberately does **not** imply it.
  - Only the `approver` role counts: a key pinned with another role alone is
    never `human_signed`. An approval whose `approval_id` is not a sealed
    request is listed separately and never makes the status `verified`.
  - `review_version` moves to `1.2.0`. The record shape is unchanged, so an
    already-deployed 4.6.x verifier computes the same content hash and raises no
    tamper alarm — it just shows a signed review, never "human approved".
  - `agent.approval.response` / `approved_by` are labelled "reported by the
    agent (not signed by a person)" wherever the CLI prints them;
    `approval_id` is now an explicit field of `approval_request()`.
- **Signing keys in an HSM or cloud KMS (`epi keys link`).** A key name can now
  point at an Ed25519 key held in a PKCS#11 HSM, AWS KMS
  (`ECC_NIST_EDWARDS25519`) or Google Cloud KMS (`EC_SIGN_ED25519`). The
  private key never leaves the vault. Signatures are standard Ed25519, so the
  `.epi` format and every verifier are unchanged. Every signing path (record,
  gateway, review, witness report, SCITT) signs through the vault. Each
  signature is checked against the vault's public key, the vault key is pinned
  at link time (a swapped key is refused), and `EPI_REQUIRE_EXTERNAL_KEY=1`
  refuses key files on disk. Optional extras: `[pkcs11]`, `[aws-kms]`,
  `[gcp-kms]`. See `docs/KEY-CUSTODY.md`.

### Changed

- **Docs split into public and internal — and the leak that motivated it.**
  `docs/` is published as a website, so `docs/internal/` was world-readable:
  `https://spec.epilabs.org/internal/BANK-READINESS-EXECUTION-PLAN.md` served
  the bank-readiness plan to anyone. Internal material now lives in the
  repo-root `internal/` tree: the bank-readiness assessment and execution plan,
  the swallow audit, the coding-agent prompts, and the org trust bundle design
  note (moved out of `docs/design/`). No public doc links into `internal/` any
  more — the enterprise briefing, the docs map, `ARCHITECTURE.md`, `SUPPORT.md`,
  `docs/adr/0003-witness-first.md`, `CLOUD`, `DATA-RETENTION`, `WITNESS`,
  `ROADMAP` and `docs/api/README.md` now state that the detail is internal
  without pointing at it. `tests/test_docs_placement.py` enforces both halves.
  This makes the material **unlisted, not secret**: `internal/` is still inside
  a public repository, so anything that must stay genuinely private does not
  belong in this repo at all.

- **Gateway approval clicks are now labelled by who made them (behaviour
  change).** A click by a **logged-in gateway user** is recorded as
  `approval_source: "gateway_link_authenticated"` and still satisfies a policy's
  "approval required" rule in `epi analyze`, labelled "gateway-attested
  (logged-in user), not a signed approval". An **anonymous** link click is
  `"gateway_link_unsigned"` and is treated as self-reported (`P6 Agent Approval
  Gap — Self-Reported`), so it no longer satisfies that rule. Neither is a
  signed approval: `verify_human_approvals()` never reports them
  `human_signed`, and `--require-human-approval` still fails on both. Events
  recorded by older gateways keep their stored `"gateway_human"` label, keep
  satisfying the rule (no flipped results for old cases), and gain an
  informational note that anyone with the URL could trigger them. For a signed
  approval use `epi review <file.epi> approve` (step 3a).
  `approval_source` is a **claim, not a proof**: it is a plain string, so the
  gateway's capture endpoints (`/capture`, `/capture/batch`, `/capture/llm`, the
  proxy paths) demote a client-supplied gateway label to
  `raw_api_unverified` and keep it as `claimed_approval_source`; only the
  gateway's own approval route writes the real labels. In an SDK recording the
  agent writes its own steps, so the analysis approval checks remain
  **heuristics** — the only cryptographic proof is
  `epi verify --require-human-approval` with a signed approval.

- **Data-only is now the default seal; the embedded HTML viewer is opt-in
  (behaviour change).** `record()`, `epi demo`, `epi run` and `epi record` now
  write a small `legacy-zip` `.epi` with **no** `viewer.html` member and no
  outer polyglot HTML — a 5-step demo drops from ~507 KB to ~17 KB, small enough
  to email. The artifact verifies identically with `epi verify` and still opens
  in the local viewer via `epi view` (which regenerates the viewer locally).
  Pass `--with-viewer` (or `record(..., with_viewer=True)`) to embed the
  self-opening **envelope-v2** polyglot shell instead. `epi migrate` preserves
  whichever form an artifact already has; `epi refresh-viewer` now **refuses** a
  data-only file unless `--with-viewer` is given, rather than silently
  re-adding a viewer. `epi verify` output is unchanged, including the key-bound
  seal-timestamp line.

### Fixed

- **One story for low-severity observations (issue #157).** A `low`/`info`
  heuristic finding (e.g. P11b orphaned `tool.call`) made `epi analyze` print
  `FAULT DETECTED` while `analysis.json` said `fault_detected: false` and the
  seal summary said "no heuristic issues flagged". Faults are now medium+ only;
  `epi analyze` prints "No anomalies detected" plus an "Observations" line, and
  the summary reports "N low-severity observation(s) — not a fault".
- **`VERIFY.txt` states the sealing version, not a hardcoded one.** It now lists
  `EPI Version:` (the artifact's `producer_version`) and `Spec Version:`, and the
  correct command (`epi verify <file>`, with a `python -m epi_cli verify`
  fallback). The refresh-path template was updated to match.
- **`manifest.policy` is populated when a policy was actually applied.** It was
  always `null` even with `policy_load_status: "loaded"`. It now carries the
  formal evaluation (`policy_id`, `version`, `status`, rule IDs,
  `violation_count`) when loaded and stays `null` when the policy is `absent` or
  `failed`.
- **Seal timestamps now bind the signing key.** `record()` packed the file
  unsigned, stamped that first pack (so `imprinted_public_key` was `null`), then
  signed a repack with `EPI_NOTARIZE=0`. The timestamp is now taken on the
  signed repack, once the key exists, so `imprinted_public_key` is the sealing
  key and `epi verify` reports `sealed by key <fingerprint> no later than
  <gen_time>` with `timestamps.key_binding: "key-bound"`. Verify also rejects a
  file whose signing key was swapped after sealing (`imprint_mismatch`) instead
  of recomputing the imprint with the recorded key and passing. Seals made
  before this change keep verifying exactly as before as `"contents-only"` —
  no silent upgrade, no new FAIL. See `docs/VERIFICATION_CONTRACT.md` and
  `docs/KNOWN_LIMITATIONS.md`.
- **The embedded viewer no longer shows a file-integrity PASS it did not
  compute.** `_create_embedded_viewer` baked `integrity: {ok: true}` at pack
  time, so a `.epi` whose sealed evidence was rewritten after sealing still
  displayed a green "N checked / 0 mismatches" in the viewer's diagnostic matrix
  when opened by double-click — the display layer lying about the very thing EPI
  exists to catch. The pack-time viewer now bakes no verdict (`ok: null`), and
  the matrix shows a pass only when the page actually hashed the members against
  the signed manifest (an authoritative `epi view` context, or a live check
  against the archive); otherwise it reads "NOT VERIFIED HERE — drop this file on
  epilabs.org/verify". The fail-closed path for a known failure is unchanged.

### Security

- **Hardened gateway approval links.** The approval link is now a single-use,
  expiring capability instead of an unauthenticated GET/POST that recorded on
  its own. `GET /api/approve/<workflow>/<approval>` renders a confirmation page
  and records **nothing** (mail scanners pre-open links); only the POST records,
  once, with a token (≥256 bits, stored as SHA-256 only in the gateway's SQLite
  store) that is bound to that workflow + approval and expires after
  `EPI_APPROVAL_LINK_TTL_HOURS` (default 72). The body token doubles as the CSRF
  token. `reviewer` is never taken from the query string: the authenticated
  principal when gateway auth is on, otherwise `approval-link (identity not
  verified)`. A missing, wrong, expired or reused token returns the **same**
  403; attempts are rate-limited per client IP (60/min). Every value
  interpolated into the gateway's HTML and the approval email is escaped, and
  links issued before this change stop working (no fallback). See
  [docs/HUMAN-APPROVAL.md](docs/HUMAN-APPROVAL.md).
- **Approvals could be forged with the agent's own key, or claimed from an
  unauthenticated link.** Before this release a review signature trusted the
  public key embedded in the signature itself, so the agent (or anyone holding
  the file) could present a "signed review" as a human approval; and a plain GET
  on the gateway approval URL recorded a decision, so a mail scanner could
  approve on its own. An approval is now `human_signed` only when it is signed
  with a key pinned in the verifier's **approver** registry and differing from
  the sealing key, and `epi verify --require-human-approval` is the only
  cryptographic way to assert a person approved. See
  [docs/HUMAN-APPROVAL.md](docs/HUMAN-APPROVAL.md).

## [4.6.3] - 2026-10-23

Security and honesty release. **4.6.2 on PyPI did not contain these
verifier/identity fixes** even though parts of the docs described them; this
section is the authoritative list of what changed after 4.6.2. **4.6.3 was
uploaded on 2026-10-23 with the project API token because Trusted Publishing
was still unconfigured. The 4.6.3 wheel has no PEP 740 attestations (its PyPI
provenance endpoint returns HTTP 404). Configure Trusted Publishing before
4.6.4.** See `docs/RELEASING.md`.

### Security

- **Display-layer forgery is caught by `epi verify` (red-team F-01).** The
  outer polyglot viewer is byte-identical to the sealed `viewer.html` member,
  whose SHA-256 is in the signed `file_manifest`. 4.6.2 only checked the
  unsigned, self-referential `reserved_tail[0:32]` copy, so an attacker who
  edited the viewer and recomputed that copy still got `Integrity: Verified`.
  `epi verify` now checks the outer region against the signed value (for legacy
  envelope-v2 files whose signed `file_manifest` lists `viewer.html`) and
  reports `FAIL — Integrity compromised`.
- **The viewer no longer paints a verdict it cannot support (F-02).** A baked
  envelope failure can never be upgraded to green; missing data defaults to
  unverified.
- **Identity wording stops implying a pin that does not exist (F-19).** A DID
  key verified only against its own DID is reported as
  `SIGNER SELF-ASSERTED (DID)`, with `pin_source` stating why a key counts as
  known. Only an out-of-band pin earns `IDENTITY PINNED`.
- **Remote trust registry remains informational**, and pinned local signing
  keys no longer make unrelated senders fail.
- **Hardening:** decompression-bomb guards and Cloud trust-link validation
  (red-team batch #159 / PR #162).

### Fixed

- **Default redaction no longer destroys evidence values (P0-3/B2).** Bare
  9–10 digit numbers are no longer matched as SSN/phone. Those patterns now
  require separators or a `+`/parentheses, and a bare number is redacted only
  when the field name itself is PII (`ssn`, `phone`, `mobile`, …). New
  `redaction.allowlist_fields` exempts explicit non-PII fields.
- **`epi demo` no longer silently pins the local key (B3).** The vendor's own
  files show the documented `LOCAL` state instead of `IDENTITY PINNED`;
  pinning is an explicit `epi keys trust`.
- **`epi cloud storage set --help` no longer crashes** on Rich markup (B4).
- **A damaged/altered file opened by double-click shows an explanation**
  instead of a blank page (B5), and the neutral banner says how to verify
  (B6).
- **`epi view --extract` marks a failed-seal output folder `_ALTERED` (B7).**
- **`epi keys trust` only suggests `--witness-log` when a witness log exists
  (B8).**
- **`epi export trace` explains the unsigned alternative** when
  `--transcript-uri` is missing (B9).

### Docs

- Corrected product-version claims, canonicalization/test vectors, policy and
  trust tables, viewer section names, `EPI_KEY_PASSWORD`, plan limits, SCITT
  wording, telemetry wording, and stale roadmap/website/release notes.
- `FILE-SAFETY.md` lists the real inert JSZip URLs and a working
  `epi export trace` example.
- `RELEASING.md` records the 4.6.2 attestation gap and the four Trusted
  Publisher fields.

## [4.6.2] - 2026-10-22

First PyPI upload of 4.6.2 (GitHub had a tag; Trusted Publishing was not
configured, so `pip install` stayed on 4.6.1).

Release/tag alignment: the `v4.6.2` tag was re-pointed on 22 Oct to
`623c22cf`, which contains the #143 viewer fail-closed fix and the #145
pack-time fix — the same tree the PyPI wheel uploaded that day was built
from (verified: the wheel's `epi_core/container.py` carries both fixes). If
you fetched the tag on 20–21 Oct, re-fetch; the earlier position predated
#145.

### Security

- **Viewer fail-closed on envelope tamper (#141, #143).** Outer display-layer
  edits left inner ZIP hashes intact and the live browser check overwrote the
  baked envelope failure with INTEGRITY VERIFIED. A baked envelope verdict
  (`__envelope_header__` / `__polyglot_viewer__`) can never be upgraded to
  green; missing data defaults to unverified; the loading placeholder is no
  longer green. **This fixed the in-viewer badge only.** `epi verify` in
  4.6.2 still accepted a display-layer forgery whose unsigned
  `reserved_tail[0:32]` copy had been recomputed; the signed
  `file_manifest` check ships in 4.6.3.
- **Remote trust registry remains informational** (shipped in 4.6.1; still
  true here).

### Added

- **EPI Cloud login from the terminal.** `epi cloud login` (no flags) shows a
  short code; type it at cloud.epilabs.org/auth/device and the CLI picks up
  a push-only key by itself (RFC 8628 device flow). Flag version
  (`--url/--org/--api-key`) kept for automation. `epi auth login` is an
  alias of the same flow.
- **One account system.** Website Sign In and the CLI use EPI Cloud only;
  the old Render login is retired (see docs/CLOUD.md).
- **Cloud setup dashboard.** Guided start (company → computer → first run →
  customer → trust link) then tabs for Runs, Customers, Trust links and
  Computers & keys. Trust links are scoped to one customer by default.
- **Evidence pack (M6).** One "Download evidence pack" button on trust pages
  zips the whole link in the reviewer's browser (never on the server): every
  artifact's hash-checked bytes, `trust.json`, `witness.json`, `README.txt`
  with the exact offline verify commands, and `MANIFEST.json` with SHA-256
  per file. Witness lines arrive link-scoped behind the share token, each
  with a per-line Ed25519 receipt checkable offline (`epi verify
  --witness-log witness.json --witness-pubkey ...` — the key in the file is
  never trust; reviewers pin it from the well-known endpoint and the
  checkpoints repo); revoked keys ride with
  reasons. Full-log consistency stays covered by the signed daily checkpoint;
  per-line Merkle inclusion proofs are planned, not present.
- **Key registry (M5).** Vendors register **public** keys (`epi cloud keys
  push` reads only `*.pub` and refuses anything else); anyone can read the
  history at `/o/{slug}/keys.json`, shown on trust pages with revocations
  and reasons. Revoked keys are kept as tombstones (hard delete refuses them;
  a mistaken revoke is recovered with `epi cloud keys unrevoke`).
  Registration is informational only and never a pin: `epi keys trust
  --from-cloud {slug}` still requires the exact fingerprint confirmed with
  the sender, and refuses revoked keys.
- **Customer-owned storage (M4).** Every sealed `.epi` can also go straight
  to the vendor's own S3-compatible bucket (`EPI_STORAGE_URL=s3://bucket/prefix`,
  endpoint override for MinIO/R2/GCS, credentials from AWS env/profile).
  Outbox-first with bounded background delivery: sealing never fails or slows
  down, offline seals queue and `epi cloud storage flush` retries. EPI Cloud
  never sees these bytes or credentials - it only shows the recorder's
  health heartbeat as vendor-reported. New: `epi cloud storage
  show|set|test|flush`, `docs/STORAGE.md` (write-only bucket policy,
  Object Lock guidance).
- **Witness verdicts say what happened (#131).** A witness receipt signed
  by a key that is not the EPI witness reads NOT CONFIRMED ("STAMP NOT
  FROM THE EPI WITNESS"), never MISMATCH — MISMATCH means the file bytes
  differ.
- **Witness stamps get through (#132).** The recorder stamps with a
  distinctive client User-Agent (proxies were blocking the default one),
  with honest hints: 401 means re-run login, 403 means a network block.
- **Demo tells the truth (#133).** `epi demo` prints "Witnessed by EPI
  Cloud" (or why not, with the fix) and one Next step; the Runs list shows
  a short id and seal time under each title, goal-less runs show
  "Run 29e5812b", and every non-witnessed badge explains itself. Re-pushing
  refreshes a stale witness status and fills in a missing customer tag —
  never replacing one.
- **Walkthrough fixes (#134).** Sign out works (fetch POST, no more
  `Origin not allowed`); the guide says 3 steps; plan limits say
  "customers"; `epi cloud login` nudges after 30 silent seconds; trust
  pages explain counts before the first checkpoint.
- **Cloud customer overhaul (#135).** Team endpoints (members, invites,
  remove member, never the last owner) with an invite page; dashboard plan
  bar with usage; customer names match case-insensitively; closed
  customers free their plan slot; device login resolves the customer first
  (no dead keys); expired share links don't count toward limits; trust
  page catches viewer-tampered files; three security fixes (invites bound
  to the invited email, runs can't be moved between customers, reviewer
  drop-zone checks the embedded viewer).
- **Founder plan admin.** A founder-only page (`/admin`) lists every
  workspace with owner, usage and a plan picker — no more D1 console for
  plan changes. Every change is audited. Unlimited plans show a short
  "Plan: <Name> — unlimited" with no Upgrade link.
- **Paid plan limits match the pricing note (#139).** Startup: 3 customer
  relationships and 1,000 evidence files (1-year retention). Growth: 15
  relationships and 10,000 files (7-year retention). Limits speak in
  customers, never internal metric names.

### Fixed

- **Pack-time viewer carries VERIFY.txt; prohibition guards see original
  case (#145).**
- **CI signing uses the org key, not a throwaway.** `epi annex pack` (and
  `sign` / `multi-sign`) now import `EPI_SIGNING_KEY` — a 64-hex Ed25519
  seed — as the named key when it does not exist locally, instead of
  minting a disposable key. A green compliance-gate run now proves the
  signature came from the org's key. New `KeyManager.import_hex_seed()`.
- **Independent JS verifier can read real artifacts.** `docs/epi-verifier/`
  located the ZIP via a magic value that envelope-v2 files never have, and
  its bundled Ed25519 core could not verify a signature. It now finds the
  payload via the `EPI_ZIP_PAYLOAD_START` marker (legacy ZIP still works),
  uses the same proven crypto core as the shipped viewer, and verifies
  signatures for real 4.6.2 and legacy-zip seals.
- **`epi integrate guardrails` is listed.** The target existed but was
  missing from the help text and the command summary.
- **Docs matched to code.** `docs/`: Annex IV commands, EU AI Act evidence
  claims, EPI-SPEC required/optional members, trust-level table, canonical
  hash references, witness render strings, telemetry opt-in wording, Cloud
  plan entitlements, and the gateway/Cloudflare deployment notes now match
  the implementation. New: `docs/FILE-SAFETY.md`, `docs/adr/`, `docs/api/`,
  `docs/DPA.md`, `docs/SUBPROCESSORS.md`, `docs/DATA-RETENTION.md`,
  `docs/MIGRATION.md`, `docs/ROADMAP.md`, `docs/GOVERNANCE.md`,
  `SUPPORT.md`, `CODE_OF_CONDUCT.md`, `CODEOWNERS`, Dependabot, CodeQL,
  Scorecard, SBOM, and Sigstore-signed releases with `SHA256SUMS`.
- **Smaller Cloud fixes.** D1 migrations run before every cloud deploy (prod
  sign-in repair); device-code guess throttling; push-only `status`
  explains instead of dumping 403; witness exports enforce trust-link
  inbox scope.

## [4.6.1] - 2026-10-13

### Security

- **Remote trust registry is informational only.** A key listed only in
  `https://epilabs.org/.well-known/epi-trust-registry.json` no longer counts
  as trusted: the file is unsigned, so anyone controlling it could otherwise
  make every verifier accept their key. Such keys report
  `LISTED … (informational; not a pin)`, stay `UNKNOWN` (WARN under standard,
  FAIL under strict), and `epi verify` prints
  `Registry: listed as "<name>" by epilabs.org (not a pin)`. Remote
  revocations are still honoured. `--policy strict` never fetches the list:
  strict is local-only and needs no network. That also means strict never
  resolves `did:web`: an unpinned `did:web` key FAILs under strict until you
  pin it (`epi keys trust --from-did did:web:<domain>`, then phone-confirm
  the fingerprint). Remote revocation entries apply only to keys you have
  NOT pinned, and only under `standard` (strict never fetches): your own
  pins and revocations (`epi keys revoke` / `unrevoke`) are decided only
  by you — EPI Labs cannot overrule them through the unsigned list.

- **Share links really expire.** `epi share` uploads default to 7 days
  (max 30) and are deleted afterwards: expired shares return 410 Gone
  ("This link has expired") even before the hourly purger removes their
  files. Anonymous uploads are capped at 10 per hour per IP (429 beyond
  that). This enforces the retention the privacy page promises.

## [4.6.0] - 2026-10-12

**Highlights:**
- Offline RFC 3161 timestamp validation for seal and checkpoints.
- Customer witness on every seal (hash-only, outbox-first).
- Hash-chained gateway exports with capture-time checkpoints.
- did:web identity onboarding and key pinning.
- Checkpoints moved off the agent's hot path (background submit).

### Fixed

- **Bank-side safety from three rounds of user walkthroughs.**
  - A witness log entry for the same workflow but a different copy is
    `✘ FAIL — NOT THE VERSION REPORTED TO YOU` (`Witness: DIFFERENT VERSION`), never
    "FILE ALTERED"; the file's own integrity is reported as it is. Gateway witness reports
    carry `case_id`.
  - `epi keys trust <file>.epi` requires `--fingerprint` matching the file's key (a file can
    carry anyone's key). Verify output never suggests pinning from the file being checked;
    a DID line says whether it was resolved or only claimed.
  - Revocation applies to the key (every pin with it shows revoked); `epi keys unrevoke`
    undoes it; revoked-key reasons no longer advise re-pinning.
  - Under the default policy, incomplete evidence (`Forensic: FAIL`) is WARN, not PASS.
  - `epi audit` checks the real hash chain; an altered file FAILs every domain, is rated
    `altered` and exits 1. `epi view` (also `--extract`) exits 1 on an altered file.
  - Every printed hint uses the one recommended command:
    `epi verify FILE --policy strict --witness-log received.jsonl`.
- **Witness tooling.** `epi witness serve` (the customer receiver, now installed with the
  package), `epi witness drop` for undeliverable reports, clearer flush hints (no secret vs.
  wrong secret). `epi gateway export` reuses the DID and witness URL of `epi gateway serve`
  on the same storage dir. The gateway no longer creates a stray `./evidence_vault/`.
- **Pinning and repacking hardening.** A case file can never replace a pinned sender's key
  (`--overwrite` from an `.epi` is refused; rotate from the sender's key file or DID). `epi
  refresh-viewer` refuses altered files and files sealed by someone else's key, and a
  refreshed file stays `WITNESSED`. A file re-packed by a zip tool gets one clear error in
  verify, audit, view and export-html, and `--report` is still written. Restarting `epi
  gateway serve` without flags keeps the saved DID and witness URL.
- **Fingerprints on the vendor side.** `epi keys generate`, `did` and `list` print them.
- **No-timestamp seals are announced, and no longer hang.** All configured time-stamp
  services are asked in parallel with a 10 s default (`EPI_TSA_TIMEOUT`), so a network that
  silently drops traffic costs one wait instead of 30 s per service. When no timestamp is
  obtained, sealing prints one line naming the services and the fix (`EPI_TSA_URLS`, or
  `EPI_NOTARIZE=0` to skip).
- **A seal missing from your witness log is never a clean PASS.** `epi verify --witness-log`
  downgrades PASS to WARN with "never reported to your witness log" — what a re-run or
  re-sealed case looks like. A witness log path that cannot be read now FAILs instead of
  being silently skipped. A tampered file no longer shows a green WITNESSED line.
- **One key fingerprint everywhere.** `epi verify`, `epi keys export`, `epi keys trust`,
  `epi keys list`, the witness log and `VERIFY.txt` all show the same fingerprint, grouped
  for reading aloud (`4148 fb59 a148 a6dc`). `epi keys list` also lists pinned keys.
  `epi keys trust` accepts a vendor's `did.json` or the base64 key `epi keys export` prints.
- **Witness delivery is visible at seal time.** One line: delivered, or queued with the
  reason and `epi witness flush`. `epi witness flush` exits 1 while anything is undelivered
  and hints at `EPI_WITNESS_SECRET` on 401/403.
- **`record()` file paths.** A bare name (`"demo.epi"`) still goes to `./epi-recordings/`;
  a path with a folder (`"./demo.epi"`, `"out/demo.epi"`) is written exactly there. An
  existing non-empty file is never replaced silently: the new seal goes to `demo-2.epi`
  (`EPI_OVERWRITE=1` restores replace-in-place). "Next:" hints print the real path.
- **Local SCITT receipts are labelled as such.** `epi-register` without `--service` says the
  receipt is self-issued, and `epi verify` shows `Transparency: LOCAL (self-issued receipt,
  not an independent ledger)` instead of `VERIFIED (SCITT)`.
- **`epi gateway serve` ignored its flags, including `--access-token` (security).** The CLI
  imported `epi_gateway.main`, whose module-level app is built from the environment at import
  time, before exporting its flags, then ran that stale app. `--storage-dir`,
  `--retention-mode`, `--proxy-failure-mode`, `--webhook-url`, `--access-token` and
  `--users-file` were silently ignored: a `0.0.0.0` bind with `--access-token` ran with auth
  disabled. uvicorn now runs the `create_app` factory after the env is set. Regression since
  v4.5.0 (never published to PyPI).
- **A file sealed by a key you did not pin now FAILs.** When the verifier has pinned other
  parties' keys and the file was sealed by none of them, `epi verify` (standard policy)
  returns `FAIL — NOT A KEY YOU TRUST` with exit 1 instead of `WARN` / exit 0, and no longer
  suggests pinning the key from the file itself. The user's own auto-pinned key (`epi demo`)
  does not count as a pin for this rule.
- **`epi view`, `epi audit` and `epi export-html` flag tampered files.** `view` printed a fixed
  "Seal OK"; `audit` ticked "Cryptographic" from the signature alone; `export-html` packaged an
  altered file as a shareable page. They now report `ALTERED`, show `✗ FILE ALTERED`, and refuse
  to export, respectively.
- **Verify headline names what failed.** `SEAL FAIL — FILE ALTERED`, `SEAL FAIL — SIGNATURE
  INVALID`, `FAIL — NOT A KEY YOU TRUST`, or `FAIL — SEAL INTACT, REQUIREMENT NOT MET` (e.g.
  `--require-timestamp` with no timestamp), instead of `SEAL FAIL` for all of them. The
  `--require-timestamp` reason is a sentence, not appended to "Integrity verified…". A FAIL is
  no longer re-labelled "VERIFIED (enforcement downgraded…)".
- **`epi-register demo.epi` finds `epi-recordings/demo.epi`**, like `epi verify` and `epi view`
  (README 60-second path).
- **Gateway docs match the code.** Defaults are `full_content` / `fail-closed`; install with
  `pip install "epi-recorder[gateway]"`; runbook port 8787 and relative links.
- **`--tsa-root` now applies to checkpoint timestamps too.** `epi verify --tsa-root PATH`
  previously added trusted TSA roots for the seal timestamp only; SDK checkpoints
  (`epi_core/checkpoints.py` `verify_checkpoints()`) and gateway capture checkpoints
  (`epi_core/case_store.py` `verify_capture_checkpoints()`) still used pinned roots plus
  `EPI_TSA_TRUST_ROOTS`. Both verifiers take an optional `trust_roots` passthrough and the
  CLI builds the list once (`_tsa_trust_roots`: pinned + `--tsa-root` + env) for all three
  paths. Custom-TSA checkpoints report UNVERIFIED without the flag and valid with it.
- **Checkpoint `UNVERIFIED` prints as `[WARN]`, not `[FAIL]`.** The SDK checkpoint block in
  `epi_cli/verify.py` now matches the gateway block (`CAPTURE TIMESTAMP UNVERIFIED`).
- **Seal timestamp scope is stated plainly.** A `valid` seal timestamp proves "these contents
  existed no later than T"; in the default `record()` flow (`imprinted_public_key` null) it
  does not bind the signing key. See `docs/VERIFICATION_CONTRACT.md` and
  `docs/KNOWN_LIMITATIONS.md`. Customer docs (`docs/IDENTITY-ONBOARDING.md`) now recommend
  `epi verify run.epi --require-timestamp --witness-log received.jsonl`.

### Changed

- **Core vs experimental split (no code deleted).** README project layout and new `docs/SCOPE.md`
  name the core (`epi_recorder`, `epi_core`, `epi_cli`, `epi_gateway`, viewers, `pytest_epi`,
  `website/`) vs frozen experimental surfaces (MCP, portal/billing, TRACE + AGT, guardrails,
  `website-v2/`, remote SCITT) under the rule "no new surface until three external companies use
  the core". Tests carry an `experimental` marker: the release gate runs
  `-m "not browser and not experimental"` with a separate non-blocking experimental CI job.
  The keep-warm schedule is disabled (nothing core depends on Render); the demo fails seal-time
  timestamps fast (`EPI_TSA_TIMEOUT=5`).

### Added

- **did:web identity onboarding.** `epi keys did --domain vendor.com [--path agents/claims] [--key default]`
  writes `did.json` and prints the DID, the exact hosting URL and free hosting options;
  `record(..., did=...)` / `EPI_DID` (gateway: `did_web` setting) binds it into the seal; `epi keys trust
  --from-did did:web:vendor.com --name vendor` resolves once, pins locally and prints the fingerprint for
  out-of-band confirmation. Verify shows red `NOT A KEY YOU TRUST (you have pinned: ...)` when pins exist
  but the file's key is untrusted (soft `NOT_PINNED` when no pins exist at all), supports `--offline`
  (DID declared but unresolved; local pins decide), and accepts any listed key for rotation. Guide:
  `docs/IDENTITY-ONBOARDING.md`.
- **Gateway exports are hash-chained with capture-time checkpoints (issue #26).** Projected steps carry
  `prev_hash` (`CHAIN_START` genesis, same JCS construction as the SDK recorder) after the ordering freeze,
  so trimming after export breaks the chain; exports also attest `total_steps`. The gateway worker maintains
  a running chain over raw capture events in acceptance order, checkpoints the head to the TSA throttled per
  case, and the export bundles `artifacts/capture/events.jsonl` plus `artifacts/capture/checkpoints/`.
  `epi verify` recomputes the raw-event chain and reports `CAPTURE TRIMMED` on deletion and `CAPTURE
  CHECKPOINT MISMATCH` on reorder (10k-event export measured at ~4 s). Old unchained exports verify on the
  pre-chain path as before — no migration.
- **Customer witness on every seal.** With `EPI_WITNESS_URL` (or `record(..., witness_url=)`, comma-separated
  for several customer systems) every sealed `.epi` is reported at seal time as a hash-only payload
  (`schema: epi-witness/v1` — workflow id, manifest/file hashes, key fingerprint, step count; no content,
  goal only with `witness_include_goal=True`). HMAC header when `EPI_WITNESS_SECRET` is set, plus an Ed25519
  seal signature verifiable with the vendor's pinned key. Outbox-first (`~/.epi/witness_outbox.jsonl`) with
  daemon-thread delivery and a bounded wait, so witnessing never fails or slows the seal; `epi witness flush`
  retries the undelivered and `epi witness status` lists entries. `epi verify --witness-log received.jsonl`
  reports WITNESSED / NOT IN WITNESS LOG / MISMATCH (a mismatch FAILs). Gateway case export witnesses through
  the same settings. Reference receiver in `examples/witness_receiver/`; customer guide in `docs/WITNESS.md`.
  `send_signed_webhook` moved to `epi_core/webhook.py` (re-exported from the gateway module, behaviour unchanged).
- **RFC 3161 timestamps are now validated offline by `epi verify` (4.6.0).** Seal time stamps a recomputable
  imprint (`epi-tsa-imprint/v1`: workflow id, creation time, sealing key, payload file hashes) with two
  independent TSAs (FreeTSA + DigiCert; `EPI_TSA_URLS` overrides, `EPI_TSA_URL` still a single-URL override).
  Verification checks the imprint, CMS signature, critical timeStamping EKU and chain to pinned roots shipped
  with the package (`epi_core/assets/tsa_roots/`), for seal tokens and heartbeat checkpoints alike. New flags
  `epi verify --tsa-root` (repeatable) and `--require-timestamp`; `report.timestamps` and
  `facts.timestamp_verified` in JSON output; AIUC-1 Accountability gains timestamp evidence without claiming any
  control. Pre-4.6 tokens report legacy/presence-only and never change the decision; the browser viewer still
  does not validate and says so.

- **Per-tool sign-in declarations** (`_meta.securitySchemes`, `oauth2` with one scope) on all four tools, for hosts that read
  them, and a test that every tool sets all three directory hints explicitly. The seal tool's comment now says plainly that
  it sends a hash to a public time-stamp service.

- **Privacy, terms and support pages, and a ChatGPT app submission pack.** `/privacy`, `/terms` and
  `/support` describe what the hosted connector actually does (retention hours come from the code), with
  the contact set by `EPI_SUPPORT_EMAIL`. The server now deletes expired sealed files on a timer and forgets
  rate-limit addresses after an hour, so those promises hold on a quiet server. Publishing EPI in
  ChatGPT's app directory is the route to working on every plan.
- **`/seal` takes the export zip as downloaded.** Upload the ChatGPT or Claude data-export zip
  directly (sharded `conversations-000.json` files included), pick one conversation by part of its
  title or its number, and large histories are read one conversation at a time with safe size limits
  (30 MB zip, 80 MB unzipped). This is the route for ChatGPT plans without custom connectors.
- **ChatGPT connector support, tested end to end.** Tools now carry titles and confirmation hints
  (sealing is a write that touches nothing outside the server; verify, read back and compare are
  read-only), so ChatGPT asks for confirmation only where it should. A new test replays ChatGPT's
  whole connection sequence against a real server (OAuth discovery, registration with ChatGPT's
  redirect URI, PKCE with the resource parameter, tool calls, refresh). Docs have current setup steps.
- **Seal a conversation without a chat model: `/seal` page.** Upload a Claude or ChatGPT
  chat export (or paste the text) and get a sealed `.epi` with the exact words and the export's
  real times, plus the same view and download links. Sealing through a chat host makes the model
  re-type the whole conversation into a tool call, which hosts can pause and a model can shorten.
  The original export's SHA-256 is recorded as the first event. Public, size- and rate-limited.
- **View a sealed file in the browser with nothing installed.** Each seal now returns a
  `view_url` (alongside `download_url`) that opens the sealed record as a web page, sandboxed
  and protected by the same expiring link token, and a `how_to_view` note that points to
  epilabs.org/verify for saved files. A raw `.epi` only downloads in a browser, so a new
  user had no way to look at the result without installing `epi-recorder`.
- **Natural requests now reach the sealer.** The seal tool's description and the server
  instructions say that "seal / save / export this chat" means this tool, not a Markdown
  file, and the connector offers two one-click prompts ("Seal this conversation", "Seal
  your last answer") so nobody has to word a request.
- **Sign in with GitHub for the evidence connector** (`EPI_IDP_ISSUER=github`). The simplest
  free way to name the person who sealed a file: a GitHub OAuth app, no review, and the
  sealed file records the public username (email only if the person opts in). Same rules
  as the OpenID Connect path: shown only when integrity and signature pass, never proof
  of who typed the conversation.
- **Optional sign-in for the evidence connector.** When an operator configures an
  OpenID Connect provider (`EPI_IDP_ISSUER`, `EPI_IDP_CLIENT_ID`,
  `EPI_IDP_CLIENT_SECRET`; Google, Microsoft Entra, Okta, Auth0), the approve
  page offers "Sign in and approve". The verified account is written into the
  sealed file's signed `environment.json` (`sealer_identity`), gives that person
  one stable signer across reconnects, and is shown by the viewer and
  `epi verify` only when integrity and signature passed. The email is included
  only if the person leaves the box ticked. Anonymous one-click approval stays
  the default and is unchanged. The identity is the sealing server's statement:
  it does not prove who typed the conversation.
- Optional `EPI_APPROVE_PASSPHRASE` and per-caller / server-wide storage quotas
  for the evidence connector.

#### MCP evidence connector (`epi_mcp`)

- Seals carry an honest provenance record: `caller_provided` capture scope,
  per-event timestamp source (caller vs server-received), per-event
  `fidelity` (verbatim / summary / hash_only), a real `prev_hash` chain, and
  the sealer's own caveats as declared known gaps. The viewer shows those
  caveats directly above the timeline.
- Stable per-caller signing identity derived from `EPI_OAUTH_SECRET` /
  `EPI_SIGNING_SEED`, so a signer survives restarts and `epi keys trust`
  pinning lasts. OAuth clients and refresh tokens are signed tokens (no
  database needed).
- Expiring browser download links; sealed files the server wrote are deleted
  when the link expires. `epi_verify` / `epi_export_summary` / `epi_compare_runs`
  accept the returned `artifact_id`.
- Step origin is labelled correctly (`user.message` is `user`, not `reasoning`);
  tool calls without a name are flagged; declared omissions are counted.
- Model-facing tool text no longer uses phrasing that host safety systems can
  misread as a request to expose reasoning; oversized records fail fast with a
  way forward. Requires `mcp>=2.0`.
- Schema: `CapturePath` gains `caller_provided`.

### Changed

- **`epi verify --aiuc1` no longer prints PASS or FAIL next to AIUC-1.** Each domain now reads "evidence found",
  "some evidence found" or "no evidence found" (`FOUND`, `PARTIAL`, `NOT_FOUND` in JSON, including the verify
  portal's `aiuc1.overall` and its signed attestation), with a note that these are EPI's own checks and not an
  AIUC-1 result. The overall line is `FOUND` only when every domain is, `NOT_FOUND` only when none is, and
  `PARTIAL` otherwise. **Society** no longer requires the analyzer to have found faults (a clean run scored
  lower than a faulty one) or two kinds of redaction; it now checks that a complete analysis was sealed.
  Scripts that compared these values to `PASS`/`FAIL` need updating.
- **The wording Claude and ChatGPT read from the connector states facts instead of giving orders.** Phrases such as
  "Do not write a Markdown file", "Replace passwords" and "tell the user" could read as steering and make a host more
  cautious. They now say what is true (a Markdown file is not a signed record). A test fails if directive wording returns.
- Tool titles are also set inside each tool's annotations, as the Claude connector directory expects.
- **Repository cleanup: removed top-level debug files and moved developer scripts to `scripts/dev/`. No behaviour change.**
- **Connector text is leaner and phrased to avoid host safety pauses.** The tool description,
  server notes and one-click prompts shown to the model are about 40% shorter and no longer
  mention decision rationale, host-supplied or system text, or "every message / word for word".
  The summary-fidelity hint moved into the seal warnings. A test checks all model-visible
  text for risky phrasing.

### Fixed

- **Checkpoint timestamping no longer blocks the agent's step.** `RecordingContext.add_step` called the TSA
  synchronously (up to a 30 s HTTP timeout per heartbeat). Heartbeats now only enqueue
  `(index, event_count, chain_head)` to a per-recording daemon thread that calls `create_checkpoint`;
  `finalize()` drains the queue for at most `EPI_CHECKPOINT_DRAIN_SECONDS` (default 10) before sealing and
  records unfinished checkpoints as a runtime gap. Each checkpoint stays bound to the chain head at enqueue
  time, so imprints are unchanged.
- **Internal sales templates are no longer publicly deployed.** `website/outreach.md` (cold-email templates and
  target-company lists) was synced into `site/`, `verify_portal/static/` and `epi-official/`. All four copies are
  removed, and both sync paths (`scripts/sync_website.py` and `npm run build`) now refuse to copy any `website/`
  Markdown other than `README.md` into public outputs, with a test pinning it. The file's "August 2, 2026" EU AI Act
  date was also stale (Annex III high-risk obligations apply from 2 December 2027 under Regulation (EU) 2026/1744);
  no other non-archive public file carried that date.
- **A redaction note no longer counts as an unlabelled event.** A `redaction.omitted` event describes what was left out and
  has no text to mark verbatim or summary, so it no longer triggers "events do not say whether their content is verbatim".
- **The seal result carries a copy-ready `share_text`** (view link, download link, SHA-256, expiry). In one real chat the
  assistant rebuilt the view link itself, using the hash as the id and dropping the access token, so the link did not work.
- **The seal summary counted events by the names the caller sent.** A chat that sent `tool_call` reported `tool_calls: 0`
  and listed `user_request` while the sealed record said `user.message`. The counts now use the same canonical kinds.
- **`epi_verify`, `epi_export_summary` and `epi_compare_runs` now accept `artifact_id`.** Their descriptions told the chat
  assistant to pass the artifact id, but the parameter was named `epi_path`, so the call was rejected. Both names work.
- **Near-miss event kinds are read as the real ones.** Chat models often send `user_request`, `assistant_response` or
  `tool_call`. The sealer mapped none of them, so it warned "No user message" on a record full of user messages and the viewer
  labelled them wrongly. These now map to `user.message`, `assistant.message`, `tool.call` and so on, and the name the
  caller sent is kept in the step's provenance.
- **Viewer no longer shows `+0.000s` on every row of a chat seal.** Chat hosts give no per-message times, so the sealer
  stamps its own receive time. Those rows now say "received" instead of an offset that reads as a measured gap.
  Times a caller supplied still show offsets. The trusted RFC 3161 timestamp on the file is unchanged.
- **A slow public time-stamp service could make a hosted seal fail.** Every seal waits for a free RFC 3161
  service (freetsa.org) for up to 30 seconds. When it was slow or down, the seal call outlasted what the
  chat host would wait and the host reported a server error, even though nothing was wrong with the record.
  The hosted server now waits at most 6 seconds (`EPI_TSA_TIMEOUT`; the local CLI keeps 30), seals without the
  timestamp, and adds a warning that no trusted timestamp was obtained. The signature and hash chain are
  unaffected.
- Remote callers no longer get the whole sealed file back as base64 text when view and download links exist
  (a small chat was over half a megabyte, filling the chat model's context). Local and stdio use is unchanged.

- **Viewer showed a valid signature as INVALID** when signed metadata contained
  non-ASCII text (an em dash, an accent, a checkmark in the goal). The browser
  viewer decoded `manifest.json` as Latin-1; it now decodes UTF-8. Applies to
  every sealed file's embedded viewer, the hosted viewer mirrors and the 40
  embedded demo pages. Python verification was never affected. A repo-wide test
  blocks the old pattern.
- **`epi view` / `export-html` showed "scope undeclared (pre-v artifact)"** for
  every artifact: the capture manifest and checkpoints were missing from the
  data passed to the viewer.

### Security

- **Hosted connector: every approved caller signed with one shared key, and a caller could choose where
  the server writes.** The seal tool forced the caller to the server operator even over HTTP, so all people
  sealing through the connector shared one signing key and one storage quota (per-person signers and quotas
  only worked when the tool was called directly). Separately, `output_path` was honoured from the network,
  letting an approved caller make the server write a file at any path it could write to, and skip the quota.
  Now the caller the server identified is kept, `output_path` is ignored for anyone but the local operator, and
  verify, read-back and compare accept only the `artifact_id` returned by sealing over the network (file paths
  remain for local stdio use). **Signers change:** files sealed through the hosted connector before this fix
  carry the old shared key; new ones carry a per-person key, so re-pin trusted signers.

### Documentation

- **AIUC-1 evidence document rewritten to claim only what EPI does.** It no longer calls EPI "the definitive" container or says it "satisfies" AIUC-1 domains; it lists what each domain's evidence covers and does not, explains that `--aiuc1` PASS/PARTIAL/FAIL are EPI's own evidence checks rather than AIUC-1 results, and notes that the default SCITT receipt is local, not independent. No behaviour change.
- **Honest badges, architecture overview, consistent spec labels, fixed links.** README uses the real Release Gate CI badge; new `ARCHITECTURE.md` describes the packages and integrity model from the code; `docs/spec/` version labels read 4.5.0; `docs/README.md` archive links are marked archived and README presents them in one Archive row. No behaviour change.

### Ops

- `keep-warm` also pings the MCP connector so the first seal of a session does
  not hit a cold start.

## [4.5.0] - 2026-10-04

### Behavior changes (read before upgrading)

- **Gateway `serve` defaults are now fail-closed**: `--retention-mode`
  `redacted_hashes` → `full_content`, `--proxy-failure-mode` `fail-open` →
  `fail-closed` (`epi_cli/gateway.py`, matching library defaults).
- **CORS closed by default**: `allowed_origins` `["*"]` → `[]`. Set
  `EPI_GATEWAY_ALLOWED_ORIGINS` explicitly to allow browser origins.
- **Client `x-epi-failure-mode` header ignored**: the server setting always
  wins; a proxied agent can no longer downgrade enforcement per-request.
- **Non-loopback bind requires auth**: `epi gateway serve --host 0.0.0.0`
  without `--access-token`/`--users-file` refuses to start.
- **`/metrics` requires auth when gateway auth is configured**.
- **AGT exporter `epi_signature_valid` now means verified**: previously
  presence-only; adds `epi_signature_present`.

### Docs

- TSA wording is presence-only everywhere ("token present, not validated").
- `VERIFICATION_CONTRACT.md` lists every verdict; browser never exceeds CLI.
- `KNOWN_LIMITATIONS.md` current (PyPI line, gaps, strict sprint rule).

## [4.4.8] - 2026-09-26

### Security — container and browser verifier

- **Zip-slip guard in `refresh_viewer`** `container.py`: payload extraction now rejects `../` entries (same guard `unpack` already had). Regression test poisons a payload and asserts `ValueError`.
- **Browser JCS parity** `epi_viewer_static/crypto.js` (inlined into every sealed viewer): escape-decoding tokenizer fix, JCS number encoding (`900.0` hashes as `"900"`), offset-to-UTC datetime normalization, era-aware legacy handling, CBOR-v1 honest-unsupported path, `key_name` binding check. Proven by an 11-fixture Node↔Python byte-equality harness plus a live Python-seal → browser-verify round-trip (valid / relabeled-key / tampered / v1).
- **Portal parity** `website/js/epi-manifest-preimage.js`, `website/js/home-verify.js` (+ synced mirrors): same JCS number/datetime fixes, v1 honest error, genesis-anchored chain audit. Proven against Python hashes including the 4.3.0 golden and a synthetic legacy-with-float manifest.

### Fixed — one canonical dispatch, strict chain, honest decisions

- **Unified canonicalization dispatch** `serialize.py:canonical_format_for`: sign, signature-verify, and chain-verify previously answered differently for old/missing/malformed `spec_version` (three answers for input `"foo"`). One function now decides CBOR (1.x) vs legacy JSON (2.x–pre-4.4.1) vs JCS; legacy normalization deduplicated into shared helpers. Round-trip test signs and verifies across 13 version inputs.
- **Strict step chain** `verify.py`: genesis marker (`CHAIN_START`) allowed only at index 0 — mid-chain restart is reported as possible truncation; index sequence anchored at 0; pre-chain artifacts pass loudly with a warning instead of silently.
- **Unsigned no longer outranks signed** `trust.py`: unsigned-intact under STANDARD is now WARN (was PASS — stripping a signature upgraded your verdict while signed-unknown only gets WARN).
- **Coverage honesty** `verify.py --verbose`: names what file hashes do not cover (mutable review files, SCITT receipts, self-asserted manifest on unsigned artifacts).
- **Verify portal** `verify_portal/main.py`: passes the real `spec_version` to chain verification (was `None`, which only worked by coincidence) and anchors its sequence audit.

### Docs

- **EPI-SPEC alignment**: header table (restored `format` byte, documented `viewer_sha256` tail split), marker-based parsing rule, MIME clarification, the three canonicalizations + dispatch table, corrected signing preimage (`signature` excluded only), true `file_manifest` exemption list, `CHAIN_START` genesis, and the two-`payload_hash` naming trap.

## [4.4.7] - 2026-09-26

### Fixed — Viewer/CLI agreement on findings (screenshot-review follow-ups)

- **§6 advisory styling**: heuristic-only observations no longer render inside the green all-clear block; they get an amber "Pattern Noted (advisory — not a fault)" block `web_viewer/app.js, styles.css`
- **§3 banner counts all patterns**: the verdict note names the total detected count with the primary headline instead of the primary alone
- **1-based step numbers everywhere**: CLI completeness gaps (`verify.py`), viewer primary/secondary flag steps now use 1-based step numbers matching the analyzer `step_number` and the §4 log
- **Sealed `controls_failed` undercount**: auto-extracted policy evaluation no longer resets the baseline failure count (`container.py`) — new seals report the true total
- **Disclosure**: artifacts sealed before this fix may report `controls_failed` lower than the failed entries in `results` (baseline failures were dropped when auto-extracted rules were present). The `results` array itself was always complete — recount from `results`, not the header field. See `KNOWN_LIMITATIONS.md`

## [4.4.6] - 2026-09-10

### Fixed — Viewer shows the version that sealed the file (Task 1)

- **Seal-time `producer_version`** `schemas.py:ManifestModel` new optional field, stamped by `container.py:pack` from the sealing package version (never backfilled on load; omitted from the signature preimage when absent so pre-4.4.6 seals still verify)
- **Viewer header/footer** `container.py:_create_embedded_viewer` + `view.py:_create_decision_ops_viewer` now render `manifest.producer_version` (fallback `spec_version`) instead of the verifier's installed version — a 4.4.1 artifact opened with 4.4.6 installed reports 4.4.1
- **Two labelled fields**: header shows `Spec_Version (envelope)` (canonicalization selector, unchanged) alongside `Producer_Version (sealed by)`; §8 appendix carries both plus `"epi-recorder"`
- Browser preimages (`epi_viewer_static/crypto.js`, `epi-manifest-preimage.js`, `epi-verify-core.js` mirrors) omit null `producer_version`, matching `serialize.py:MANIFEST_OMIT_NONE_FROM_HASH`
- Regression test `tests/test_producer_version.py` (seal → manifest version == package version)

### Breaking — Stricter verification (correctness)

- **Trust ranking** `UNSIGNED` now `LOW` not `MEDIUM` above `signed-unknown`; `32B/64B` length enforced `trust.py:239,124`
- **Trailing bytes** after `EOCD` now `FAIL` `container.py:623` (was `PASS` injection)
- **Header transplant** `artifact_uuid/created_at_micros` cross-checked `container.py:1648`
- **payload_hash** recomputed after `viewer.html/VERIFY.txt` `container.py:1177` (was stale)
- **Gateway** `retention_mode full_content` + `proxy_failure_mode fail-closed` `gateway/main.py:95` (was `redacted_hashes/fail-open`), streaming `501`
- **Billing** unknown `price_id` now `ValueError` `billing.py:127` (was silent `hosted`)
- **Auth** `TOKEN_TTL 90->7` + strict CSRF `auth.py:36,522`

### Fixed — Evidence completeness (14 MUST)

- Streaming `pre_commit` canonical `sha256(messages+model)` + `tool_calls/reasoning` captured `wrappers/openai.py:72, anthropic.py:54, patcher.py:230`
- Guardrails `[:2000]` truncation removed `guardrails/session.py:609`
- SCITT fallback `transparency_ok=None` not `PASS` `verify_portal/main.py:813`
- Verification `verification_class` single-source `schemas.py:compute_verification_class` never `None`
- LangGraph `put/get/list` running-loop safe + nested chains captured `adapters/langchain.py:406`
- Deadletter `litellm/otel/langchain/bootstrap/api` warn + `.epi-deadletter.jsonl`
- Rate-limit `XFF last-entry + CF-Connecting-IP` `verify_portal/main.py:583`
- Packaging `cryptography<51 typer<0.28 rich<16` `pyproject.toml:58`, `setup.py` gateways, `docker 3.12`, demos re-sealed `payload_hash` fix

### Docs

- `KNOWN_LIMITATIONS.md` `Fixed in 4.4.6` audit trail, `spec 4.4.3->4.4.5`, `.well-known` mirrors synced

### Fixed — NICE batches (B1/C1/D1/D2/B2)

- **B1 viewer genTime** `TSTInfo.genTime` parsed at seal into `notarization.json:tsa_genTime` `notarize.py`; extractor hardened (UTCTime/fractions/TZ) `view.py:434`; viewer shows `host · time` `web_viewer/app.js:636`
- **B2 TRACE strict** signed export fail-closed on placeholder `transcript_uri`/`transparency` `trace_exporter.py:strict`; CLI `--sign` requires `--transcript-uri`; golden updated to `steps.jsonl` hash
- **C1 Merkle RFC6962** leaf `sha256(0x00||entry_hash)` `scitt.py:126` (was index-prefixed); verify accepts legacy receipts; portal + mock synced
- **D1 Redis persistence** opt-in `EPI_GATEWAY_REDIS_URL` shared sliding-window limiter `gateway/main.py` (fail-deny on outage); quota already SQLite-persistent
- **D2 auth local users** plaintext `password_hash` rejected `auth_local.py:37`; `password:` warns deprecation; `epi gateway hash-password` migration helper; world-readable users-file warning
- **Leak** OTel best-effort deadletter gated behind `EPI_DEADLETTER=1` `opentelemetry.py:425` (was unconditional raw-steps write); `*.epi.deadletter` gitignored
- **Legacy EPI1** header-size probe instead of fixed 16B `container.py` (was rejecting spec-conformant files); audit tool + SPEC §2.2 aligned
- **Windows fallback** VBS launcher probes payload start (bare/EPI1/envelope) + `ChrB` InStrB fix + stale temp sweep + cscript compile gate `platform/associate.py`
- **Tests** aligned stale expectations (nested chains captured, UNSIGNED LOW) + demo subprocess works without pip install `dev.py`
- **Redact** user-declared literal secrets via `record(redact_secrets=[...])`, `EPI_REDACT_SECRETS`, config `literal_secrets`
- **Audit** resurrected as plain command (group callback never parsed ARTIFACT) + honest low rating for signed artifacts
- **Policy** prohibition scans ignore redaction receipts instead of flagging them
- **Billing** empty/unknown Paddle price_id raises (non-2xx, retried) instead of minting Hosted
- **Site** undeliverable Team bullets removed; honest support/SCITT wording
- **CI** gate deps derived from pyproject (no stale pins); fresh-venv harness skips cleanly, Windows venv paths fixed

## [4.4.5] - 2026-09-07

### Fixed — TRACE integration unblocked

- **Pydantic ceiling relaxed: `pydantic>=2.0.0,<3.0.0`.** The `<=2.12.3` cap (a defensive cap from March 2026 with no associated breakage) conflicted with `agentrust-trace==0.10.0`, which requires `pydantic>=2.13.5`, making the two packages uninstallable together. Verified safe before relaxing: full suite on pydantic 2.13.5 gives `1533 passed, 108 skipped` with only 8 pre-existing harness failures (asyncio-loop / Playwright-browser-environment issues that reproduce identically on the pinned 2.12.3 baseline; no traceback touches pydantic), and the signature-critical suites (`test_legacy_preimage`, `test_cross_verifier_parity`, `test_verifier_single_source`) are fully green.
- **Emitter proven against 0.10.0.** `epi export trace` emits the optional `references` block (`rel: behavior-trace`, `digest` equal to the `.epi` sha256), `iter_errors` is empty, and `trace-tests verify --level 0` PASSES with TR-SIG green.

### Notes

- The `cryptography<44`, `typer<0.26`, and `rich<14` ceilings already exclude current PyPI latest releases (50.0.1, 0.27.2, 15.0.0 respectively) and are left untouched this release for separate handling.

---

## [4.4.4] - 2026-08-31

### Fixed — Fail-closed evidence

- **Policy loading now fail-closed with `EPI_ENFORCE=1` / `--policy strict`.** `load_policy()` raises `PolicyLoadError` on malformed `epi_policy.json` when strict, instead of silently downgrading to `heuristic_only`. Manifest now records `policy_load_status` (`loaded`/`failed`/`absent`) so a verifier can tell if a run claiming policy enforcement actually had one. Added `policy_load_status` to `MANIFEST_OMIT_NONE_FROM_HASH` and mirrored in browser verifiers (`website/js`, `epi_viewer_static`).
- **Key fallback no longer silently uses tmpdir.** `_resolve_default_keys_dir` now requires `EPI_ALLOW_TMP_KEYS=1` for `tmpdir/epi/keys`; otherwise raises `PermissionError` with clear message that tmpdir may be cleared on reboot and make artifacts permanently unverifiable.

### Tests

- Updated `FROZEN_MANIFEST_FIELDS` and canonical hash vectors for `policy_load_status`.
- `tests/test_verifier_single_source.py` now also checks `policy_load_status` in embedded viewer.

---

## [4.4.3] - 2026-08-29

First PyPI release after the withdrawn 4.4.2 GitHub-only build. **Do not yank 4.4.1.**

### Fixed — Sealed content completeness

- **Step payloads are sealed in full.** `RecordingContext.add_step` no longer truncates strings at 2000 characters. The viewer still shortens *display* summaries; `steps.jsonl` is the evidence.
- **`manifest.content_truncated`** — new seals set `false` at pack time. `epi verify` **FAIL**s if the flag is `true`. Artifacts without the field (everything shipped through 4.4.1) **WARN**.

### Fixed — Legacy signature preimage

- **`content_truncated` null no longer enters the signed bytes.** Shared omit list for JCS and legacy Ed25519. Frozen goldens under `tests/goldens/`; preflight fails if a spec 4.3.0 golden does not verify.

### TRACE

- `origin.producer` is `epi-recorder/` plus **package** `get_version()`, not the artifact `spec_version`.

### Tests

- Frozen goldens `tests/goldens/legacy-spec-4.3.0.epi` and `legacy-spec-4.4.0.epi` must keep `signature_valid` true. New `ManifestModel` optional fields that are absent from the 4.3.0 golden must be listed in `MANIFEST_OMIT_NONE_FROM_HASH`.
- `scripts/preflight.py` fails if a pre-4.4.1 artifact does not verify `signature_valid`.

### Changed — Homepage honesty

- Hero copy states the seal proves integrity after sealing, not that every call was captured. Builder loop leads with gateway proxy; `record()` is the quickstart.

---

## [4.4.2] - 2026-08-29 — withdrawn before PyPI

**Withdrawn.** The GitHub Release and `v4.4.2` tag were deleted. That build hashed Pydantic's synthetic `content_truncated: null` on the legacy Ed25519 path (`spec_version` before 4.4.1), so every artifact sealed before 4.4.1 failed `Invalid signature` while file hashes still matched. It never reached PyPI. Use **4.4.1** (still on PyPI, truncates step strings) or **4.4.3**. Hotfix landed on `main` before 4.4.3.

### Fixed — Legacy signature preimage

- **`content_truncated` null no longer enters the signed bytes.** `omit_absent_optional_hash_fields` is shared by the JCS hash and the legacy JSON path. Keep `true`/`false` bound.

### Fixed — Sealed content completeness

- **Step payloads are sealed in full.** `RecordingContext.add_step` no longer truncates strings at 2000 characters. The viewer still shortens *display* summaries; `steps.jsonl` is the evidence.
- **`manifest.content_truncated`** — new seals set `false` at pack time so completeness of sealed payloads is asserted, not implied. `epi verify` **FAIL**s if the flag is `true`. Artifacts without the field (everything shipped through 4.4.1) **WARN**: those seals may have truncated strings. Do not treat pre-this-change `.epi` files as complete transcripts.

### Changed — Homepage honesty

- Hero copy states the seal proves integrity after sealing, not that every call was captured. Builder loop leads with gateway proxy; `record()` is the quickstart.

---

## [4.4.1] - 2026-08-29

### Fixed — Wheel, Canonicalization & TRACE Interop (evidence-correctness)

#### Changed

- **Wheel size 11.0 MB → 0.64 MB** — removed `verify_portal` (19.5 MB demo assets, duplicate video) from `pyproject.toml` `packages.find` + `package-data`. Verified via `zipfile` inventory: `verify_portal 150 → 0` files. Hosted demos remain on `epilabs.org`, not in pip wheel.
- **Canonical JSON now RFC 8785 (JCS)** — `epi_core/serialize.py` `_get_json_canonical_hash` and `epi_core/container.py` notarize payload now use `rfc8785.dumps` (hard dep `rfc8785>=0.1.4`) to match `agentrust-trace 0.9.0`. Fixes float `1.0 → 1` divergence. Missing `rfc8785` raises; it does not silently fall back. **Verifier dispatch is version-gated:** `manifest.spec_version` `<4.4.1` → legacy `json` sort_keys (warning at dispatch, including short artifacts with no chain), `>=4.4.1` → JCS, `1.x` → CBOR. New seals use different signature bytes than 4.4.0.
- **Duplicate asset removed** — `verify_portal/static/assets/demo/epi-walkthrough.mp4` identical to parent (SHA256 `9dbbe7eb…` 897609 B) deduplicated.

#### Added

- **`epi export trace`** — Level 0 log-import TRACE Trust Record exporter (`epi_recorder/integrations/trace_exporter.py` + `epi_cli/main.py` `export trace`). Maps `.epi` → `tool_transcript.hash = sha256(.epi)`, `call_count`, `origin.kind=log-import`, `policy.enforcement_mode=declared`, `runtime.software-only`. Validated via `agentrust_trace.iter_errors == 0` and `sign_record`/`verify_record` (both py3.11 store + py3.12). Uses only shipped TRACE v0.2 fields; `references` correctly rejected.

#### Verified

- Old `.epi` (`docs/assets/readme-demo.epi`) still `WARN` (seal valid, chain PASS)
- New `.epi` with `balance=1.0` + `école` now `PASS` on both interpreters (was step 3 prev_hash FAIL before fix)
- `tests/test_core_loop_golden.py` 2 passed
- TRACE `iter_errors 0`, tamper → `InvalidSignature`, stale `90000s` → rejected, `references` → `Additional properties not allowed`

---

## [4.4.0] - 2026-05-31

### Portal Launch, SCITT Service & AGT Interoperability

#### Added

- Live verify portal - Full EPI-OFFICIAL website on Render.
- SCITT transparency service - Live receipt signing and verification.
- AGT adapter - Microsoft AGT mapping layer.
- AIUC-1 compliance mapping - 6-domain audit layer.
- epi export-html - Zero-install browser sharing.
- Auto-SCITT anchoring - Per-workflow receipt embedding.
- DID:WEB trust registry - did:web:epilabs.org identity.

#### Changed

- Render deployment - render.yaml blueprint.
- Railway deployment - railway.toml config.
- Self-hosted runbook - Operations guide.

#### Fixed

- Security audit - 8 flaws resolved.
- SCITT hash consistency - Statement alignment.
- Viewer error handling - Error URLs, 413 handling.
- Portal routing - Explicit routes, redirects.
- Packaging hygiene - verify_portal in wheels.

#### Documentation

- New: AGT quickstart, AIUC-1 submission, SCITT predicate.
- Updated: CLI ref, spec, release docs, README.

---

EPI follows [Semantic Versioning](https://semver.org/) and treats version changes as
**corrections to evidence guarantees**, not just feature updates.

---

## [4.1.0] - 2026-05-14

### Chain Verification & Trust Correctness Release

#### Fixed

- **`prev_hash` chain verification** -- Changed `StepModel` hashing from CBOR to JSON canonicalization via new `format="json"` parameter in `get_canonical_hash()`. Added chain verification to `epi verify` and `chain_ok` to verification reports. Old CBOR-hashed artifacts gracefully default to `chain_ok=True`.
- **Guardrails test skip** -- Added `pytest.importorskip("guardrails")` to 5 tests in `tests/integration/test_epi_guardrails.py` when guardrails is not installed.
- **Typer CLI compatibility** -- Changed `DedupStrategy` annotation from `Literal[...]` to `str` in `epi_cli/importer.py` to avoid `RuntimeError: Type not yet supported` in typer 0.12.5.

#### Notes

- No artifact wire-format changes. Existing `.epi` files remain valid and readable.
- No CLI interface changes. All commands behave the same.

---

## [4.0.3] - 2026-05-03

### Forensic Viewer Redesign & Trust Correctness Release

#### Changed

- **Forensic document viewer -- complete redesign** -- Replaced the 8,382-line SPA (inbox queues, team panels, filters) with a 2,340-line forensic document viewer. New design: numbered sections (section 0-8), monospace aesthetic, expandable step rows with terminal-style JSON expansion, heatmap timeline bar, fixed sidebar navigation. Oriented around case investigation rather than team workspace management.
- **`did_web.py` rewritten to use stdlib `urllib.request`** -- Eliminates the undeclared `requests` dependency. Added `generate_did_document()` helper for self-hosting. Added support for both `publicKeyMultibase` (z-prefixed base58btc) and `publicKeyJwk` (crv=Ed25519) key formats.

#### Fixed

- **`workflow_name` resolution** -- Viewer title and source name always showed UUID in v4.0.2. Both `epi_core/container.py` (`_create_embedded_viewer`) and `epi_cli/view.py` (`_build_preloaded_case_payload`) now read `workflow_name` from the `session.start` step content, which is the authoritative source.
- **Case context not visible** -- `manifest.goal`, `manifest.notes`, `manifest.metrics`, and `manifest.approved_by` are now displayed as section 2 (Case Context) in the forensic viewer.
- **Smart step summaries** -- 14+ step kinds now show human-readable summaries in the evidence timeline instead of raw `JSON.stringify` dumps. Covered: `session.start/end`, `llm.request/response`, `tool.call/response`, `agent.decision`, `agent.approval.request/response`, `agent.run.start/end`, `application.intake`, `credit.check`, `policy.check`, `environment.captured`, `source.record.loaded`.
- **`epi verify` Forensic: FAIL on normal recordings** -- `completeness_ok` in `epi_cli/verify.py` incorrectly required guardrails steps in every artifact. Fixed: `len(iteration_steps) == 0 or all(...)` so empty guardrails step lists are treated as complete. Normal recordings now show `Forensic: PASS`.
- **`VERIFY.txt` always showed `public_key: None`** -- Was written before signing. Now written after signing so it contains the real Ed25519 public key. Also excluded from `file_manifest` to prevent integrity failures on re-open.
- **DID identity missing from `epi verify` trust report** -- Trust report now shows `DID: did:web:...` when the artifact was recorded with a DID:WEB governance binding.
- **Viewer hardcoded signature state to unsigned** -- Signature state is now read from case payload verification result. Properly signed artifacts now show `SIGNED` in the viewer header.

#### Added

- **Simulation framework** -- `simulation/run_simulation.py` with five scenarios (loan happy path, loan policy fault, medical triage, refund compliant, refund policy fault), all passing end-to-end.

#### Notes

- No artifact format changes. Existing `.epi` files remain valid and readable.
- No CLI interface changes. All commands behave the same.
- The viewer fix is a **correction to evidence guarantees** -- previously, auto-open paths and the baked-in viewer could show incorrect trust state, missing case context, and unreadable step summaries.

---

## [4.0.2] - 2026-05-02

### Viewer Consistency & AGT Interoperability Release

#### Fixed

- **Eliminated stale "old viewer" across all open paths** — `_open_viewer()` in `epi_cli/run.py` was using a throwaway temp dir (`epi_view_<uuid>`) and regenerating the legacy embedded viewer (`epi-data` format). It now uses the persistent viewer cache (`~/.epi/view-cache/`) and the current decision-ops viewer (`epi-preloaded-cases` format), matching `epi view` behavior.
- **`EPIContainer._create_embedded_viewer()` now bakes the new viewer format** — the embedded `viewer.html` inside every `.epi` artifact now uses the `epi-preloaded-cases` payload (`cases[]` + `ui` config) instead of the legacy flat `epi-data` format. This fixes:
  - Windows double-click VBS fallback
  - `epi extract` output
  - `epi refresh-viewer` output
  - Offline/email sharing of the baked-in viewer

#### Added

- AGT export features and interoperability adapters:
  - workspace and archive exporters in `epi_recorder.integrations.agt.exporter`
  - `EPIContainer.pack(..., embed_agt=True)` to optionally embed `artifacts/agt_export.json` into `.epi` artifacts
  - identity resolution using the local `epi_cli.identity` mapping to populate AGT `agent` fields
  - compact `agt_compat` summary block in `policy_evaluation.json` for downstream governance systems
- Demo and pitch assets: `demo_assets/README.md` and `scripts/package_demo.py` to create a demo bundle
- Unit tests and automation: added `tests/test_policy_evaluation_agt_compat.py`, `tests/test_workspace_to_agt_exporter.py`, `tests/test_export_identity_resolution.py`, and the reusable verifier `tests/verify_3layer.py`

#### Changed

- Documentation and examples updated to describe AGT export, embedding, and identity mapping workflows

#### Notes

- This release focuses on EPI-side interoperability for AGT without modifying AGT itself; features are opt-in and additive.
- The viewer fix is a **correction to evidence guarantees** — previously, auto-open paths (`epi run`, `epi init`) and the baked-in viewer could display stale or incomplete verification context. All paths now render the same current decision-ops UI.

---

## [4.0.1] - 2026-04-12

### Go-To-Market Layer

#### Added

- **Privacy-first opt-in telemetry**
  - `epi telemetry status|enable|disable|test` now manages local opt-in state
  - no telemetry is sent, and no install ID is created, before opt-in
  - telemetry is limited to non-content metrics such as command, integration type, success/failure, artifact bytes, artifact count, CI flag, Python version, OS, and EPI version
- **Pilot signup**
  - `epi telemetry enable --join-pilot` captures explicit contact consent
  - telemetry can be linked to a pilot profile only with explicit `--link-telemetry` consent
- **Onboarding distribution commands**
  - `epi init --github-action` can create a safe CI evidence workflow
  - `epi integrate <target>` generates examples for `pytest`, `langchain`, `litellm`, `opentelemetry`, and `agt`
- **Gateway telemetry ingestion**
  - self-hosted gateways can enable `POST /api/telemetry/events` and `POST /api/telemetry/pilot-signups` with `EPI_GATEWAY_TELEMETRY_ENABLED=true`
  - telemetry records and pilot signup records are stored separately as append-only JSONL

#### Documentation

- Added telemetry privacy documentation.
- Added legal-safe `.epi` evidence-preparation guidance.
- Added an internal go-to-market execution plan with AGT outreach thresholds, framework PR fallbacks, dashboard beta definition, and contingency paths.

---

## [4.0.0] - 2026-04-08

### `.epi` Envelope Format

#### Added

- **New binary `.epi` outer envelope**
  - newly written artifacts now use an `EPI1` header instead of starting with ZIP magic bytes
  - the envelope stores payload length and SHA-256 so readers can fail fast before opening the embedded evidence payload
- **Dual-format container support**
  - EPI now reads both legacy ZIP-based `.epi` files and the new envelope-based `.epi` files transparently
  - legacy artifacts remain valid and readable
- **Artifact migration command**
  - `epi migrate` converts between legacy ZIP and envelope container formats without changing the inner evidence payload

#### Changed

- **Default wire format**
  - `EPIContainer.pack()` and the normal CLI write paths now default to `envelope-v2`
  - the signed inner manifest remains the trust root for this release line
- **Share and gateway transport**
  - new envelope artifacts are served as `application/vnd.epi`
  - legacy ZIP artifacts keep `application/vnd.epi+zip`

#### Fixed

- **Raw artifact identity during sharing**
  - `.epi` files no longer begin with ZIP bytes by default, which avoids the most common “compressed folder” misclassification path in download channels
- **Container abstraction coverage**
  - `view`, `verify`, `review`, `export-summary`, policy inspection, AGT import, and share validation now route through one shared container layer instead of assuming the outer file is a ZIP archive

---

## [3.0.3] - 2026-04-07

### AGT Front-Door Release Polish

#### Added

- **Microsoft Agent Governance Toolkit quickstart**
  - the public docs now treat `epi import agt` as a first-class onboarding path instead of leaving it buried in examples
  - a canonical `AGT -> EPI` walkthrough now starts from `examples/agt/sample_bundle.json`
- **Imported-evidence trust guidance**
  - current docs now explain the imported artifact surfaces that matter most to reviewers:
    - `steps.jsonl`
    - `policy.json`
    - `policy_evaluation.json`
    - `analysis.json`
    - `artifacts/agt/mapping_report.json`

#### Improved

- **Current release documentation alignment**
  - README, docs hub, CLI reference, policy guide, spec, self-hosted runbook, and flagship explainer now align on `v3.0.3`
  - the current docs set now points at the `v3.0.3` flagship explainer instead of the previous release-line document
- **First-time AGT user flow**
  - the CLI help and importer output now make the `import -> verify -> view` flow more obvious to users coming from exported AGT evidence

#### Notes

- `v3.0.3` is a release-polish line focused on discoverability, trust clarity, and current-doc consistency for the AGT import path.

---

## [3.0.2] - 2026-04-04

### Offline Viewer Packaging Fix

#### Fixed

- **Extracted browser viewer**
  - `epi view --extract` now vendors and inlines `jszip.min.js` instead of leaving a JSDelivr dependency in the generated `viewer.html`
  - extracted viewers now open cleanly in offline and air-gapped environments without remote script loading
- **Embedded and policy editor viewer parity**
  - the shared viewer inlining path now bundles the same JSZip runtime for embedded artifact viewers and the browser policy editor
- **Release audit coverage**
  - wheel auditing now fails if the vendored `web_viewer/jszip.min.js` runtime asset is missing from the built package

---

## [3.0.1] - 2026-04-02

### Front-Door Reliability Patch

#### Fixed

- **Packaged browser viewer**
  - `epi view` now works from a clean wheel install because the `web_viewer` assets ship in the package and are loaded through package resources
- **LangChain callback stability**
  - `EPICallbackHandler` no longer crashes when LangChain omits `serialized` metadata in callback payloads
- **Insurance policy threshold alignment**
  - the built-in `insurance.claim-denial` profile now evaluates the public `amount` field shape while keeping `claim_amount` compatibility
- **Threshold analyzer realism**
  - high-value approval rules now wait for the consequential decision/action instead of flagging intermediate fraud or coverage investigation steps

#### Improved

- **Release audit coverage**
  - wheel auditing now fails if required viewer assets are missing from the packaged artifact
- **Current release docs**
  - release-facing documentation now matches the packaged `3.0.1` behavior and current share/view guidance

---

## [2.8.10] - 2026-03-24

### Notebook Packaging Correction

#### Fixed

- **Source release demo assets**
  - `colab_demo.ipynb` and `EPI NEXUA VENTURES.ipynb` are now packaged in the source distribution
  - older notebook snapshots are explicitly kept out of the release artifact
- **Release audit coverage**
  - release gating now audits the source tarball for the required notebooks and rejects temporary packaging leaks
- **Release honesty**
  - release-facing docs now describe the notebooks as GitHub/source-release assets while keeping the wheel runtime-focused

## [2.8.9] - 2026-03-24

### Colab Viewer Fix and Policy Schema Hotfix

#### Added

- **Branded investor notebook**
  - `EPI NEXUA VENTURES.ipynb` added to the repo as an investor-grade Colab walkthrough

#### Improved

- **Colab demo fidelity**
  - both notebook surfaces now render the actual extracted `viewer.html` inside an iframe so Colab shows the real embedded artifact viewer
- **Release alignment**
  - current release surfaces now align on `2.8.9`

#### Fixed

- **Policy schema compatibility**
  - reusable approval policies now accept both `approval_id` and `id`
  - policy rules now accept list-valued `applies_at`
  - tool-permission evaluation now handles list-valued `applies_at`
- **Notebook product fit**
  - tracked Colab demos now match the current Policy v2 and viewer behavior instead of relying on brittle notebook-only fallbacks

## [2.8.8] - 2026-03-24

### Tight Release Hardening

#### Added

- **OpenAI Agents-style event bridge**
  - `OpenAIAgentsRecorder`
  - `record_openai_agent_events(...)`
  - stream-event mapping into EPI agent steps for messages, tools, approvals, handoffs, memory, and decisions

#### Improved

- **Policy validation UX**
  - `epi policy validate` now accepts both standalone policy files and embedded artifact policies
  - invalid JSON now reports line-and-column diagnostics
  - invalid schema fields now report clearer field-level validation errors
- **Viewer reviewer flow**
  - jumping from failed controls into the timeline auto-opens the target step details

#### Fixed

- **Release consistency**
  - release surfaces aligned on `2.8.8`
- **Windows installer guardrails**
  - regression coverage now prevents unsupported Inno task flags from slipping back into the installer script

## [3.0.0] - 2026-04-01

### Stable Evidence Release Line

#### Added

- **Policy-first workflow surfaces**
  - guided `epi policy init`
  - sealed `policy.json` and `policy_evaluation.json`
- **Insurance/compliance-facing review flow**
  - Decision Record export
  - browser review surfaces for trust, policy, and case evidence
- **Hosted pilot foundations**
  - gateway share routes
  - hosted browser case page

#### Fixed

- **Release packaging and docs**
  - release surfaces aligned around the `3.0.0` evidence workflow and policy model

#### Notes

- `3.0.0` is the stable software line for the current `.epi` evidence specification.

---

## [2.8.7] - 2026-03-24

### Policy v2 Foundation and Trust Hardening

#### Added

- **Policy v2 metadata**
  - `policy_format_version`, `policy_id`, policy scope, approval policy references, rule `mode`, and rule `applies_at`
- **Enterprise control support**
  - `tool_permission_guard`
  - structured `policy_evaluation.json` output sealed into artifacts when policy is present
- **Viewer control review flow**
  - control outcomes panel in the embedded viewer
  - jump-to-step navigation from failed controls into the timeline

#### Improved

- **Policy review clarity**
  - `epi policy show` surfaces policy ID and scope when present
  - policy docs now describe both the current rulebook model and the next enterprise direction
- **Version consistency**
  - installer metadata and current-version docs now align with `2.8.7`

#### Fixed

- **Desktop trust verification**
  - the separate `epi-viewer` app now performs real Ed25519 manifest verification instead of format-only checks
- **Windows association honesty**
  - association repair now fails honestly if post-registration diagnostics are still broken
  - system elevation prefers the current install's adjacent `epi.exe` instead of a stale `PATH` entry
- **Packaging/release hygiene**
  - stale static-file manifest include removed
  - release/version drift checks tightened

## [2.8.6] - 2026-03-22

### Product Hardening and Agent-First Workflow Evidence

This release makes the `v2.8.x` line feel much more like a product for both normal users and AI-agent workflows.

#### Added

- **Agent-first recording surface**
  - `epi.agent_run(...)` / `epi.agent(...)` for direct `record(...)` sessions
  - `get_current_session().agent_run(...)` in `epi run` bootstrap mode
  - first-class agent events for plans, tool calls/results, decisions, approvals, memory reads/writes, handoffs, and pause/resume checkpoints
- **Agent-aware viewer flow**
  - agent timeline filter
  - clearer summaries for agent/tool/approval/memory events
  - case-level highlights for approvals, handoffs, and pause/resume checkpoints
- **`approval_guard` policy rule**
  - explicit policy rule for actions that require an approved response before execution

#### Improved

- **First-run onboarding**
  - `epi init` now behaves more like a setup wizard
  - generated demo content teaches the difference between console evidence and structured workflow evidence
- **`epi run` usability**
  - captures plain `print(...)` output as `stdout.print`
  - distinguishes console-only evidence from richer structured workflow evidence
  - prefers a child script's real `record(...)` artifact over a misleading bootstrap artifact
- **Reviewer trust flow**
  - `epi review` shows trust state first and blocks tampered evidence from review
  - `epi policy show` now works directly on `.epi` artifacts with embedded rulebooks
- **Viewer clarity**
  - better plain-language trust guidance
  - clearer review-first and rulebook-first explanations for non-technical reviewers
- **CLI responsiveness**
  - lazy imports and narrower startup checks make basic commands materially faster on Windows
- **Windows opening reliability**
  - association/open flow now prefers the live `epi view \"%1\"` path to avoid stale viewer launches

#### Fixed

- **Front-door trust issues**
  - onboarding/demo artifacts no longer get noisy `stdout` context-drop faults
  - short healthy workflows no longer trigger misleading context-drop findings
- **Viewer packaging/injection**
  - embedded viewer data is HTML-safe
  - stale generated files are cleared before sealing
  - repeated reviews replace `review.json` cleanly instead of creating duplicate ZIP entries
- **Trust consistency**
  - `run`, `view`, `verify`, and `ls` now interpret signed/unsigned/invalid artifacts more consistently
- **CLI and Windows dev quality**
  - stale standalone test scripts were repaired for Windows encoding/path behavior
  - developer association diagnostics are stricter about stale launcher drift

## [2.7.2] - 2026-03-14

### Bug Fixes & Reliability

This patch release closes a critical verification gap for pre-v2.7.1 evidence files and hardens the CLI across the board.

#### Fixed

- **Legacy Signature Compatibility (Critical)**: `verify_signature()` now auto-detects encoding — it tries **Hex** first (current format) and falls back to **Base64** (pre-v2.7.1 format). Previously, any `.epi` file signed by an older version would fail verification with a cryptic error instead of a meaningful result.
- **Browser Viewer Signature Compatibility**: `crypto.js` (inlined into every new `.epi` file) now applies the same hex-then-base64 fallback, so the built-in HTML viewer correctly verifies both old and new files.
- **`epi associate` Exit Code**: The `associate` command incorrectly returned exit code `1` when the file association was already registered. It now prints a confirmation and exits `0`.
- **Verbose Verify Traceback**: In `--verbose` mode, `epi verify` would print a spurious Python traceback when verification failed (e.g. tampered file). `typer.Exit` is now re-raised before the generic exception handler catches it.
- **Analytics Import Crash**: `import epi_recorder` would crash with `ModuleNotFoundError` if `pandas` was not installed, even for users who never use analytics. Import is now lazy with a clear error on first use.
- **Missing `wrap_anthropic` Export**: `wrap_anthropic` and `TracedAnthropic` were not exported from the top-level `epi_recorder` package despite being documented.
- **Incorrect Google AI Studio URL**: `epi chat` help text linked to a dead URL for obtaining a Gemini API key. Fixed to `aistudio.google.com/app/apikey`.
- **`analytics` Missing from Optional Dependencies**: `pyproject.toml` had no `analytics` extras group, so `pip install epi-recorder[analytics]` failed. Added `analytics = ["pandas>=1.5.0", "matplotlib>=3.5.0"]`.

#### Internal

- Extracted shared subprocess helpers (`ensure_python_command`, `build_env_for_child`) from `epi_cli/run.py` and `epi_cli/record.py` into `epi_cli/_shared.py`, eliminating duplicate code.
- `associate` command in `main.py` now calls `_needs_registration()` before delegating to `register_file_association()` to produce the correct "already registered" message.

---

## [2.7.1] – 2026-03-12

### 🛡️ Decentralized Trust & Architectural Symmetry

This release stabilizes the v2.7 series by aligning decentralized verification logic across all components and hardening the file association system.

#### Added
- **Self-Healing File Association**: Registry hooks now perform real-time health checks on every CLI run. If associations are missing or broken (due to OS updates or manual deletion), they are automatically repaired silently.
- **Embedded Public Key Verification**: `epi run` and `epi verify` now prioritize the public key embedded in the `.epi` manifest, enabling zero-config verification on air-gapped or guest machines without local keys.

#### Fixed
- **Architectural Symmetry**: aligned all cryptographic components to use **Hex** encoding for signatures (matching backend/gateway) and **Canonical JSON** for hashing v2.x manifests.
- **SQL Integrity (Critical)**: Fixed a column index mismatch in `epi_analyzer/detector.py` that caused JSON decoding failures when loading recordings from SQLite.
- **`epi run` Verification Logic**: Fixed a bug where `epi run` would incorrectly report successful verification for signed files even if the signer's identity wasn't embedded.
- **Windows Encoding**: Ensured UTF-8 wrap for stdout/stderr is applied at the entry point of every CLI command.

#### Internal
- Final comprehensive audit of `epi_cli`, `epi_core`, and `epi_recorder` completed.
- Full parity between CLI verification and GitHub Actions verification logic.

---

## [2.7.0] – 2026-03-11

### 🚀 Zero-Friction File Opening & Unicode Safety

This release makes `.epi` files first-class OS citizens — double-clicking opens the viewer automatically — and eliminates Unicode crashes across the codebase.

#### Added

**Cross-Platform File Association** (`epi_core/platform/associate.py`)
- Automatic OS-level registration of `.epi` file type at first CLI use
- Windows: `HKEY_CURRENT_USER\Software\Classes` registry (no admin required)
- macOS: Minimal `EPI Viewer.app` bundle with UTI declaration
- Linux: `xdg-mime` MIME type + `.desktop` launcher
- Idempotent: runs once, never duplicates entries
- `epi associate` — manually (re)register file association
- `epi unassociate` — clean removal of file association

#### Fixed

**Unicode Safety (Windows Critical)**
- Windows console encoding fixed at CLI entry point (`cp1252` → `utf-8`)
- All file I/O now uses explicit `encoding="utf-8"` (3 calls fixed in `main.py`, `run.py`)
- All path operations use `pathlib.Path` — no string concatenation
- `epi view` uses `webbrowser.open(path.as_uri())` — correct cross-platform method

**`epi view` Robustness**
- Stem resolution now picks most recent match by mtime when multiple files match
- Temp directories auto-cleaned after 5 seconds via daemon thread
- Explicit `BadZipFile` handling with clear error message
- Warning when file lacks `.epi` extension
- Exit code 1 on all error paths

#### Internal
- New `epi_core/platform/` package for OS integration utilities
- `pyproject.toml` `setuptools.packages.find` includes `epi_core*` (covers new subpackage)

---

## [2.6.0] – 2026-02-20

### 🚀 Framework Integrations, CI Verification & OpenTelemetry Support

This release transforms EPI from a standalone recorder into a **framework-native evidence layer** — integrating with the tools AI engineers already use.

#### Added

**LiteLLM Integration** (`epi_recorder.integrations.litellm`)
- `EPICallback` — callback handler for 100+ LLM providers
- `enable_epi()` / `disable_epi()` — one-line global activation
- Captures request, response, error, and streaming events

**LangChain Callback Handler** (`epi_recorder.integrations.langchain`)
- `EPICallbackHandler` — logs LLM, tool, chain, retriever, and agent events
- Works with LangChain, LangGraph, and any callback-compatible framework
- Graceful fallback when LangChain is not installed

**OpenAI Streaming Support**
- `stream=True` auto-routed to streaming handler in `TracedCompletions`
- Chunks yielded in real-time, assembled response logged after completion
- Usage stats captured from final streaming chunk

**pytest Plugin** (`pytest-epi`)
- `--epi` flag generates signed `.epi` evidence per test
- `--epi-dir` for custom output directory
- End-of-session summary with file listing
- Registered via `pytest11` entry point

**GitHub Action** (`.github/actions/verify-epi/`)
- Composite action for CI/CD pipeline verification
- Scans for `.epi` files, verifies integrity and signatures
- Generates GitHub Step Summary with pass/fail table
- Configurable `fail-on-tampered` and `fail-on-unsigned` inputs

**Global Install/Uninstall** (`epi install --global` / `epi uninstall --global`)
- Injects EPI auto-recording into `sitecustomize.py`
- Idempotent installation (safe to run multiple times)
- Clean removal with `EPI_AUTO_RECORD=0` disable flag
- Respects existing sitecustomize.py content

**OpenTelemetry Exporter** (`epi_recorder.integrations.opentelemetry`)
- `EPISpanExporter` — converts OpenTelemetry spans to signed `.epi` files
- `setup_epi_tracing()` — one-line setup for any OTel-instrumented application
- Trace-level grouping, LLM semantic conventions, batch flushing
- Graceful fallback when OpenTelemetry is not installed

#### Fixed

- **Signature verification**: `verify_signature()` now correctly extracts public key from manifest
- **LangChain handler**: Warns instead of crashing when LangChain is not installed
- **pytest plugin**: Uses `makereport` hookwrapper for correct test outcome capture
- **pytest plugin**: Safe `config.getini()` access with fallback

#### Internal
- 60 end-to-end test assertions, all passing
- Real `.epi` file generation and verification in tests
- Real `sitecustomize.py` round-trip testing

## [2.5.0] – 2026-02-13

### 🚀 Major Features

#### Added

**Anthropic Claude Wrapper**
- `wrap_anthropic()` — proxy wrapper for Anthropic's Claude API
- `TracedAnthropic` — fully wrapped client with automatic evidence capture
- `TracedMessages` — traced `messages.create()` for Claude conversations
- Captures `temperature`, `top_p`, and `system` parameters in evidence logs
- Full request/response logging: messages, tokens, latency, model info
- Mirrors `wrap_openai()` architecture for consistency

**Enhanced Provider Support**
- Anthropic now has first-class wrapper support (not just explicit API)
- Updated supported providers table

#### Fixed

**Critical: Path Resolution Bug**
- Fixed `_resolve_output_path()` double-prepending `epi-recordings/` directory
- Before: `record("epi-recordings/test.epi")` → `epi-recordings/epi-recordings/test.epi` (broken)
- After: `record("epi-recordings/test.epi")` → `epi-recordings/test.epi` (correct)
- Root cause: relative paths containing the recordings directory name were not detected

**Signing & Verification**
- Confirmed Ed25519 signing and verification are fully operational
- Fixed file creation appearing to fail due to path resolution bug above

#### Internal
- Comprehensive signing/verification test suite
- Path resolution test coverage
- Anthropic wrapper test suite (19 tests, 100% pass rate)

---

## [2.4.0] – 2026-02-12

### 🚀 Major Features

This release adds comprehensive agent development and monitoring capabilities.

#### Added

**Agent Analytics Engine**
- `AgentAnalytics` class for analyzing `.epi` files in batch
- Performance summary: success rates, costs, duration trends
- Error pattern detection and analysis
- Tool usage distribution tracking
- Period comparison (this week vs last week, etc.)
- HTML dashboard generation (`generate_report()`)

**Async/Await Support**
- Async context manager (`async with record()`)
- `__aenter__` and `__aexit__` methods
- `alog_step()` async logging method
- Non-blocking I/O using `asyncio.run_in_executor()`
- Full backward compatibility with sync mode
- Perfect for LangGraph, AutoGen, and async-first frameworks

**LangGraph Integration**
- `EPICheckpointSaver` class (native checkpoint backend)
- Implements LangGraph's `BaseCheckpointSaver` interface
- Async checkpoint methods: `aput()`, `aget()`, `alist()`
- Smart state serialization (hashes large states >1MB)
- Automatic capture of all state transitions
- Integration with EPI recording sessions

**Local LLM Support (Ollama)**
- Full compatibility with Ollama's OpenAI-compatible API
- Enables free, unlimited local testing
- Works with DeepSeek-R1, Llama, and other Ollama models
- Zero API costs for development and testing

#### Documentation
- Updated README with "New in v2.3.0" section
- Comprehensive feature documentation
- Code examples for all new features
- Usage guides for analytics, async, LangGraph, and Ollama

#### Internal
- Created `epi_recorder/analytics/` package
- Created `epi_recorder/integrations/` package
- Added comprehensive test suites (15 new tests)
- All tests passing

---

## [2.3.0] – 2026-02-06

### ⚠️ Design Correction (Migration Required)

This release clarifies EPI's role as an **evidence system**, not a passive logger.

#### Breaking
- **Implicit monkey-patching disabled by default**
  - Automatic interception of LLM calls is no longer enabled
  - Evidence capture is now **explicit by design**

#### Rationale
Evidence systems must be:
- intentional
- reviewable in code
- stable across SDK versions

Implicit interception was convenient but fragile.  
Explicit capture provides stronger evidentiary guarantees.

#### Added
- **Explicit evidence API**
  - `log_llm_call(response)` — structured capture of LLM responses
  - `log_chat(data)` — simplified, framework-agnostic capture
- **Wrapper clients**
  - `wrap_openai()` — proxy wrapper enabling capture without SDK modification
- **TracedOpenAI**
  - Fully wrapped OpenAI client with automatic evidence capture

#### Deprecated
- `legacy_patching=True`
  - Temporary compatibility flag
  - Will be removed in v3.0.0

---

## [2.2.1] – 2026-02-06

### Fixed
- Guaranteed creation of `steps.jsonl` at recording start
- Updated tests to match current evidence specification
- Removed brittle test return semantics

### Added
- `unpatch_all()` to restore original methods in legacy patching mode
- Viewer support for error-level evidence steps:
  - `llm.error`
  - `http.request`
  - `http.response`
  - `http.error`

### Changed
- Evidence spec version bumped to 2.2.1

---

## [2.2.0] – 2026-01-30

### Clarified Scope
- EPI's primary artifact is a **portable, verifiable `.epi` artifact that packages execution as evidence**
- Debugging tools are treated as **secondary consumers** of evidence

### Added
- Thread-safe recording using `contextvars`
- Crash-safe SQLite-based evidence storage
- `epi debug` — heuristic analysis of recorded evidence
- Async recording API for concurrent workflows

### Changed
- License standardized to MIT
- Documentation updated to emphasize execution evidence

### Technical
- Replaced global state with context-isolated recording
- Introduced atomic, append-only storage guarantees

---

## [2.1.3] – 2026-01-24

### Added
- Google Gemini evidence capture
- `epi chat` — natural language querying of evidence files

### Fixed
- Windows terminal compatibility issues
- Improved error classification and reporting
- Reduced SDK deprecation noise

---

## [2.1.2] – 2026-01-17

### Security
- Client-side, offline signature verification in embedded viewer
- Canonical serialization and public-key inclusion in evidence manifests

### Changed
- Viewer trust indicators updated
- Evidence specification versioned

---

## [2.1.1] – 2025-12-16

### Added
- Reliable `python -m epi_cli` fallback
- Automatic PATH repair on Windows
- Universal install scripts
- Self-healing `epi doctor` diagnostics

### Fixed
- Windows Unicode terminal issues
- Packaging and installer reliability

---

## [1.0.0] – 2025-12-15

### Initial Release
- Portable `.epi` evidence format
- Cryptographic sealing with Ed25519
- Embedded offline viewer
- Zero-config CLI recording
