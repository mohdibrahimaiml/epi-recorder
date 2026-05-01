param(
    [string]$Python = ".\.venv-release\Scripts\python.exe"
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot

function Resolve-PythonCommand([string]$PythonValue) {
    if (Test-Path $PythonValue) {
        return (Resolve-Path $PythonValue).Path
    }

    $cmd = Get-Command $PythonValue -ErrorAction SilentlyContinue
    if ($cmd) {
        if ($cmd -is [array]) {
            return $cmd[0].Source
        }
        return $cmd.Source
    }

    throw "Python not found at '$PythonValue'. Pass -Python explicitly."
}

$PythonCmd = Resolve-PythonCommand $Python

$runId = Get-Date -Format "yyyyMMdd_HHmmss"
$gateRoot = Join-Path $repoRoot ".tmp-release-gate\$runId"
$baseTemp = Join-Path $gateRoot "pytest"
$buildTemp = Join-Path $gateRoot "build-tmp"
$distDir = Join-Path $gateRoot "dist"
$repoBuildDir = Join-Path $repoRoot "build"

New-Item -ItemType Directory -Path $baseTemp | Out-Null
New-Item -ItemType Directory -Path $buildTemp | Out-Null
New-Item -ItemType Directory -Path $distDir | Out-Null

if (Test-Path $repoBuildDir) {
    Remove-Item -Recurse -Force $repoBuildDir
}

$env:TMP = $buildTemp
$env:TEMP = $buildTemp

function Test-PythonTempWrite([string]$PythonExecutable) {
    $probeFile = Join-Path $buildTemp "temp-write-probe.py"
    $probeScript = @'
import pathlib
import tempfile

with tempfile.TemporaryDirectory() as d:
    path = pathlib.Path(d) / "input.json"
    path.write_text('{"ok": true}', encoding="utf-8")
    print(path)
'@

    Set-Content -Path $probeFile -Value $probeScript -Encoding UTF8
    try {
        cmd /d /c "`"$PythonExecutable`" `"$probeFile`" >nul 2>nul" | Out-Null
        return $LASTEXITCODE -eq 0
    }
    finally {
        Remove-Item -Path $probeFile -Force -ErrorAction SilentlyContinue
    }
}

function Write-PythonTempShim([string]$ShimDir, [string]$SafeTempDir) {
    New-Item -ItemType Directory -Path $ShimDir -Force | Out-Null
    New-Item -ItemType Directory -Path $SafeTempDir -Force | Out-Null

    $siteCustomize = @"
import os
import pathlib
import shutil
import tempfile
import uuid

_SAFE_BASE = pathlib.Path(r"$SafeTempDir")
_SAFE_BASE.mkdir(parents=True, exist_ok=True)

def _manual_mkdtemp(suffix=None, prefix=None, dir=None):
    base = pathlib.Path(dir) if dir else _SAFE_BASE
    base.mkdir(parents=True, exist_ok=True)
    name = f"{prefix or 'tmp'}{uuid.uuid4().hex}{suffix or ''}"
    path = base / name
    path.mkdir(parents=True, exist_ok=False)
    return str(path)

class _ManualTemporaryDirectory:
    def __init__(self, suffix=None, prefix=None, dir=None, ignore_cleanup_errors=False):
        self.name = _manual_mkdtemp(suffix=suffix, prefix=prefix, dir=dir)
        self._ignore_cleanup_errors = ignore_cleanup_errors

    def __enter__(self):
        return self.name

    def __exit__(self, exc_type, exc, tb):
        self.cleanup()
        return False

    def cleanup(self):
        shutil.rmtree(self.name, ignore_errors=self._ignore_cleanup_errors)

tempfile.mkdtemp = _manual_mkdtemp
tempfile.TemporaryDirectory = _ManualTemporaryDirectory
tempfile.tempdir = str(_SAFE_BASE)
os.environ["TMP"] = str(_SAFE_BASE)
os.environ["TEMP"] = str(_SAFE_BASE)
"@

    Set-Content -Path (Join-Path $ShimDir "sitecustomize.py") -Value $siteCustomize -Encoding UTF8
}

Write-Host "== EPI Release Gate =="
Write-Host "Repo: $repoRoot"
Write-Host "Python: $PythonCmd"
Write-Host ""

& $PythonCmd -m epi_cli.main version
if ($LASTEXITCODE -ne 0) { throw "Failed: epi version" }
& $PythonCmd -m pytest tests/test_version_consistency_runtime.py tests/test_truth_consistency.py -q --basetemp $baseTemp
if ($LASTEXITCODE -ne 0) { throw "Failed: targeted consistency tests" }
& $PythonCmd -m pytest tests -q --maxfail=20 --basetemp $baseTemp
if ($LASTEXITCODE -ne 0) { throw "Failed: full test suite" }

# Prefer PEP517 build. On hosts where Python tempfile directories have broken ACLs,
# inject a local sitecustomize shim so backend subprocesses use safe temp dirs.
$originalPythonPath = $env:PYTHONPATH
$usingTempShim = $false
if (-not (Test-PythonTempWrite $PythonCmd)) {
    $shimDir = Join-Path $gateRoot "pep517-temp-shim"
    $safeTempDir = Join-Path $gateRoot "pep517-safe-temp"
    Write-Host "Python tempfile probe failed on this host; injecting a safe tempdir shim for PEP 517 build."
    Write-PythonTempShim -ShimDir $shimDir -SafeTempDir $safeTempDir
    if ($originalPythonPath) {
        $env:PYTHONPATH = "$shimDir;$originalPythonPath"
    }
    else {
        $env:PYTHONPATH = $shimDir
    }
    $env:TMP = $safeTempDir
    $env:TEMP = $safeTempDir
    $usingTempShim = $true
}

& $PythonCmd -m build --no-isolation --sdist --wheel --outdir $distDir
$pep517Succeeded = $LASTEXITCODE -eq 0

if ($usingTempShim) {
    if ($null -ne $originalPythonPath -and $originalPythonPath -ne "") {
        $env:PYTHONPATH = $originalPythonPath
    }
    else {
        Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
    }
    $env:TMP = $buildTemp
    $env:TEMP = $buildTemp
}

if (-not $pep517Succeeded) {
    if (Test-Path $distDir) {
        Get-ChildItem -Path $distDir -File | Remove-Item -Force -ErrorAction SilentlyContinue
    }
    Write-Host "build failed in this environment; falling back to setup.py artifacts..."
    & $PythonCmd setup.py bdist_wheel --dist-dir $distDir
    if ($LASTEXITCODE -ne 0) { throw "Failed: wheel build fallback" }
    & $PythonCmd setup.py sdist --dist-dir $distDir
    if ($LASTEXITCODE -ne 0) { throw "Failed: sdist build fallback" }
}
$distFiles = Get-ChildItem -Path $distDir -File | Select-Object -ExpandProperty FullName
& $PythonCmd -m twine check $distFiles
if ($LASTEXITCODE -ne 0) { throw "Failed: twine check" }

$sdistFiles = Get-ChildItem -Path $distDir -Filter *.tar.gz | Select-Object -ExpandProperty FullName
if (-not $sdistFiles) { throw "Failed: no source distribution artifacts found for audit" }
& $PythonCmd (Join-Path $repoRoot "scripts\audit_sdist.py") $sdistFiles
if ($LASTEXITCODE -ne 0) { throw "Failed: sdist content audit" }

$wheelFiles = Get-ChildItem -Path $distDir -Filter *.whl | Select-Object -ExpandProperty FullName
if (-not $wheelFiles) { throw "Failed: no wheel artifacts found for audit" }
& $PythonCmd (Join-Path $repoRoot "scripts\audit_wheel.py") $wheelFiles
if ($LASTEXITCODE -ne 0) { throw "Failed: wheel content audit" }

Write-Host ""
Write-Host "Release gate PASSED. Artifacts in: $distDir"
