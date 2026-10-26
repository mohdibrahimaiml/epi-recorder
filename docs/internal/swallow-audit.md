# Swallowed-exception audit (`except Exception: pass`)

**Scope:** `epi_core/` and `epi_recorder/` product code.  
**Method:** Python AST scan for `except Exception/BaseException` handlers whose body is
exactly `pass`, run on `main` after #180.  
**Status:** read-only classification for red-team readiness (weeks 7–8).

> An earlier text-line scan reported 86. The AST scan is authoritative at **92**: the
> line scan missed six handlers where `pass` carries a trailing comment (`pass  # …`).

## Classes

| Class | Meaning | Action |
|-------|---------|--------|
| **A** | Seal/verify path: the swallow can yield a sealed artifact that should have failed, been redacted, or been complete. | Fix before the red team. |
| **B** | Silently degrades a report, verdict, identity, gap list, or piece of evidence. | Fix or log. |
| **C** | Genuinely optional / best-effort (telemetry, adapters, OS integration, cleanup). | Leave; add a one-line comment explaining why. |

**Totals:** A=17  B=30  C=45  (total 92)

## Class A — fix before the red team

> **Status: fixed** in `fix/swallowed-seal-errors` — fault-analyzer detectors now
> record `detector_errors` in `analysis.json` (surfaced by `epi analyze` and the
> seal summary); a corrupt capture manifest is no longer downgraded to "absent";
> bootstrap finalize failures warn; environment redaction fails closed. Classes
> B and C remain as listed.

| file:line | what is swallowed | consequence |
|-----------|-------------------|-------------|
| `epi_core/fault_analyzer.py:865` | Pass 1 — error continuation detector crashed | A real fault is silently omitted from the sealed analysis; the artifact can read 'no fault'. |
| `epi_core/fault_analyzer.py:871` | Pass 2 — constraint violation detector crashed | A constraint breach is silently omitted from the sealed analysis. |
| `epi_core/fault_analyzer.py:878` | Pass 3 — sequence violation detector crashed | An out-of-order policy breach is silently omitted. |
| `epi_core/fault_analyzer.py:884` | Pass 4 — threshold violation detector crashed | A threshold breach is silently omitted. |
| `epi_core/fault_analyzer.py:890` | Pass 5 — prohibition violation detector crashed | A prohibited action is silently omitted → sealed artifact can read compliant. |
| `epi_core/fault_analyzer.py:896` | Pass 6 — agent approval gap detector crashed | A missing approval is silently omitted. |
| `epi_core/fault_analyzer.py:903` | Pass 7 — approval guard violation detector crashed | An approval-guard breach is silently omitted. |
| `epi_core/fault_analyzer.py:909` | Pass 8 — context drop detector crashed | A context-drop fault is silently omitted. |
| `epi_core/fault_analyzer.py:916` | Pass 9 — tool permission guard detector crashed | A permission breach is silently omitted. |
| `epi_core/fault_analyzer.py:923` | Pass 10 — time-gap tamper detector crashed | A timestamp-tamper signal is silently omitted. |
| `epi_core/fault_analyzer.py:929` | Pass 11 — coverage gap detector crashed | An instrumentation-coverage gap is silently omitted. |
| `epi_core/fault_analyzer.py:935` | Pass 11b — orphaned tool call detector crashed | An unmatched tool call is silently omitted. |
| `epi_core/fault_analyzer.py:941` | Pass 11c — unmatched LLM request detector crashed | An unmatched LLM request is silently omitted. |
| `epi_core/fault_analyzer.py:947` | Pass 11d — anomalous time gap detector crashed | An anomalous time gap is silently omitted. |
| `epi_core/manifest.py:379` | reading the embedded capture manifest from an artifact | A corrupt/invalid sealed capture manifest is silently treated as 'pre-v' (None) instead of surfacing corruption → completeness silently unknown on a file that verifies. |
| `epi_recorder/bootstrap.py:142` | finalising the bootstrap recording at shutdown | Steps may not be flushed before packing; the artifact still seals, so it can look complete while silently missing the tail of the run. |
| `epi_recorder/environment.py:235` | applying global redaction to the env snapshot | On failure it returns the UNREDACTED snapshot: secrets can be sealed into the artifact while the caller believes redaction ran. |

**A fix plan (one PR):**

1. **fault_analyzer pass guards (14)** — a crashed detector must not read as 'no fault'.
   Record a `DETECTOR_ERROR` observation (and set `analysis_status="partial"` / an
   `analysis_error`) instead of dropping the pass, so `analysis.json`, `epi analyze`,
   and the summary all say the detector failed.
2. **manifest:379** — distinguish 'pre-v artifact' from 'member present but invalid'.
   Only return `None` for a genuinely absent member; a present-but-unparseable member
   must raise or be reported as a corrupt capture manifest.
3. **bootstrap:142** — finalisation failure must surface (stderr + a recorded gap), not
   be swallowed at shutdown, so a truncated run cannot seal as complete.
4. **environment:235** — a redaction failure must not return the unredacted snapshot.
   Fail the snapshot (raise) or omit secret-bearing fields and record the failure.

## Full table (by file)


### `epi_core/aiuc1_mapping.py`

| line | class | what is swallowed | consequence |
|------|:-----:|-------------------|-------------|
| 214 | B | artifact member listing for a domain check | A read failure is reported as 'member absent' → a domain can be scored wrong (false gap). |
| 303 | B | analysis.json read for a domain check | Analysis-based domain scoring silently degrades to 'no data'. |

### `epi_core/case_store.py`

| line | class | what is swallowed | consequence |
|------|:-----:|-------------------|-------------|
| 482 | B | copying `_epi_capture` metadata onto a step | Gateway export can drop capture metadata → completeness/gaps understated. |
| 683 | B | collecting gateway enforcement flags from events | Enforcement metadata silently missing from the exported case payload. |

### `epi_core/checkpoints.py`

| line | class | what is swallowed | consequence |
|------|:-----:|-------------------|-------------|
| 49 | B | recording a runtime gap | A TSA/checkpoint outage is not recorded in known_gaps → the artifact understates its gaps. |
| 130 | B | enqueuing a checkpoint | A checkpoint is silently not submitted (queue full) → forward-secure evidence missing with no signal. |
| 174 | B | creating a checkpoint record in the worker thread | Checkpoint creation failure is swallowed → missing checkpoint, no report. |
| 179 | C | queue.task_done() bookkeeping | Worker accounting can go wrong; no effect on the sealed artifact. |

### `epi_core/container.py`

| line | class | what is swallowed | consequence |
|------|:-----:|-------------------|-------------|
| 999 | C | setting policy_load_status='failed' before raising PolicyLoadError | Seal fails right after, so no misleading artifact is produced; only the status write is lost. |
| 1018 | B | recording policy_load_status on the manifest | If this write fails, a policy-bearing artifact seals with no load status → verifier cannot tell a policy ran. |
| 1132 | B | reading review.json to detect a signed §7 attestation | Corrupt/unreadable review makes a reviewed rule look un-reviewed → sealed policy verdict can be wrong (fails conservative). |
| 1290 | C | writing the 'capture manifest build failed' gap note | The build already failed; only the explanatory note is lost. |
| 1758 | C | stamping producer_version via get_version() | Falls back to the installed version in VERIFY.txt; no integrity effect. |

### `epi_core/did_web.py`

| line | class | what is swallowed | consequence |
|------|:-----:|-------------------|-------------|
| 154 | B | base58 multibase key decode | Key extraction silently falls through to JWK → identity resolution can degrade. |
| 168 | B | JWK base64url key decode | A malformed key entry is skipped → DID:WEB identity not resolved (unknown identity). |

### `epi_core/fault_analyzer.py`

| line | class | what is swallowed | consequence |
|------|:-----:|-------------------|-------------|
| 865 | A | Pass 1 — error continuation detector crashed | A real fault is silently omitted from the sealed analysis; the artifact can read 'no fault'. |
| 871 | A | Pass 2 — constraint violation detector crashed | A constraint breach is silently omitted from the sealed analysis. |
| 878 | A | Pass 3 — sequence violation detector crashed | An out-of-order policy breach is silently omitted. |
| 884 | A | Pass 4 — threshold violation detector crashed | A threshold breach is silently omitted. |
| 890 | A | Pass 5 — prohibition violation detector crashed | A prohibited action is silently omitted → sealed artifact can read compliant. |
| 896 | A | Pass 6 — agent approval gap detector crashed | A missing approval is silently omitted. |
| 903 | A | Pass 7 — approval guard violation detector crashed | An approval-guard breach is silently omitted. |
| 909 | A | Pass 8 — context drop detector crashed | A context-drop fault is silently omitted. |
| 916 | A | Pass 9 — tool permission guard detector crashed | A permission breach is silently omitted. |
| 923 | A | Pass 10 — time-gap tamper detector crashed | A timestamp-tamper signal is silently omitted. |
| 929 | A | Pass 11 — coverage gap detector crashed | An instrumentation-coverage gap is silently omitted. |
| 935 | A | Pass 11b — orphaned tool call detector crashed | An unmatched tool call is silently omitted. |
| 941 | A | Pass 11c — unmatched LLM request detector crashed | An unmatched LLM request is silently omitted. |
| 947 | A | Pass 11d — anomalous time gap detector crashed | An anomalous time gap is silently omitted. |

### `epi_core/keys.py`

| line | class | what is swallowed | consequence |
|------|:-----:|-------------------|-------------|
| 433 | B | raw public-key decoding fallback | A key that cannot be decoded is silently treated as absent → pin/identity checks degrade. |

### `epi_core/manifest.py`

| line | class | what is swallowed | consequence |
|------|:-----:|-------------------|-------------|
| 108 | B | enumerating built-in instrumented surfaces | The declared capture surface list can be silently incomplete. |
| 116 | B | enumerating framework integration surfaces | Installed-integration surfaces can be silently missing from the capture manifest. |
| 292 | B | reading capture_gaps.json | Known gaps silently dropped from the manifest → completeness understated. |
| 379 | A | reading the embedded capture manifest from an artifact | A corrupt/invalid sealed capture manifest is silently treated as 'pre-v' (None) instead of surfacing corruption → completeness silently unknown on a file that verifies. |
| 400 | B | appending a runtime gap | A gap (e.g. TSA outage) silently not recorded. |

### `epi_core/platform/associate.py`

| line | class | what is swallowed | consequence |
|------|:-----:|-------------------|-------------|
| 120 | C | locating the packaged icon | Icon fallback only; no evidence effect. |
| 356 | C | resolving the epi command path | Falls back to a default command string. |
| 562 | C | task-scheduler self-heal ShellExecute | Repair helper; failure leaves OS state unchanged. |
| 616 | C | Shell notification after register | Explorer refresh only. |
| 686 | C | ctypes load in system register | OS-integration fallback. |
| 762 | C | Shell notification after unregister | Explorer refresh only. |
| 1029 | C | persisting the registration flag | Best-effort state file. |

### `epi_core/redactor.py`

| line | class | what is swallowed | consequence |
|------|:-----:|-------------------|-------------|
| 350 | C | chmod 0600 on the redaction secret | Permissions may not be settable on all platforms; secret still generated. |
| 769 | C | creating a default redactor config | Falls back to built-in defaults. |

### `epi_core/storage_sink.py`

| line | class | what is swallowed | consequence |
|------|:-----:|-------------------|-------------|
| 409 | C | customer-bucket heartbeat | Best-effort delivery telemetry; never affects the seal. |

### `epi_core/telemetry.py`

| line | class | what is swallowed | consequence |
|------|:-----:|-------------------|-------------|
| 240 | C | container detection | Environment label only. |

### `epi_core/trust.py`

| line | class | what is swallowed | consequence |
|------|:-----:|-------------------|-------------|
| 341 | B | AUD-IA-04 trust/keys dir independence warning | A security warning about registry independence can be silently skipped. |
| 368 | B | reading a pinned key file to compare against revoked keys | A revoked key can be misclassified in pinned_names (identity display). |
| 373 | B | reading a pinned key file to compare against local signing keys | A local key can be misclassified as an external pin. |
| 376 | B | enumerating pinned key names | Pinned-name list can silently be empty/wrong → identity verdict wording wrong. |
| 445 | B | scanning local signer keys in _is_locally_pinned | Returns False on error → identity may show LOCAL/UNKNOWN instead of matching. |
| 553 | C | importing requests for online key-source check | Optional network feature; offline verdict unaffected. |

### `epi_core/tsa_verify.py`

| line | class | what is swallowed | consequence |
|------|:-----:|-------------------|-------------|
| 267 | B | loading pinned extra TSA certs for signer selection | Fewer candidates → a valid token can be rejected (false negative); never a false pass. |
| 378 | B | parsing RSASSA-PSS salt length | Falls back to digest size; a valid PSS token can fail to verify. |
| 805 | B | loading pinned extra certs for chain building | Chain building can fail on a valid token (false negative); fails closed. |

### `epi_core/viewer_assets.py`

| line | class | what is swallowed | consequence |
|------|:-----:|-------------------|-------------|
| 234 | C | deleting a temp node-check file | Cleanup only. |

### `epi_core/webhook.py`

| line | class | what is swallowed | consequence |
|------|:-----:|-------------------|-------------|
| 738 | C | scanning the witness outbox for duplicates | At worst a duplicate queued report; delivery is best-effort. |

### `epi_core/workspace.py`

| line | class | what is swallowed | consequence |
|------|:-----:|-------------------|-------------|
| 70 | C | probing temp-dir candidates | Fallback temp selection. |

### `epi_recorder/adapters/langchain.py`

| line | class | what is swallowed | consequence |
|------|:-----:|-------------------|-------------|
| 164 | C | JSON-serialising a LangChain payload | Adapter captures a string fallback; recording continues. |

### `epi_recorder/integrations/agt/exporter.py`

| line | class | what is swallowed | consequence |
|------|:-----:|-------------------|-------------|
| 312 | C | hashing a workspace file for AGT export | Derived export only. |

### `epi_recorder/integrations/agt/mapping.py`

| line | class | what is swallowed | consequence |
|------|:-----:|-------------------|-------------|
| 47 | C | parsing an ISO timestamp from AGT evidence | Best-effort normalisation of imported data. |

### `epi_recorder/integrations/langgraph.py`

| line | class | what is swallowed | consequence |
|------|:-----:|-------------------|-------------|
| 207 | C | writing the LangGraph adapter state file | Adapter convenience only. |

### `epi_recorder/integrations/litellm.py`

| line | class | what is swallowed | consequence |
|------|:-----:|-------------------|-------------|
| 118 | C | extracting cost from LiteLLM response | Optional usage metadata. |
| 155 | C | JSON-serialising a LiteLLM request | Adapter falls back to str(). |
| 183 | C | JSON-serialising a LiteLLM success event | Adapter falls back to str(). |
| 229 | C | JSON-serialising a LiteLLM failure event | Adapter falls back to str(). |

### `epi_recorder/integrations/opentelemetry.py`

| line | class | what is swallowed | consequence |
|------|:-----:|-------------------|-------------|
| 179 | C | JSON-serialising an OTEL export payload | Derived trace export only. |

### `epi_recorder/integrations/trace_exporter.py`

| line | class | what is swallowed | consequence |
|------|:-----:|-------------------|-------------|
| 217 | C | reading policy members for a TRACE export | Derived export omits policy fields. |
| 229 | C | reading SCITT governance for a TRACE export | Derived export omits SCITT fields. |

### `epi_recorder/api.py`

| line | class | what is swallowed | consequence |
|------|:-----:|-------------------|-------------|
| 171 | C | parsing a child-process output line | Output forwarding only. |
| 1090 | C | recording telemetry after seal | Telemetry must never break recording. |
| 1752 | C | parsing witness settings JSON | Witness is best-effort; seal unaffected. |
| 1782 | C | importing the witness report helper | Witness is best-effort; seal unaffected. |
| 1797 | C | customer-bucket copy | Storage is best-effort and outbox-backed; seal unaffected. |
| 1852 | B | auto-SCITT anchoring after seal | A transparency anchor can be silently missing with no signal; the artifact still verifies. |
| 1989 | C | parsing witness result for display | Display only. |
| 2022 | C | parsing witness result for display | Display only. |

### `epi_recorder/bootstrap.py`

| line | class | what is swallowed | consequence |
|------|:-----:|-------------------|-------------|
| 80 | C | parsing a child-process output line | Output forwarding only. |
| 96 | C | JSON-serialising a bootstrap log line | Logging fallback. |
| 142 | A | finalising the bootstrap recording at shutdown | Steps may not be flushed before packing; the artifact still seals, so it can look complete while silently missing the tail of the run. |

### `epi_recorder/environment.py`

| line | class | what is swallowed | consequence |
|------|:-----:|-------------------|-------------|
| 96 | C | listing installed pip packages | Env snapshot omits the package list. |
| 114 | C | filtering packages to runtime-imported ones | Env snapshot keeps the unfiltered list. |
| 131 | C | adding the seal-time version to the env snapshot | Env snapshot omits the version pin. |
| 235 | A | applying global redaction to the env snapshot | On failure it returns the UNREDACTED snapshot: secrets can be sealed into the artifact while the caller believes redaction ran. |

### `epi_recorder/patcher.py`

| line | class | what is swallowed | consequence |
|------|:-----:|-------------------|-------------|
| 114 | B | setting up the checkpoint directory | Checkpoints may be silently disabled for the run. |
| 150 | C | reading `_epi_capture` metadata on a step | Optional metadata; step still recorded. |
| 235 | B | creating the checkpoint submitter | Checkpointing silently disabled → missing forward-secure evidence. |
| 240 | B | importing checkpoint APIs | Checkpointing silently disabled. |
| 265 | B | finalising checkpoints | Tail checkpoints may be silently lost. |
| 658 | C | reading Gemini usage metadata | Optional usage fields. |

### `epi_recorder/trust/approval.py`

| line | class | what is swallowed | consequence |
|------|:-----:|-------------------|-------------|
| 150 | C | invoking an approval-request callback | Callback is best-effort; ticket still recorded. |

### `epi_recorder/trust/engine.py`

| line | class | what is swallowed | consequence |
|------|:-----:|-------------------|-------------|
| 337 | B | stripping redaction receipts before a prohibition scan | Receipts are scanned as content → false-positive policy violations (fails conservative). |

## Reproduce

```python
# AST scan: handlers whose body is exactly Pass
import ast, pathlib
for p in pathlib.Path('.').glob('epi_core/**/*.py'):
    tree = ast.parse(p.read_text())
    for n in ast.walk(tree):
        if isinstance(n, ast.Try):
            for h in n.handlers:
                if len(h.body) == 1 and isinstance(h.body[0], ast.Pass):
                    print(f'{p}:{h.lineno}')
```

> Not in scope: `except Exception: return None/False/[]` (no `pass`). Those were not
> audited here and should be a follow-up sweep before the red team.

