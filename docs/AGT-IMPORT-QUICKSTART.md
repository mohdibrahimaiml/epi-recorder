# AGT -> EPI Quickstart (v4.6.2)

If you already have exported Microsoft Agent Governance Toolkit evidence, this is the fastest path to a portable, signed `.epi` case file.

Related docs:
- [AGT example bundle](../examples/agt/README.md)
- [AGT -> EPI Demo](../examples/agt-epi-demo/README.md)

---

## 1. Clone And Install From The Repo Root

```bash
git clone https://github.com/mohdibrahimaiml/epi-recorder
cd epi-recorder
pip install .
```

This maintainer-safe quickstart uses the checked-in sample bundles and demo files from the `epi-recorder` repo itself.

---

## 2. Import AGT Evidence

`epi import agt` now accepts three EPI-side input forms:

- a neutral AGT bundle JSON
- a raw AGT evidence directory
- an EPI-owned AGT import manifest JSON

From the repo root, all of these work:

```bash
epi import agt examples/agt/sample_bundle.json --out sample.epi
epi import agt examples/agt/evidence-dir --out sample.epi
epi import agt examples/agt/manifest-input/agt_import_manifest.json --out sample.epi
```

Those commands convert exported AGT evidence into a normal `.epi` artifact that works with the rest of the EPI toolchain.

If you are not running from this repo checkout, replace the sample path with your own AGT bundle, AGT evidence directory, or AGT import manifest.

The manifest path is EPI-owned convenience input for raw AGT outputs. It maps non-standard filenames into the same internal bundle contract used by the converter.

---

## 3. Verify Trust

```bash
epi verify sample.epi
```

You should see a clean integrity result and, when a default signing key is available, a valid signature result.

---

## 4. Extract The Review Proof

```bash
epi view --extract review sample.epi
```

This produces a self-contained `review/` folder with `viewer.html`, the normalized trace, the policy artifacts, and the AGT transformation audit.

If you also want the interactive browser flow after that deterministic proof step:

```bash
epi view sample.epi
```

For AGT imports, the same eight-section viewer opens; expect:

- decision, review, and trust state in **0 Summary** and **3 Verdict**
- integrity/signature/chain details in **1 Integrity**
- normalized AGT steps in **4 Evidence**
- policy/control outcomes in **5 Governance**
- findings in **6 Analysis**, with provenance markers on imported steps
- the full transformation audit in `artifacts/agt/mapping_report.json`
  (also surfaced in the Appendix) — there is no separate `Mapping` panel

What you should expect inside the extracted review folder / artifact:

- `steps.jsonl` - normalized execution trace from AGT evidence
- `policy.json` - imported policy/rule document
- `policy_evaluation.json` - imported governance/control outcomes
- `analysis.json` - synthesized findings used by `epi review` when analysis is enabled
- `artifacts/agt/mapping_report.json` - transformation audit showing what the importer copied exactly, translated, derived, synthesized, preserved raw, or dropped

---

## 5. Strict Mode

If you want the importer to fail instead of falling back on unknown mappings or ambiguous dedupe cases:

```bash
epi import agt examples/agt/evidence-dir --out strict.epi --strict --dedupe fail
```

Useful options:

- `--analysis none` omits `analysis.json`
- `--no-attach-raw` skips attaching the source AGT payloads under `artifacts/agt/`

---

## 6. Why The Trust Story Is Clear

Imported AGT artifacts carry two trust layers:

1. EPI sealing and verification for the final `.epi` case file
2. `artifacts/agt/mapping_report.json` so the transformation itself is inspectable

That means a reviewer can answer both:

- "Is this artifact still intact?"
- "What happened during the AGT -> EPI conversion?"

---

## 7. Related Docs

- [CLI Reference](CLI.md)
- [EPI Specification](spec/EPI-SPEC.md)
- [AGT example bundle details](../examples/agt/README.md)
- [Docs index](README.md) · [Enterprise briefing](EPI_MASTER_DOCUMENTATION.md)
