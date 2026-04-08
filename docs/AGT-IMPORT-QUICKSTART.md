# AGT -> EPI Quickstart (v4.0.0)

If you already have exported Microsoft Agent Governance Toolkit evidence, this is the fastest path to a portable, signed `.epi` case file.

---

## 1. Install

```bash
pip install epi-recorder
```

---

## 2. Import One Bundle

Use the checked-in sample bundle for the canonical first run:

```bash
epi import agt examples/agt/sample_bundle.json --out sample.epi
```

That command converts exported AGT evidence into a normal `.epi` artifact that works with the rest of the EPI toolchain.

If you are not running from this repo checkout, replace `examples/agt/sample_bundle.json` with your own exported AGT JSON bundle.

---

## 3. Verify Trust

```bash
epi verify sample.epi
```

You should see a clean integrity result and, when a default signing key is available, a valid signature result.

---

## 4. Open The Case

```bash
epi view sample.epi
```

This opens the case in the browser review flow.

What you should expect inside the artifact:

- `steps.jsonl` - normalized execution trace from AGT evidence
- `policy.json` - imported policy/rule document
- `policy_evaluation.json` - imported governance/control outcomes
- `analysis.json` - synthesized findings used by `epi review` when analysis is enabled
- `artifacts/agt/mapping_report.json` - transformation audit showing what the importer copied exactly, translated, derived, synthesized, preserved raw, or dropped

---

## 5. Strict Mode

If you want the importer to fail instead of falling back on unknown mappings or ambiguous dedupe cases:

```bash
epi import agt examples/agt/sample_bundle.json --out strict.epi --strict --dedupe fail
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
- [EPI Specification](EPI-SPEC.md)
- [AGT example bundle details](../examples/agt/README.md)
- [Flagship product explainer](EPI-DOC-v4.0.0.md)
