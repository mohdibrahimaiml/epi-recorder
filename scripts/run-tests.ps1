param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$PytestArgs
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$PythonExe = Join-Path $RepoRoot ".venv-release\Scripts\python.exe"

function Resolve-WritableRoot {
    param(
        [string[]]$Candidates
    )

    foreach ($candidate in $Candidates) {
        try {
            New-Item -ItemType Directory -Force -Path $candidate | Out-Null
            $probe = Join-Path $candidate ".epi_write_probe"
            Set-Content -Path $probe -Value "ok" -Encoding UTF8
            Remove-Item -Path $probe -Force -ErrorAction SilentlyContinue
            return $candidate
        }
        catch {
            continue
        }
    }

    throw "Could not find a writable temp root. Tried: $($Candidates -join ', ')"
}

$tempCandidates = @(
    "C:\epi-temp",
    (Join-Path $env:LOCALAPPDATA "EPILabs\temp"),
    (Join-Path $RepoRoot ".epi-temp")
)

$pytestTempCandidates = @(
    "C:\epi-pytest",
    (Join-Path $env:LOCALAPPDATA "EPILabs\pytest-temp"),
    (Join-Path $RepoRoot ".pytest-tmp")
)

$TempRoot = Resolve-WritableRoot -Candidates $tempCandidates
$PytestTempRoot = Resolve-WritableRoot -Candidates $pytestTempCandidates
$PytestRunRoot = Join-Path $PytestTempRoot ([guid]::NewGuid().ToString())

if (-not (Test-Path $PythonExe)) {
    Write-Error "Could not find repo test Python at $PythonExe"
}

New-Item -ItemType Directory -Force -Path $PytestRunRoot | Out-Null

$env:TMP = $TempRoot
$env:TEMP = $TempRoot
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"

$ArgsToRun = @("-m", "pytest", "--basetemp", $PytestRunRoot)
if ($PytestArgs) {
    $ArgsToRun += $PytestArgs
}

Write-Host "EPI local test runner"
Write-Host "  Python:    $PythonExe"
Write-Host "  TMP/TEMP:  $TempRoot"
Write-Host "  basetemp:  $PytestRunRoot"
Write-Host ""

Push-Location $RepoRoot
try {
    & $PythonExe @ArgsToRun
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
