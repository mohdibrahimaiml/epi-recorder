I drafted a minimal RFC and built a working prototype for AGT -> `.epi` as an extension to the Annex IV exporter.

AGT already has governance evidence and Annex IV export machinery. The current prototype keeps AGT unchanged and adds the missing portable, sealed case-file layer on top of that evidence path.

Runnable proof from the repo root:

```bash
git clone https://github.com/mohdibrahimaiml/epi-recorder
cd epi-recorder
pip install .
epi import agt examples/agt/evidence-dir --out case.epi
epi verify case.epi
epi view --extract review case.epi
```

The same `epi import agt` path also accepts a neutral AGT bundle JSON or an EPI-owned AGT import manifest. This prototype is still EPI-side today and does not claim native AGT integration yet. It turns AGT evidence into a single portable, verifiable case file with:
- decision and reasoning
- full trace
- policy evaluation
- preserved source data
- transformation audit
- independent trust verification

Without this, auditors still have to reconstruct decisions manually from logs and exports.

Links:
- Hub: `docs/agt-epi/README.md`
- RFC: `docs/agt-epi/artifact-rfc.md`
- Demo: `examples/agt-epi-demo/README.md`
- Screenshot: `docs/assets/agt-epi-demo-case-view.png`

Would appreciate feedback on whether this direction makes sense before taking it further toward an AGT-side adapter / exporter integration.
