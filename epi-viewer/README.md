# EPI Viewer

**Evidence Inspection Instrument**

A cross-platform desktop application for viewing and verifying `.epi` cryptographic evidence files.

---

## What is EPI Viewer?

EPI Viewer is **not a document reader**—it's an **evidence inspection instrument** that:

✅ Verifies cryptographic signatures **before** rendering content  
✅ Validates file integrity using SHA-256 hashes  
✅ Displays evidence in a read-only, institutional interface  
✅ Provides 3-layer progressive disclosure (Narrative → Facts → Cryptographic)  
✅ Works completely offline (air-gapped ready)  

**Design Philosophy**: Institutional, minimal, trustworthy—built for regulators, auditors, and courts.

---

## Installation

### Prerequisites

**Node.js 18+** is required. Download from [nodejs.org](https://nodejs.org/)

### Quick Start

```bash
cd epi-viewer
npm install
npm start
```

This launches the viewer in development mode.

### Build Installers

```bash
# Windows installer
npm run build:win

# macOS installer  
npm run build:mac

# Linux installer
npm run build:linux
```

Installers will be created in the `dist/` directory.

---

## Usage

### Opening .epi Files

**Method 1: Double-Click** (after installation)
- `.epi` files will automatically open in EPI Viewer

**Method 2: File Dialog**
- Launch EPI Viewer
- Click "Open .epi File"

**Method 3: Drag & Drop**
- Drag an `.epi` file onto the viewer window

### Verification Flow

The viewer follows a strict **verify-before-render** security model:

```
1. Parse .epi file (ZIP structure)
2. Verify mimetype and manifest
3. Check file integrity (SHA-256 hashes)
4. Verify cryptographic signature (Ed25519)
5. ONLY if all checks pass → render content
```

**If verification fails, NOTHING is rendered.**

---

## Interface

### Status Banner (Always Visible)

```
✓ VERIFIED | Ed25519 | 2026-01-24T12:00:00Z | EPI 2.1.3
```

This banner stays visible at all times and cannot be hidden.

### Evidence Layers

**Layer 1: Narrative**  
Human-readable view with embedded viewer.html (if present).

**Layer 2: Facts**  
Structured table of metadata, inputs, outputs, environment.

**Layer 3: Cryptographic**  
Raw signatures, hashes, file manifest for expert review.

---

## Security Model

✅ **Fully local execution** - No network calls  
✅ **Sandboxed webview** - Embedded HTML runs in isolated environment  
✅ **Read-only** - No editing or mutations allowed  
✅ **Verify-before-render** - Content blocked until verified  
✅ **Air-gapped ready** - Works without internet  

---

## File Association

After installation, `.epi` files will be associated with EPI Viewer:

- **Windows**: Double-click opens viewer
- **macOS**: Double-click opens viewer  
- **Linux**: Double-click opens viewer (depends on desktop environment)

---

## Export Verification Report

Click **"Export Report"** to generate a verification certificate:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   EPI VERIFICATION REPORT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Status: VERIFIED ✓
Verified at: 2026-01-14T09:22:33Z
Verified by: EPI Viewer v1.0.0

[Evidence Summary]
Workflow ID: ...
Signature: VALID
Integrity: VALID

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

This report can be shared with auditors and regulators.

---

## Technology Stack

- **Electron 28** - Cross-platform desktop framework
- **Node.js** - Backend file processing & verification
- **Vanilla JavaScript** - Frontend (no frameworks)
- **Institutional CSS** - Minimal, professional styling

**Why Electron?**  
- Easier to maintain (JavaScript)  
- Faster to build  
- Good enough for desktop apps

**(Future: Tauri migration for smaller binaries)**

---

## Development

### Project Structure

```
epi-viewer/
├── main.js              # Electron main process (backend)
├── preload.js           # Security bridge
├── renderer/
│   ├── index.html       # UI layout
│   ├── styles.css       # Institutional styling
│   └── viewer.js        # Frontend logic
├── package.json         # Dependencies & build config
└── icons/               # App icons for branded distribution
```

### Running in Development

```bash
npm install
npm start
```

### Building for Distribution

```bash
# Install electron-builder globally (first time)
npm install -g electron-builder

# Build for your platform
npm run build:win   # Windows
npm run build:mac   # macOS
npm run build:linux # Linux
```

---

## Roadmap

### v1.0 (Current)
- [x] Basic file opening & verification
- [x] Verify-before-render security model
- [x] 3-layer evidence display
- [x] Export verification reports
- [x] Full Ed25519 signature verification
- [ ] File association installers
- [ ] App icons

### v1.1 (Future)
- [ ] Print verification report
- [ ] Batch verification (multiple files)
- [ ] Settings/preferences
- [ ] Export to PDF

### v2.0 (Future)
- [ ] Migrate to Tauri (smaller binaries)
- [ ] Full Rust-based verification
- [ ] Web-based viewer (WASM)

---

## Troubleshooting

### "Cannot find module 'extract-zip'"

```bash
npm install
```

### "epi files don't auto-open"

File associations are configured in `package.json` under `build.fileAssociations`.  
After installing the built application, they should work automatically.

### "Signature verification fails on legacy artifacts"

Current desktop verification supports current EPI v2+ manifest signatures.  
If you need older legacy v1 artifacts, verify them with the main Python `epi verify` flow.

---

## License

Apache 2.0 - See [LICENSE](../LICENSE)

---

## Contact

Part of the **EPI Recorder** project.  
Built with ❤️ by [Mohd Ibrahim Afridi](https://github.com/mohdibrahimaiml)

**Website**: [epilabs.org](https://epilabs.org)  
**Email**: epitechforworld@outlook.com

---

**Trust Your AI. Verify Everything.** 🔐


 
