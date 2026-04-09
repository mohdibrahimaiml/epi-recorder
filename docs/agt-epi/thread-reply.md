I drafted a minimal RFC and built a working prototype for AGT -> `.epi` as an extension to the Annex IV exporter.

The current version keeps AGT unchanged and works on top of the existing neutral evidence bundle shape already supported by `epi import agt`.

Demo:

```bash
epi import agt examples/agt-epi-demo/sample_annex_bundle.json --out case.epi
epi verify case.epi
epi view case.epi
```

This turns AGT evidence into a single portable, verifiable case file with:
- decision and reasoning
- full trace
- policy evaluation
- preserved source data
- transformation audit
- independent trust verification

Without this, auditors still have to reconstruct decisions manually from logs and exports.

Links:
- RFC: `docs/agt-epi/artifact-rfc.md`
- Demo: `examples/agt-epi-demo/README.md`
- Screenshot: `docs/assets/agt-epi-demo-case-view.png`

Would appreciate feedback on whether this direction makes sense before taking it further toward an AGT-side integration.
