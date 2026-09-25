# Step namespace rule (agt_adapter) — DRAFT

**Proposed. Not implemented. Not part of the current review. Requires a
version bump — renames agt_-prefixed fields and removes the duplicate
trace_id write.**

## Findings (why this rule is needed)

1. **`agt_` prefixes break one-to-one auditor traceability.** The shipped
   adapter writes `content.agt_entry_id` and `content.agt_entry_hash`
   where the AGT fields are named `entry_id` and `entry_hash`. An auditor
   mapping a step field back to the AGT record must know the renaming.
   Preserved payload should keep AGT's own field names.
2. **`trace_id` has two homes.** It is written to top-level `trace_id`
   (`StepModel`'s linkage field — the correct home) and duplicated into
   `content.trace_id`. Two copies of one value are two sources of truth.
3. **`agt_unknown_fields` needs naming as the single quarantine for
   unknown fields.** Unknown AGT fields must not spread as verbatim
   top-level keys (future-collision risk with EPI keys); they belong in
   one documented container.

## Proposed rule

Every value in a generated step has exactly one home. The namespace tells
the reader who is speaking — AGT's record or EPI's reading of it:

- `content.*` — preserved AGT payload, verbatim, in AGT's own field names,
  no interpretation. An auditor maps a `content` key back to the AGT field
  trivially. Defensive `agt_` prefixes are not used: they break that
  one-to-one traceability for no current collision. The single documented
  exception is `content.agt_unknown_fields`, a container for AGT fields
  unknown to the adapter — spreading them as verbatim top-level keys would
  risk collision with future EPI keys, so they are quarantined in one
  named place instead.
- `governance.*` — EPI's own derivation or normalisation (enum translations,
  extracted names). Every field here must be traceable to the input it was
  derived from, and that trace lives in the mapping report: a `governance`
  field with no provenance entry is a defect, not a shortcut.
- Top level (`kind`, `timestamp`, `index`, `trace_id`, spans) — EPI's own
  step fields. `trace_id` lives here because it is `StepModel`'s linkage
  field, not AGT payload; it is not duplicated into `content`.

Consequences: nothing verbatim in `governance.*`, nothing derived in
`content.*`, nothing in two places. A preserved value relabelled as an
assessment (e.g. an error restated as a correction, a recorded rule name
restated as policy authorship) violates this rule even when the value is
unchanged — the namespace, not just the bytes, is the claim.
