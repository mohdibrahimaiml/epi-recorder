# EPI DOC v4.0.2

Author: Codex  
Date: 2026-05-02  
Repo analyzed: `C:\Users\dell\epi-recorder`  
Release line observed in source: `v4.0.2`

---

## 1. What EPI is

EPI is an evidence system for AI workflows.

Its core job is simple:

- capture what happened
- seal it into one portable `.epi` case file
- let reviewers reopen it later
- let anyone verify that the artifact was not changed after sealing

The product center is still the artifact itself, not a hosted dashboard.

If you remember one sentence, remember this:

**EPI turns an AI workflow into a sealed, reviewable case file.**

---

## 2. What `v4.0.1` means

`v4.0.2` is the point where the product becomes much clearer in three different ways:

1. the artifact now has a stronger outer identity
2. the review experience now reads more like a case investigation system than a setup dashboard
3. **the viewer is now consistent across every open path** — `epi view`, `epi run`, `epi init`, Windows double-click, and offline sharing all show the same current decision-ops UI

Earlier EPI lines already had the core product idea:

- one portable artifact
- trust and signature checks
- browser review
- policy and human review layers
- AGT import as an evidence bridge

`v4.0.2` makes those ideas easier to trust, easier to understand, and guarantees the same review surface no matter how the artifact is opened.

In practical terms, the current `v4.0.2` line means:

- new `.epi` files no longer begin with ZIP magic bytes by default
- legacy ZIP-based `.epi` files still work
- the browser viewer opens into a case-first investigation flow
- the baked-in `viewer.html` uses the modern `epi-preloaded-cases` format, so even offline or double-click opens the same UI
- auto-open after `epi run` or `epi init` no longer creates throwaway temp dirs with stale HTML
- AGT-imported evidence is treated as a first-class source inside the same viewer
- the CLI and fresh-install paths are closer to the documented product surface

So `v4.0.2` is not only a format update.

It is a clearer, more consistent product line for:

- portable evidence
- local review
- provenance and transformation audit
- trust under scrutiny

`v4.0.1` keeps the same artifact wire format and adds the go-to-market layer around the product: opt-in telemetry, explicit pilot signup, safer GitHub Actions onboarding, and framework integration examples.

---

## 3. The most important mental model

The best mental model for the current product is:

```text
Capture -> Artifact -> Trust -> Investigation -> Sharing
```

In repo terms:

- `epi_recorder/` = capture and integrations
- `epi_core/` = artifact model, container logic, trust, policy, review
- `epi_cli/` = terminal front door
- `web_viewer/` = browser investigation UI
- `epi_gateway/` = shared review and capture infrastructure
- `pytest_epi/` = regression evidence capture

The key idea is still:

- capture once
- seal once
- review the same artifact later
- verify the same artifact later
- hand off one file instead of reconstructing logs

That is what makes EPI closer to a decision record than to generic observability.

---

## 4. The four main starting paths

### Developer repro path

Use this when you want to capture a run directly from Python:

```bash
pip install epi-recorder
epi demo
epi view <artifact>
epi verify <artifact>
```

This is the fastest path for a normal user to understand the product.

The current demo now produces a richer case file with:

- a named workflow
- explicit goal and notes
- review-required context
- clearer evidence steps for policy and handoff

### AGT import path

Use this when you already have exported Microsoft Agent Governance Toolkit evidence:

```bash
epi import agt examples/agt/sample_bundle.json --out sample.epi
epi verify sample.epi
epi view sample.epi
```

This is the cleanest path from governance evidence to a portable case artifact.

### Governed workflow path

Use this when you own the workflow and want policy-grounded review:

1. create or attach a policy
2. run the workflow with EPI capture
3. inspect `analysis.json` and `policy_evaluation.json`
4. review or export the resulting case

### Shared review path

Use this when a team needs a local/shared review workspace:

1. start `epi connect open`
2. review cases in the browser
3. export reviewed cases back to `.epi`

---

## 5. What a `.epi` file is in `v4.0.2`

The `.epi` artifact is the center of the whole product.

In the current `v4.0.2` line, it is a self-identifying binary envelope with a signed ZIP evidence payload inside it.

The most important practical change is this:

- older `.epi` files looked like ZIP files from the first bytes onward
- new `.epi` files start with `EPI1`

That means the artifact is more clearly its own thing when moved between systems or download channels.

The usual mental model is:

```text
EPI1 outer shell
    -> ZIP evidence payload
        -> manifest, steps, environment, analysis, policy, review, viewer, artifacts
```

Typical contents include:

- `manifest.json`
- `steps.jsonl`
- `environment.json`
- `analysis.json`
- `policy.json`
- `policy_evaluation.json`
- `review.json`
- `viewer.html` (now baked with the modern `epi-preloaded-cases` format for consistency across all open paths)
- `artifacts/...`

For AGT imports, important additional contents may include:

- `artifacts/agt/mapping_report.json`
- raw AGT payloads under `artifacts/agt/`
- imported annex or source materials under `artifacts/`

The important distinction is:

- EPI is not only a viewer
- EPI is a portable evidence format with a built-in trust model

---

## 6. Why the envelope change matters

The outer envelope change can sound small if you describe it only as a byte-format update.

It matters because the artifact itself is the product.

The current `v4.0.1` line improves three things:

### Artifact identity

The file is more clearly an EPI artifact instead of looking like a generic ZIP container.

### Transport credibility

Raw file sharing is less likely to trigger the "compressed folder" mental model or byte-signature classification path.

### Container abstraction discipline

The main product commands now have to work through a real container layer instead of assuming the outer file is a ZIP archive.

That makes the following surfaces more coherent:

- `epi view`
- `epi verify`
- `epi review`
- `epi share`
- `epi export-summary`
- `epi import agt`
- `epi migrate`

So the outer-envelope work is not just cosmetic. It reinforces the idea that `.epi` is its own evidence format.

---

## 7. Why the case-first viewer matters

The viewer is one of the most important product surfaces in the repo.

In earlier lines, the browser experience could still feel too much like a setup workspace or tooling shell.

In the current `v4.0.1` line, the viewer is much closer to a case investigation surface.

The important shift is:

- not "what app settings do I configure?"
- but "what happened, why, and what do I need to do next?"

The current case view is organized around:

- `Overview`
- `Evidence`
- `Policy`
- `Review`
- `Mapping`
- `Trust`
- `Attachments`

That is a better mental model for:

- engineers debugging a failure
- reviewers deciding whether to approve or reject
- auditors checking trust and provenance
- AGT users trying to understand imported governance evidence

This matters because the browser UI is where EPI stops being "just a format" and starts feeling like a product.

---

## 8. Why the AGT path matters even more in `v4.0.2`

The AGT integration story is one of the strongest parts of the current repo.

The important principle is:

**AGT is an imported evidence source inside EPI, not a separate product path.**

That is the right architecture because:

- AGT and EPI solve adjacent problems
- AGT is a governance/control-plane evidence source
- EPI is the portable artifact, trust, and review layer

The current viewer direction supports that well.

For AGT-imported artifacts, the UI can now clearly communicate:

- `Source system: AGT`
- `Import mode: EPI`
- trust and review state
- transformation audit availability
- preserved raw payloads

That is important because AGT users need to answer two different questions:

- "What did AGT say?"
- "What did EPI preserve, translate, or synthesize?"

The critical file here is:

- `artifacts/agt/mapping_report.json`

That file makes the AGT -> EPI conversion inspectable instead of opaque.

This is the right product relationship:

- AGT remains a source system
- EPI remains the artifact and trust system
- the viewer makes both intelligible in one place

---

## 9. What the current viewer should answer

At a product level, the current viewer should let someone answer:

### In 5 seconds

- what decision was made
- whether the file is trusted
- whether a person still needs to act
- what source system the case came from

### In 30 seconds

- why the decision happened
- what evidence and policy state matter most

### In 2 minutes

- which steps support the decision
- which findings or policy results matter
- what was imported or transformed

### In 5 minutes

- whether the full chain can be audited locally
- whether the artifact still holds up under scrutiny

That is a much better product target than "show all raw logs."

---

## 10. The trust model is still the moat

The trust model remains the most important differentiator.

EPI is not only valuable because it records data.

It is valuable because it can later answer:

- is this file intact?
- was it signed?
- did someone append review without overwriting sealed evidence?
- what exactly was part of the sealed case?

The current trust model still centers on:

- `file_manifest` hashing
- Ed25519 signatures
- verification through `epi verify`
- additive review rather than destructive overwrite

That matters because it lets the same file support:

- debugging
- review
- handoff
- evidence retention
- later audit

The viewer and CLI are important, but the moat is still the artifact and trust layer in `epi_core/`.

---

## 11. The CLI story is stronger when tested from a fresh install

One thing the current `v4.0.1` line makes clearer is that EPI has to be judged at the user surface, not only at the function surface.

That matters especially for:

- `epi demo`
- `epi view`
- `epi verify`
- `epi import agt`
- `epi debug`

The current line is stronger because the fresh-install path was exercised more like a real user would:

- install the package cleanly
- generate or import a case
- verify it
- open it in the browser

That is the right standard for this product, because the CLI is part of the public interface, not just a thin wrapper around internals.

---

## 12. What is most credible today

As of the current `v4.0.1` source line, EPI is strongest where someone may later ask:

- what happened
- why it happened
- which controls or policy outputs applied
- who reviewed it
- whether the artifact was changed
- what came from the source system versus EPI synthesis

That is why EPI fits especially well in:

- approvals
- denials
- escalations
- workflow audits
- agent bug-report artifacts
- compliance evidence handoff
- AGT evidence packaging and review

The strongest current mental model is:

**portable AI case files with built-in trust, review, and provenance**

---

## 13. Related docs

- [AGT Import Quickstart](AGT-IMPORT-QUICKSTART.md)
- [CLI Reference](CLI.md)
- [Policy Guide](POLICY.md)
- [Self-Hosted Runbook](SELF-HOSTED-RUNBOOK.md)
- [EPI Specification](EPI-SPEC.md)
- [EPI Codebase Walkthrough](EPI-CODEBASE-WALKTHROUGH.md)
- [Changelog](../CHANGELOG.md)

---

## 14. Final plain-language summary

EPI is infrastructure for portable AI case files.

`v4.0.2` strengthens that idea in the three places that matter most:

- the artifact is more clearly its own format
- the review experience is more clearly a case investigation system

That means the current product is easier to describe honestly:

- capture or import once
- seal once
- investigate locally
- verify trust
- hand off one artifact

That is the right shape for a product that wants to hold up under real scrutiny.
