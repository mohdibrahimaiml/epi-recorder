# Release Verification Checklist for v2.8.2

This checklist is the minimum release gate for `epi-recorder` v2.8.2 before publishing to PyPI and GitHub.

## Scope

v2.8.2 introduces these release-critical areas:

- policy-grounded fault analysis
- Windows `.epi` opening and icon behavior
- installer-backed Windows user experience

## 1. Python Package Verification

Run in a clean Python 3.11+ environment:

```bash
pip install --upgrade pip
pip install -e ".[dev]"
pytest tests/test_fault_analyzer.py tests/test_container_with_analysis.py tests/test_associate.py tests/test_associate_extended.py
```

Expected:

- tests pass
- `threshold_guard` and `prohibition_guard` enforcement is covered
- invalid `epi_policy.json` produces a warning but does not break packing

## 2. Policy / Fault Analysis Smoke Test

Run:

```bash
python scripts/smoke_policy_fault_analysis.py
```

Expected:

- script exits successfully
- analysis detects a policy violation
- produced `analysis.json` includes `fault_detected: true`
- produced `analysis.json` includes a `rule_id`

## 3. Packaging Verification

Build:

```bash
pyinstaller epi.spec --clean --noconfirm
```

Expected:

- `dist/epi/epi.exe` exists
- `epi.exe --version` reports `2.8.2`
- bundled app includes the `.epi` icon and viewer assets

## 4. Windows Installer Verification

Build:

```powershell
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" "installer\windows\setup.iss"
```

Expected:

- installer artifact created in `installer/windows/Output/`
- installer filename uses `2.8.2`

## 5. Clean Windows Machine / VM Verification

This must be done on a clean Windows machine or VM, not a dirty dev box.

### Installer path

1. Run `epi-setup-2.8.2.exe`
2. Confirm install completes successfully
3. Confirm `.epi` icon is visible in Explorer
4. Double-click a known-good `.epi` file
5. Confirm viewer opens successfully
6. Reboot machine
7. Double-click the same `.epi` file again
8. Confirm viewer still opens successfully

### Developer path

1. Install Python
2. `pip install epi-recorder`
3. Run one `epi` command once
4. Run `epi associate` or `epi associate --system` as appropriate
5. Double-click a known-good `.epi`
6. Reboot machine
7. Confirm `.epi` still opens

## 6. Policy Workflow Verification

In a clean project directory:

```bash
epi policy init --yes
epi policy validate
epi run sample.py
```

Expected:

- `epi_policy.json` created successfully
- validation succeeds
- packed `.epi` contains `analysis.json`
- packed `.epi` contains `policy.json`

## 7. Review Workflow Verification

Run:

```bash
epi review <artifact.epi>
epi review <artifact.epi> show
```

Expected:

- reviewer can confirm or dismiss a policy violation
- `review.json` is appended to the artifact
- existing sealed evidence remains intact

## 8. Final Release Decision

Do not publish if any of these are false:

- package version says `2.8.2`
- targeted tests pass
- smoke test passes
- PyInstaller bundle builds
- Windows installer builds
- clean-machine double-click works before and after reboot
- policy + analysis + review workflow is demonstrably working
