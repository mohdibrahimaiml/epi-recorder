# Operation Identity and Event Completeness (`epi-operation/v1`)

**Status:** Approved implementation contract
**Branch:** `feat/epi-operation-identity`
**Scope:** P0 / P0b (event pairing). P1/P2 (capture scope) are referenced, not implemented here.
**Related:** `docs/VERIFICATION_CONTRACT.md`, `docs/KNOWN_LIMITATIONS.md`, `docs/adr/`

---

## 1. Problem

The sequence-completeness audit decides whether every recorded operation that started
also finished. Today it can decide that incorrectly, and it does so in three ways.

**1.1 Ordering is used as evidence.**
`epi_cli/verify.py:625-626`, `:640-641`, `:658-659`:

```python
if not matched and pending_tool_calls:
    pending_tool_calls.pop(0)
```

When an event carries no `call_id`/`span_id`, or carries one that matches nothing, the
auditor consumes the oldest pending operation of that family. Membership in a queue is
treated as proof of identity. A terminal belonging to tool C can therefore discharge a
pending tool A, and the run can later report a fully matched sequence.

**1.2 A producer is invisible.**
`epi_recorder/adapters/langchain.py:217,251` emits `llm.call` on start; the auditor
collects starts only on `kind == "llm.request"` (`verify.py:630`). A LangChain LLM call
that never returns is not an incomplete finding — it is not a finding at all.

**1.3 A foreign producer can corrupt another's pairing.**
LangChain terminal events carry no `span_id`, so they reach the fallback at
`verify.py:640-641` and can consume a pending request emitted by the OpenAI wrapper.
One integration's traffic silently discharges another's.

This is a correctness defect in the evidence product, not a documentation gap: the
auditor asserts completeness it has not established.

---

## 2. Claim boundary

This work changes what EPI may say about event pairing. It does not change what EPI can
say about capture coverage.

- **In scope (this RFC):** for operations the recorder observed, determine whether their
  recorded lifecycles are complete and correctly correlated.
- **Out of scope (P1/P2):** whether the event stream contains every operation the
  application actually performed.

Resulting claim, which must be used verbatim in docs and marketing:

> EPI can establish that recorded operations are complete within the audited event
> stream. It cannot yet establish that the event stream contains every operation the
> application performed.

---

## 3. Non-goals

No new hash chain, heartbeat, timestamp authority, external evidence store, execution
modelling engine, or parallel completeness subsystem. No event-kind renames. No viewer
redesign in P0. No capture-scope fields in P0 beyond what §9 requires for wording.

---

## 4. Invariants

| # | Invariant | Rationale |
|---|---|---|
| I1 | The recorder **overwrites** `content.correlation`; application-supplied values are discarded | The field must not become a new forgery surface |
| I2 | Ordering never participates in matching, in any version, including legacy | Eliminates the defect class, not one instance |
| I3 | Governance is decided **per family**, not per artifact | Prevents partial-migration blind spots |
| I4 | The verifier recomputes the audit; it never trusts a producer-written verdict | Seal declarations, recompute conclusions |
| I5 | Missing evidence and ambiguous evidence are distinct findings with distinct consequences | An auditor must know which one is in front of them |
| I6 | Event kinds never change; only `content.correlation` is added | No sealed-format break, no consumer breakage |

---

## 5. Protocol

### 5.1 Schema

```json
"correlation": {
  "scheme": "epi-operation/v1",
  "group_id": "opg_<hex16>",
  "operation_id": "opo_<hex16>",
  "attempt": 1,
  "external_id": "call_abc123"
}
```

- `group_id` — stable across attempts of one logical operation.
- `operation_id` — unique per attempt.
- `attempt` — positive integer, sequential within a group, starting at 1.
- `external_id` — optional; provider `response_id`, LangChain `run_id`, OpenAI `call_id`.
  **Never a pairing key** in the `epi-operation/v1` path.
- Identifiers: `secrets.token_hex(16)` with prefix. No new dependency.
- No `phase` field. `kind` encodes phase; a second field that can contradict it is a
  defect generator.

### 5.2 `group_id` boundary

`group_id` connects attempts **only when EPI observes the retry relationship**:

- EPI's own retry helper performs the retry, or
- the producer supplies an explicit same-request marker (for example an idempotency key)
  and EPI can confirm the calls are the same logical request.

Otherwise every observation gets a fresh `group_id`. Repeated business calls with equal
arguments are **not** retries and must not be labelled as such. Provider-internal retries
that the wrapper cannot observe are not represented as separate recorded attempts.

### 5.3 Lifecycle map

| Family | Start | Commitment | Terminal |
|---|---|---|---|
| `llm` | `llm.request`, `llm.call` | `llm.pre_commit` | `llm.response`, `llm.error` |
| `tool` | `tool.call` | — | `tool.response` |
| `approval` | `agent.approval.request` | — | `agent.approval.response` |

`llm.pre_commit` binds to the same `operation_id` as its request and is cleared only by
that operation's terminal. It is neither a start nor a terminal.

A commitment with no start is `unbound_commitment`.
A commitment with no terminal is `unresolved_commitment` — the existing "committed but
never executed" gap, now attributed instead of guessed.

Kinds outside these families are not audited and are reported as `ungoverned_kinds`.

---

## 6. Audit model

### 6.1 Per-family governance

```
family has ≥1 step with scheme == "epi-operation/v1"   → GOVERNED
family has no such step                                → UNGOVERNED (legacy)
```

Governance is decided per family so a run that mixes a migrated producer with an
unmigrated one cannot report a clean result.

### 6.2 States

| Condition | `event_audit.status` |
|---|---|
| any governed family incomplete | `incomplete` |
| no incomplete family, no audited lifecycle events at all | `no_observed_lifecycle_events` |
| no incomplete family, at least one ungoverned family | `consistent_scope_unknown` |
| all present families governed and complete | `complete` |

### 6.3 Findings

`missing_terminals`, `orphan_terminals`, `duplicate_operations`, `duplicate_terminals`,
`unresolved_commitments`, `unbound_commitments`, `ambiguous_correlations`,
`family_mismatches`, `ungoverned_steps`, `ungoverned_kinds`.

Every finding entry carries `{family, kind, index, operation_id?, group_id?, attempt?}`
where available. `index` is the step's list index; human messages keep the existing
1-based `step N` convention.

### 6.4 Governed-family rules

- A start must have exactly one terminal with the same `operation_id`.
- Missing terminal → `missing_terminals` → `incomplete`.
- Terminal with no start → `orphan_terminals` → `incomplete`.
- More than one terminal for an `operation_id` → `duplicate_terminals` → `incomplete`.
- An `operation_id` observed with a different `family` → `family_mismatches` → `incomplete`.
- Any lifecycle step in a governed family without `correlation` → `ungoverned_steps`
  → `incomplete`. This is the deform-closed rule that makes partial migration fail.
- `attempt` must be ≥ 1 and sequential within a group; a gap is reported but does not by
  itself make the family incomplete (attempts may be unobserved).

### 6.5 Ungoverned (legacy) rules

No FIFO, no ordering, no heuristics.

- Pair on a **unique** `call_id` / `span_id` / name match.
- If a terminal has zero candidates → record the finding; consequence per §8.
- If a terminal has two or more candidates → `ambiguous_correlations`; **consume nothing**;
  findings for that family are suppressed as warnings, because attribution is unknown.
- `llm.call` remains a valid start alias in legacy artifacts, closing the historical
  blind spot without renaming kinds.

---

## 7. Output contract

`facts.event_audit`, always recomputed by the verifier (I4):

```json
{
  "event_audit": {
    "status": "incomplete",
    "scheme": "mixed",
    "basis": "mixed",
    "families": {
      "llm":  {"status": "incomplete",               "basis": "operation_identity"},
      "tool": {"status": "consistent_scope_unknown", "basis": "name_based"},
      "approval": {"status": "consistent_scope_unknown", "basis": "name_based"}
    },
    "counts": {"started": 14, "completed": 13, "orphaned": 0},
    "missing_terminals": [], "orphan_terminals": [],
    "duplicate_operations": [], "duplicate_terminals": [],
    "unresolved_commitments": [], "unbound_commitments": [],
    "ambiguous_correlations": [], "family_mismatches": [],
    "ungoverned_steps": [], "ungoverned_kinds": []
  }
}
```

- `scheme` / `basis` are `mixed` when families differ. The per-family map is authoritative;
  the globals are a convenience and must never be used to infer a family's basis.
- `completeness_gaps` (`verify.py:2415`) is retained, derived from the findings as human
  strings, for backward compatibility.
- **Empty event stream:** an artifact with no audited lifecycle events receives
  `no_observed_lifecycle_events`, not `complete`. Without a declared scope the verifier
  cannot distinguish "made no calls" from "made calls that were never captured". P1
  resolves this; until then it is a WARN ceiling, never a failure (see §9).

---

## 8. Legacy three-way rule

Legacy artifacts must not be retroactively failed for insufficient identifiers, but
neither may a real gap be softened into a warning.

| Legacy outcome | Status | Strict consequence |
|---|---|---|
| Unambiguous gap (unique identity, no terminal; or terminal with no candidate) | `incomplete`, `basis: name_based` | **FAIL** — identical to today |
| Ambiguous (≥2 candidates or no identity) | `consistent_scope_unknown` + `ambiguous_correlations` | **WARN** ceiling |
| Clean (all pairs unique, no gaps) | `consistent_scope_unknown` | **WARN** ceiling |

A legacy artifact can never report `complete`, even when every event pairs cleanly.
The only path to `complete` is EPI-minted identity.

**Cryptographic failures are never softened.** The WARN ceiling applies to correlation
uncertainty only. Integrity failure, invalid signature, and chain failure remain FAIL at
every version (see §9).

---

## 9. Policy integration

Three values stay separate (condition #4):

1. `event_audit.status` — the honest assessment.
2. `completeness_ok` — the legacy compatibility boolean.
3. `decision` — sufficiency under the selected policy.

`completeness_ok` is defined as:

- governed artifact: `status == "complete"`
- legacy, clean or ambiguous: the legacy name-based result (compatibility value)
- empty stream: `True` (nothing is missing; nothing was audited either)

`completeness_ok` alone is no longer a sufficient gate in `apply_policy`
(`epi_core/trust.py:988`). Policy consults `event_audit.status` explicitly:

| `event_audit.status` | standard | strict |
|---|---|---|
| `complete` | no constraint | no constraint |
| `incomplete` (governed) | WARN | **FAIL** |
| `incomplete` (legacy, unambiguous) | WARN | **FAIL** (unchanged behaviour) |
| `consistent_scope_unknown` | WARN | **WARN** |
| `no_observed_lifecycle_events` | WARN | **WARN** |

Existing conditions (integrity, signature, identity, `chain_present`) are evaluated first
and unchanged. Exit codes are unchanged: WARN exits 0, FAIL exits 1.

### 9.1 Strict wording

`trust.py:1139` becomes:

> All strict criteria met (Integrity, Identity, Event completeness — capture scope not declared)

and for `basis: name_based`:

> Event completeness audited by name only; operation identity not proven. Re-seal with a
> current recorder to obtain a provable audit.

The strict string must never imply capture scope was checked.

---

## 10. API compatibility

`_audit_step_sequence_completeness(steps, answered_ids, case_level) -> (bool, list[str])`
is imported by `verify_portal/main.py:969` and four test modules. Its signature is
preserved as a thin adapter over the new implementation:

```python
def audit_event_sequence(steps, answered_approval_ids=None, case_level_answered=False) -> dict
def _audit_step_sequence_completeness(...) -> tuple[bool, list[str]]   # adapter
```

No caller churn in P0.

---

## 11. Producers and migration order

| Phase | Producer | File | Notes |
|---|---|---|---|
| **P0** | OpenAI wrapper | `wrappers/openai.py` (91, 152, 161, 195, 324, 330) | stream + non-stream; self-contained, does not use `base.py` helpers |
| P0b | Session API | `api.py` (347-379, 447-513, 1417, 1520-1844) | largest surface |
| P0b | Legacy patcher | `patcher.py` (381-673) | streaming pre-commit gap already documented |
| P0b | Anthropic wrapper | `wrappers/anthropic.py` (75-300) | mirror of OpenAI |
| P0b | LangChain adapter | `adapters/langchain.py` (217-407) | closes the blind spot; `on_llm_error` emits `llm.response` |
| P0b | Base helpers | `wrappers/base.py` (40-77) | test-only today; migrate or mark deprecated |
| P0b | LiteLLM / OTel | `integrations/*` | emission sites to be confirmed in the inventory sweep |
| P1 | MCP sealer / gateway | `epi_mcp`, `epi_serve` | caller-provided path; scope work |

---

## 12. Phases and exit criteria

| Phase | Deliverable | Exit criteria |
|---|---|---|
| **P0** | Auditor rewrite, OpenAI producer, adversarial tests, strict wording | Zero `pop(0)`; OpenAI emits correlation on request/pre_commit/response/error for stream and non-stream; legacy fixture → `consistent_scope_unknown`; full suite green; contract reviewed |
| **P0b** | Remaining producers | Conformance test enumerates every producer and fails on missing correlation; no governed family has uncorrelated steps; mixed-producer run audits correctly |
| **P1** | Capture scope declaration, verifier-recomputed verdict | Strict cannot pass without a declared scope; `capture_scope` block emitted; old artifacts degrade to scope-unknown, never fail |
| **P2** | Instrumentation provenance | Activation events sealed; supported/declared/activated/observed distinction; enforcement mode recorded |
| **P3** | Cross-surface consistency, failure codes | Shared conformance vectors across CLI, portal, browser; exit codes unchanged |
| **P4** | Docs, spec, release | Version bump in a single final commit, gated by the conformance test |

---

## 13. Commit sequence

1. `docs(rfcs): operation identity and event completeness` — this document.
2. `feat(core): operation identity primitives and lifecycle map` — no behaviour change.
3. `refactor(verify): audit on operation identity; remove FIFO` — **review checkpoint: the contract**.
4. `feat(wrappers): OpenAI emits operation correlation`.
5. `fix(policy): strict wording names event completeness, not capture scope`.
6. `test(verify): adversarial concurrency, cross-producer, legacy matrix` — **review checkpoint: the proof**.

The branch is not merged until P0b, the full test matrix, and the version transition
complete.

---

## 14. Test matrix

**Auditor (synthetic steps)**
reversed concurrent responses · missing id under `epi-operation/v1` → incomplete ·
unrelated id must not consume a pending operation · duplicate `operation_id` ·
duplicate terminal · retry with same `group_id`, new `operation_id` · `pre_commit` with
no start · `pre_commit` with no terminal · approval pairing · family mismatch · governed
family with one uncorrelated step · repeat calls must not be labelled retries · empty
step list → `no_observed_lifecycle_events` · determinism (identical input → identical
output).

**Producers**
OpenAI non-stream success · stream success · non-stream error · stream error · stream
cancelled mid-flight.

**Cross-producer**
Interleaved LangChain `llm.call` and OpenAI `llm.request`; the LangChain terminal must
not consume the OpenAI request. Run **with** and **without** identifiers — only the
without variant reproduces the current defect.

**Legacy**
Real 4.11.2 fixture → `consistent_scope_unknown`, compatibility boolean preserved,
strict WARN not FAIL. Legacy artifact with `tool.call` and no response → still `incomplete`
→ strict FAIL. Legacy ambiguity → WARN, nothing consumed.

**Property / fuzz**
Random interleavings of starts, terminals and commitments; assert
`started == completed + missing_terminal_entries + unresolved_commitments` and that no
pair is ever created without an identity.

Fixtures: `tests/fixtures/operation_identity/*.jsonl`, tests in `tests/test_event_audit_*.py`.

---

## 15. Version transition

`ManifestModel.spec_version` defaults from the package version (`epi_core/schemas.py:132-135`),
so a premature bump commits every untouched producer at once.

1. Add manifest `correlation_scheme` for new artifacts. Policy selection order: per-step
   scheme → manifest scheme → `spec_version` fallback. This makes mixed-producer runs an
   explicit, inspectable state.
2. Add a release-gating test, `test_all_producers_emit_correlation`, that fails if any
   lifecycle producer lacks `epi-operation/v1`. Shipping the bump early becomes impossible
   rather than discouraged.
3. `pyproject.toml` stays at `4.11.2` on this branch. New-protocol tests construct
   manifests with an explicit `spec_version="4.12.0"`. The bump is the final commit of P4,
   after every producer has migrated.

---

## 16. Consumer impact

- `verify_portal/main.py:969` and four test modules import the tuple API — preserved (§10).
- `epi analyze`, viewer, AGT exporter key on kinds, not correlation — unaffected.
- `steps_hash` changes for new artifacts only; sealed legacy bytes are untouched.
- **Streaming apps will see new findings.** Closing a stream without a terminal was
  previously invisible and becomes `missing_terminals`. Correct, but it changes pass
  rates; call it out in the release notes and warn pilot users.

---

## 17. Risks

| Risk | Mitigation |
|---|---|
| Retroactive downgrade of sealed legacy evidence | §8 three-way rule; WARN ceiling for uncertainty, FAIL only for proven gaps and crypto failures |
| Partial migration creates a blind spot | Per-family governance (§6.1) + conformance gate |
| Premature version bump | `correlation_scheme` + release-gating test + single final bump commit |
| Application forges `correlation` | Recorder overwrites the field (I1) |
| Duplicate ids from internal SDK retries | Mint once at the true attempt boundary; duplicates surface as findings |
| Auditor performance | Single pass, per-operation maps, O(n) |

---

## 18. Acceptance criteria

Every one of these must hold before the branch merges:

1. **No operation may be declared successfully paired because it happened to be the next
   event in the sequence. It must have a valid, unambiguous identity.**
2. Zero FIFO or ordering-based matching remains anywhere, including the legacy path.
3. `llm.call` is a first-class start alias; the LangChain blind spot is closed.
4. A LangChain terminal cannot consume an OpenAI pending request.
5. Every supported producer emits `epi-operation/v1` (P0b gate).
6. Legacy artifacts never report `complete`; unambiguous legacy gaps still FAIL.
7. Integrity, signature and chain failures remain FAIL at every version.
8. Empty event streams report `no_observed_lifecycle_events`, never `complete`.
9. Strict wording never implies capture scope was checked.
10. `_audit_step_sequence_completeness` remains importable with its existing signature.

---

## 19. Decision record

| Decision | Answer |
|---|---|
| Legacy artifacts under strict | WARN when identity cannot be established; FAIL when a gap is unambiguous or crypto fails |
| `event_audit` location | `facts`, recomputed by the verifier; never a producer-written verdict |
| Existing auditor API | Preserved as a compatibility adapter |
| Identifier format | `opg_` / `opo_` + `secrets.token_hex(16)`, no new dependency |
