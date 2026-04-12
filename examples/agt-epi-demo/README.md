# AGT -> EPI Demo

Before: AGT evidence is spread across logs and JSON exports.

After: EPI adds the missing portable, verifiable case-file layer on top of AGT's existing evidence and Annex IV export path.

Without this, auditors still have to reconstruct decisions manually from logs and exports.

## Maintainer-proof flow from the repo root

```bash
git clone https://github.com/mohdibrahimaiml/epi-recorder
cd epi-recorder
pip install .
epi import agt examples/agt-epi-demo/sample_annex_bundle.json --out case.epi
epi verify case.epi
epi view --extract review case.epi
```

The same import path also accepts AGT-style raw outputs directly:

```bash
epi import agt examples/agt/evidence-dir --out case.epi
epi import agt examples/agt/manifest-input/agt_import_manifest.json --out case.epi
```

## What this gives you

- one portable case artifact
- full trace preserved
- policy and evaluation included
- raw AGT evidence preserved
- transformation audit visible
- trust independently verifiable

The deterministic proof output is the extracted `review/` folder. It should contain:

- `viewer.html`
- `steps.jsonl`
- `policy.json`
- `policy_evaluation.json`
- `analysis.json`
- `environment.json`
- `artifacts/annex_iv.md`
- `artifacts/annex_iv.json`
- `artifacts/agt/mapping_report.json`
- preserved raw AGT payloads under `artifacts/agt/`

After that deterministic check, you can optionally open the interactive review flow with:

```bash
epi view case.epi
```

## Visual proof

![AGT evidence reopened as one portable case file with policy, evidence, trust, and transformation audit.](../../docs/assets/agt-epi-demo-case-view.png)

What the viewer proves in one screen:

- decision-first case summary instead of raw logs
- source traceability with `AGT -> EPI import`
- independent trust verification
- explicit human review state
- policy and transformation audit in the same case file

## Honesty note

This prototype uses the current EPI-side AGT compatibility layer in `epi import agt`.

Today that path accepts a neutral AGT bundle, a raw AGT evidence directory, or an EPI-owned import manifest. AGT already has Annex IV export assembly. The intended AGT-side next step is for that exporter to emit one of those compatible inputs directly or invoke an equivalent EPI adapter.

## Related docs

- [AGT + .EPI docs](../../docs/agt-epi/README.md)
- [Artifact RFC](../../docs/agt-epi/artifact-rfc.md)
