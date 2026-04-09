# AGT + .EPI Docs

This kit demonstrates how AGT evidence can be turned into a portable, verifiable case artifact using `.epi`, without changing AGT itself.

## What's included

- [Artifact RFC](artifact-rfc.md): proposal to add `.epi` as an optional Annex IV export layer
- [Thread reply](thread-reply.md): ready-to-post maintainer message with runnable demo
- [Runnable demo](../../examples/agt-epi-demo/README.md): 2-minute proof using the existing `epi import agt` path
- [Visual proof](../assets/agt-epi-demo-case-view.png): AGT evidence reopened as a structured, verifiable case in the EPI viewer

## Positioning

- AGT stays unchanged
- `.epi` is an optional portable artifact layer, not a replacement
- current prototype is bundle-first (Annex IV-compatible shape)
- direct bare Annex IV JSON ingestion is intentionally not claimed in this pass

## Why this matters

Today, AGT evidence is distributed across logs and exports.

This approach enables:

- a single portable case file
- full trace and policy evaluation
- preserved source evidence
- independent trust verification
