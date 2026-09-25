# Known Limitations

This file tracks gaps between what the product can do and what a user might
reasonably expect. Each entry names the gap honestly, not as a bug report but as
a current boundary. No implied promises — just what's true right now.

## Sealed `controls_failed` may undercount (fixed after 4.4.6)

**Artifacts sealed through 4.4.6 can report `policy_evaluation.json`
`controls_failed` lower than the failed entries in `results`.** When
auto-extracted policy rules were merged alongside baseline heuristics at
pack time, the baseline failure count was reset instead of preserved
(`container.py`). The `results` array itself was always complete — recount
failed controls from `results`, not the header field. Fixed for new seals;
old seals verify byte-identical as before (their bytes are unchanged, the
field included).

## Fixed in 4.4.6 (2026-09-10 batch)

The following were gaps and are now fixed — kept here for audit trail:

- **Streaming pre_commit** — `openai.py`/`anthropic.py` streaming now emits `llm.pre_commit` with canonical `sha256(messages+model)` and TSA binding; `delta.tool_calls/reasoning` captured (was `delta.content` only)
- **Vacuous pre_hash** — `sha256(model+len+time)` replaced with `sha256(canonical_json(messages)+model)`
- **Trust ranking** — `UNSIGNED` now `LOW` not above `signed-unknown`; `32B/64B` sig/pubkey length enforced
- **Envelope trailing bytes & header transplant** — `extract_inner_payload` fails on extra bytes; `verify_integrity` cross-checks `header uuid/timestamp`
- **Viewer 4MiB cap** — outer viewer hash scans full gap, not `4MiB`
- **payload_hash stale** — recomputed after `viewer.html/VERIFY.txt/notarization`
- **Guardrails truncation** — `epi_guardrails/session.py [:2000]` removed, full content sealed
- **Gateway defaults** — `epi gateway serve` defaults to `retention_mode redacted_hashes` and `proxy_failure_mode fail-open` (direct-uvicorn runs default to `full_content`/`fail-closed` instead). Pass the flags explicitly when you need full capture + fail-closed; streaming `501` either way
- **SCITT fallback** — missing service key now `transparency_ok=None` not `PASS`
- **Billing** — unknown `price_id` now `ValueError` (empty keeps `hosted` compat)
- **Packaging** — `cryptography<51 typer<0.28 rich<16`, `setup.py` gateways, `docker 3.12`, `spec 4.4.3->4.4.5`, `.well-known` mirrors synced, demos re-sealed

---

## Pre-execution commitment (llm.pre_commit)

**Streaming calls skip pre-commit entirely.** Both `openai.py` and `anthropic.py`
generate `llm.pre_commit` entries for non-streaming API calls, but streaming
paths (`stream=True`) silently fall back to the old behavior with no pre-commit
entry. No error, no warning — the chain just doesn't include the commitment step.

This affects anyone using streaming responses. The pricing page now notes
"(non-streaming calls)" next to this feature. **Fixed in 4.4.6 for wrappers — see above; `patcher.py` legacy path still has gap.**

---

## Hosted infrastructure

**Render free tier.** The verify API, SCITT service, and account system all run
on a single Render free-tier instance (`render.yaml: plan: free`). This means:

- 750 hours/month limit (~31 days)
- Sleeps after 15 minutes of inactivity
- Cold starts cause 2-5 second delays on first request
- No horizontal scaling
- No SLA, no uptime guarantee

The status page (`/status`) discloses this and the pricing page says "shared
infrastructure, cold starts happen." Offline CLI verify works regardless.

---

## verification_class auto-population

**The model_validator doesn't fire during recording.** Steps are serialized as
raw dicts in `packer.py`, bypassing Pydantic's `model_validator`. The
classification is computed inline via `_compute_verification_class()` in
`packer.py`. If a new step kind is added without updating that function, it gets
`None` instead of a classification.

---

## Hosted billing (Paddle) vs operator set-plan

**Self-serve Subscribe is only live when Paddle env vars are configured** on the
hosted API (client token, price IDs, webhook secret, etc.). If those are empty,
pricing CTAs should fall back to sign-in / contact — not a working checkout.

**Pilot / invoice path (works without Paddle):** user signs in once at
`/account`, then EPI Labs promotes the plan with the admin **set-plan** endpoint
(see [OPERATOR-RUNBOOK.md](./OPERATOR-RUNBOOK.md) — operators only).

Public tiers after `normalize_plan` (must match `verify_portal/tier_gating.py`
and `website/pricing.html`):

| Plan key | Public label | Hosted checks/mo | Remote SCITT | API keys |
|----------|--------------|------------------|--------------|----------|
| `free` | Open Source | 100 | no | 1 |
| `hosted` | Hosted (~$15) | 10,000 | yes | 10 |
| `team` | Team (design partners) | 50,000 | yes | 50 |
| `enterprise` | Enterprise | custom | yes | unlimited |

Aliases `pro` and `starter` normalize to **`hosted`**. Offline CLI verify is
unlimited free. Hosted PDF API is **not** implemented (HTTP 501); use CLI Annex PDF.

There is **no automated sync** between the Paddle dashboard and Render env vars —
ops must keep them aligned when self-serve is enabled.

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

**New artifacts** also store `SHA-256(outer_viewer_html_bytes)` in
`reserved_tail[0:32]` of the envelope header. Mutating CSS/JS/labels in the
outer HTML region fails `epi verify` (integrity mismatch on `__polyglot_viewer__`).

**Legacy artifacts** (viewer hash all-zero) still open and can PASS seal checks
while the outer display HTML is forgeable. For those files: **trust `epi verify`,
not the colors or verdict chrome of the double-click UI.** Documented in
`VERIFY.txt` inside each new pack.

ZIP-internal `viewer.html` was already in `file_manifest`; the gap was only the
**outer** polyglot region used when a human double-clicks the file.

---

## Seats, SSO, hosted PDF

Not shipped. Pricing and tier gates must not claim them. Seats/SSO are consulting
or future product; PDF is CLI-only.

---

## Site mirrors

Production static source is **`website/`**. `scripts/sync_website.py` copies into
`site/`, `verify_portal/static/`, and `epi-official/`. `website-v2/` is a sandbox
and is **not** the deploy source. Stale mirrors after editing `website/` are a
known ops hazard until sync runs.

---

## PyPI

Current published line: **4.4.5**. **4.4.1** remains on PyPI (not yanked) and still truncates sealed strings at 2000 characters. **4.4.2** never reached PyPI.

---

## Canonicalization migration (4.4.1)

**Pre-4.4.1 artifacts used `json.dumps(sort_keys=True)`; 4.4.1+ uses RFC 8785 (JCS).** JCS differs on number formatting (`1.0` → `1`) and ensures cross-implementation agreement with TRACE (`agentrust-trace` `rfc8785`). Old artifacts would fail if re-hashed with JCS.

**Verifier dispatches by `manifest.spec_version`:** `<4.4.1` → legacy json sort_keys, `>=4.4.1` → JCS, `1.x` → CBOR. No trial — one path per artifact. Legacy path emits `Verified via legacy canonicalization (spec_version=X <4.4.1)` warning. New artifacts must be sealed with `rfc8785>=0.1.4` (hard dep — broken install raises, never silently diverges). Notarization payload (RFC 3161) also uses JCS for new artifacts; old timestamps remain over old bytes.

---

## Byte-level seal scope (from 1KB sweep, 4.4.0 demo-banking-aml.epi, 405612 B)

**Task:** flip one byte at every 1 KB, plus first/last byte of every ZIP member and file, then `epi verify`. Offset 658 is the example from the report.

**Map for `verify_portal/static/assets/demo/demo-banking-aml.epi` (marker at 305552, payload at 305584, 12 ZIP members):**

| Outer offset | Region (from `ZipInfo.header_offset` + `compress_size`) | In `file_manifest`? | In `payload_sha256`? | In `__polyglot_viewer__` (reserved_tail[0:32])? | `epi verify` after flip |
|---|---|---|---|---|---|
| `0` | Envelope header byte 0 (`<` of `<!--`) | — | — | — | **PASS** (not detected — header magic not strictly hashed) |
| `10` | Envelope header | — | — | — | **FAIL** (`payload_sha256` or header length) |
| `128` | HTML prelude start (outer viewer) | No | No | **Yes** | **FAIL** (`__polyglot_viewer__` mismatch) |
| `658` | **HTML prelude** (outer viewer, `viewer.html` not inner) | No | No | **Yes** | **FAIL** `integrity False {__polyglot_viewer__: expected 0c1f..., got 6c8a...}` `signature_valid True` `decision FAIL` |
| `305542` | HTML prelude near marker | No | No | Yes | **FAIL** |
| `305552` | Marker `<!-- EPI_ZIP_PAYLOAD_START -->` | No | No | No | **FAIL** (marker not hashed, but payload length changes) |
| `305584` | ZIP local header for `mimetype` | No (mimetype excluded) | **Yes** (full ZIP hash) | No | **FAIL** |
| `305622` | ZIP data `mimetype` | No | Yes | No | **FAIL** |
| `310040` | ZIP data `steps.jsonl` start | **Yes** (`steps.jsonl` in `file_manifest`) | Yes | No | **FAIL** (both) |
| `405611` | File last byte (EOCD) | — | Yes | No | **FAIL** |
| `405512` | ZIP central directory | — | Yes | No | **FAIL** |

**Summary from full 1 KB sweep (405 offsets + 26 member edges + 2 file edges = 433):**

* **HTML prelude [128, 305552)** — 298 KB of outer viewer HTML **is sealed** via `reserved_tail[0:32]` (`__polyglot_viewer__`). Flipping any byte there → `integrity False` `__polyglot_viewer__` mismatch, not `file_manifest` or `step chain`. This is the display layer, not the evidence, but it is tamper-evident since 4.4.1 (legacy all-zero tail was not).
* **ZIP payload [305584, 405612)** — all 12 members' headers, compressed data, central directory, and EOCD are sealed via `payload_sha256` (envelope) **and** for 10/12 members via `file_manifest` SHA256 (all except `mimetype` and `manifest.json`/`viewer.html` inside ZIP? Actually `viewer.html` **is** in `file_manifest` with `0c1f...`, `steps.jsonl` with `8abe...`, etc.). Flipping any byte there → `FAIL` (either `payload_sha256` or `file_manifest` mismatch, plus `step chain` for `steps.jsonl`).
* **Envelope header [0,128)** — exhaustive 2026-08-29 XOR of every byte, then `epi verify` (4.4.1): **undetected** offsets **0–3** (magic), **16–31** (artifact UUID), **32–39** (`created_at_micros`). Detected: 4–15 (version/format/flags/length), 40–71 (`payload_sha256`), 72–103 (viewer hash), 104–127 (padding must be zero). These PASS bytes are not `spec_version` (that field is not in the 128-byte header).

**Classification for offset 658:** **Inside sealed scope** (`__polyglot_viewer__`), **correctly detected** (`FAIL` with `integrity False`, `signature_valid True`), **not a verifier bug**. Documented here as display-layer seal, not evidence-layer. If the HTML were outside scope it would be a limitation, but it is inside when `reserved_tail[0:32]` is non-zero. Artifacts with an all-zero viewer hash still skip this check (legacy warning).

**Offset 658 PASS vs FAIL contradiction:** Isolated re-run (2026-08-29) of the same `docs/assets/demo-banking-aml.epi` XOR at byte 658: **PyPI 4.4.0 and local 4.4.1 both FAIL** via `__polyglot_viewer__` (`verifier_version` 4.4.0 vs 4.4.1). Official `epi-recorder==4.4.0` wheel already contains `verify_polyglot_viewer`. 4.4.1 did not close a 4.4.0 detection hole for this offset. An earlier `rc=0 PASS` is not a version split; likely a sweep that only hashed ZIP/`file_manifest` (HTML prelude at 658 is outside those hashes) or `python -m epi_cli` from the repo cwd importing 4.4.1 sources while `pip show` said 4.4.0. The 433-offset sweep that reported FAIL used a verifier with `__polyglot_viewer__` (present in both 4.4.0 PyPI and 4.4.1).

**Evidence for offset 658 flip (literal `epi verify --json`):**
```
manifest spec_version 4.4.0
integrity False {'__polyglot_viewer__': 'polyglot viewer HTML hash mismatch: expected 0c1f41d1ef6281e7…, got 6c8a8cb340e25c1d… (display layer may have been tampered)'}
signature_valid True
decision FAIL Integrity compromised
```

---

## Unsealed envelope header bytes (0–3, 16–39)

The 128-byte envelope-v2 header is **not** signed. `payload_sha256` (bytes 40–71) covers the ZIP payload only. The Ed25519 signature covers canonical `manifest.json` (minus `signature`). XOR of these 28 header bytes still yields `epi verify` PASS.

| Bytes | Field | What it is | Authoritative sealed copy |
|-------|--------|------------|---------------------------|
| 0–3 | magic `<!--` | Polyglot HTML-comment opener | None. Cosmetic for “opens in a browser.” Tampering can still locate the ZIP via `EPI_ZIP_PAYLOAD_START` / EOCD. |
| 16–31 | `artifact_uuid` | 16 raw bytes copied from `manifest.workflow_id` at pack | **`manifest.json` `workflow_id`** (also `manifest.trust.artifact_uuid`). Signed + hashed. There is no top-level `artifact_uuid` key in the manifest schema. |
| 32–39 | `created_at_micros` | `int(manifest.created_at.timestamp() * 1e6)` at pack | **`manifest.json` `created_at`**. Signed + hashed. RFC 3161 TSA token is over the canonical **unsigned manifest** (includes `created_at` and `workflow_id`), not these header bytes. |

On a clean artifact the header copies **match** the manifest (`workflow_id` / `created_at`). Changing the header does **not** change what `epi verify`, the forensic viewer title/created line, `epi export trace` (`subject` from `workflow_id`; `iat` is wall-clock at export, not either timestamp), or SCITT (`manifest_hash` of the signed manifest) report. Those readers use the ZIP manifest (or `time.time()` for TRACE `iat`).

The header UUID/timestamp are therefore **redundant, unsealed copies**. They are not a silent evidence-time or identity rewrite for current CLI/viewer/TRACE/SCITT paths. Do not treat envelope bytes 16–39 as the source of truth.

RFC 3161 is implemented (`artifacts/notarization/`) but the viewer and CLI report TSA **presence** (host / token present, `genTime` read) — never validity. The token's CMS signature, chain, and `messageImprint` are not validated. The independent time claim is the TSA token over the sealed manifest hash, not `created_at_micros`.

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

## RFC 3161 timestamps are presence-only (no token validation yet)

The sealed artifact records a timestamp token (`artifacts/notarization/tsa_reply.tsr`) and its `genTime`, but **the verifier does not currently validate the token's CMS signature, certificate chain, or that its `messageImprint` matches the manifest hash**. The viewer and `epi verify` report "RFC 3161 token present (genTime read, signature not validated)" in neutral styling — never a green tick. Treat the timestamp as an unverified corroborating field until validation lands (planned: CMS signature check, chain to a trust anchor **embedded at seal time**, critical `id-kp-timeStamping` EKU, imprint match, genTime within signing-cert validity — offline by construction, no fetch).

## Historical step-content truncation (through 4.4.1)

Through **4.4.1** (last PyPI release before 4.4.3), `RecordingContext.add_step` shortened strings in sealed `steps.jsonl` at **2000 characters** (`[...truncated: N chars total]`). **Every `.epi` sealed with that recorder may be missing the tail of long prompts and responses.** Those files are not complete transcripts.

**4.4.2** sealed full payloads and added `manifest.content_truncated`, then was **withdrawn** (GitHub Release and tag removed) before PyPI: the new field’s JSON `null` broke Ed25519 for artifacts sealed before 4.4.1.

**4.4.3** is the first PyPI release that seals full step payloads, truncates only in the viewer, sets `content_truncated=false` on new seals, **FAIL**s verify if the flag is `true`, and **WARN**s when the field is absent (everything shipped through 4.4.1).

---

## Last updated

2026-09-14 — RFC 3161 display honesty (viewer + CLI neutral, no green tick); timestamp + gateway completeness documented as unverified.

2026-08-29 — unsealed header 0–3/16–39 documented; header vs sealed manifest authority; Level 0 TRACE; offset-658 both 4.4.0/4.4.1 FAIL

2026-08-01 — residual fix-before-PyPI: hosted plan key, dual-mode verify,
browser Ed25519 honesty, contact route de-dup, product-first home, release hold.
