# Signed release records

**Product version:** 4.9.0. Product map: [README.md](./README.md).

A **release record** is a sealed `.epi` that pins one version of the decision
logic: the policy file, prompt templates, model ids, tool schemas, code commit
and config that version is allowed to use. A **decision record** names the
release it was produced under. `epi verify --release` compares what EPI
observed while the decision ran with what was approved.

It answers a narrower question than "is this decision correct":

> "Was this decision produced by the version of the logic that a named person
> approved?"

Read it with [DECISION-RECORD.md](./DECISION-RECORD.md),
[HUMAN-APPROVAL.md](./HUMAN-APPROVAL.md) and
[KNOWN_LIMITATIONS.md](./KNOWN_LIMITATIONS.md).

---

## Create a release

```bash
epi release create \
  --name credit-policy --version 3.2 \
  --policy credit=policies/x.yaml \
  --prompt system=prompts/system.txt \
  --prompt tools=prompts/tools.txt \
  --model anthropic:claude-x \
  --tools refund=tools/refund.json \
  --config runtime=config/prod.yaml \
  --git-commit auto \
  --require-approvals 2 \
  --out releases/credit-policy-3.2.epi
```

- Files are pinned by SHA-256; models and the code commit by exact identifier.
- A bare value keeps the file's basename as the logical name. If two entries of
  the same type would share a logical name, the command **refuses** and asks
  you to name them (`--prompt system_a=...`). Names are how a decision is
  matched later; paths are only information.
- `--git-commit auto` reads `git rev-parse HEAD` and marks the release
  `dirty` when the tree has uncommitted changes. A dirty release can never
  reach `MATCHES`.
- The release is sealed through the normal path: Ed25519 signature, seal
  sequence number, optional RFC 3161 timestamp, and an `epi.release` witness
  report.
- `required_approvals` is **inside** `release_digest`, together with name,
  version and the sorted components. A second artifact with the same
  components but a lower threshold has a different digest and id, so it
  cannot be substituted for a 2-approval release.

`release_id` is `rel_` + the first 16 hex characters of the digest; identical
name, version, threshold and components always get the same id.

## Approve it

```bash
epi release approve releases/credit-policy-3.2.epi --as alice@bank.com
```

- The key comes from the **approver** keys directory only, never the agent key,
  and must differ from the sealing key (separation of duties).
- The signed review content includes `release_digest`, so an approval cannot
  be replayed onto another version: its signature stops matching.
- An additive `epi.release_approval` report is staged to the witness, so the
  approval time is observed independently instead of coming from the
  approver's clock.
- Status is computed, never stored: `approved` when the number of distinct
  **pinned** approver keys with a valid signature over this digest meets the
  threshold. Pin the approver out of band first (`epi approvers add`).
- The vendor's threshold is a floor, not a ceiling: `epi verify
  --min-approvals N` uses `max(release.required_approvals, N)`. The customer
  sets policy.

## Record against it

```python
from epi_recorder import record

with record("claim-1001.epi",
            release="releases/credit-policy-3.2.epi",
            prompts={"system": "prompts/system.txt"},
            goal="adjudicate claim CLM-1001") as epi:
    ...
```

The release is resolved and verified **before the run starts**; a missing or
invalid release is a configuration error and raises before any decision is
taken. The decision's signed manifest then carries:

```json
"release_ref": {"release_id": "rel_…", "release_digest": "…"},
"runtime_components": [
  {"type": "policy", "name": "epi_policy.json", "sha256": "…", "observed": true},
  {"type": "prompt", "name": "system", "sha256": "…", "observed": true,
   "sha256_at_start": "…", "sha256_at_seal": "…"},
  {"type": "model", "name": "anthropic:claude-x", "identifier": "anthropic:claude-x",
   "observed": true}
]
```

EPI observes what it can actually see:

- **policy**: the `epi_policy.json` EPI loaded (or the file passed as
  `policy=`). It is **not** the vendor's business logic, model weights,
  retrieval index or prompts unless they are passed in and observed.
- **model**: the distinct served model ids in the sealed `llm.*` steps.
- **prompt / tool_schema / config**: files passed to `record(...)`, hashed at
  start and again at seal.

A file that changes mid-run is **still sealed**: the component is
`observed: true` with `sha256_at_start` and `sha256_at_seal`, a DRIFT reason,
and a capture gap. It never raises unless the caller opts in with
`release_strict=True`.

## Verify a decision

```bash
epi verify claim-1001.epi --release releases/credit-policy-3.2.epi
epi verify claim-1001.epi --release-dir ./releases        # resolve by id
epi verify claim-1001.epi --require-release               # FAIL unless MATCHES
epi verify claim-1001.epi --release … --min-approvals 2
```

The report gains a `Release:` block:

```text
- Release:      credit-policy 3.2  MATCHES
                approved by 2/2
- Order:        release before decision (basis: witness received_at)
```

Statuses:

| Status | Meaning |
| --- | --- |
| `MATCHES` | release verifies, threshold met, approvals predate the decision, release sealed first, every component observed and equal, code tree clean |
| `DRIFT` | a component differs; the line names what ran and what was pinned |
| `UNDECLARED` | something observed at runtime is not in the release (e.g. a second model answered) |
| `UNAPPROVED RELEASE` | fewer pinned approvals than the effective threshold |
| `APPROVED AFTER USE` | the approvals that meet the threshold were signed after the decision was sealed |
| `RELEASE SEALED AFTER DECISION` | the release was sealed later than the decision |
| `DIRTY RELEASE` | the release pins an uncommitted code tree |
| `RELEASE NOT FOUND` | `release_ref` names nothing supplied (or the digest does not match) |
| `AMBIGUOUS RELEASE` | two supplied artifacts share the id; the verifier refuses to pick one |
| `NOT FULLY OBSERVED` | a component EPI could not see; never counted as a match |
| `NOT DECLARED` | the decision has no `release_ref` |

`epi verify` exits 0 for these by default (a warning), and 1 with
`--require-release` (or under `--policy strict` plus `--require-release`).
Decisions with no release keep their existing verdict unless
`--require-release` is passed.

**Ordering basis**, strongest first, printed with the result:

1. an RFC 3161 `gen_time` on both artifacts (independent);
2. the customer witness `received_at` of both reports, when `--witness-log`
   is supplied (independent);
3. the same ledger's seal sequence (strong but vendor-side);
4. the signed `created_at` (vendor clock, marked "not independent").

Approval time uses, in order: the approval's own RFC 3161 token, the
`received_at` of its own `epi.release_approval` report, then the approver's
signed `signed_at` (marked "not independent"). A decision report says nothing
about when an approval happened and is never used for that.

## Rollback and history

Rolling back is recording against an older release: the decision names it, and
verification shows which version each decision used. List the versions:

```bash
epi release history ./releases
epi release history ./releases --json
```

Rows are ordered by seal sequence (falling back to seal time) with the
approval count and status.

## What this does NOT prove

- EPI can only compare components it **observes**. Code that runs outside the
  instrumented path, an unobserved prompt, a retrieval index, a feature flag
  or a model alias can differ from the release without being noticed.
- The runtime `policy` component is the EPI policy file EPI loaded, not the
  vendor's business logic.
- A matching model id does not prove the provider served the same weights;
  an identifier is a label.
- `created_at`, `signed_at` and the seal sequence are vendor-side unless an
  independent basis is printed.
- An approval proves a pinned key signed this digest, not that the person saw
  the truth or approved before the action left the building.
- A decision that was never sealed at all is invisible here, exactly as in the
  customer witness.
