# EPI Recorder Universal Installation Script for Windows
# Usage: iwr https://install.epilabs.org/epi.ps1 -useb | iex

$ErrorActionPreference = "Stop"

# Display banner
Write-Host ""
Write-Host "╔════════════════════════════════════════╗" -ForegroundColor Blue
Write-Host "║  EPI Recorder - Universal Installer   ║" -ForegroundColor Blue
Write-Host "╚════════════════════════════════════════╝" -ForegroundColor Blue
Write-Host ""

# Detect Python
Write-Host "→ Checking Python installation..." -ForegroundColor Blue

$PythonCommand = $null
foreach ($cmd in @("python", "python3", "py")) {
    try {
        $version = & $cmd --version 2>&1
        if ($version -match "Python 3\.(\d+)") {
            $PythonCommand = $cmd
            Write-Host "✓ Found Python: " -NoNewline -ForegroundColor Green
            Write-Host "$version" -ForegroundColor Cyan
            break
        }
    }
    catch {
        continue
    }
}

if (-not $PythonCommand) {
    Write-Host "✗ Python 3.11+ not found!" -ForegroundColor Red
    Write-Host "  Please install Python from: https://www.python.org/downloads/" -ForegroundColor Yellow
    exit 1
}

Write-Host ""

# Install EPI via pip
Write-Host "→ Installing EPI Recorder..." -ForegroundColor Blue
try {
    & $PythonCommand -m pip install --user --upgrade epi-recorder --quiet
    Write-Host "✓ EPI Recorder installed" -ForegroundColor Green
}
catch {
    Write-Host "✗ Installation failed: $_" -ForegroundColor Red
    exit 1
}

# Get Scripts directory
Write-Host ""
Write-Host "→ Configuring PATH..." -ForegroundColor Blue

$ScriptsDir = & $PythonCommand -c "import site; import os; print(os.path.join(site.USER_BASE, 'Scripts'))"
Write-Host "  Scripts directory: " -NoNewline
Write-Host "$ScriptsDir" -ForegroundColor Yellow

# Check if Scripts directory exists
if (-not (Test-Path $ScriptsDir)) {
    Write-Host "⚠ Scripts directory doesn't exist yet, creating..." -ForegroundColor Yellow
    New-Item -ItemType Directory -Path $ScriptsDir -Force | Out-Null
}

# Get current user PATH
$CurrentPath = [Environment]::GetEnvironmentVariable("Path", "User")

# Check if already in PATH
if ($CurrentPath -like "*$ScriptsDir*") {
    Write-Host "✓ PATH already configured" -ForegroundColor Green
}
else {
    Write-Host "→ Adding to PATH..." -ForegroundColor Blue
    
    try {
        # Add to user PATH
        $NewPath = "$CurrentPath;$ScriptsDir"
        [Environment]::SetEnvironmentVariable("Path", $NewPath, "User")
        
        # Also update current session
        $env:Path += ";$ScriptsDir"
        
        Write-Host "✓ PATH updated successfully" -ForegroundColor Green
    }
    catch {
        Write-Host "⚠ Could not update PATH automatically: $_" -ForegroundColor Yellow
        Write-Host ""
        Write-Host "Manual fix:" -ForegroundColor Yellow
        Write-Host "  1. Press Win + R" -ForegroundColor White
        Write-Host "  2. Type: sysdm.cpl" -ForegroundColor White
        Write-Host "  3. Advanced → Environment Variables" -ForegroundColor White
        Write-Host "  4. Edit user 'Path' variable" -ForegroundColor White
        Write-Host "  5. Add: $ScriptsDir" -ForegroundColor Cyan
    }
}

Write-Host ""
Write-Host "→ Verifying installation..." -ForegroundColor Blue

# Test epi command
$EpiWorks = $false
try {
    $TestResult = & epi version 2>&1
    if ($LASTEXITCODE -eq 0 -or $TestResult -match "EPI|version") {
        $EpiWorks = $true
    }
}
catch {
    # Command not found
}

Write-Host ""

if ($EpiWorks) {
    # Success!
    Write-Host "╔════════════════════════════════════════╗" -ForegroundColor Green
    Write-Host "║    Installation Successful! 🎉         ║" -ForegroundColor Green
    Write-Host "╚════════════════════════════════════════╝" -ForegroundColor Green
    Write-Host ""
    Write-Host "Quick Start:" -ForegroundColor Blue
    Write-Host "  epi init          " -NoNewline -ForegroundColor Green
    Write-Host "# Interactive setup wizard"
    Write-Host "  epi run script.py " -NoNewline -ForegroundColor Green
    Write-Host "# Record your first script"
    Write-Host ""
}
else {
    Write-Host "⚠ EPI installed but command not immediately available" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Next Steps:" -ForegroundColor Blue
    Write-Host "  1. Close this PowerShell window" -ForegroundColor White
    Write-Host "  2. Open a NEW PowerShell window" -ForegroundColor White
    Write-Host "  3. Try: " -NoNewline -ForegroundColor White
    Write-Host "epi init" -ForegroundColor Green
    Write-Host ""
    Write-Host "Alternative (works immediately):" -ForegroundColor Yellow
    Write-Host "  python -m epi_cli init" -ForegroundColor Cyan
    Write-Host ""
}

Write-Host "Documentation: " -NoNewline
Write-Host "https://github.com/mohdibrahimaiml/EPI-V2.2.0" -ForegroundColor Cyan
Write-Host "Issues: " -NoNewline
Write-Host "https://github.com/mohdibrahimaiml/EPI-V2.2.0/issues" -ForegroundColor Cyan
Write-Host ""

