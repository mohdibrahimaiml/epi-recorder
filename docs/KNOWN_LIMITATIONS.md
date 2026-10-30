# Known Limitations

**Product version:** 4.7.0. Docs map: [README.md](./README.md).

This file tracks gaps between what the product can do and what a user might
reasonably expect. Each entry names the gap honestly, not as a bug report but as
a current boundary. No implied promises — just what's true right now.

## Plain summary (read this first)

EPI seals whatever was written into the file and proves nobody changed it
afterwards. It does **not** prove everything important was recorded, that the
signer is who they claim (until you pin their key), or that any regulation is
satisfied. A signed file from an unknown key is math, not trust. The viewer
inside the file paints its own verdict — verify with `epi verify`, never with
the in-file colours. Files from untrusted senders deserve HTML-attachment
caution; a data-only form exists when the clickable shell is unwanted
(`epi migrate case.epi --out case-data.epi --legacy-zip`, plus JSON/text
exports — see [FILE-SAFETY.md](./FILE-SAFETY.md) §7).
Timestamps prove "existed no later than T" only when a valid RFC 3161 token or
a customer witness backs them. Everything below is the engineering detail
behind those sentences.

## A human approval proves a pinned key signed it, not that the person saw the truth

**What you see:** `epi verify` says `Human approval: VERIFIED — alice@bank.com
… approved "refund REF-7"`.

**What is true:** that means a key **you** pinned as alice@bank.com signed an
approval of *this artifact's* decision, and that key is not the key that sealed
the run. It does **not** prove the person read the underlying data, that the
recorded run is truthful, that the key really belongs to Alice (pinning is a
human step done out of band), or that the approval is recognised on other hosts
(registries differ). An approval also cannot be forged without the approver's
private key, but anyone who can edit the file can append a **broken** review —
which turns the status to FAILED, deliberately fail-closed. It can block a run;
it can never create a `human_signed` record. See
[HUMAN-APPROVAL.md](./HUMAN-APPROVAL.md).

**Whether yours is affected:** any run where "a person approved this" is relied
on. Pin the approver's key yourself and read the fingerprint aloud; `--policy
strict` does not imply human approval — pass `--require-human-approval` too.

**Who can write `approval_source`.** It is a plain string in the step content.
The gateway demotes a client-supplied gateway label at its capture endpoints
(`/capture`, `/capture/batch`, `/capture/llm`, the proxy paths) to
`raw_api_unverified` and records it as `claimed_approval_source`, so only the
gateway's own approval route writes these labels there. But in an **SDK**
recording the agent writes its own steps, so it can write any label — including
`gateway_link_authenticated`. Treat `epi analyze`'s approval checks as
heuristics. The only cryptographic proof that a person approved something is
`epi verify --require-human-approval` with a signed approval from a pinned
approver key.

---

## The signature covers the canonical manifest, not its raw bytes (red-team F-07)

**What you see:** `epi verify` passes a `manifest.json` that contains a duplicate
JSON key.

**What is true:** the Ed25519 signature is computed over the RFC 8785 canonical
form of the manifest, not over its raw bytes. Duplicate keys and insignificant
whitespace therefore sit **outside** the signature. Python and the browser
canonicalizer both resolve duplicate keys last-wins, so they agree today — but a
consumer that resolves them first-wins could read a different `goal` or
`decision` than the verifier did.

**Whether yours is affected:** only files that were modified after sealing (the
signature would otherwise fail). It is a display-layer divergence risk, not a
signature bypass: the canonical form the verifier checked is the authoritative
one for EPI itself.

---

## A .epi can no longer expand without limit (red-team F-22)

**What you see (before):** `epi verify` expanded whatever the archive declared.
The red team measured **524,637,162 bytes written out of a 957,623-byte
artifact (547x)** — enough to exhaust the disk of any machine that opens an
untrusted file.

**What is true now:** the container reader enforces an expansion budget, checked
against the ZIP **central directory** so nothing is expanded to make the
decision — a per-member uncompressed cap, a total uncompressed cap, and a total
expansion-ratio cap (`epi_core/container.py::_check_expansion_budget`). The same
file is now refused before a single member is expanded.

**Residual:** the guard is a policy, not a format limit. Operators can raise it
with `EPI_MAX_EXPANDED_BYTES`, `EPI_MAX_MEMBER_BYTES` and
`EPI_MAX_EXPANSION_RATIO` (a value of `0` or an unparsable value falls back to
the default). The defaults are deliberately generous: legitimate artifacts are
text/JSON and compress well under 50x.

---

## The key-name derivation is not case-normalised (red-team F-09)

**What you see:** nothing — this is fail-closed.

**What is true:** the signing path (`epi_core/trust.py:85`) derives the key name
from the public key string exactly as stored in the manifest, while the
verification path (`trust.py:125`) and the browser (`crypto.js:652`) derive it
from the lowercased hex. They agree only while the manifest stores lowercase
hex. A manifest with an uppercase `public_key` is **rejected** (signature
invalid), so this is a latent inconsistency rather than an impersonation path.

---

## A file with no step hash chain is not claim-ready (red-team F-13)

**What you see:** `epi verify` reports `facts.chain_ok = true` and, under
`--policy strict`, "All strict criteria met (Integrity, Identity, Completeness)".

**What is true:** for an artifact whose steps carry **no `prev_hash` links at
all**, the chain check passes *vacuously* — there is nothing to compare, so
nothing fails. Such a file proves nothing about the recorded **order**: a
producer could reorder the timeline, drop a step, and re-sign, and the file
would still verify. `strict` is documented as the claim-ready policy, so
certifying that file was an overclaim.

**Fixed:** `facts.chain_present` now reports whether the steps carry any chain
links at all. `--policy strict` FAILs a chainless file; `standard` WARNs
instead of printing a clean PASS.

**Whether yours is affected:** any artifact sealed before the chain existed
(spec < 4.4.x) that never carried `prev_hash` links. Check
`facts.chain_present`. Every current release seals a chained timeline, and all
4.6.x sample artifacts in `docs/assets/` are chained.

---

## Seal timestamp does not bind the signing key in pre-change seals

**What you see:** `epi verify` reports a `valid` seal timestamp with
`contents existed no later than T` and `key_binding: "contents-only"`.
**What is true:** seals made before the fix stamped the file on its unsigned
first pack, so at stamping time `imprinted_public_key` is `None`. The timestamp
proves "these contents existed no later than T", not "this signing key sealed
them by time T". New seals stamp the signed repack, so `imprinted_public_key`
is the sealing key and verify reports `key_binding: "key-bound"` with the key
fingerprint. See `docs/VERIFICATION_CONTRACT.md` (timestamps section) and
`epi_core/notarize.py`.
**Whether yours is affected:** check
`artifacts/notarization/notarization.json`: `imprinted_public_key` null means
contents-only. Old files are not upgraded and keep verifying exactly as before
(no FAIL for this); re-seal to obtain a key-bound timestamp.

## Sealed `controls_failed` may understate failures (4.4.1–4.4.6; fixed forward in 4.4.7)

**What you see:** `policy_evaluation.json` reports e.g. `controls_failed: 1`.
**What is true:** counting the `results` array in the same file gives 2
failed. When auto-extracted policy rules were merged alongside already-failing
baseline heuristics at pack time, the baseline failure count was reset instead
of preserved (`epi_core/container.py`, introduced in `e298bc97`, first shipped
in 4.4.1; 4.4.2 was withdrawn and pre-4.4.1 has no auto-extract path).

**Whether yours is affected:** open `policy_evaluation.json`. If
`policy_source` is `"auto_extracted"` (or `results` include
`auto_policy_check` entries), count the entries with `"status": "failed"`
and compare to the `controls_failed` header — if the header is lower, yours
undercounts. Pure-baseline files and pre-4.4.1 seals are unaffected.

**Can it be corrected? No — by design.** Fixing the number would change
sealed bytes and break the file's own signature. The artifact stays valid
and verifiable; only this header field understates. A format where a wrong
number in an old artifact *could* be quietly fixed would be a worse format.

Standing rule, beyond this bug: recount from `results`, never from the
header. A derived count is always weaker evidence than the thing it was
derived from. New seals from 4.4.7 report the true total.

## `epi_signature_valid` in the AGT helper now runs a real check (fixed)

`build_agt_log_data()` used to set `"epi_signature_valid":
bool(manifest.signature)` (presence only). It now calls
`verify_embedded_manifest_signature`. Independent of that helper, auditors
should still run `epi verify` on the artifact. The old presence-only
behaviour remains a reading risk on anything that consumed the helper
before this fix.

## Fixed in 4.7.x (unreleased batch)

- **Tool-call decisions dropped by the SDK wrappers** - `wrappers/openai.py` and `wrappers/anthropic.py` copied only `role` and `content` off each response. A model that decided by calling a tool - which is how most agents act - was sealed as `content: null`, with the tool name and its arguments missing. Both now seal every `tool_calls` / `tool_use` block (id, name, arguments), the flat decision at the top of the step (`tool_calls` / `tool_uses`, with `arguments_parsed` when the payload is JSON), the served model (`served_model`), the provider request id (`response_id`), `system_fingerprint`, `created`/`stop_reason`, and the request settings that shaped the answer (`temperature`, `top_p`, `max_tokens`, `top_k`, `seed`, `tool_choice`, and the names/descriptions of the tools offered). `log_llm_call()` had the same defect and is fixed with it. Streaming was already partly covered and now records the same identity fields.
- **No structured decision step** - `agent.decision()` now takes `basis=` for the data the decision relied on, next to `decision` (outcome), `rationale` (reason) and `output` (structured result).

**Still a limit:** the wrapper records the model's *request* to call a tool. Whether the tool actually ran, and what it returned, is in the file only if the agent logs it (`agent.tool_call` / `agent.tool_result`, or a framework integration). The effect is still shown - a tool call with no recorded result is an incomplete-evidence finding under `--policy strict`.

## Fixed in 4.4.6 (2026-09-10 batch)

The following were gaps and are now fixed — kept here for audit trail:

- **Streaming pre_commit** — `openai.py`/`anthropic.py` streaming now emits `llm.pre_commit` with canonical `sha256(messages+model)` and TSA binding; `delta.tool_calls/reasoning` captured (was `delta.content` only)
- **Vacuous pre_hash** — `sha256(model+len+time)` replaced with `sha256(canonical_json(messages)+model)`
- **Trust ranking** — `UNSIGNED` now `LOW` not above `signed-unknown`; `32B/64B` sig/pubkey length enforced
- **Envelope trailing bytes & header transplant** — `extract_inner_payload` fails on extra bytes; `verify_integrity` cross-checks `header uuid/timestamp`
- **Viewer 4MiB cap** — outer viewer hash scans full gap, not `4MiB`
- **payload_hash stale** — recomputed after `viewer.html/VERIFY.txt/notarization`
- **Guardrails truncation** — `epi_guardrails/session.py [:2000]` removed, full content sealed
- **Gateway defaults** — `epi gateway serve` (and direct uvicorn runs) default to `retention_mode full_content` and `proxy_failure_mode fail-closed`: full prompts and responses are stored. Pass `--retention-mode redacted_hashes` to keep hashes only. Streaming returns `501` either way
- **SCITT fallback** — missing service key now `transparency_ok=None` not `PASS`
- **Billing** — unknown `price_id` now `ValueError` (empty keeps `hosted` compat)
- **Packaging** — `cryptography<51 typer<0.28 rich<16`, `setup.py` gateways, `docker 3.12`, `spec 4.4.3->4.4.5`, `.well-known` mirrors synced, demos re-sealed

---

## Pre-execution commitment (llm.pre_commit)

**Streaming calls on the legacy patcher path still skip pre-commit.**
`wrappers/openai.py` and `wrappers/anthropic.py` have emitted a streaming
`pre_commit` since 4.4.6; `patcher.py`'s legacy path still falls back to the
old behavior with no pre-commit entry and no warning. Do not assume every
streaming call has a commitment step.

---

## Hosted infrastructure (what runs where)

EPI Cloud runs on Cloudflare (Workers + D1 + R2 + Durable Objects); limits and
capacity math live in [CLOUD.md](./CLOUD.md). The old Render **login** is
retired — sign-in for the website and the CLI goes through EPI Cloud.

What still lives on Render (legacy hosted paths — not the account system, not
required to record or verify): the default `epi share` upload, MCP HTTP
hosting, opt-in telemetry/pilot signup URLs, the keep-warm cron, and some
`/api/*` Cloudflare proxies. Offline CLI verify works regardless of any
hosted service.

---

## Plans and billing (no self-serve checkout)

Cloud is **private beta**. Entitlements, in customers: Free 1 customer;
Startup 3 customers / 1,000 stored files (1-year retention); Growth 15 / 10,000
(7-year). Verification is never limited or charged, and Cloud checkout is not
self-serve on the public site — the old hosted-verification subscriptions are
not for sale. (The legacy `free` / `hosted` / `team` / `enterprise`
hosted-check counters still exist in `verify_portal/tier_gating.py` for the
retired self-serve path; do not quote them as current pricing.) Plan changes go
through the Cloud founder admin page and are audit-logged. Product rules:
[CLOUD.md](./CLOUD.md).

---

## verification_class auto-population

**How it works:** `verification_class` (`recomputable` vs `attested_only`) is
computed in one place — `compute_verification_class()` in
`epi_core/schemas.py:15` — and applied two ways: the `StepModel`
`mode="before"` validator fills it on every construction from a dict
(`schemas.py:346-348`), and `epi_recorder/patcher.py` computes it explicitly
at step creation (belt and braces, with a local fallback that never returns
a silent `None`).

**What to know:** non-empty unknown step kinds default to `attested_only`,
never `None` (empty/missing `kind` yields `None` — a gap, not a silent
default). And `recomputable` requires the recorder to set
`epi_deterministic=True` on tool-like steps — i.e. the value is
self-attested. A sealed file from a 4.6.2 recorder carries the field on every
step (spot-check any `steps.jsonl`); pre-4.4.3 files may lack it. Treat the
field as the recorder's claim about re-executability, not a proof of it.

---

## Browser verification honesty

- **Authoritative verify** remains `epi verify` (CLI).
- Browser private check (`/verify/` mode device, home drop zone) uses Web Crypto
  Ed25519 when the browser supports it (Chrome/Edge). When it cannot, UI must
  show **pending / not verified** — never a green PASS for an unverified signature.
- Identity trust (KNOWN/HIGH) still requires CLI key pin / trust bundle; browser
  only proves signature-over-manifest when crypto works.

---

## Polyglot embedded viewer (display layer)

`.epi` envelope-v2 files are polyglots: a 128-byte header, outer viewer HTML
(for double-click in a browser), then a ZIP payload. The **ZIP payload** (steps,
manifest, `viewer.html` inside the archive) is sealed via `payload_sha256` and
`file_manifest` + Ed25519.

**Default is data-only.** `record()`, `epi demo`, `epi run` and `epi record`
seal a plain `legacy-zip` with **no** `viewer.html` member and no outer HTML, so
there is no display layer to forge; `epi view` regenerates the viewer locally.
Everything below applies to artifacts sealed with `--with-viewer`, or to
legacy/migrated envelope-v2 files that still embed a viewer.

**New artifacts** bind the outer viewer to the **signed**
`file_manifest["viewer.html"]` hash. Mutating CSS/JS/labels in the outer HTML
region fails `epi verify` (integrity mismatch on `__polyglot_viewer__`). The
envelope's `reserved_tail[0:32]` copy is unsigned; it only catches naive
corruption.

Through 4.6.1 the **in-file viewer** could still paint INTEGRITY VERIFIED after
an envelope failure (the live inner-ZIP check overwrote the baked verdict).
**4.6.2** made the viewer fail-closed (#141/#143): a baked envelope failure
cannot be upgraded to green. **4.6.3** made `epi verify` check the signed
`viewer.html` hash, so a consistent display-layer forgery now fails the CLI
too. Trust `epi verify`, not the colours.

**The header copy alone was not enough — and the docs said otherwise.** The
`reserved_tail[0:32]` value is unsigned and self-referential: it lives in the
same untrusted header as the bytes it describes, so an attacker who edits the
display layer can recompute it and the file looks self-consistent. Through
4.6.2, `epi verify` reported **PASS** for such a file, including under
`--policy strict`. The 4.6.2 release note claimed this was fixed; it was not.
`THREAT_MODEL.md` R1 and the `VERIFY.txt` shipped inside every artifact were
premature for 4.6.2.

**Fixed in 4.6.3:** the outer polyglot region is byte-identical to the sealed
`viewer.html` member, whose SHA-256 lives in the **signed** `file_manifest`.
`epi verify` now checks the outer region against that signed value, so a
display-layer edit fails even when the header copy is recomputed.

**Legacy envelope-v2 artifacts** whose signed `file_manifest` includes
`viewer.html` are covered by the same check, even when their
`reserved_tail[0:32]` is all-zero, so their outer display layer is **not
forgeable**. Artifacts whose manifest predates the `viewer.html` entry have no
signed binding for the display layer; the verifier says so rather than
claiming coverage. The earlier blanket claim that *all* legacy artifacts left
the display HTML unsealed is too broad in one direction and too narrow in the
other — the manifest entry is what decides.

**The viewer never paints a verdict it cannot support.** The double-click
polyglot page carries a pack-time *copy* of the manifest — taken before the
archive's `manifest.json` was re-signed, so it is a different, stale
pre-image — and the whole page is editable by whoever holds the file. A check
against that copy is self-consistent by construction. The viewer therefore
requires the **shipped** manifest bytes (from the archive) before it will
report a verdict, and otherwise shows a neutral **"INTEGRITY NOT VERIFIED
HERE"** instead of green. `epi view` injects a context built from the CLI's
own verification and still shows green for an intact file.

ZIP-internal `viewer.html` was already in `file_manifest`; the gap was only the
**outer** polyglot region used when a human double-clicks the file.

---

## Seats, SSO, hosted PDF

Not shipped. Pricing and tier gates must not claim them. Seats/SSO are consulting
or future product; PDF is CLI-only.

---

## Site mirrors

Production static source is **`website/`**. `scripts/sync_website.py` copies into
`site/`, `verify_portal/static/`, and `epi-official/`. `site/` is build output.
Stale mirrors after editing `website/` are a known ops hazard until sync runs.
See [WEBSITE.md](./WEBSITE.md).

---

## PyPI

Current release line: **4.8.0**, published on PyPI: **4.8.0**. It went up through
**Trusted Publishing** (28 Oct 2026), so both files carry **PEP 740 attestations**
— check with `https://pypi.org/integrity/epi-recorder/4.7.0/<file>/provenance`
(HTTP 200). The **4.6.3** wheel has **no PEP 740 attestations** because it was
uploaded with the project API token; its provenance endpoint returns HTTP 404. It
added signed display-layer verification, the viewer fail-closed fix (#141/#143),
and the pack-time viewer / prohibition-guard fix (#145). The published
**4.6.2** wheel does **not** include the 4.6.3 verifier fixes. **4.4.1** remains
on PyPI (not yanked) and still truncates sealed strings at 2000 characters.
**4.4.2** never reached PyPI. **4.4.3+** seals full payloads
(`content_truncated=false`; verify FAILs when `true`, WARNs when absent).

---

## Canonicalization migration (4.4.1)

**Pre-4.4.1 artifacts used `json.dumps(sort_keys=True)`; 4.4.1+ uses RFC 8785 (JCS).** JCS differs on number formatting (`1.0` → `1`) and ensures cross-implementation agreement with TRACE (`agentrust-trace` `rfc8785`). Old artifacts would fail if re-hashed with JCS.

**Verifier dispatches by `manifest.spec_version`:** `<4.4.1` → legacy json sort_keys, `>=4.4.1` → JCS, `1.x` → CBOR. No trial — one path per artifact. Legacy path emits `Verified via legacy canonicalization (spec_version=X <4.4.1)` warning. New artifacts must be sealed with `rfc8785>=0.1.4` (hard dep — broken install raises, never silently diverges). Notarization payload (RFC 3161) also uses JCS for new artifacts; old timestamps remain over old bytes.

---

## Byte-level seal scope (summary; full sweep in appendix)

A 1 KB byte-flip sweep of a 4.4.0 artifact (405 offsets + 26 member edges
+ 2 file edges = 433) found every modified byte detected by `epi verify`
— except 28 unsealed envelope-header bytes (offsets 0–3, 16–39; see next
section), which are redundant copies whose authoritative values live in
the signed manifest. The outer viewer HTML is sealed via the signed
`file_manifest` entry, so a consistent forgery that also recomputes the
unsigned header copy still fails. Full per-region table, the red-team
caveat, and the offset-658 evidence: [BYTE-SWEEP-APPENDIX.md](./BYTE-SWEEP-APPENDIX.md).

## Unsealed envelope header bytes (0–3, 16–39)

The 128-byte envelope-v2 header is **not** signed. `payload_sha256` (bytes 40–71) covers the ZIP payload only. The Ed25519 signature covers canonical `manifest.json` (minus `signature`). XOR of these 28 header bytes still yields `epi verify` PASS.

| Bytes | Field | What it is | Authoritative sealed copy |
|-------|--------|------------|---------------------------|
| 0–3 | magic `<!--` | Polyglot HTML-comment opener | None. Cosmetic for “opens in a browser.” Tampering can still locate the ZIP via `EPI_ZIP_PAYLOAD_START` / EOCD. |
| 16–31 | `artifact_uuid` | 16 raw bytes copied from `manifest.workflow_id` at pack | **`manifest.json` `workflow_id`** (also `manifest.trust.artifact_uuid`). Signed + hashed. There is no top-level `artifact_uuid` key in the manifest schema. |
| 32–39 | `created_at_micros` | `int(manifest.created_at.timestamp() * 1e6)` at pack | **`manifest.json` `created_at`**. Signed + hashed. The RFC 3161 TSA token binds the seal imprint (`epi-tsa-imprint/v1`: workflow id, `created_at`, sealing key, payload file hashes — see `docs/VERIFICATION_CONTRACT.md`), not these header bytes. |

On a clean artifact the header copies **match** the manifest (`workflow_id` / `created_at`). Changing the header does **not** change what `epi verify`, the forensic viewer title/created line, `epi export trace` (`subject` from `workflow_id`; `iat` is wall-clock at export, not either timestamp), or SCITT (`manifest_hash` of the signed manifest) report. Those readers use the ZIP manifest (or `time.time()` for TRACE `iat`).

The header UUID/timestamp are therefore **redundant, unsealed copies**. They are not a silent evidence-time or identity rewrite for current CLI/viewer/TRACE/SCITT paths. Do not treat envelope bytes 16–39 as the source of truth.

RFC 3161 is implemented (`artifacts/notarization/`). `epi verify` validates seal-time and checkpoint tokens offline against pinned TSA roots (imprint, CMS signature, critical timeStamping EKU, chain) — see `docs/VERIFICATION_CONTRACT.md`. The browser viewer still reports presence only and never validates. The independent time claim is the TSA token over the seal imprint, not `created_at_micros`.

---

## TRACE `policy.bundle_hash` is not a Cedar hash

TRACE specifies `policy.bundle_hash` as the SHA-256 of the Cedar policy bundle that governed the session. EPI does not ship or evaluate Cedar. `epi export trace` hashes sealed `policy.json` (fallback `policy_evaluation.json`) and sets `policy.enforcement_mode` to `"declared"`. That is an honest binding to authored policy bytes, not a claim that a Cedar engine ran. Reviewers should not treat the field as a Cedar digest.

`appraisal.status` is always `"none"` on export — we have not issued a TRACE verifier judgment.

---

## Capture completeness vs seal integrity

The seal proves that a `.epi` file was not altered **after** it was sealed. It does not prove that every LLM call, tool call, or subprocess was recorded. In-process `record()` is self-attestation. Prefer the gateway proxy (fail-closed) when that distinction matters.

The gateway complements `record()` — it does not prove artifact completeness:

- It only witnesses **LLM traffic routed through the proxy** (`/v1/chat/completions`, `/v1/messages`). Tool calls, approvals, and decisions are still recorded in-process and are exactly what the completeness check audits.
- **Streaming requests are rejected with 501**, so streaming apps either fail or bypass the proxy entirely.
- Capture is **async-enqueued**: fail-closed covers enqueue-time failure, but a worker crash after acceptance still leaves a gap.

## RFC 3161 timestamps are validated by `epi verify` (fixed in 4.6.0)

Until 4.6.0 the sealed artifact recorded a timestamp token and its `genTime`, but **the verifier did not validate the token's CMS signature, certificate chain, or that its `messageImprint` matches the sealed bytes**. Since 4.6.0 `epi verify` validates all three offline against pinned roots, and a failing new-scheme token FAILs verification. Pre-4.6 tokens report `legacy` (presence only, never a failure).

Remaining timestamp limitations (all still true):

- **No revocation checks.** Validation is fully offline: a compromised TSA key or a revoked TSA certificate is not detected. The check assumes the TSA's private key was not compromised and its clock was honest.
- **Legacy tokens attest nothing checkable.** Files sealed before 4.6 keep their previous verdict; the token is an unverified corroborating field.
- **The browser viewer does not validate.** It reports presence only and names `epi verify` as the only validation place.

## Historical step-content truncation (through 4.4.1)

Through **4.4.1** (last PyPI release before 4.4.3), `RecordingContext.add_step` shortened strings in sealed `steps.jsonl` at **2000 characters** (`[...truncated: N chars total]`). **Every `.epi` sealed with that recorder may be missing the tail of long prompts and responses.** Those files are not complete transcripts.

**4.4.2** sealed full payloads and added `manifest.content_truncated`, then was **withdrawn** (GitHub Release and tag removed) before PyPI: the new field’s JSON `null` broke Ed25519 for artifacts sealed before 4.4.1.

**4.4.3** is the first PyPI release that seals full step payloads, truncates only in the viewer, sets `content_truncated=false` on new seals, **FAIL**s verify if the flag is `true`, and **WARN**s when the field is absent (everything shipped through 4.4.1).

---

## Release rule: strict mode for deliverables

Release deliverables (claims, insurer/bank/audit handoff, release gates) must use:

```bash
epi verify run.epi --policy strict --witness-log received.jsonl
# add --require-timestamp only if the vendor seals with a reachable timestamp service
```

`--policy strict` FAILs unknown/unpinned sealers, unsigned artifacts, integrity
failure, truncated payloads, and incomplete evidence (e.g. a `tool.call` with
no `tool.response`). Scripts must rely on the exit code with
`--policy strict`: WARN exits `0`. `standard` WARNs on unknown sealers by design
(valid seal · not org pin) — never claim-ready. The `--policy` help text and
`docs/VERIFICATION_CONTRACT.md` list every verdict; the browser verifier never
ranks above the CLI for the same bytes.

Recording gaps that survive this rule (no silent completeness claim):

- SDK `record()` is self-attestation; gateway witnesses LLM proxy traffic only.
- Gateway streaming → 501 (streaming apps bypass or fail); async-enqueue worker
  crash after acceptance leaves a gap fail-closed cannot cover.
- Legacy artifacts: pre-4.4.3 truncation (WARN), `controls_failed` undercount
  4.4.1–4.4.6 (recount `results`), all-zero viewer-hash polyglots **without** a
  signed `viewer.html` manifest entry (display layer not integrity-covered;
  with the entry, 4.6.3 verifies it), unsealed header bytes 0–3/16–39 (redundant
  copies; manifest is authority), SCITT presence-only, pre-4.6 TSA tokens
  legacy/presence-only.

---

## Customer witness limits

With `EPI_WITNESS_URL` (or `witness_url=`) configured, every seal is reported
at seal time to endpoint(s) the customer controls (`docs/WITNESS.md`). The
witness only proves **what was sent**: the vendor can choose not to send a
seal, and a seal covers only what was recorded. A missing witness entry for
a case the customer knows happened is itself evidence — ask the vendor why.
The payload is hashes and counts only (no content); the goal is included
only with `witness_include_goal=True`.

---

## Last updated

2026-10-22 — red-team F-01/F-02: display layer bound to the signed `file_manifest`; viewer no longer paints a verdict it cannot support. Red-team F-13: `--policy strict` FAILs a file with no step hash chain.
2026-10-11 — customer witness on every seal (`epi-witness/v1`, outbox + `epi witness flush/status`, `epi verify --witness-log`).
2026-10-10 — RFC 3161 offline validation in `epi verify` (4.6.0): imprint, CMS signature, critical timeStamping EKU, chain to pinned roots; legacy tokens presence-only; no revocation checks; viewer still presence-only.

2026-09-14 — RFC 3161 display honesty (viewer + CLI neutral, no green tick); timestamp + gateway completeness documented as unverified.

2026-08-29 — unsealed header 0–3/16–39 documented; header vs sealed manifest authority; Level 0 TRACE; offset-658 both 4.4.0/4.4.1 FAIL

2026-08-01 — residual fix-before-PyPI: hosted plan key, dual-mode verify,
browser Ed25519 honesty, contact route de-dup, product-first home, release hold.
