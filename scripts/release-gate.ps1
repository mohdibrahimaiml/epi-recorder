param(
    [string]$Python = ".\.venv-release\Scripts\python.exe"
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot

if (!(Test-Path $Python)) {
    throw "Python not found at '$Python'. Pass -Python explicitly."
}

$runId = Get-Date -Format "yyyyMMdd_HHmmss"
$gateRoot = Join-Path $repoRoot ".tmp-release-gate\$runId"
$baseTemp = Join-Path $gateRoot "pytest"
$buildTemp = Join-Path $gateRoot "build-tmp"
$distDir = Join-Path $gateRoot "dist"

New-Item -ItemType Directory -Path $baseTemp | Out-Null
New-Item -ItemType Directory -Path $buildTemp | Out-Null
New-Item -ItemType Directory -Path $distDir | Out-Null

$env:TMP = $buildTemp
$env:TEMP = $buildTemp

Write-Host "== EPI Release Gate =="
Write-Host "Repo: $repoRoot"
Write-Host "Python: $Python"
Write-Host ""

& $Python -m epi_cli.main version
if ($LASTEXITCODE -ne 0) { throw "Failed: epi version" }
& $Python -m pytest tests/test_version_consistency_runtime.py tests/test_truth_consistency.py -q --basetemp $baseTemp
if ($LASTEXITCODE -ne 0) { throw "Failed: targeted consistency tests" }
& $Python -m pytest tests -q --maxfail=20 --basetemp $baseTemp
if ($LASTEXITCODE -ne 0) { throw "Failed: full test suite" }

# Prefer PEP517 build; fallback for temp-constrained Windows environments.
& $Python -m build --no-isolation --sdist --wheel --outdir $distDir
if ($LASTEXITCODE -ne 0) {
    Write-Host "build failed in this environment; falling back to setup.py artifacts..."
    & $Python setup.py bdist_wheel --dist-dir $distDir
    if ($LASTEXITCODE -ne 0) { throw "Failed: wheel build fallback" }
    & $Python setup.py sdist --dist-dir $distDir
    if ($LASTEXITCODE -ne 0) { throw "Failed: sdist build fallback" }
}
& $Python -m twine check "$distDir\*"
if ($LASTEXITCODE -ne 0) { throw "Failed: twine check" }

Write-Host ""
Write-Host "Release gate PASSED. Artifacts in: $distDir"
