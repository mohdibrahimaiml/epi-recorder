param(
    [string]$StorageDir = ".\.epi-data",
    [string]$OutFile = "",
    [string]$KeysDir = ""
)

$resolvedStorage = Resolve-Path -LiteralPath $StorageDir -ErrorAction Stop
if (-not $OutFile) {
    $timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $backupDir = Join-Path (Get-Location) "backups"
    New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
    $OutFile = Join-Path $backupDir "epi-gateway-backup-$timestamp.zip"
}

$stagingRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("epi-gateway-backup-" + [guid]::NewGuid().ToString("N"))
$stagingStorage = Join-Path $stagingRoot "storage"
New-Item -ItemType Directory -Force -Path $stagingStorage | Out-Null

$eventsPath = Join-Path $resolvedStorage.Path "events"
if (Test-Path -LiteralPath $eventsPath) {
    Copy-Item -LiteralPath $eventsPath -Destination (Join-Path $stagingStorage "events") -Recurse -Force
}

$databasePath = Join-Path $resolvedStorage.Path "cases.sqlite3"
if (Test-Path -LiteralPath $databasePath) {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if (-not $pythonCommand) {
        Remove-Item -LiteralPath $stagingRoot -Recurse -Force -ErrorAction SilentlyContinue
        throw "python is required to snapshot cases.sqlite3 during backup."
    }

    $snapshotScript = Join-Path $PSScriptRoot "sqlite_snapshot.py"
    & $pythonCommand.Source $snapshotScript $databasePath (Join-Path $stagingStorage "cases.sqlite3")
    if ($LASTEXITCODE -ne 0) {
        Remove-Item -LiteralPath $stagingRoot -Recurse -Force -ErrorAction SilentlyContinue
        throw "Failed to snapshot cases.sqlite3"
    }
}

$metadata = @{
    backup_version = 1
    created_at = (Get-Date).ToString("o")
    source_storage = $resolvedStorage.Path
    includes = @("events", "cases.sqlite3")
}
$metadata | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $stagingRoot "backup-metadata.json") -Encoding UTF8

if ($KeysDir) {
    $resolvedKeys = Resolve-Path -LiteralPath $KeysDir -ErrorAction Stop
    Copy-Item -LiteralPath $resolvedKeys.Path -Destination (Join-Path $stagingRoot "keys") -Recurse -Force
}

try {
    Compress-Archive -Path (Join-Path $stagingRoot "*") -DestinationPath $OutFile -Force
    Write-Host "Backup written to $OutFile"
}
finally {
    Remove-Item -LiteralPath $stagingRoot -Recurse -Force -ErrorAction SilentlyContinue
}
