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
