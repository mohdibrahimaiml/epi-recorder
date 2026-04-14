Demo assets for AGT interoperability
===================================

This folder documents the demo bundle produced for the AGT interoperability
release. The repository includes a runnable demo that writes a sealed `.epi`
artifact in `epi-recordings/demo_refund.epi` and an associated AGT export
(`epi-recordings/demo_refund.agt.json`) created by the verifier.

Included artifacts (when present):

- `epi-recordings/demo_refund.epi` — sealed EPI artifact produced by the demo
- `epi-recordings/demo_refund.agt.json` — AGT-style JSON export produced by the exporter

How to recreate the demo bundle (local):

1. Run the demo script to generate the `.epi` artifact:

   python demo_refund.py

2. Create the AGT export and package assets (scripts/package_demo.py will
   attempt to find the latest demo artifact and bundle it):

   python scripts/package_demo.py --out release/demo_refund_demo.zip

Notes:

- The packaging script is best-effort and will skip missing files rather than
  failing; it is intended to quickly produce a bundle for demos and slides.
- The `tests/verify_3layer.py` script shows the verification workflow used in
  testing and can be used to reproduce the exported AGT JSON for the demo.
