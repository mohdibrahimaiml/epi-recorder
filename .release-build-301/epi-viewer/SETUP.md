# EPI Viewer - Setup Instructions

## Quick Start (For You Right Now)

### 1. Install Node.js

**Download**: https://nodejs.org/  
**Version**: 18.x or later (LTS recommended)

### 2. Navigate to viewer directory

```powershell
cd c:\Users\dell\epi-recorder\epi-viewer
```

### 3. Install dependencies

```powershell
npm install
```

This will install:
- Electron (desktop framework)
- extract-zip (for .epi parsing)
- electron-builder (for creating installers)

### 4. Run the viewer

```powershell
npm start
```

The EPI Viewer window should open!

### 5. Test with your .epi files

Once the viewer is running:
1. Click "Open .epi File"
2. Navigate to `epi-recorder/epi-recordings/` or `distribution_ready/`
3. Select any `.epi` file
4. Watch it verify and display!

---

## Building Installers

Once you've tested and it works:

### Windows Installer

```powershell
npm run build:win
```

This creates:
- `dist/EPI Viewer Setup 1.0.0.exe` (installer)
- `dist/win-unpacked/` (portable version)

Users can double-click the installer, and after installation, `.epi` files will auto-open in EPI Viewer.

### macOS Installer (if you have a Mac)

```bash
npm run build:mac
```

### Linux Installer

```bash
npm run build:linux
```

Creates AppImage and .deb packages.

---

## Pre-Distribution Checklist

### 1. Add App Icons (Recommended Branding)

Create icons and place in `icons/` directory:
- `icon.ico` (Windows, 256x256)
- `icon.icns` (macOS)
- `icon.png` (Linux, 512x512)

You can use your EPI logo.

### 2. Verify Current Ed25519 Support

Signature verification is implemented for current EPI v2+ artifacts in the desktop app.

If you need older legacy v1 artifacts, verify them with the main Python `epi verify` flow.

### 3. Test File Associations

After building the installer:
1. Install it
2. Double-click a `.epi` file
3. Verify it opens in EPI Viewer

---

## Current Status

✅ Project structure created  
✅ Verify-before-render logic implemented  
✅ Institutional UI designed  
✅ 3-layer evidence display  
✅ File association configuration  
⏳ Waiting for Node.js installation  
⏳ Testing needed  
⏳ Icons needed  
✅ Full Ed25519 verification for current EPI v2+ artifacts

---

## Next Steps

1. **Install Node.js** (10 minutes)
2. **Run `npm install`** in viewer directory (2 minutes)
3. **Test with `npm start`** (immediate)
4. **If it works**, build installer with `npm run build:win`
5. **Share installer** with investors/users

Then you have a working EPI Viewer! 🚀


 
