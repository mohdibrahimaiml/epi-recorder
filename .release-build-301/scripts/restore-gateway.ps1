param(
    [Parameter(Mandatory = $true)]
    [string]$BackupFile,
    [string]$RestoreDir = "."
)

$resolvedBackup = Resolve-Path -LiteralPath $BackupFile -ErrorAction Stop
$resolvedRestoreDir = Resolve-Path -LiteralPath $RestoreDir -ErrorAction SilentlyContinue
if (-not $resolvedRestoreDir) {
    New-Item -ItemType Directory -Force -Path $RestoreDir | Out-Null
    $resolvedRestoreDir = Resolve-Path -LiteralPath $RestoreDir -ErrorAction Stop
}

Expand-Archive -Path $resolvedBackup.Path -DestinationPath $resolvedRestoreDir.Path -Force
Write-Host "Backup restored into $($resolvedRestoreDir.Path)"
