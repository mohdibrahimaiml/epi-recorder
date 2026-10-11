# EPI remaining-work plan (for the coding agent)

Owner: Mohd Ibrahim Afridi. Written 2026-10-11 against `main` at `a3b54e1` (after PRs #80–#86 merged).

This continues `plans/EVIDENCE-HARDENING-PLAN.md`. Read that file's **section 0, "Ground rules"**, first. All of it
still applies: one branch and one PR per work package, honesty rules, no paid services, keep old `.epi` files
verifiable, update `CHANGELOG.md` under `Unreleased`.

Already done and merged (do not redo): WP0 (#80), WP1a timestamps (#81), WP1a-2 async checkpoints (#82),
WP1b witness (#83), WP3 gateway export chain (#84), WP1c did:web (#85), WP4 core/experimental split (#86).

---

## 0. Before you start (read this once)

### 0.1 How merging works in this repo

- `main` is protected. A PR can only merge when it is **up to date with `main`** and its required checks are
  green ("Full test, build, and wheel audit" on ubuntu and windows).
- So do the work packages **one at a time, in the order below**. Open the next branch only after the previous PR
  has merged, starting from the new `main`. Otherwise every PR conflicts in `CHANGELOG.md` and `epi_cli/verify.py`.
- Never force-push to `main`. Never rewrite another PR's history. Use merge commits.

### 0.2 Checks to run before every push

```bash
python -m pytest tests/test_version_consistency_runtime.py tests/test_truth_consistency.py -q
python -m pytest tests -m "not browser and not experimental" -q --maxfail=20
```

Known environment quirk: `tests/test_v271_features.py::TestReliabilityFixes::test_flag_unwritable_doesnt_crash`
fails when tests run as **root** (a read-only file is still writable for root). It passes in CI. Do not "fix" it
by skipping it; just know why it fails locally if you run as root.

### 0.3 Order

| # | Work package | Branch | Size |
|---|---|---|---|
| 1 | WP-R0: small follow-ups from the review | `fix/review-followups` | half a day |
| 2 | WP2.1: any-language docs | `docs/any-language` | 2–3 hours |
| 3 | WP2.2: gateway streaming (issue #31) | `feat/gateway-streaming` | 3–4 days |
| 4 | WP2.3: OTLP/HTTP trace receiver | `feat/gateway-otlp` | 3 days |
| 5 | WP1d: Sigstore Rekor spike (time-boxed) | `spike/rekor` | 1 day max |
| 6 | WP5: launch drafts (nothing is posted) | `docs/launch-assets` | half a day |

---

## WP-R0. Small follow-ups from the review

Four small fixes found while reviewing the merged work. Do them in one PR.

### R0.1 `--tsa-root` is ignored for checkpoint timestamps

**Problem.** `epi verify --tsa-root PATH` adds trusted TSA roots for the **seal** timestamp only. These two
call sites still use only the pinned roots plus the `EPI_TSA_TRUST_ROOTS` env var:
- SDK checkpoints: `epi_core/checkpoints.py`, `verify_checkpoints()` (around line 318), which calls
  `validate_tsr(_token, _expected)` around line 387.
- Gateway capture checkpoints: `epi_core/case_store.py`, `verify_capture_checkpoints()` (around line 2543), which calls
  `validate_tsr(token, expected)` around line 2651.

So anyone using their own TSA sees checkpoints as "untrusted" even after passing `--tsa-root`.

**Fix.**
1. Add an optional keyword `trust_roots=None` to both `verify_checkpoints()` and `verify_capture_checkpoints()`,
   and pass it through to `validate_tsr(..., trust_roots=trust_roots)`.
   Keep the default `None` so existing callers behave the same.
2. In `epi_cli/verify.py`, the seal path already builds a list called `trust_roots` (around lines 85–88: pinned
   roots plus `--tsa-root` certificates). Move that construction into a small helper,
   `_tsa_trust_roots(tsa_root_paths)`, call it once in `verify_command`, and pass the same list to both checkpoint
   verifiers (call sites around line 1364 and in the capture-checkpoint step).
3. **Test** in `tests/test_tsa_validation.py`: a checkpoint token signed by the test-only TSA (the `MiniPKI`
   helper already in that file) is `untrusted` without `--tsa-root` and `valid` with it.
   Add the same test for a gateway export in `tests/test_gateway_export_chain.py`.

### R0.2 Checkpoint "UNVERIFIED" messages print as [FAIL]

In `epi_cli/verify.py`, the SDK checkpoint block prints every message in `_cp_messages` with a red `[FAIL]`
label, even when `ok` is true and the message is the warning `CHECKPOINT TIMESTAMP UNVERIFIED ...`.
The gateway block already handles this correctly: it prints `[WARN]` for messages starting with
`CAPTURE TIMESTAMP UNVERIFIED`. Apply the same rule to the SDK block.

Add a test asserting the human output shows `[WARN]`, not `[FAIL]`, for an untrusted-root checkpoint.

### R0.3 Say plainly what the seal timestamp proves

In the normal `record()` flow, the file is first packed unsigned and signed on the second pack. So at stamping time
`imprinted_public_key` is `None`. The seal timestamp therefore proves **"these contents existed no later than
time T"**, not **"this signing key sealed them by time T"**.

Document this, without changing code:
- `docs/VERIFICATION_CONTRACT.md`, in the timestamps section: one paragraph explaining what the imprint covers and
  that the signing key is covered only when `imprinted_public_key` is non-null.
- `docs/KNOWN_LIMITATIONS.md`: a new entry, "Seal timestamp does not bind the signing key in the default
  `record()` flow".
- `epi_cli/verify.py`: when a seal timestamp is `valid` and `imprinted_public_key` is null, the statement line
  must read "contents existed no later than T" (check the current wording and correct it if it implies more).

### R0.4 Tell customers to require a timestamp

`docs/WITNESS.md` already says to verify with `--require-timestamp`. `docs/IDENTITY-ONBOARDING.md` does not.
Add one short "Recommended verify command for customers" section to `IDENTITY-ONBOARDING.md`:

```bash
epi verify run.epi --require-timestamp --witness-log received.jsonl
```

Explain in two sentences: without `--require-timestamp`, a file with no timestamp still passes, so a vendor
could remove the timestamp; with it, such a file FAILs.

**Acceptance for WP-R0:** all new tests pass; the full core suite passes; `CHANGELOG.md` has a "Fixed" entry.

---

## WP2.1. Any-language docs

**Why.** The README and plan describe EPI as "Python only". That is not true: the gateway already accepts any
language. The docs just never show how.

**What already exists in `epi_gateway/main.py` (do not change code here):**
- `POST /capture` and `POST /capture/batch`: generic events in the `CaptureEventModel` shape
  (`epi_core/capture.py`, line 76). Required: `kind`. Useful optional fields: `content`, `meta`, `case_id`,
  `workflow_id`, `workflow_name`, `trace_id`, `decision_id`, `actor_id`, `provider`, `model`.
- `POST /capture/llm`: a request/response pair, normalized by `epi_core/llm_capture.py`.
- `POST /v1/chat/completions`: OpenAI-compatible proxy, non-streaming until WP2.2.
- `POST /v1/messages`: Anthropic-compatible proxy, non-streaming until WP2.2.
- `POST /api/cases/{case_id}/export`: export a case to a sealed `.epi`.
- Start it with `epi gateway serve` (default port **8787**, see `epi_cli/gateway.py` line 20).
  Read `epi gateway serve --help` for the auth and retention flags, and note the defaults
  (`retention_mode redacted_hashes`, `proxy_failure_mode fail-open`) in the doc.

**Write `docs/ANY-LANGUAGE.md`** with these sections, each a short runnable snippet:

1. **Start the gateway**: the one command, plus how to point it at a real provider (`OPENAI_API_KEY`, or the
   upstream URL env vars defined at the top of `epi_gateway/proxy.py`).
2. **TypeScript, OpenAI SDK**: `new OpenAI({ baseURL: "http://localhost:8787/v1" })` with a `stream: false` call.
3. **TypeScript, Anthropic SDK**: `new Anthropic({ baseURL: "http://localhost:8787" })`.
4. **Any language, raw HTTP**: a `curl` POST to `/capture` with a tool-call event and a decision event that share
   a `case_id`. Use real field names from `CaptureEventModel`.
5. **Get the evidence file**: `curl -X POST http://localhost:8787/api/cases/<case_id>/export`, then
   `epi verify <file>.epi`.
6. **Limits**:
   - streaming (until WP2.2);
   - the gateway records only what passes through it;
   - auth is required when bound to a non-loopback host (see `require_auth_for_host`).

**Smoke test** (`tests/test_any_language_docs.py`):
- Start the app with FastAPI's `TestClient`.
- Parse the JSON bodies **out of the markdown file**: put them in fenced blocks with a marker comment, and read
  them with a small regex.
- POST each one, export the case, and run verify on the result.

This makes the docs fail CI if the API changes.

**Also:** in `README.md`, add an "Any language" row to the integrations table that links to the new doc.
Remove or soften any "Python only" wording. Grep for it in `README.md`, `website/`, `docs/` (not
`docs/archive/`) and `plans/`.

**Acceptance:** the smoke test passes; every snippet in the doc is copy-paste correct.

---

## WP2.2. Gateway streaming (closes issue #31)

**Why.** `stream: true` returns **501** today (`epi_gateway/main.py` around lines 1374 and 1441). Streamed calls
must therefore use the SDK wrapper, which has no fail-closed enforcement. Most production agents stream, so this
is the biggest gap on the gateway path.

**Read first:** issue #31; `epi_gateway/proxy.py` (all of it); `_enqueue_llm_capture` in `epi_gateway/main.py`
(around line 882); `epi_core/manifest.py` lines 30–40 (the declared known gap) and 180–240 (how `streaming` is
tagged).

### Design

1. **Async upstream client.** Today `relay_json_request` uses blocking `urllib` inside `async def` routes, which
   stalls the server's event loop for every concurrent request.
   - Add `relay_stream(url, payload, headers, timeout)` to `epi_gateway/proxy.py`. Use `httpx.AsyncClient`
     (`httpx` is already a dependency) with `client.stream("POST", ...)`.
   - It yields raw byte chunks and exposes the upstream status code and headers before the first chunk.
   - Leave the non-streaming path alone in this PR. Converting it to async is optional: do it only if it falls
     out naturally, with its own tests.
2. **Assemblers** (new file `epi_gateway/stream_assembly.py`, pure functions, no I/O):
   - `OpenAIStreamAssembler.feed(chunk: bytes)`:
     - split server-sent events on blank lines and read `data:` lines;
     - stop at `data: [DONE]`;
     - accumulate `choices[i].delta.content`;
     - merge `choices[i].delta.tool_calls` by `index`, concatenating `function.arguments` strings and keeping the
       first non-empty `id`, `type` and `function.name`;
     - keep `finish_reason`, `model`, `id`, `system_fingerprint`, and `usage` (sent in the last chunk when
       `stream_options.include_usage` is true).
     - `.result()` returns a dict shaped like a normal non-streaming chat completion, so
       `build_openai_proxy_capture_request(response_payload=...)` works unchanged.
   - `AnthropicStreamAssembler.feed(chunk)`:
     - handle event types `message_start` (take `message`), `content_block_start`, `content_block_delta` (text from
       `text_delta`, tool input from `input_json_delta.partial_json`), `content_block_stop` (parse the joined tool
       JSON; if it fails, keep the raw string and set `"input_parse_error": true`), `message_delta` (stop_reason,
       usage) and `message_stop`;
     - ignore `ping`;
     - record `error` events as an error payload.
     - `.result()` returns a normal Messages API response shape.
   - Both must handle chunks that split a line or an event mid-way: buffer until a full event arrives.
3. **Routes.** In both proxy routes, replace the 501 branch with a streaming branch:
   - Resolve the failure mode and run the **same readiness check as today, before** opening the upstream stream.
     If fail-closed and the worker is not ready, return the existing 503-style `_capture_failure_response`.
   - Open the upstream stream. If upstream returns a non-2xx status before streaming starts, read the body, build
     the error capture (as the non-streaming error branch does) and return that status and body. This is not a
     streamed response.
   - Otherwise return a `StreamingResponse` with the upstream `content-type` (`text/event-stream`). The generator:
     - yields each upstream chunk **unchanged and immediately** (no re-encoding);
     - feeds each chunk to the assembler;
     - in a `finally:` block (so it also runs on client disconnect or upstream error), builds the capture request
       from `assembler.result()` and calls `_enqueue_llm_capture(..., streaming=True)`.
     - If the client disconnected or upstream broke mid-stream, add `"stream_incomplete": true` and the reason to
       the capture meta.
     - A capture failure at this point can no longer change the HTTP response. In fail-closed mode, log it at
       ERROR and record a runtime gap so the case shows it.
   - Response headers: keep the existing capture-status header the non-streaming path sets (check
     `_build_proxy_response` for its name). Since the status is only known at the end, send
     `capture_status="streaming"` up front.
4. **Known gaps.** Remove the "gateway returns 501 for streaming" entry from `epi_core/manifest.py` (around line 37),
   and add the honest replacement: *"streamed calls: a capture failure after the stream has started cannot block
   the response; it is recorded as a gap."*
   Update `docs/KNOWN_LIMITATIONS.md` and `tests/test_known_limitations_current.py` to match.

### Tests (`tests/test_gateway_streaming.py`)

- Use a fake upstream: a small ASGI app, or `httpx.MockTransport` injected through an optional `transport=`
  parameter on `relay_stream`.
- Record realistic SSE fixtures for both providers in `tests/fixtures/streams/`, including:
  - plain text;
  - two parallel tool calls whose `arguments` are split across 5+ chunks;
  - an Anthropic `input_json_delta` split mid-token;
  - a final usage chunk;
  - chunk boundaries that cut a `data:` line in half.
- Assert that the client receives **byte-identical** output to the fixture.
- Assert that the captured case contains the full text, the parsed tool arguments, usage, and `streaming: true`
  in `_epi_capture`.
- Fail-closed with an unready worker returns 503 before any upstream call (assert the fake upstream was never hit).
- An upstream 4xx before the stream returns the same status and is captured as an error.
- Client disconnect midway still produces a capture with `stream_incomplete: true`.
- Update every existing test that asserts the 501 (`tests/test_v271_features.py`, `tests/test_pro_capabilities.py`,
  `tests/test_ls_view.py`; grep `501` in `tests/` and check each one) to the new behaviour. Do not delete them.

**Docs:** remove the streaming limitation from `docs/ANY-LANGUAGE.md` and add a streaming TypeScript snippet.

**Acceptance:** all of the above; close issue #31 from the PR description (`Closes #31`).

---

## WP2.3. OTLP/HTTP trace receiver

**Why.** `epi_recorder/integrations/opentelemetry.py` says it works with "ANY language", but `EPISpanExporter`
runs inside a Python process. A receiver in the gateway makes the claim true: TypeScript, Go or Java agents that
already emit OpenTelemetry traces just point their exporter at it.

### Design

1. **Route** `POST /v1/traces` in `epi_gateway/main.py`:
   - Accept `Content-Type: application/json`: OTLP/HTTP JSON, an `ExportTraceServiceRequest`.
   - For `application/x-protobuf`:
     - if the optional `opentelemetry-proto` package is installed (new extra `otlp` in `pyproject.toml`), decode
       with it;
     - otherwise return **415** with the message "set your exporter to JSON (OTEL_EXPORTER_OTLP_PROTOCOL=http/json)".
   - Accept `Content-Encoding: gzip` (decompress before parsing; the standard library is enough).
   - Apply the gateway's existing auth and the same rate limit as `/capture`.
   - Respond **200** with `{"partialSuccess": {}}`. On partial rejects, fill in `rejectedSpans` and `errorMessage`.
2. **Parsing (OTLP JSON specifics, get these right):**
   - Structure: `resourceSpans[].resource.attributes`, `resourceSpans[].scopeSpans[].spans[]`.
   - `traceId` and `spanId` are **hex strings** in OTLP JSON (not base64).
   - `startTimeUnixNano` and `endTimeUnixNano` are **strings** of integers.
   - An attribute is `{"key": ..., "value": {"stringValue" | "intValue" (string) | "doubleValue" | "boolValue" |
     "arrayValue": {"values": [...]} | "kvlistValue": {"values": [...]}}}`. Write one `otlp_value()` helper that
     unwraps all of these.
   - Span `events[]` have `name`, `timeUnixNano` and `attributes`.
   - `status.code`: 0 unset, 1 ok, 2 error.
3. **Mapping:** move the span-to-step logic out of `epi_recorder/integrations/opentelemetry.py` (`_span_to_step`,
   around line 210) into a new shared `epi_core/otel_mapping.py`.
   - Both the Python exporter and the gateway call it, and the gateway must not import `epi_recorder`.
   - Map the GenAI semantic-convention attributes:
     - `gen_ai.system` / `gen_ai.provider.name` → provider;
     - `gen_ai.request.model` / `gen_ai.response.model` → model;
     - `gen_ai.operation.name` → kind (`chat` → `llm.request`/`llm.response`, `execute_tool` → `tool.call`);
     - `gen_ai.tool.name`;
     - `gen_ai.usage.input_tokens` / `output_tokens`.
   - Message content comes in two forms; support both:
     - newer attributes `gen_ai.input.messages` and `gen_ai.output.messages` (JSON strings);
     - older span events `gen_ai.user.message`, `gen_ai.assistant.message`, `gen_ai.choice`, `gen_ai.tool.message`.
   - Keep unknown attributes under `meta.otel`.
   - Keep the existing `llm.*` fallbacks the Python exporter already supports.
4. **Cases:**
   - One case per `traceId`: set `case_id = "otel-" + traceId` and `trace_id = traceId` on every event.
   - Order events by `startTimeUnixNano`, then `spanId`.
   - Store parent/child links (`parentSpanId`) in `meta`.
   - Errors (`status.code == 2`) become an error event.
   - Set provenance to say the source was OTLP (`source_app` from `service.name` in the resource attributes).
5. **Redaction:** events go through the same redaction and retention path as `/capture`. Check `_apply_retention_mode`
   and the `/capture` handler and reuse them. Never store raw prompts when retention mode is `redacted_hashes`.
6. **Fix the docstring** in `opentelemetry.py`: it should describe the two honest paths, the in-process Python
   exporter and any language via the gateway's `/v1/traces`.

### Tests (`tests/test_gateway_otlp.py`)

- Hand-write a realistic OTLP JSON fixture (`tests/fixtures/otlp/genai_chat_and_tool.json`) with one trace
  containing:
  - a chat span using new-style message attributes;
  - a tool span;
  - an error span;
  - int and array attributes;
  - nested `kvlistValue`.
- POST it; assert the case's steps, order, provider, model, tool name, token usage and the error event.
- The same content via old-style span events maps to the same steps.
- A gzip body works.
- Protobuf without the extra returns 415.
- With retention `redacted_hashes`, no prompt text is stored.
- Export the case and run verify: it PASSes.
- The existing `tests/test_opentelemetry_integration.py` still passes after moving the mapping code.

**Docs:** add a section to `docs/ANY-LANGUAGE.md`:
- Node: `@opentelemetry/exporter-trace-otlp-http` with `url: "http://localhost:8787/v1/traces"`.
- Go: `otlptracehttp.WithEndpoint("localhost:8787")`, `WithURLPath("/v1/traces")`, `WithInsecure()`.
- The env var route: `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://localhost:8787/v1/traces`,
  `OTEL_EXPORTER_OTLP_TRACES_PROTOCOL=http/json`.

**Acceptance:** tests pass; a doc snippet is covered by the any-language smoke test.

---

## WP1d. Sigstore Rekor spike (one day maximum, then stop)

**Goal.** Find out whether EPI can log each sealed file's hash in Sigstore's **free public** transparency log,
replacing the Render-hosted SCITT service as the neutral third-party log.

**Network first:** check that the sandbox can reach Sigstore's hosts. If it cannot, write that down and stop. Do
not work around network policy.

### Spike steps

1. Read the current Sigstore docs to find the live public Rekor endpoints. Rekor v2 ("rekor-tiles", with yearly log
   shards) replaced v1 for new entries during 2025–2026, and the entry types and key types it accepts differ from
   v1. Do not assume the old `rekor.sigstore.dev/api/v1/log/entries` flow still works. Write the current endpoint
   and API version in the spike notes.
2. Find out which key types the current log accepts for a signed hash entry, specifically whether **Ed25519** is
   allowed. Ed25519 signs messages, not pre-hashed digests, so `hashedrekord` with Ed25519 may be rejected.
3. Try, **against the staging instance only**, in this order:
   - (a) A signed-hash entry with EPI's Ed25519 key, where the logged artifact is a small statement:
     `{"workflow_id", "manifest_hash", "file_sha256"}` in canonical JSON (`rfc8785`).
   - (b) If (a) is not accepted, a DSSE envelope (if the current log accepts DSSE with Ed25519) wrapping the same
     statement.
   - (c) If neither works with Ed25519, stop. Do **not** add a second key type just for Rekor in this spike.
4. If an entry is accepted, check how to verify the inclusion proof **offline**: which log public key or checkpoint
   to pin, and what bytes the verifier needs to store.
5. Write `plans/REKOR-SPIKE.md` covering:
   - what worked and what did not, with the exact request and response (redact nothing secret, there should be
     none);
   - the offline verification method;
   - **privacy**: entries are public and permanent and reveal timing and the key fingerprint, so this must be
     opt-in and must never include goals or content;
   - a go / no-go recommendation.

### If it is a go (separate later PR, `feat/rekor-anchor`; do not do it in the spike)

- Opt-in only: `epi-register --rekor` and env `EPI_REKOR=1`.
- Embed the entry under `artifacts/transparency/rekor_entry.json`, following the existing SCITT embedding pattern
  in `epi_cli/scitt.py` (`_build_scitt_artifact`).
  - `artifacts/transparency/` is already excluded from the witness content digest, so a later witness check still
    reports WITNESSED.
- Verify the inclusion proof offline in `epi verify` against a pinned key in `epi_core/assets/`.

### If it is a no-go

Add a line to `docs/KNOWN_LIMITATIONS.md` ("No public transparency log yet; independent time comes from RFC 3161
timestamps and the customer witness") and close the spike.

---

## WP5. Launch drafts (the agent writes, the owner posts)

Write everything to `plans/launch/`. **The agent must not post anything**: no GitHub comments, no Hacker News, no
PRs to other repositories. The owner reviews and posts personally.

1. **`plans/launch/show-hn.md`**
   - Title options (2–3), for example: "Show HN: Signed evidence files for AI agent runs, with timestamps checked
     offline".
   - Body, under 300 words:
     - what a `.epi` file is;
     - what it proves, now true after #81/#83: contents unchanged since sealing; existed no later than a time
       attested by an independent timestamp authority, checked offline; optional customer witness;
     - what it does **not** prove: quote `docs/KNOWN_LIMITATIONS.md` (completeness of capture, agent correctness;
       the seal timestamp does not bind the signing key in the default flow);
     - the 60-second demo command;
     - links to the threat model and `docs/ANY-LANGUAGE.md`.
   - No marketing adjectives. Every claim must be something `epi verify` actually checks.
2. **`plans/launch/awesome-list-pr.md`**: the exact one-line entry and PR description for
   `systempromptio/awesome-ai-agent-governance` (audit-trail section), in that list's own format (read its
   README to copy the style).
3. **`examples/langgraph_evidence/`**: a minimal runnable LangGraph agent recorded with
   `epi_recorder.integrations.langgraph`.
   - A fake LLM, so no API key is needed.
   - A `README.md` written so it could later be proposed upstream as a community example.
   - A smoke test in `tests/` that runs it and verifies the output file.
4. **`plans/launch/issue-76-reply.md`**: a draft reply to issue #76 (Receipt Protocol, a peer project), answering
   its three questions factually and citing code paths:
   - **Files vs APIs:** both. The `.epi` file is the portable unit; the gateway is the API.
   - **What `epi-register` does:** read `epi_cli/scitt.py` and `epi_cli/register.py` and describe exactly what it
     embeds and where. It is not on-chain.
   - **Redaction:** automatic regex patterns, on by default (`epi_core/redactor.py`), with an HMAC marker per
     redaction.

   Keep it collegial and short.
5. **`scripts/dev/pypi_stats.py`**:
   - Standard library only.
   - Fetches `https://pypistats.org/api/packages/epi-recorder/recent` and `/overall`.
   - Prints last day, week and month, plus a CSV line the owner can append to a local file.
   - No scheduling and no new telemetry.
6. **`plans/launch/metrics.md`**: what to track weekly with **no new tracking code**:
   - PyPI downloads (the script above);
   - GitHub stars and forks;
   - replies to outreach (counted by hand);
   - only if the existing opt-in telemetry already records verifies (check `docs/TELEMETRY-PRIVACY.md`), the
     count of distinct externally made files verified.

**Acceptance:** files exist; the LangGraph example's smoke test passes; nothing was posted anywhere.

---

## Appendix. Facts the agent should not re-research

- Gateway default port **8787**; start it with `epi gateway serve`.
- Generic capture: `POST /capture`, `/capture/batch`, `/capture/llm`. Proxies: `/v1/chat/completions`,
  `/v1/messages`. Export: `POST /api/cases/{case_id}/export`.
- Timestamps: `epi_core/tsa_verify.py` (`validate_tsr`, `load_pinned_tsa_roots`, `load_pem_roots`); pinned roots
  in `epi_core/assets/tsa_roots/`.
- Witness: `epi_core/webhook.py` (`witness_content_digest` excludes the signature, `governance.scitt` /
  `governance.transparency`, and `artifacts/scitt/` / `artifacts/transparency/` members).
- EU AI Act high-risk (Annex III) obligations apply from **2 December 2027** (Regulation (EU) 2026/1744).

## Claims allowed after each WP

| After | New claim allowed |
|---|---|
| WP2.1 | "Any language can send evidence to the gateway over HTTP." |
| WP2.2 | "The gateway captures streamed OpenAI- and Anthropic-style calls." |
| WP2.3 | "Any OpenTelemetry-instrumented agent (JSON export) can send traces to EPI." |
| WP1d (go) | "Optionally logged in Sigstore's public transparency log." |

Never claim completeness of capture, correctness of the agent, or compliance with any regulation.
