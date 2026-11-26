# Build the Microsoft Store package (.msix) from the PyInstaller bundle.
#
#   pyinstaller epi.spec --clean --noconfirm        # builds dist\epi\
#   .\scripts\build_msix.ps1 -Version 4.11.2 `
#       -IdentityName "<from Partner Center>" `
#       -Publisher "CN=<from Partner Center>" `
#       -PublisherDisplayName "EPI Labs"
#
# The package is written unsigned: the Microsoft Store signs it on publication.
# The identity values must match Partner Center (your app > Product identity)
# exactly, or the Store rejects the upload.
param(
    [Parameter(Mandatory = $true)][string]$Version,
    [Parameter(Mandatory = $true)][string]$IdentityName,
    [Parameter(Mandatory = $true)][string]$Publisher,
    [Parameter(Mandatory = $true)][string]$PublisherDisplayName,
    [string]$BundleDir = "dist\epi",
    [string]$OutDir = "installer\msix\Output",
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"

if ($Version -notmatch '^\d+\.\d+\.\d+$') { throw "Version must be X.Y.Z, got '$Version'" }
if ($Publisher -notmatch '^CN=') { throw "Publisher must start with 'CN=' (copy it from Partner Center)" }
if (-not (Test-Path "$BundleDir\epi.exe")) { throw "$BundleDir\epi.exe not found; run PyInstaller first" }

$msixVersion = "$Version.0"
$staging = Join-Path $env:RUNNER_TEMP "msix-staging"
if (-not $env:RUNNER_TEMP) { $staging = Join-Path ([IO.Path]::GetTempPath()) "msix-staging" }
if (Test-Path $staging) { Remove-Item $staging -Recurse -Force }
New-Item -ItemType Directory -Path "$staging\epi", "$staging\Assets" | Out-Null

Copy-Item "$BundleDir\*" "$staging\epi" -Recurse
& $Python scripts\msix_assets.py epi_core\assets\epi.ico "$staging\Assets"
if ($LASTEXITCODE -ne 0) { throw "Logo generation failed" }

# Values go into XML attributes and text, so escape them first.
function Escape-Xml([string]$s) { [System.Security.SecurityElement]::Escape($s) }
$manifest = Get-Content "installer\msix\AppxManifest.xml" -Raw
$manifest = $manifest.Replace("@IDENTITY_NAME@", (Escape-Xml $IdentityName)).
    Replace("@PUBLISHER@", (Escape-Xml $Publisher)).
    Replace("@PUBLISHER_DISPLAY_NAME@", (Escape-Xml $PublisherDisplayName)).
    Replace("@VERSION@", $msixVersion)
if ($manifest -match '@[A-Z_]+@') { throw "Unfilled placeholder in manifest: $($Matches[0])" }
[IO.File]::WriteAllText("$staging\AppxManifest.xml", $manifest, (New-Object System.Text.UTF8Encoding($false)))

$makeappx = Get-ChildItem "${env:ProgramFiles(x86)}\Windows Kits\10\bin" -Recurse -Filter makeappx.exe -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -match '\\x64\\' } |
    Sort-Object FullName -Descending | Select-Object -First 1
if (-not $makeappx) { throw "makeappx.exe not found; install the Windows 10/11 SDK" }

New-Item -ItemType Directory -Path $OutDir -Force | Out-Null
$out = Join-Path $OutDir "EPIRecorder-$Version-x64.msix"
& $makeappx.FullName pack /d $staging /p $out /o
if ($LASTEXITCODE -ne 0) { throw "makeappx pack failed" }

Write-Host "MSIX: $out ($([math]::Round((Get-Item $out).Length / 1MB, 1)) MB), version $msixVersion"
