# AGT + .EPI Docs

This kit demonstrates how AGT evidence can be turned into a portable, verifiable case artifact using `.epi`, without changing AGT itself.

AGT already has real runtime-governance evidence, compliance artifacts, and Annex IV export assembly. `.epi` does not replace that work. It adds the portable, sealed, reviewer-friendly case-artifact layer on top.

## What's included

- [Artifact RFC](artifact-rfc.md): proposal to add `.epi` as an optional Annex IV export layer
- [Thread reply](thread-reply.md): ready-to-post maintainer message with runnable repo-root proof
- [Runnable demo](../../examples/agt-epi-demo/README.md): deterministic maintainer proof using the existing `epi import agt` path
- [Visual proof](../assets/agt-epi-demo-case-view.png): AGT evidence reopened as a structured, verifiable case in the EPI viewer

## Positioning

- AGT stays unchanged
- AGT already has Annex IV export machinery; `.epi` is an optional portable artifact layer on top of that evidence/export path
- current prototype is still EPI-side and can start from a neutral bundle JSON, a raw AGT evidence directory, or an EPI-owned AGT import manifest
- direct bare Annex IV JSON ingestion is intentionally not claimed in this pass

## Why this matters

Today, AGT evidence can be generated and exported, but it still is not a single portable, independently verifiable case file a reviewer can reopen later with full trust.

This approach enables:

- a single portable case file
- full trace and policy evaluation
- preserved source evidence
- independent trust verification
