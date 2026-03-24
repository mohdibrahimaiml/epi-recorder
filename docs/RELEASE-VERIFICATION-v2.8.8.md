# Release Verification Checklist for v2.8.8

This checklist is the minimum release gate for `epi-recorder` v2.8.8 before publishing to PyPI and GitHub.

## Scope

v2.8.8 is a tight release-hardening cut focused on:

- clearer `epi policy validate` diagnostics
- OpenAI Agents-style event bridging
- reviewer flow polish in the embedded viewer
- installer and release-gate hardening

## 1. Python Package Verification

Run in a clean Python 3.11+ environment:

```bash
pip install --upgrade pip
pip install -e ".[dev]"
pytest tests/test_policy_cli.py tests/test_container.py tests/test_openai_agents_integration.py tests/test_version_consistency_runtime.py
```

Expected:

- tests pass
- `epi policy validate` accepts both `.json` policy files and `.epi` artifacts
- invalid JSON and schema errors are reported clearly
- OpenAI Agents-style event mapping is covered

## 2. Policy Validation Smoke Test

Create an invalid policy file:

```json
{
  "system_name": "bad-demo",
  "rules": [
    { "id": "R001", "type": "approval_guard", "severity": "critical" }
  ]
}
```

Run:

```bash
epi policy validate bad_policy.json
```

Expected:

- command exits non-zero
- output explains what is invalid
- JSON parse errors include line/column when the file is malformed

## 3. Agent Integration Smoke Test

Run:

```bash
pytest tests/test_openai_agents_integration.py -q
```

Expected:

- tests pass
- `OpenAIAgentsRecorder` and `record_openai_agent_events(...)` are importable from `epi_recorder.integrations`
- mapped events produce agent-native EPI steps

## 4. Viewer Reviewer Flow Check

Run:

```bash
pytest tests/test_container.py tests/test_container_with_analysis.py -q
```

Expected:

- tests pass
- artifacts embed `policy_evaluation.json` when policy is active
- jumping from a failed control to a timeline step auto-expands the target step details

## 5. Release / Installer Consistency

Run:

```bash
pytest tests/test_version_consistency_runtime.py -q
python -m epi_cli.main version
```

Expected:

- tests pass
- runtime version is `2.8.8`
- `pyproject.toml` and `installer/windows/setup.iss` both say `2.8.8`
- unsupported Inno task flags are rejected by tests

## 6. Full Release Gate

Run:

```bash
powershell -ExecutionPolicy Bypass -File scripts/release-gate.ps1
```

Expected:

- full suite passes
- `python -m build` completes successfully
- on Windows hosts with broken Python tempdir ACL behavior, the release gate injects a safe tempdir shim and still stays on the PEP 517 build path
- `twine check` passes
- wheel audit passes

## 7. Desktop Viewer Trust Smoke

Run:

```bash
node epi-viewer/test-signature.cjs
```

Expected:

- script passes
- Electron-side signature verification still agrees with the Python trust engine

## Release Verdict

`v2.8.8` is ready to release only if:

- all targeted tests pass
- the full release gate passes
- built artifacts are named `epi_recorder-2.8.8-*`
- documentation and versioned surfaces report `2.8.8`
