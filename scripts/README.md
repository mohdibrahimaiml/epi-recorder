# EPI Recorder - Installation Scripts

This directory contains universal installation scripts for EPI Recorder that automatically handle PATH configuration on all platforms.

## Scripts

### `install.sh` - Unix/Mac Installation
Universal installation script for Linux and macOS systems.

**Features:**
- Detects OS and Python version
- Installs epi-recorder via pip
- Auto-detects shell (bash/zsh/fish)
- Automatically adds to PATH
- Verifies installation
- Works with: Ubuntu, Debian, CentOS, macOS, etc.

### `install.ps1` - Windows Installation
Universal installation script for Windows systems.

**Features:**
- Detects Python installation
- Installs epi-recorder via pip
- Automatically updates Windows PATH registry
- Verifies installation
- Works with: Windows 10, Windows 11, Windows Server

## Hosting

These scripts should be hosted at:
- `https://install.epilabs.org/epi.sh` (Unix/Mac)
- `https://install.epilabs.org/epi.ps1` (Windows)

### GitHub Pages Setup

1. Create a repository: `epi-install`
2. Add these files to root
3. Enable GitHub Pages
4. Set up custom domain: `install.epilabs.org`

### Alternative: Static File Host

Upload to any static file hosting:
- AWS S3 + CloudFront
- Netlify
- Vercel
- GitHub Gists (for quick testing)

## Testing Locally

### Unix/Mac:
```bash
bash scripts/install.sh
```

### Windows:
```powershell
.\scripts\install.ps1
```

## Usage in Documentation

```markdown
## Installation

### Quick Install (Recommended)

**Unix/Mac:**
```bash
curl -sSL https://install.epilabs.org/epi.sh | sh
```

**Windows (PowerShell):**
```powershell
iwr https://install.epilabs.org/epi.ps1 -useb | iex
```

### Manual Install:
```bash
pip install epi-recorder
python -m epi_cli doctor  # If PATH issues
```
```

## Security

Both scripts:
- ✅ Use official pip to install
- ✅ Only modify user PATH (not system)
- ✅ Verify installation before completing
- ✅ Provide fallback instructions
- ✅ Never run arbitrary code
- ✅ Open source and auditable

Users can always review scripts before running:
```bash
curl -sSL https://install.epilabs.org/epi.sh  # View before running
```

