$ErrorActionPreference = "Stop"

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

    throw "Could not find a writable root. Tried: $($Candidates -join ', ')"
}

$TempRoot = Resolve-WritableRoot -Candidates @(
    "C:\epi-temp",
    (Join-Path $env:LOCALAPPDATA "EPILabs\temp")
)

$PytestTempRoot = Resolve-WritableRoot -Candidates @(
    "C:\epi-pytest",
    (Join-Path $env:LOCALAPPDATA "EPILabs\pytest-temp")
)

[Environment]::SetEnvironmentVariable("TMP", $TempRoot, "User")
[Environment]::SetEnvironmentVariable("TEMP", $TempRoot, "User")

Write-Host "Configured Windows developer temp roots for EPI."
Write-Host "  TMP  = $TempRoot"
Write-Host "  TEMP = $TempRoot"
Write-Host "  pytest --basetemp should use $PytestTempRoot"
Write-Host ""
Write-Host "Next steps:"
Write-Host "  1. Restart your terminal so the new user environment variables are loaded."
Write-Host "  2. Run: powershell -ExecutionPolicy Bypass -File scripts\\run-tests.ps1"
Write-Host ""
Write-Host "Recommended Defender exclusions if temp locks persist:"
Write-Host "  - C:\epi-temp"
Write-Host "  - C:\epi-pytest"
Write-Host "  - C:\Users\dell\epi-recorder"
Write-Host "  - C:\Users\dell\epi-recorder\.venv-release"
