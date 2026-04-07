# AGT -> EPI Import Example

This example shows the neutral JSON bundle expected by `epi import agt`.

Generate an artifact from the checked-in sample bundle:

```bash
epi import agt examples/agt/sample_bundle.json --out sample.epi
epi verify sample.epi
epi view sample.epi
```

What you should see:

- `steps.jsonl` for the normalized AGT execution trace
- `policy.json` and `policy_evaluation.json` for the imported governance evidence
- `analysis.json` for synthesized review-ready findings
- `artifacts/agt/mapping_report.json` for the transformation audit

The sample payload mirrors real AGT evidence sections:

- `audit_logs`
- `flight_recorder`
- `compliance_report`
- `policy_document`
- `runtime_context`
- `slo_data`
- `annex_markdown` / `annex_json`

For a stricter import that fails on unknown mappings or ambiguous dedupe cases:

```bash
epi import agt examples/agt/sample_bundle.json --out strict.epi --strict --dedupe fail
```

For the public walkthrough, see [docs/AGT-IMPORT-QUICKSTART.md](../../docs/AGT-IMPORT-QUICKSTART.md).
