# Using `.epi` artifacts for AI evidence preparation

**Product version:** 4.6.2.

This guide is for teams that need durable evidence for AI workflows.

It is not legal advice. EPI does not guarantee regulatory compliance, regulator approval, or suitability for a specific legal duty. Use it as evidence workflow infrastructure and review the final process with legal counsel.

There is no article-by-article “compliance matrix” in this repo. Annex IV support is **templates you fill**: [ANNEX-IV.md](./ANNEX-IV.md).

## What teams may need

High-risk AI workflows often need evidence that can answer practical review questions:

- what happened during the workflow
- when important steps happened
- which inputs, tools, controls, and decisions were involved
- whether the record was changed after it was sealed
- how reviewers can preserve and inspect the evidence later

Logs help, but logs are often system-local, mutable, and hard to hand to another reviewer. `.epi` artifacts package **captured** execution evidence into a portable file. Uninstrumented calls are not in the file.

## What `.epi` provides

EPI can provide:

- portable `.epi` artifacts
- `steps.jsonl` execution timelines
- timestamps for captured events
- sealed manifests with file hashes
- Ed25519 signatures when signing keys are configured
- offline CLI verification with `epi verify`
- browser-based review with `epi view`
- client-side browser verification at `https://epilabs.org/verify` (no upload)

Tool: https://github.com/mohdibrahimaiml/epi-recorder

Format spec (this repo): [spec/EPI-SPEC.md](./spec/EPI-SPEC.md)

## What `.epi` does not provide

EPI does not provide:

- a legal compliance guarantee
- regulator approval
- a substitute for legal counsel
- a complete risk-management system by itself
- automatic proof that the underlying AI system is safe, fair, or lawful
- proof that every model or tool call was captured

An `.epi` artifact can support an evidence process, but the organization remains responsible for policy, review, retention, governance, and legal interpretation.

## How to use EPI with AGT

When AGT evidence is available:

1. export AGT evidence
2. package it as `.epi`
3. verify the `.epi` artifact
4. review the mapped evidence
5. preserve the artifact and review notes according to your retention plan

Example:

```bash
epi import agt ./agt-export --out agt-case.epi
epi verify agt-case.epi
epi view agt-case.epi
```

Imported AGT payloads are preserved under `artifacts/agt/` when configured. EPI also writes `artifacts/agt/mapping_report.json` so reviewers can inspect what was preserved, translated, derived, or synthesized. Quickstart: [AGT-IMPORT-QUICKSTART.md](./AGT-IMPORT-QUICKSTART.md).

## Evidence checklist

Use this as a practical preparation checklist, not a legal compliance checklist:

- captured execution trace
- event timestamps present
- artifact integrity verified
- signature state reviewed
- verification report preserved
- reviewer notes recorded when needed
- retention plan documented
- source-system export mapping preserved when imported from another system

## Sample workflow

```bash
pip install epi-recorder
epi demo
epi verify epi-recordings/demo_refund.epi
epi view epi-recordings/demo_refund.epi
```

## Disclaimer

EPI supports evidence workflows. Compliance responsibility remains with the organization and its legal counsel.
