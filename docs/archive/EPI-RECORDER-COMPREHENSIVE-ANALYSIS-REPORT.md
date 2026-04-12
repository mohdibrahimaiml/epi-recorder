# EPI Recorder - Comprehensive Product and Codebase Report

> Historical snapshot: this report describes the repository as analyzed on
> 2026-03-27 against the `v2.8.10` line. For current release references, use
> [`README.md`](../README.md), [`CLI.md`](../CLI.md), and [`EPI-SPEC.md`](../EPI-SPEC.md),
> which now target `v3.0.2`.

Version: `2.8.10`  
Language: Python `>=3.11`  
License: MIT  
Author: Mohd Ibrahim Afridi  
Organization: EPI Labs  
Report Date: 2026-03-27

## Table of Contents

1. Executive Summary
2. Analysis Method
3. What EPI Is Today
4. Repository Shape
5. Architecture Overview
6. Subsystem Analysis
7. Artifact and Trust Model
8. Product and UX Direction
9. Gateway and AI Infrastructure Direction
10. Testing and Verification Posture
11. Strengths
12. Risks and Current Gaps
13. Best-Fit Use Cases
14. Recommended Next Moves
15. Bottom-Line Assessment

## 1. Executive Summary

EPI is no longer just a Python recorder library.

In its current state, the repository implements three overlapping but related
product layers:

- a portable proof and trust system built around the `.epi` artifact
- a recorder and CLI product for developers and operators
- an emerging browser-based Decision Ops and gateway-based AI infrastructure layer

The durable center of the system is still the same:

1. capture workflow evidence
2. package it into a portable artifact
3. embed policy and analysis when available
4. allow later human review
5. verify trust and integrity at any later time

That core is real and technically differentiated. The strongest parts of the
repo are the proof format, trust layer, policy-backed analysis, and offline
reviewability.

The codebase is also clearly in transition. It now carries:

- the original artifact-first product
- a newer non-technical Decision Ops experience
- a new open-core AI infrastructure direction through `epi_gateway`

Those directions can reinforce each other, but they are not fully unified yet.

The most accurate current product definition is:

**EPI is a portable evidence, review, and trust layer for consequential AI decisions.**

The most important long-term opportunity is:

**turn that portable evidence model into the default capture and control layer for live AI systems, while keeping `.epi` as the exportable proof format.**

## 2. Analysis Method

This report is based on a full repo-level inspection of the `epi-recorder`
workspace on 2026-03-27.

The analysis included:

- top-level tree inventory
- package and doc inspection
- architecture and entrypoint review
- viewer and gateway surface review
- packaging and release script inspection
- test suite execution

The full automated test suite was run with:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run-tests.ps1 -q
```

Fresh result on 2026-03-27:

- `705 passed`
- `9 skipped`

The result indicates that the repository is not merely documented or aspirational.
It is actively regression-tested across core runtime, packaging, policy, trust,
viewer, and newer gateway flows.

## 3. What EPI Is Today

At the product level, EPI currently behaves as all of the following:

- a Python package for recording AI workflows
- a CLI for running, viewing, reviewing, verifying, and configuring evidence artifacts
- a portable artifact format with cryptographic trust properties
- a browser-based local reviewer experience
- a policy-backed fault analysis layer
- an early AI gateway and normalized capture layer

It is not yet a full multi-user enterprise control plane, but the repo now
contains the foundations for that direction.

The repo's current public positioning is reflected in:

- `README.md`
- `docs/EPI-SPEC.md`
- `docs/internal/OPEN-CORE-ARCHITECTURE.md`
- `docs/CLI.md`

The positioning has shifted from "developer recording tool" toward:

- AI evidence infrastructure
- system of record for consequential AI decisions
- open-source capture and proof with future enterprise control on top

## 4. Repository Shape

The workspace is a mix of product code, website work, examples, release
artifacts, and local development residue.

Important current signals:

- tracked files: `215`
- untracked files: `28`
- current git status entries: `48`

The largest directories in the workspace are not source code. They include:

- `epi-viewer/`
- `venv/`
- `.venv-release/`
- `dev/`
- `build/`

The core product source is concentrated in:

- `epi_core/`
- `epi_recorder/`
- `epi_cli/`
- `epi_gateway/`
- `web_viewer/`
- `epi_viewer_static/`
- `tests/`

This means the software itself is meaningful and reasonably scoped, but the
workspace as a whole is not cleanly separated between:

- runtime code
- website code
- release/build output
- local experimental residue

That matters because the repo can look more chaotic than the actual product
code really is.

## 5. Architecture Overview

EPI currently has five primary architecture layers.

### 5.1 Core Proof Layer

Main package:

- `epi_core`

Responsibilities:

- define the `.epi` artifact model
- canonical hashing and serialization
- manifest generation
- trust and signature verification
- review append semantics
- storage and workspace support

This is the moat.

### 5.2 Recorder Runtime Layer

Main package:

- `epi_recorder`

Responsibilities:

- expose `record(...)`
- manage recording sessions
- capture console and structured steps
- support agent-shaped traces
- expose integrations and wrappers

This is the main developer entrypoint.

### 5.3 Policy and Analysis Layer

Main modules:

- `epi_core/policy.py`
- `epi_core/fault_analyzer.py`

Responsibilities:

- load and validate `epi_policy.json`
- define starter policies and profiles
- evaluate workflow steps against rules
- produce structured findings and analysis payloads

This is what makes EPI more than generic tracing.

### 5.4 Operational and UX Layer

Main package:

- `epi_cli`

Responsibilities:

- CLI commands
- local setup and onboarding
- view, verify, review, connect, and gateway startup
- Windows association and install flows

This is the practical front door for many users.

### 5.5 Viewer and Gateway Layer

Main packages:

- `web_viewer`
- `epi_gateway`

Responsibilities:

- Decision Ops browser UI
- non-technical review flows
- setup wizard and local bridge behavior
- provider-normalized capture ingress
- early proxy/gateway functionality

This layer is the clearest sign of where the repo is going next.

## 6. Subsystem Analysis

### 6.1 `epi_core`

This is the strongest package in the repo.

Key files:

- `epi_core/container.py`
- `epi_core/trust.py`
- `epi_core/schemas.py`
- `epi_core/serialize.py`
- `epi_core/review.py`
- `epi_core/policy.py`
- `epi_core/fault_analyzer.py`
- `epi_core/capture.py`
- `epi_core/llm_capture.py`

What it does well:

- packages the artifact reliably
- signs and verifies manifests using Ed25519
- preserves additive review semantics
- embeds viewer data safely
- supports policy-backed analysis
- now includes a normalized capture schema for future infra use

Why it matters:

- if `epi_core` is strong, EPI remains defensible
- if `epi_core` weakens, the product becomes "just another trace layer"

### 6.2 `epi_recorder`

This is the developer-facing recording engine.

Key file:

- `epi_recorder/api.py`

What stands out:

- explicit `record(...)` remains the clearest recording path
- agent-oriented step modeling is now much richer than basic logging
- wrappers and integrations cover a broad spread of AI tooling
- bootstrap and stdout capture make `epi run` more forgiving and educational

This package is still central to adoption for engineers.

### 6.3 `epi_cli`

This is broad and operationally important.

Key files:

- `epi_cli/main.py`
- `epi_cli/view.py`
- `epi_cli/policy.py`
- `epi_cli/connect.py`
- `epi_cli/gateway.py`

What it does:

- run and record workflows
- verify artifacts
- open the Decision Ops browser surface
- initialize and edit policy
- launch a local bridge and viewer
- start the gateway

The CLI has become more than a shell wrapper. It now carries a significant
amount of product logic.

### 6.4 `web_viewer`

This is the new non-technical product surface.

Key files:

- `web_viewer/index.html`
- `web_viewer/app.js`
- `web_viewer/styles.css`

Current behavior:

- browser-first local review
- Quick Setup flow
- example case loading
- local connector bridge support
- live record preview
- policy editing
- review export and signed review handling
- offline reviewed `.epi` rebuild

This is the main reason EPI now feels more like a product than a devtool.

### 6.5 `epi_gateway`

This is the earliest version of EPI as AI infrastructure.

Key files:

- `epi_gateway/main.py`
- `epi_gateway/proxy.py`
- `epi_gateway/worker.py`

Current behavior:

- accepts normalized capture events
- accepts LLM capture payloads
- exposes OpenAI-compatible proxy route
- exposes Anthropic-compatible proxy route
- persists batches of capture events locally

What it is not yet:

- not yet a full case store
- not yet a full control plane backend
- not yet fully streamed/hardened infrastructure

But the direction is correct.

### 6.6 Viewer Multiplicity

The repo still has several viewer generations:

- `web_viewer/`
- `epi_viewer_static/`
- `epi_viewer.py`
- `epi-viewer/`

This is one of the clearest signs of transition and one of the biggest current
sources of conceptual duplication.

## 7. Artifact and Trust Model

The `.epi` file remains the real center of product value.

According to `docs/EPI-SPEC.md`, current artifacts are ZIP archives that may
contain:

- `mimetype`
- `steps.jsonl`
- `environment.json`
- `analysis.json`
- `policy.json`
- `policy_evaluation.json`
- `review.json`
- `viewer.html`
- `artifacts/`
- `manifest.json`

The trust model is strong and coherent:

- sealed files are hashed into `manifest.file_manifest`
- the manifest is signed with Ed25519
- the public key is embedded for verification
- `review.json` is additive
- the viewer is generated presentation content, not sealed source evidence

This is exactly the kind of design choice that supports auditability without
making the product brittle.

## 8. Product and UX Direction

The repository now reflects a deliberate move away from pure CLI-first usage.

That shift is visible in:

- `web_viewer/`
- `docs/internal/EPI-MVP-DECISION-OPS.md`
- `docs/internal/EPI-VNEXT-NONTECH-PLAN.md`
- `docs/internal/HIGH-RISK-ADOPTION-ROADMAP.md`

The intended product experience is now:

- inbox
- case review
- rules
- reports

This is commercially clearer than the original artifact-only framing.

The important thing the repo has done correctly is not to throw away the trust
layer underneath. The newer UI is trying to change the interface, not remove
the evidence model.

## 9. Gateway and AI Infrastructure Direction

The open-core infrastructure direction is now explicit in:

- `docs/internal/OPEN-CORE-ARCHITECTURE.md`
- `epi_core/capture.py`
- `epi_core/llm_capture.py`
- `epi_gateway/main.py`
- `epi_gateway/proxy.py`

The architectural thesis is:

- open-source capture and proof
- enterprise control plane on top
- `.epi` remains portable proof

This is the right direction if the goal is broader adoption.

The key architectural idea is strong:

- one canonical event model
- many provider adapters
- portable proof export underneath

That gives EPI a path to become infrastructure without abandoning what makes it
different.

## 10. Testing and Verification Posture

The repo has broad test coverage across:

- core container behavior
- trust and verification
- policy loading and CLI
- runtime and wrappers
- viewer packaging and browser flows
- install and Windows association logic
- gateway capture/proxy behavior

Fresh full-suite result on 2026-03-27:

- `714` collected
- `705 passed`
- `9 skipped`

This is a strong signal of engineering seriousness.

Coverage is not uniform. Lower-coverage areas include:

- `epi_cli/chat.py`
- `epi_cli/review.py`
- `epi_cli/gateway.py`
- parts of `epi_cli/connect.py`
- parts of newer capture normalization logic

So the core is well tested, while some newer product and infra surfaces still
need deeper coverage.

## 11. Strengths

- Clear artifact-based trust model
- Real Ed25519 verification path
- Strong policy and analysis depth
- Good developer ergonomics through recorder and wrappers
- Much improved non-technical browser experience
- Broad integration ambition without abandoning the core format
- Serious test posture
- Thoughtful open-core versus enterprise framing

## 12. Risks and Current Gaps

### 12.1 Repo Hygiene

The workspace contains a lot of local state, website work, temp roots, build
outputs, bundled assets, and duplicated surfaces.

That hurts readability and increases maintenance overhead.

### 12.2 Viewer Duplication

There are too many active viewer surfaces.

That creates ambiguity about which viewer is canonical and which one is legacy.

### 12.3 Gateway Immaturity

`epi_gateway` is strategically important but still early.

Today it is best understood as:

- real foundation
- not yet full infrastructure

### 12.4 Product Boundary Blur

The repo contains:

- runtime code
- website repo work
- product strategy docs
- notebooks
- deployment bundles

That makes the open-core boundary harder to perceive in code than it is in
docs.

### 12.5 Multi-User Reality

EPI is no longer purely local-first, but it is also not yet a full enterprise
shared review system with:

- auth
- RBAC
- durable reviewer queues
- organization-wide case store

## 13. Best-Fit Use Cases

EPI is strongest today for:

- refunds and approval workflows
- claims review
- support escalation review
- high-stakes internal AI workflows
- local or self-hosted governance pilots
- teams that care about portable trust and later proof

EPI is less ideal today for:

- generic chatbot observability
- teams that only want live cloud dashboards
- very large multi-tenant reviewer operations without a backend control plane

## 14. Recommended Next Moves

### Near-term

- consolidate viewer surfaces around `web_viewer`
- continue hardening `epi_gateway`
- add a real case store behind gateway capture
- let live gateway capture export directly to `.epi`
- keep improving shared reviewer workflows

### Product-level

- keep `.epi` as the portable proof format
- keep open capture and proof in the open repo
- move enterprise control concerns to a distinct layer
- avoid turning EPI into a generic workflow builder

### Repo-level

- separate product code from website/bundle residue more cleanly
- reduce workspace clutter
- tighten the canonical architecture story in code layout

## 15. Bottom-Line Assessment

EPI is technically stronger and commercially clearer than a typical early-stage
AI tooling project.

Its best qualities are not cosmetic:

- portable evidence
- cryptographic trust
- policy-grounded analysis
- human review
- offline verification

Those are real foundations for a category-defining product.

The repo is still in the middle of a transition from:

- developer recording tool

to:

- evidence and review product

and from there toward:

- open-core AI infrastructure with enterprise control on top

That transition is visible, and sometimes messy, but the direction is
coherent.

**Final conclusion:**

EPI already has a defensible core. The next challenge is not inventing value.
It is cleaning the repo boundaries, unifying the active product surfaces, and
turning the gateway plus reviewer plane into a truly operational system.
