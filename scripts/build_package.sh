#!/bin/bash
# Build script for EPI Recorder package
# Run this in bash/zsh to build distribution files

set -e  # Exit on error

echo "================================"
echo "EPI Recorder Package Builder"
echo "================================"
echo ""

# Check if build tools are installed
echo "Checking build tools..."
if ! python -m pip show build >/dev/null 2>&1 || ! python -m pip show twine >/dev/null 2>&1; then
    echo "Installing build tools (build and twine)..."
    python -m pip install --upgrade build twine
fi
echo "✓ Build tools ready"
echo ""

# Clean previous builds
echo "Cleaning previous builds..."
rm -rf dist/ build/ *.egg-info
echo "✓ Clean complete"
echo ""

# Run tests first
echo "Running tests..."
python -m pytest tests/ -v --tb=short
echo "✓ All tests passed"
echo ""

# Build the package
echo "Building package..."
python -m build
echo "✓ Build complete"
echo ""

# Check the distribution
echo "Checking distribution..."
twine check dist/*
echo "✓ Distribution check passed"
echo ""

# List created files
echo "Created files:"
ls -lh dist/
echo ""

# Next steps
echo "================================"
echo "Build Successful! 🎉"
echo "================================"
echo ""
echo "Next steps:"
echo "1. Upload to Test PyPI:"
echo "   twine upload --repository testpypi dist/*"
echo ""
echo "2. Test installation:"
echo "   pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ epi-recorder"
echo ""
echo "3. Upload to PyPI (when ready):"
echo "   twine upload dist/*"
echo ""

