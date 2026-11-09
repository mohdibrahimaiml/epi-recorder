# Pre-launch test — epi-recorder 4.10.0 + epilabs.org + EPI Cloud

**Date:** 8 November 2026  
**Branch:** `release/4.10.0-site`  
**Commit:** `598eba9d`  
**PR:** #263 (draft)  
**Preview:** `https://release-4-10-0-site.epi-recorder.pages.dev/`  
**Tester:** coding agent (test-only; no product changes made)

---

## GO / NO-GO

**NO-GO.**

A 4.10.0 artifact is rejected as **SIGNATURE INVALID** by the 4.9.0 CLI and by the live 4.9.0 browser verifier. Bank reviewers on 4.9.0 cannot verify new files. That is the P0 in this report.

### P0

| ID | Finding |
|---|---|
| P0-1 | 4.9.0 verifiers reject 4.10.0 files as signature invalid/tampered. Details under A5. |

### P1

| ID | Finding |
|---|---|
| P1-1 | `/verify` tamper lab: the page top says the file was changed, but the detail lines still show `02 Integrity PASS`, `03 Signature VALID` and `SEAL VALID`. Contradictory verdict. |
| P1-2 | Killing a seal process does not record a burn. The next seal reused the number and the audit stayed `#1..#51 contiguous`. |
| P1-3 | Windows key files inherit broad ACLs; `~/.epi/keys/default.key` is readable by two unresolved SIDs besides the owner. No explicit restrictive ACL is set by `epi keys generate`. |
| P1-4 | `/reviewers` still tells reviewers to install `epi-recorder>=4.9.0`; that version cannot verify the 4.10.0 file (ties to P0-1). |
| P1-5 | axe-core WCAG 2 A/AA: 4 violations on `/`, 1 on `/reviewers`, 2 on `/verify/` (light); 3/1/1 in dark. Includes contrast, nested interactive controls, link-in-text-block, and an ARIA-required-children error. |

### P2

| ID | Finding |
|---|---|
| P2-1 | The sdist contains the full `tests/` tree. The wheel does not. |
| P2-2 | A 50 MB low-entropy step payload fails signing with the decompression-bomb guard (938×); the message is clear, but the requested 50 MB test did not produce a signed file. High-entropy 50 MB was not tested. |
| P2-3 | The preview sitemap contains production `/blog/...` URLs. Those return 404 on production until launch; expected pre-launch, but a crawler sees them now. |
| P2-4 | `website/assets/demo/naic-claim-override.html` still embeds `spec_version: 4.9.0` (historical demo). |
| P2-5 | Lighthouse and the full 164-command docs sweep were not completed. See A10/C14. |

### Timings

| Step | Time |
|---|---|
| Full suite (`pytest -q`) | see A2 |
| Browser-marked suite (`EPI_TEST_MARKER` with `EPI_TEST_CHROMIUM=1`) | 4m 12s |
| Wheel/sdist build | ~1 min |
| 50 parallel seals | ~1 min |
| 1,000-step seal / verify | ~17 s / ~2.3 s per run |

---

## Part A — engineering

### A1 — state — PASS

`release/4.10.0-site` at `598eba9d`; clean tracked tree. Work done in `C:\epi-temp\opencode\prelaunch` with a detached worktree and fresh venvs.

### A2 — full suite — see result below

`python -m pytest -q` was run on `598eba9d`:

```
2625 passed, 59 skipped, 104 warnings in 2129.74s (0:35:29)
```

`EPI_TEST_CHROMIUM=1 python -m pytest -q -m browser`:

```
55 passed, 1 skipped, 2628 deselected in 252.02s (0:04:12)
```

No viewer test failed with Chromium enabled. One browser test skipped; the reason was not captured in this run.

### A3 — build and install — PASS (one P2)

Built `epi_recorder-4.10.0-py3-none-any.whl` and `epi_recorder-4.10.0.tar.gz`.

- Wheel metadata: `Version: 4.10.0`, `License-Expression: MIT`.
- Viewer assets present: `web_viewer/app.js`, `index.html`, `styles.css`, `jszip.min.js`, `epi_viewer_static/crypto.js`.
- LICENSE present in both.
- No tests, `internal/`, scratch, `.key`, `.env`, or private-key files in the wheel.
- The sdist contains `tests/` (P2-1). No `internal/`, scratch, or private-key files. The four `.pem` files are public TSA root certificates.

Fresh venvs:

| Python | `epi --version` | `epi doctor` |
|---|---|---|
| 3.11 | 4.10.0 | exit 0, system healthy |
| 3.12 | 4.10.0 | exit 0, system healthy |

Python 3.13 was not installed/available; “highest” was tested at 3.12.

### A4 — upgrade path — PASS

Fresh 4.9.0 venv, local `epi witness serve`, 3 sealed runs. Then upgraded to the 4.10.0 wheel.

- Old files: `WARN` before upgrade and `WARN` after. Same decision status.
- 4.10.0 `epi witness audit` on the old log: exit 0, `Unsequenced: 3 report(s) ... not an error`.
- Two new 4.10.0 runs sealed to the same log; audit: exit 0, `#1..#2 contiguous`, `clean`, old reports still unsequenced.
- 4.9.0 `epi witness audit` exits 2 (the audit command is not in 4.9.0). Not used for the compatibility claim.

### A5 — backward compatibility — **FAIL, P0**

Artifact: `website/assets/demo/decision-example.epi` (4.10.0, sealed release + pre-action approval).

**4.9.0 CLI from PyPI:**

```
$ epi verify decision-example.epi
┌────────── ✘ SEAL FAIL — SIGNATURE INVALID EPI Verification Report ──────────┐
│ DECISION: FAIL                                                              │
│ Reason: Invalid signature                                                   │
│   - Signature:    INVALID                                                   │
exit 1
```

**4.9.0 CLI with the new flags:**

```
$ epi verify decision-example.epi --release claims-policy-1.4.epi ...
Error: No such option: --release
exit 2
```

**Live 4.9.0 browser verifier** (`https://epilabs.org/verify/`):

```
02 · Integrity PASS · all file hashes match
03 · Signature
INVALID · tampered
SEAL VALID · IDENTITY NOT PINNED
```

**4.10.0 preview browser verifier:**

```
03 · Signature VALID · Ed25519 verified
SEAL VALID · IDENTITY NOT PINNED
```

The 4.10.0 preview verifier reads the seal. It does **not** display `release_ref` or the pre-action approval steps; the page correctly gives the CLI command instead of faking those results.

A bank reviewer still on 4.9.0 would be told the new file is tampered. This is the launch blocker.

### A6 — tamper tests — PASS (suite coverage)

`pytest tests/adversarial/test_integrity.py tests/adversarial/test_resign_forgery.py tests/test_tamper_surfaces.py tests/test_pre_action_approval.py tests/test_release_records.py tests/test_seal_ledger.py tests/test_seal_witness.py`:

```
72 passed
```

Coverage includes byte flip, re-sign, chain break, role/approval forgery, backdating/order, approval reuse, args changed after approval, run before approval, and duplicate/ambiguous releases. No test failure.

### A7 — concurrency / crash — PARTIAL, P1-2

- 50 parallel seals: `50 seal report(s)`, `#1..#50 — contiguous`, `clean`.
- Kill midway: process printed `READY`, was killed, then one more seal. Audit showed `#1..#51 — contiguous`, `clean`; **no `BURNED` entry**. The killed reservation was reused, not burned.

### A8 — hostile environments — PARTIAL

| Case | Result |
|---|---|
| No network / no witness | Seal and `epi verify` pass; `WARN` local-sealer verdict. |
| Path with spaces + non-ASCII | Seal and verify pass (`sp ace-é/run é.epi`). |
| 50 MB step payload | Seal fails before signing with `expansion ratio 938x exceeds the 250x limit (decompression-bomb guard)`; message clear, artifact left unsigned. High-entropy 50 MB not tested. |
| Wrong witness secret | Seal succeeds and queues; `epi witness status` shows `HTTP 401 Unauthorized` pending; clear retry/drop guidance. |
| Receiver down | Report queued in `witness_outbox.jsonl`; `epi witness flush` exits 1 with “could not reach … still queued” when the receiver is still down. A successful flush after bringing the receiver up on the same URL was not completed. |
| Read-only HOME | NOT RUN — not safely simulated on this Windows host. |

### A9 — secrets and key permissions — PARTIAL, P1-3

- Public demo files: no private key material. The `BEGIN PRIVATE KEY` strings in `demo_refund.epi`, `refund_case.epi`, `sample-hello.epi`, `sample-refund-ord9001.epi` and `docs/assets/insurance_claim_evidence.html` are viewer JavaScript that parses a PEM, not key bytes.
- Test secrets (`a4-secret`, `a7-secret`, `epi-demo-witness`) do not appear in `website/` or `docs/`.
- Windows ACL: `~/.epi/keys/default.key` has inherited read/execute for two unresolved SIDs in addition to the owner, Administrators and SYSTEM. `epi keys generate` does not apply an explicit restrictive ACL. The temp ledger directory also inherits broad ACLs.

### A10 — docs commands — NOT COMPLETED

Extracted **164** shell commands beginning `epi`, `pip` or `python scripts/` from README, `docs/*.md`, and `blog/posts/*.md` (56 files). They were not run end-to-end: many require artifacts, provider API keys, Cloud credentials, or a human sign-in, and the test is not allowed to fix or create product state. `epi demo`, the reviewer commands, and the new release/pre-action demo commands were run and are covered above.

This is a testing gap, not a product finding.

### A11 — performance — PASS

1,000-step run, 3 repetitions:

| Version | Seal | Verify |
|---|---|---|
| 4.9.0 | 17.56 / 17.60 / 15.94 s | 2.47 / 2.21 / 2.27 s |
| 4.10.0 | 17.12 / 16.43 / 17.99 s | 2.43 / 2.37 / 2.75 s |

No regression above 25%.

---

## Part B — first-time users

### Persona 1 — Priya, AI lending engineer

| ID | Task | Result |
|---|---|---|
| B1 | Install and `epi demo` | **PASS.** Demo runs, seals, verifies offline and prints the artifact path and next steps. |
| B2 | Record her own agent from the 5-minute guide | **BLOCKED.** The guide needs an OpenAI/Anthropic/LiteLLM provider key; none was available and a real key was not requested. |
| B3 | Open the record in the viewer | **PASS.** Viewer shows outcome, reasons, model, approval and release sections; no console errors. |
| B4 | Customer witness, 3 cases, audit | **PASS.** Local witness server + `epi witness audit` worked; see A4/A7. |
| B5 | Release, second approver, MATCHES | **PASS.** Release create/approve/verify produced `claims-policy 1.4 MATCHES`. |
| B6 | Pre-action approval on a separate key dir | **PASS.** `APPROVED BEFORE ACTION` with witness basis. |
| B7 | Error messages | **PASS.** Missing file, wrong witness secret (HTTP 401), and unreachable receiver all gave actionable messages. |

### Persona 2 — Martin, EU bank third-party risk reviewer

| ID | Task | Result |
|---|---|---|
| B8 | Verify with one `.epi`, witness log and `/reviewers` only | **FAIL via P0-1.** If Martin is on 4.9.0, the file is “SIGNATURE INVALID / tampered”. The page also still recommends 4.9.0. The 4.10.0 preview verifier can check the seal but does not explain release/pre-action results; it points to the CLI, which is honest. |
| B9 | Read the DORA guide | **WARN.** No obvious claim contradiction found in this pass, but the guide has not been reviewed by a bank DORA expert/lawyer; that remains required. |

---

## Part C — website journey

### C1 — first visit — PASS

Hero names the product and buyer. All three tabs work; Download and Check it yourself work.

### C2 — crawl — PARTIAL

48 URLs crawled. No preview 404s except four absolute production blog URLs in the preview sitemap (`https://epilabs.org/blog/...`) that are not live until launch. No mixed content or missing images found. Full in-page-anchor and Firefox/WebKit passes were not completed.

### C3 — `/verify` — PASS with P1-1

- `sample.epi` loads; `02 Integrity PASS`, `03 Signature VALID`, `SEAL VALID · IDENTITY NOT PINNED`.
- Flip 1 byte: page top says “This file was changed after it was sealed” and “TAMPER SIMULATION ACTIVE”, but the detail lines remain `Integrity PASS`, `Signature VALID`, `SEAL VALID`. Contradictory (P1-1).
- 4.10.0 demo file loads on the preview verifier and shows `Signature VALID`.
- The “Release + pre-action demo” panel commands match the shipped files; CLI reproduction passes.

### C4 — content/claims/versions — PARTIAL

No prohibited claim found in the pages reviewed (no “tamper-proof”, no claim of completeness, “compliant” only in denial copy). Two version findings:

- `/reviewers` still says `pip install -U "epi-recorder>=4.9.0"` and “Needs 4.9.0 or newer” (P1-4 / to raise after PyPI publish).
- `website/assets/demo/naic-claim-override.html` embeds `spec_version: 4.9.0` (historical demo, P2-4).

### C5–C12 — account, Cloud, CLI, share, limits, sign-out — BLOCKED

Not run. They require the dedicated TEST Cloud account and human sign-in at `cloud.epilabs.org`. Per instructions, testing stopped here. No password or secret was requested or entered. C6–C12 (device-code login, Cloud push, hosted witness, share link, plan limits, sign-out/re-login, cleanup) remain untested.

### C13 — accessibility — FAIL, P1-5

axe-core WCAG 2 A/AA:

| Page | Light | Dark |
|---|---|---|
| `/` | 4 violations: aria-required-children (critical), 6 contrast, link-in-text-block | 3 violations |
| `/reviewers` | 1 violation: 7 link-in-text-block | 1 violation |
| `/verify/` | 2 violations: 19 contrast, nested-interactive | 1 violation |

Keyboard-only traversal and focus-trap checks were not completed.

### C14 — performance/SEO — PARTIAL

Titles, descriptions, canonical and Open Graph tags are present on `/`, `/verify/`, `/reviewers` and the blog post. `sitemap.xml` and `robots.txt` load. Lighthouse was not run. Firefox/WebKit were not run.

## Screens

- `screens/home-hero-desktop-light.png`
- `screens/home-hero-mobile-light.png`
- `screens/reviewers-badges-desktop-light.png`
- `screens/reviewers-badges-desktop-dark.png`
- `screens/reviewers-mobile-light.png`
- `screens/comparison-mobile-scrolled-light.png`
- `screens/verify-demo-desktop-light.png`
- `screens/blog-post-desktop.png`

---

## What was not run

- C5–C12 (Cloud account, device login, Cloud witness, share link, limits, sign-out/re-login) — blocked on human TEST account sign-in.
- B2 — blocked on a provider API key.
- A8 read-only HOME — not safely simulated.
- A10 — 164 docs commands not executed end-to-end.
- Lighthouse, Firefox, WebKit, full keyboard-only traversal.

## Cleanup

Test data lives only under `C:\epi-temp\opencode\prelaunch\`. No Cloud data was created. No product files were changed by this test. Cleanup of the temp directory is pending until the report is reviewed.

## Reproduction for P0-1

```bash
python -m venv /tmp/epi-490
/tmp/epi-490/bin/pip install epi-recorder==4.9.0
/tmp/epi-490/bin/epi verify decision-example.epi
# -> DECISION: FAIL, Signature: INVALID
```

The same file on the 4.10.0 verifier is `Signature: Valid`.

---

## Round 2 — fix round after the 4.10.0 NO-GO

**Date:** 9 November 2026  
**Fix branch:** `release/4.10.0-site`  
**Fix commits:** `d92f907f` (format/tests/UI), `57c9f417` (CI gate stdout parsing), `647ea069` (Windows ACL principal matching), `11915ce4` (TSA imprint compatibility), `28f792c6` (demo hashes/CI hygiene), `c03912a0` (single-open manifest member hydration)  
**Report branch:** `qa/4.10.0`  
**Test-only changes:** none; the product changes are on the release branch.

### Verdict

**P0-1 is fixed and proven.** A 4.10.0 file now verifies as `Signature VALID` on the 4.9.0 CLI and on the live 4.9.0 browser verifier (`https://epilabs.org/verify/`). The new permanent CI gate passes against the last PyPI release, including the last release's browser preimage.

**Launch is still blocked on the Cloud journey (`C5–C12`).** Those steps need the dedicated TEST Cloud account and a human sign-in at `cloud.epilabs.org`. No tag, PyPI upload, GitHub release, merge of PR #263, or `main` push was made.

### P0-1 — forward compatibility — PASS

**Root cause confirmed.** 4.9.0 parses `manifest.json` through its own `ManifestModel`, drops unknown top-level fields, and re-hashes. The new fields (`seal_chain`, `record_kind`, `release`, `release_ref`, `runtime_components`) and `case_id` were outside that model, so genuine files read as tampered.

**Fix (format, not verifier special-case):**

- New `epi_core/manifest_members.py`. The new data is written before the `file_manifest` walk as normal archive members and is therefore listed in `file_manifest`, covered by the Ed25519 signature and the witness content digest:
  - `artifacts/seal_chain.json`
  - `artifacts/case_id.json`
  - `artifacts/record_kind.json`
  - `artifacts/release_ref.json` (contains `release_ref` and `runtime_components`)
  - `release.json` (the release document, already a member)
- The manifest top level now contains only the 4.9.0 field set. `tests/compatibility/test_manifest_schema.py` freezes the 4.9.0 field list and asserts every field added since is member-backed.
- Seal-number allocation happens once per pack, before the walk, for the main record/release paths; the generic fallback writes the member after the first sign but still before the final signature, and always rewrites it when a re-sign changes the key.
- `read_manifest` rehydrates the member fields. `manifest_storage_json` writes the top level without them.
- From 4.10 the Python and JavaScript verifiers hash the manifest as stored and keep unknown fields (`ManifestModel(extra="allow")`; the browser preimage deletes only the member fields, never unknown ones).
- Tests:
  - `tests/test_forward_compat_manifest.py` — unknown extra field survives signing, packing, CLI verification, and hashing.
  - `tests/browser/test_forward_compat_manifest_browser.py` — the browser preimage computes the same hash as Python for a manifest with an unknown field.
  - `tests/compatibility/test_manifest_schema.py` — 4.9.0 field freeze and member classification.

**Re-sealed demo files.** All 4.10.0 demo/site `.epi` files were regenerated or re-sealed with the new format. The old 4.9.0/4.8.0 `docs/assets` samples were left untouched: they are historical and still verify.

**A5 re-run by hand:**

| Verifier | File | Result |
|---|---|---|
| 4.9.0 CLI (PyPI) | all 16 `website/assets/**/*.epi` | `signature_valid=True`, `integrity_ok=True` |
| Live `https://epilabs.org/verify/` (4.9.0 code) | `decision-example.epi` | `02 Integrity PASS`, `03 Signature VALID`, `SEAL VALID` |
| Live `https://epilabs.org/verify/` | `claims-policy-1.4.epi` | `02 Integrity PASS`, `03 Signature VALID`, `SEAL VALID` |
| Live `https://epilabs.org/verify/` | `sample.epi` | `02 Integrity PASS`, `03 Signature VALID`, `SEAL VALID` |

The 4.9.0 CLI exits 1 on these files only for the expected “local sealer not org-pinned” identity warning; the signature is valid.

**Permanent CI gate.** `.github/workflows/release-gate.yml` has a blocking `compatibility-gate` job; `release-gate` now `needs` it. The job installs the last released `epi-recorder` from PyPI, checks out its tag, seals plain/witness/release/pre-action files with HEAD, runs the last release's CLI on every file, and runs the last release's browser preimage (`website/js/`) in Node. On PR #263 at `c03912a0` the whole CI is green: `Last-release compatibility (blocking)` pass (52s), `Full test, build, and wheel audit` pass on Ubuntu (9m55s) and Windows (10m10s). Local run:

```
backward-compatibility gate: HEAD vs epi-recorder 4.9.0
sealed plain: plain.epi
sealed demo: claims-policy-1.4.epi, decision-example-approved.epi,
             decision-example-escalated.epi, decision-example.epi
PASS: 5 HEAD-sealed file(s) verify on epi-recorder 4.9.0
```

### Must-fix 1 — `/verify` tamper display — PASS

`website/js/home-verify.js` now carries an outer-display-layer failure into the report instead of returning before the six check rows are re-rendered. On a flipped byte it forces `integrity_ok=false`, `signature_valid=false`, trust `NONE`, and adds the display-layer mismatch. `processFile` also calls `resetChecks()` first, so a previous PASS/VALID can never linger.

Browser test `tests/browser/test_verify_tamper_rerender.py` loads the sample, flips 1 byte, asserts `02 Integrity FAIL` and `03 Signature INVALID`, restores, and asserts `02 PASS` and `03 VALID` again. Passed.

Screenshots: `screens/verify-tamper-fail.png`, `screens/verify-tamper-restored.png`.

### Must-fix 2 — killed seal / burns — PASS (earlier evidence explained)

The earlier A7 kill landed **before allocation**: the process was killed inside `with record():` before `__exit__`, so no seal number had been spent. A contiguous `#1..#51` audit was correct for that kill.

New test-only hook `EPI_TEST_CRASH_AFTER_SEAL_ALLOCATE=1` exits immediately after the pending reservation is persisted. `tests/test_seal_burn_crash.py` then proves:

1. the crashed process leaves reservation `#1` pending;
2. the next seal reaps it as a burn and allocates `#2`;
3. a heartbeat reports the burn;
4. `epi witness audit --json` reports `contiguous=false` and `#1` in `burned` or `missing` — never a clean `#1..#2` chain.

Passed.

### Must-fix 3 — Windows key permissions — PASS

- `epi_core.keys.secure_private_file` removes inheritance and grants only the current user with `icacls /inheritance:r /grant:r "<user>:(R,W)"` (no new dependency). It is called by `KeyManager.generate_keypair`, `import_hex_seed`, and the local SCITT service key writer.
- `key_acl_advice` checks existing key files. `epi doctor` now reports broad permissions and prints the exact `icacls` fix.
- `tests/test_key_acl.py` asserts a generated private key has no extra principals (Windows) and mode `0600` (POSIX).

Existing keys on this machine still have two inherited SIDs; `epi doctor` now reports them with the repair command. New keys are owner-only.

### Must-fix 4 — accessibility — PASS

Fixed in the changed sections:

- `.z-decision-tabs`: the three `role="tab"` buttons are now inside a `role="tablist"`; the Pause button is outside it (fixes `aria-required-children`).
- Drop zones: removed `role="button"` from the containers and added real `Choose a file` / `Choose a witness log` buttons (fixes `nested-interactive`).
- Light theme: darker green (`#047857`) and amber (`#b45309`) for text; body links underlined (fixes contrast and `link-in-text-block`).
- `/reviewers` content links are underlined (`site.css`).
- `/verify`: drop-zone headings are paragraphs instead of skipped `h3`s; the witness zone has a real button; a hidden `h2` gives the result cards a correct heading order.

Axe-core WCAG 2 A/AA (Chromium, Firefox, WebKit; light and dark; `/`, `/reviewers`, `/verify/`, `/decision-record`): **0 violations in every run.**

Lighthouse accessibility: `/` 100, `/reviewers` 100, `/verify/` 100, blog post 100. Remaining Lighthouse scores are recorded under C14 below.

### Must-fix 5 — `naic-claim-override.html` version — PASS

`website/assets/demo/naic-claim-override.epi` was re-sealed at 4.10.0 and `naic-claim-override.html` was regenerated with `epi export-summary`. The embedded `spec_version` and `producer_version` are now `4.10.0`; the artifact verifies on 4.9.0 and the live browser verifier.

### Must-fix 6 — A10 docs commands — COMPLETED WITH FINDINGS

All **164** `epi`/`pip`/`python scripts/` commands were extracted from `README.md`, `docs/*.md` and `blog/posts/*.md` and run in a fresh temp working directory with an isolated `EPI_HOME`. Result: **27 PASS, 46 SKIP, 91 FAIL** in a bare sandbox.

The 91 failures were reviewed one by one. They are not new product defects:

- 55 assume an input created by an earlier step or shipped example (`case.epi`, `received.jsonl`, `decision.epi`, `run.epi`, `sample.epi`, `policies/credit.yaml`, `examples/agt/...`).
- 9 use placeholders (`<fingerprint>`, `path/to/run.epi`, `my_agent.py`, `my_run.epi`).
- 14 look like syntax errors. 10 are `epi annex ...` and 2 are `epi enterprise ...`: **paid/closed-source commands**, explicitly labelled “Paid, and not in this repository” in `README.md` and `docs/CLI.md`. `docs/ANNEX-IV.md` does not repeat that label at the top; a reader can hit `No such command 'annex'`. **P2 doc fix.** One is a diagram fragment (`epi verify / browser viewer ←───────┘`), and one is a multi-line `epi oversight report` block whose backslash is followed by a comment line.
- 6 need Cloud credentials or a signed-in session.
- 2 need a key file that the example assumes.
- 5 are interactive or need cloud-provider credentials (`epi init`, `epi policy init`, `epi telemetry enable`, `epi approvers keygen`, AWS KMS).
- `epi cloud use` in `docs/CLI.md` shows no customer argument, but the CLI requires one. **P2 doc omission.**

One minor UX finding: `epi keys trust case.epi` on a missing file says `Public key 'case.epi' not found` rather than `File not found` (**P2**). No command that had its real inputs contradicted the documented syntax.

### Re-run of the remaining failed checks

| Check | Result |
|---|---|
| Full suite (`pytest -q`) | **2637 passed, 58 skipped** in 43:46 (`28f792c6`); rerun on final `c03912a0`: **2636 passed, 59 skipped** in 31:22 |
| A6 tamper suites | **72 passed** (byte flip, re-sign, chain break, forged approval, backdate, reuse, args-after-approval, before-approval, duplicate release) |
| A7 50 parallel seals | `50 seal report(s)`, `#1..#50 contiguous`, `clean` |
| A8 read-only HOME | seal succeeds, verify `WARN` local-sealer, no crash |
| A11 performance | wall-clock verify is +37%, but process startup alone is +0.43s; profile shows canonical-hash work 0.547s (4.10) vs 0.611s (4.9). **WARN, not a blocker.** |
| C13 accessibility | 0 axe violations in Chromium, Firefox and WebKit, light and dark |
| C14 Lighthouse (mobile) | `/` perf 45, a11y 100, BP 96, SEO 100; `/verify/` 84/100/96/100; `/reviewers` 79/100/96/100; blog 94/100/96/100 |
| C14 Firefox/WebKit | pages load and axe passes in both; no browser-only failures found |
| C5-C12 Cloud | **still blocked** on the TEST Cloud account and human sign-in |

**A11 detail.** 1,000-step run, three repetitions:

| Version | Seal (s) | Verify, wall clock (s) | Process startup (s) |
|---|---|---|---|
| 4.9.0 | 14.70 / 14.71 / 15.37 | 1.60 / 1.63 / 1.84 | 1.00 |
| 4.10.0 | 15.18 / 15.23 / 15.53 | 2.20 / 2.25 / 2.25 | 1.43 (first run 2.23) |

Seal is +2%. Verify wall clock is +37%, but the 1,000-step canonical-hash work is not slower (4.10 0.547s vs 4.9 0.611s). The extra time is the larger 4.10 CLI import/startup. A final change (`c03912a0`) reads all manifest members with one ZIP open; the 114 focused container/verify/TSA/manifest tests passed after it. **P2 performance note, not a launch blocker.**

Lighthouse performance on `/` is 45 (mobile). That is a pre-existing page-weight/animation cost, not an accessibility or correctness failure; the report records it rather than hiding it.

### What is still needed before launch

1. **Cloud C5–C12.** Sign in to the dedicated TEST Cloud account. The agent must pause for the human sign-in, then test device login, `epi cloud push`, the Cloud witness (especially whether it accepts the new 4.10 report types), share/trust links, plan limits, sign-out and re-login, and clean up the test data.
2. **`/reviewers` install floor.** The A5 re-run proves the sentence is true. At launch, change the floor to 4.10.0 with: “Files from 4.10.0 also verify with 4.9.0; the new checks need 4.10.0.”
3. **Human review of Round 2** before any tag, PyPI upload, GitHub release, merge or `main` push.

### Cleanup

All test artifacts remain under `C:\epi-temp\opencode\`. No Cloud data was created. No product state was published. The only repository changes are the fixes on `release/4.10.0-site` and this report on `qa/4.10.0`.

---

## Round 3 — Cloud QA and the false `MISSING #N`

Full Cloud run: `docs/qa/CLOUD-QA-4.10.0.md` (commit `052051fb`). Summary:

- C6 (device login, `epi cloud status`, 3 seals to the Cloud witness, `epi cloud push`): PASS.
- C8 (anonymous share link, open signed out, download, verify on 4.10.0 and 4.9.0): PASS.
- C7a/C7b (heartbeat and release reports to the Cloud witness): FAIL, HTTP 400.
- C7c (customer audit of what Cloud accepted): **P0**, `MISSING #4`, exit 1. The release took seal #4 but was reported only as `epi.release`, which Cloud rejected, so the customer log had a hole and the audit accused the vendor of hiding a record.
- P1: a reviewer verifying a shared file on its own saw `RELEASE NOT FOUND` and `UNKNOWN APPROVER`; both read as failures but mean "not supplied" and "not pinned".
- P2: `epi cloud login` printed no code without a TTY; workspace/customer names kept a leading space.

### Client fix in `bed20ba6` (this repo)

1. **Every release also sends a normal `epi.sealed` report.** `report_release` stages and delivers the seal first (with the release's `seal_seq`, `ledger_id`, `prev_seq` and `prev_content_digest`), then the `epi.release` detail as an extra. Old receivers and the current Cloud accept the seal, so the number is never a hole. If the receiver rejects the extra, the CLI says: "seal delivered; this receiver doesn't accept release detail yet (the seal number is reported)".
2. **No fork when both are accepted.** `epi_core.seal_ledger.analyze` ignores an `epi.release` entry when an `epi.sealed` entry for the same key/ledger/seq is already present. A release-only log from an older client is still counted as its seal, so old numbers stay covered.
3. **Heartbeat absence is not an alarm.** `epi witness audit` now prints "Tail-gap check not available on this receiver: no heartbeat reports in this log. The seal numbers above are still checked." JSON gets `heartbeat_check: not_available`.
4. **Capability line.** `epi witness status` and `epi cloud status` show "This witness accepts: seals ✓, heartbeats ✗, releases ✗, approvals ?", inferred from the outbox delivery history.
5. **P1 wording.** `Release: rel_… RELEASE DECLARED - NOT SUPPLIED` plus "not a failure … add --release-dir". `Pre-action: signed by DEMO APPROVER - APPROVER NOT PINNED` plus "signature is valid; pin the approver to count it: epi approvers add …".
6. **P2.** `epi cloud login` flushes the device code even when stdout is a pipe; workspace and customer labels are stripped before saving.

### Tests

- `tests/test_release_witness_compat.py`: a receiver that accepts only `epi.sealed` gets the release seal #1 and normal seals #2/#3; `analyze` is clean and contiguous. A second case proves the release extra does not fork #1 when both reports are accepted.
- `tests/test_verify_wording.py`: the missing-release and unpinned-approver lines contain the new wording and hints, not `RELEASE NOT FOUND`/`UNKNOWN APPROVER`.
- `tests/test_cloud_login_device.py`: a server label with leading spaces is trimmed on save.
- Focused suites: 136 passed (witness/release/verify/pre-action/cloud); demo/site/packaging: 51 passed.
- Full suite on `bed20ba6`: result recorded below after the run.

### Still needed for full C7

The Cloud service is a separate hosted codebase, **not this repository**. It still returns HTTP 400 for `epi.heartbeat`, `epi.release`, `epi.release_approval` and `epi.approval_*`. The client fix removes the false accusation and keeps every seal number; full release/heartbeat/approval detail in Cloud waits for that service to accept and store the extra types (fix plan item 2). If the private Cloud repo is added to this session, item 2 can be implemented there.

### Cleanup still to do in the Cloud dashboard

- Delete test runs `art_5f9be6d229ecca1795eb9df3` and `art_29152f4cee6d031d02df1375`.
- Disconnect this test computer's device key.
- The anonymous share `923c97a432af3c715cd8ffe9` expires on its own 2026-11-10.
