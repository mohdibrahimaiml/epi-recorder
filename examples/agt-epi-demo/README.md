# AGT -> EPI Demo

Before: AGT evidence is spread across logs and JSON exports.

After: one signed `.epi` case file can be verified and opened locally.

## Convert AGT evidence into one portable case file

```bash
pip install epi-recorder
epi import agt sample_annex_bundle.json --out case.epi
epi verify case.epi
epi view case.epi
```

## What this gives you

- one portable case artifact
- full trace preserved
- policy and evaluation included
- raw AGT evidence preserved
- transformation audit visible
- trust independently verifiable

## Visual proof

![AGT evidence reopened as one portable case file with policy, evidence, trust, and transformation audit.](../../docs/assets/agt-epi-demo-case-view.png)

## Honesty note

This prototype uses the current neutral AGT evidence bundle already supported by `epi import agt`.

The intended AGT-side next step is for the Annex IV exporter to emit this shape directly or invoke an equivalent adapter.

## Related docs

- [AGT + .EPI docs](../../docs/agt-epi/README.md)
- [Artifact RFC](../../docs/agt-epi/artifact-rfc.md)
