# Build script for EPI Recorder package
# Run this in PowerShell to build distribution files

Write-Host "================================" -ForegroundColor Cyan
Write-Host "EPI Recorder Package Builder" -ForegroundColor Cyan
Write-Host "================================" -ForegroundColor Cyan
Write-Host ""

# Check if build tools are installed
Write-Host "Checking build tools..." -ForegroundColor Yellow
$hasBuild = python -m pip show build -ErrorAction SilentlyContinue
$hasTwine = python -m pip show twine -ErrorAction SilentlyContinue

if (-not $hasBuild -or -not $hasTwine) {
    Write-Host "Installing build tools (build and twine)..." -ForegroundColor Yellow
    python -m pip install --upgrade build twine
}

Write-Host "✓ Build tools ready" -ForegroundColor Green
Write-Host ""

# Clean previous builds
Write-Host "Cleaning previous builds..." -ForegroundColor Yellow
Remove-Item -Recurse -Force dist, build, *.egg-info -ErrorAction SilentlyContinue
Write-Host "✓ Clean complete" -ForegroundColor Green
Write-Host ""

# Run tests first
Write-Host "Running tests..." -ForegroundColor Yellow
python -m pytest tests/ -v --tb=short
if ($LASTEXITCODE -ne 0) {
    Write-Host "✗ Tests failed! Fix tests before building." -ForegroundColor Red
    exit 1
}
Write-Host "✓ All tests passed" -ForegroundColor Green
Write-Host ""

# Build the package
Write-Host "Building package..." -ForegroundColor Yellow
python -m build
if ($LASTEXITCODE -ne 0) {
    Write-Host "✗ Build failed!" -ForegroundColor Red
    exit 1
}
Write-Host "✓ Build complete" -ForegroundColor Green
Write-Host ""

# Check the distribution
Write-Host "Checking distribution..." -ForegroundColor Yellow
twine check dist/*
if ($LASTEXITCODE -ne 0) {
    Write-Host "✗ Distribution check failed!" -ForegroundColor Red
    exit 1
}
Write-Host "✓ Distribution check passed" -ForegroundColor Green
Write-Host ""

# List created files
Write-Host "Created files:" -ForegroundColor Cyan
Get-ChildItem dist/ | Format-Table Name, Length -AutoSize
Write-Host ""

# Next steps
Write-Host "================================" -ForegroundColor Cyan
Write-Host "Build Successful! 🎉" -ForegroundColor Green
Write-Host "================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "1. Upload to Test PyPI:" -ForegroundColor White
Write-Host "   twine upload --repository testpypi dist/*" -ForegroundColor Gray
Write-Host ""
Write-Host "2. Test installation:" -ForegroundColor White
Write-Host "   pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ epi-recorder" -ForegroundColor Gray
Write-Host ""
Write-Host "3. Upload to PyPI (when ready):" -ForegroundColor White
Write-Host "   twine upload dist/*" -ForegroundColor Gray
Write-Host ""

