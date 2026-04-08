# EPI DOC v4.0.0

**Status:** Current  
**Date:** 2026-04-08  
**Release line:** `v4.0.0`

---

## What changed

`v4.0.0` turns `.epi` into a self-identifying binary artifact format.

Before this release, `.epi` files were ZIP-based at the outermost layer. That
worked for tooling, but some download channels and operating systems treated
them like compressed folders because they started with ZIP magic bytes.

In `v4.0.0`, the outer file starts with an `EPI1` header instead:

- outer identity: `EPI1`
- payload length
- payload SHA-256
- embedded signed ZIP evidence payload

That means the evidence model stays the same while the transport identity gets
stronger.

---

## Why it matters

EPI is not just "logs in a ZIP." It is a portable evidence container for AI
runs:

- execution trace
- policy and control outcomes
- optional analysis
- optional human review
- cryptographic verification

The `v4.0.0` change strengthens the exact part that matters when the artifact
itself is the product: how `.epi` behaves when moved between systems.

The evidence viewer still travels inside the artifact as `viewer.html`, but
the operating system opens `.epi` through EPI tooling or file association.
Browsers do not execute the embedded viewer directly from inside the binary
container.

---

## Compatibility

`v4.0.0` is additive, not a reset.

- new artifacts default to the envelope format
- old ZIP-based `.epi` files still open normally
- `epi view`, `epi verify`, `epi review`, `epi share`, and `epi import agt`
  work across both formats
- `epi migrate` converts between the legacy ZIP container and the new envelope

---

## AGT path

The Microsoft AGT bridge still works the same way:

```bash
epi import agt bundle.json --out run.epi
epi verify run.epi
epi view run.epi
```

The difference is that the resulting `.epi` now has a stronger outer container
identity while preserving:

- `steps.jsonl`
- `policy.json`
- `policy_evaluation.json`
- `analysis.json`
- `artifacts/agt/mapping_report.json`

---

## Mental model

Think of `v4.0.0` like this:

```text
same evidence payload
+ stronger outer shell
= more credible artifact format
```

For the precise wire format, see [EPI-SPEC.md](./EPI-SPEC.md).
