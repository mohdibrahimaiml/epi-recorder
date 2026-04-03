# Release Verification Checklist for v2.8.10

This checklist is the minimum release gate for `epi-recorder` v2.8.10 before publishing to PyPI and GitHub.

## Scope

v2.8.10 is a narrow corrective release focused on:

- packaging the two supported Colab notebooks into the source distribution
- keeping notebook assets out of the installed wheel
- auditing the source tarball so future releases cannot silently miss those notebooks again

## 1. Packaging Guard

Run:

```bash
pytest tests/test_audit_sdist.py tests/test_packaging_hygiene.py -q
```

Expected:

- tests pass
- the sdist audit requires:
  - `colab_demo.ipynb`
  - `EPI NEXUA VENTURES.ipynb`
- old notebook snapshots and `.tmp*` artifacts are rejected from the source release

## 2. Policy / Analyzer Regression Check

Run:

```bash
pytest tests/test_policy_loader.py tests/test_fault_analyzer.py tests/test_policy_cli.py -q
```

Expected:

- tests pass
- `approval_policies[].id` still works as an alias for `approval_id`
- list-valued `applies_at` still works in both policy loading and analyzer evaluation
- notebook-facing policy examples remain valid

## 3. Notebook Syntax Check

Run a Python syntax pass over:

- `colab_demo.ipynb`
- `EPI NEXUA VENTURES.ipynb`

Expected:

- all code cells parse successfully after stripping notebook magics

## 4. Full Release Gate

Run:

```bash
powershell -ExecutionPolicy Bypass -File scripts/release-gate.ps1
```

Expected:

- full suite passes
- `python -m build` completes successfully
- `twine check` passes
- source distribution audit passes
- wheel audit passes

## 5. Version / Installer Consistency

Run:

```bash
pytest tests/test_version_consistency_runtime.py -q
python -m epi_cli.main version
```

Expected:

- tests pass
- runtime version is `2.8.10`
- `pyproject.toml` and `installer/windows/setup.iss` both say `2.8.10`

## Release Verdict

`v2.8.10` is ready to release only if:

- targeted packaging and policy tests pass
- full release gate passes
- built artifacts are named `epi_recorder-2.8.10-*`
- documentation and current-version surfaces report `2.8.10`
- the source tarball contains exactly the two supported notebooks and no temporary packaging junk
