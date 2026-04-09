# AGT Import Examples

`epi import agt` accepts three AGT input shapes:

- `examples/agt/sample_bundle.json`
- `examples/agt/evidence-dir`
- `examples/agt/manifest-input/agt_import_manifest.json`

From the repo root:

```bash
epi import agt examples/agt/evidence-dir --out case.epi
epi verify case.epi
epi view --extract review case.epi
```

Use the other two inputs the same way:

```bash
epi import agt examples/agt/sample_bundle.json --out case.epi
epi import agt examples/agt/manifest-input/agt_import_manifest.json --out case.epi
```

Which input should you use?

- `sample_bundle.json`: you already have one aggregated AGT JSON file
- `evidence-dir/`: AGT outputs multiple files with standard names like `audit_logs.json`
- `agt_import_manifest.json`: your AGT filenames differ and need explicit mapping

Expected result:

- `sample.epi` or `case.epi` verifies cleanly
- `review/viewer.html` is extracted
- the artifact contains `steps.jsonl`, `policy.json`, `policy_evaluation.json`, and `artifacts/agt/mapping_report.json`

Optional interactive review:

```bash
epi view case.epi
```

If directory import fails:

- make sure the directory contains at least `audit_logs.json` or `flight_recorder.json`
- if filenames differ, add `agt_import_manifest.json`

Related docs:

- [AGT quickstart](../../docs/AGT-IMPORT-QUICKSTART.md)
- [AGT -> EPI demo](../agt-epi-demo/README.md)
- [AGT + .EPI docs](../../docs/agt-epi/README.md)
