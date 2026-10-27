# Prompt for the coding agent: Step 3, real human sign-off

> Paste everything below the line into the coding agent. It is self-contained.

---

You are working in the `epi-recorder` repository (Python 3.11+, package `epi-recorder`, CLI `epi`). EPI seals AI-agent runs into signed `.epi` files that anyone can verify offline. This task is **step 3 of the bank-readiness plan** in `internal/BANK-READINESS-EXECUTION-PLAN.md`. Read that file and `internal/BANK-READINESS-ASSESSMENT.md` first.

## Goal (one sentence)

A `.epi` file must be able to prove **"a specific, known person approved this exact decision"** with a signature from **that person's own key**, and EPI must **never** present an approval as human-signed when it is only the agent's (or the gateway's) own claim.

## Why: the gaps today (verify each one yourself before changing anything)

1. **Review signatures trust whatever key they carry.** `epi_core/review.py::_verify_review_signature` reads the public key from inside the signature string (`ed25519:<pubhex>:<sighex>`) and checks the signature against that same key. The code itself says "Review pub is self-asserted, not registry-bound". Any key, including the agent's, produces `signature_valid: True`.
2. **Reviews are signed with the agent's key by default.** `epi_cli/review.py` (`review` and `bind`) uses `--key default`, the same key that sealed the run. A "signed review" therefore proves nothing about a human.
3. **The gateway approval link can be forged and fires on its own.** `epi_gateway/main.py`, route `@app.api_route("/api/approve/{workflow_id}/{approval_id}", methods=["GET", "POST"])` (~line 1616):
   - it is exempt from auth (`is_approval_path`, ~line 1124);
   - a plain **GET** records the decision, so email security scanners (Outlook Safe Links, Mimecast and others) that pre-open links can approve automatically;
   - `reviewer` comes from the query string, so anyone can claim to be anyone;
   - `approval_id` falls back to the action name (`_dispatch_approval_request_notifications`, ~line 450), so it's guessable;
   - there is no expiry and no single-use token.
4. **In-run approvals are agent claims shown as facts.** `agent.approval.response` steps and `record(approved_by=...)` are written by the agent process. The browser verifier (`website/js/home-verify.js` ~lines 477, 746–766: "`<reviewer> approved`") and `epi_cli/verify.py` show them as if a person approved.

## Scope: deliver as 3 separate PRs, in this order

### PR 3a: approver registry, signed approvals, verification (the core)

**A. Approver registry (who counts as a human approver).**
- New module `epi_core/approvers.py` and CLI group `epi approvers`:
  - `epi approvers add <pubkey-file|hex> --name <id, e.g. alice@bank.com> --role approver --fingerprint "<fp read aloud by the approver>"`. Refuse unless the fingerprint matches, the same rule `epi keys trust` uses for files.
  - `epi approvers list`, `epi approvers remove --name`.
- Store as JSON, one file per approver: `{name, public_key (hex), roles, added_at}`. Location: `EPI_TRUSTED_APPROVERS_DIR`, else `~/.epi/trusted_approvers/`. Mirror how `TrustRegistry` in `epi_core/trust.py` resolves `EPI_TRUSTED_KEYS_DIR`.
- **Keep it separate from the trusted *signer* keys.** Pinning a vendor's sealing key must never make that key an approver.
- Fingerprints: use `epi_core.keys.key_fingerprint` only. **Do not** reuse `epi_cli/role_bindings.py::_pubkey_fingerprint`, which hashes raw bytes, not the hex text, and so gives different fingerprints.

**B. Approver keys (held by the person, not the agent host).**
- `epi approvers keygen --name alice@bank.com` creates the key in a **separate** directory (`EPI_APPROVER_KEYS_DIR`, else `~/.epi/approver_keys/`), never the agent keys dir. Require encryption at rest: `EPI_KEY_PASSWORD`, or an interactive password prompt.
- `epi approvers link --name ... --uri pkcs11:...|awskms:...|gcpkms:...` for keys in an HSM or security token. Reuse step 2: `KeyManager(keys_dir=<approver dir>).link_external_key(...)` and `epi_core/signers.py`. Don't build a second signer system.
- Print the fingerprint so the approver can read it to the verifier's admin.

**C. Signed approval statement (stored in the existing review ledger).**
- Extend `ReviewRecord` (`epi_core/review.py`) with `review_version = "1.2.0"` and a new optional `approval` block:
  ```json
  {"approval": {"decision": "approve|deny", "approval_id": "...", "action": "...",
                "reason": "...", "approver": {"name": "...", "key_fingerprint": "..."}}}
  ```
- It must stay inside the existing hash, signature and append-only chain (`artifact_binding`, `previous_review_hash`, `review_hash`). Canonical JSON rules apply: no floats (see `_assert_canonical_json_value`).
- 1.0.0 and 1.1.0 reviews must keep verifying exactly as today (there are tests for this: `tests/test_review.py` and `tests/test_review_trust_protocol.py`).
- New command `epi review approve <file.epi> --approval-id <id> --decision approve|deny --as <approver-name> [--reason ...]`:
  1. Run full `epi verify` on the file first, and refuse if integrity or signature fails.
  2. **Show the person what they are signing** before signing: the task/goal, the agent's decision, the matching `agent.approval.request` step, the manifest hash and the sealing key fingerprint. Then require typed confirmation. A `--yes` flag is allowed for scripted tests only and must print a warning.
  3. Refuse if the approver key's public key equals the file's sealing key (`manifest.public_key`). Separation of duties: the agent cannot approve itself.
  4. Refuse if `--approval-id` is not present as an `agent.approval.request` in the sealed steps. Add `--case-level` for approving the whole run when there is no request step.
- Adding an approval must not change the sealed evidence. The original seal must still verify byte-for-byte; reviews are additive today, so keep it that way and test it.

**D. Verification: classify every approval honestly.**
- In `verify_review_trust` (or a new `verify_human_approvals` it calls), classify each review/approval as one of:
  - `human_signed`: the signature is valid, the key is pinned in the approver registry, the key is NOT the sealing key, the record is bound to this artifact, and the chain is intact;
  - `signed_by_sealing_key`: signed by the same key that sealed the run. Say plainly: "not independent of the agent";
  - `signed_unknown_key`: valid signature, but the key isn't a pinned approver;
  - `unsigned`;
  - `invalid`.
- Add a top-level verify report field: `"human_approval": {"status": "verified" | "none" | "unverified" | "failed", "approvals": [...]}`. `verified` only when at least one `human_signed` approval exists.
- `epi verify` human output: one plain line, for example:
  - `Human approval: VERIFIED — alice@bank.com (fp 3f78 7c9e …) approved "refund REF-7" on 2026-…`
  - `Human approval: NONE — this run only contains approvals reported by the agent itself`
- New flag `epi verify --require-human-approval`: exit non-zero unless the status is `verified` and the latest decision is `approve`. `--policy strict` should imply it **only if** that matches the existing strict-policy design. Check `epi_cli/verify.py` and decide; explain the decision in the PR.
- Everywhere `agent.approval.response` or `approved_by` is printed by the CLI, label it **"reported by the agent (not signed by a person)"**.

**E. Backward compatibility of `epi review` / `epi review bind`.**
- Keep them working (don't break users). Their signatures now verify as `signed_by_sealing_key` or `signed_unknown_key`, never as `human_signed`. Print a one-line hint pointing to `epi review approve --as`.

### PR 3b: harden the gateway approval link

In `epi_gateway/main.py`:
- **GET never records anything.** It shows a confirmation page (action, workflow, reason) with Approve/Deny buttons that **POST**.
- Every approval link carries a random, single-use token (≥128 bits, `secrets.token_urlsafe`), stored server-side (hashed) with an expiry (default 72h, setting `EPI_APPROVAL_LINK_TTL_HOURS`). Reject a missing, wrong, expired or reused token with 403, and don't leak which of these it was.
- `approval_id` must be a generated id, never the action name.
- `reviewer` is never taken from the query string. When gateway auth is on, use the authenticated principal. Otherwise record `"reviewer": "approval-link (identity not verified)"`.
- Mark the recorded event content `"approval_source": "gateway_link_unsigned"`. Verify and viewers must show it as a **link click, not a signed human approval**. The human-signed path stays `epi review approve` (PR 3a).
- Escape all values interpolated into the HTML response; `action`/`reason` are currently inserted raw. Add a test with `<script>` in `action`.
- Update `tests/test_gateway_approval_flow.py` and add tests for:
  - a GET does not record;
  - a POST with a valid token records once;
  - replay → 403;
  - expired → 403;
  - token for another workflow → 403;
  - `?reviewer=ceo` is ignored.
- Update the approval email and webhook payload (`epi_gateway/approval_notify.py`, `_dispatch_approval_request_notifications`) for the new link.

### PR 3c: browser verifier labels

In `website/js/home-verify.js` (and anything else that renders steps; `grep -rn "approval" website/ epi_viewer_static/ web_viewer/`):
- In-run approvals display as "**Agent-reported**: <reviewer> approved …", never as a bare "<reviewer> approved".
- A `1.2.0` signed approval displays "Signed approval, key fingerprint XXXX. Pin approvers with `epi approvers add` and run `epi verify` to confirm who." The browser has no approver registry, so it must never say "verified human approval".
- Extend the existing Playwright tests (`tests/test_verify_drop.py`, the `dashboard-browser` workflow) with: a file whose only approval is agent-reported, and a file with a 1.2.0 signed approval.

## Out of scope (don't build; mention as follow-ups in the PR)

- **Passkeys (WebAuthn).** WebAuthn assertions are usually ES256 (P-256) over `authenticatorData || SHA-256(clientDataJSON)`, not Ed25519 over our hash. Supporting them changes what verifiers must accept, so it needs its own design note first.
- SSO/OIDC identity for approvers.
- Changing the `.epi` manifest signature format.

## Hard rules

- **Never** classify anything as `human_signed` unless the key is in the approver registry and differs from the sealing key. Write a test that tries every shortcut: the agent's own key, an unpinned key, a pinned *signer* key (not an approver), a tampered approval, an approval bound to a different file, an approval reordered in the chain.
- Old `.epi` files (with and without reviews) must verify with the **same result as before**. Run the whole suite to prove it.
- Don't skip, disable or weaken any existing test. If an existing test asserted the old self-asserted-key behaviour, change it only when the old behaviour is the bug, and say so in the PR.
- No float values in signed JSON.
- Match the surrounding code style. Keep comments as sparse as the files around them.

## How to test (run all of these before each push)

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e ".[test,pkcs11]" pytest-xdist
python -m pytest tests/test_review.py tests/test_review_trust_protocol.py tests/test_gateway_approval_flow.py tests/test_external_signers.py -q -o addopts=""
python -m pytest tests -m "not browser and not experimental" -q -o addopts=""   # the release gate's own selection
ruff check <every file you changed>
```

Known pre-existing failures to ignore (check that they also fail on `main`): `tests/test_v271_features.py::TestReliabilityFixes::test_flag_unwritable_doesnt_crash` when running as root. Don't run with `-n` (xdist): `tests/test_api_integration.py` is a script that collides with itself under parallel workers.

**End-to-end check by hand (paste the output into the PR):**
1. `epi keys generate` (agent key). Record a run that includes an `agent.approval.request` step with `approval_id: "refund-7"`.
2. `epi verify run.epi` → `Human approval: NONE`.
3. `epi approvers keygen --name alice@bank.com`, then `epi approvers add <alice.pub> --name alice@bank.com --fingerprint "<fp>"`.
4. `epi review approve run.epi --approval-id refund-7 --decision approve --as alice@bank.com` → `epi verify run.epi --require-human-approval` exits 0 with `Human approval: VERIFIED — alice@bank.com …`.
5. Try `epi review approve ... --as` with the **agent's** key → refused. Try the old `epi review` with `--key default` → verify shows `signed_by_sealing_key`, and `--require-human-approval` exits non-zero.
6. `epi approvers remove --name alice@bank.com` → verify now shows `signed_unknown_key`, not VERIFIED.
7. Change one byte in a sealed step → integrity FAIL, and no approval is reported as verified.
8. PR 3b: run the gateway, open the approval link with `curl` (GET) and confirm nothing was recorded. POST with the token → recorded once. POST again → 403.

## Docs (in PR 3a, updated by 3b/3c)

- New `docs/HUMAN-APPROVAL.md`: what a human-signed approval proves and doesn't, the approver onboarding steps (keygen → read the fingerprint aloud → `approvers add`), and how a bank enforces `--require-human-approval`.
- Update `docs/VERIFICATION_CONTRACT.md` (the new `human_approval` field and its states), `docs/KNOWN_LIMITATIONS.md`, `docs/CLI.md`, `docs/THREAT_MODEL.md` (agent self-approval and gateway link forgery: now mitigated), `CHANGELOG.md` under `[Unreleased]`, and the step-3 row in `internal/BANK-READINESS-EXECUTION-PLAN.md`.

## Definition of done

- Three PRs (3a, 3b, 3c), each with green CI, each description listing what changed, the hand-run output, and anything deliberately left out.
- `epi verify --require-human-approval` passes **only** for a run approved with a pinned approver key that is not the sealing key, and fails for every shortcut listed under Hard rules.
- The gateway approval link can't be triggered by a GET, a guessed id, a reused or expired token, or a forged reviewer name.
- No screen anywhere says a person approved something unless it was human-signed (CLI), or says "agent-reported" or "signed, key XXXX, pin to confirm" (browser).
