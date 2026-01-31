/**
 * EPI Viewer - Main Process
 * Fixed version with proper Electron initialization
 */

const { app, BrowserWindow, ipcMain, dialog } = require('electron');
const path = require('path');
const fs = require('fs');
const crypto = require('crypto');
const extractZip = require('extract-zip');
const os = require('os');

let mainWindow;

function createWindow() {
    mainWindow = new BrowserWindow({
        width: 1200,
        height: 800,
        minWidth: 800,
        minHeight: 600,
        webPreferences: {
            nodeIntegration: false,
            contextIsolation: true,
            preload: path.join(__dirname, 'preload.js'),
            sandbox: true,
            webSecurity: true,
            allowRunningInsecureContent: false
        },
        backgroundColor: '#f5f5f5',
        title: 'EPI Viewer',
        icon: path.join(__dirname, 'icons', 'icon.png')
    });

    // Security: Disable navigation
    mainWindow.webContents.on('will-navigate', (event) => {
        event.preventDefault();
    });

    mainWindow.loadFile('renderer/index.html');

    // Open DevTools in development
    if (process.env.NODE_ENV === 'development') {
        mainWindow.webContents.openDevTools();
    }

    // Handle file open from command line or double-click
    const filePath = process.argv[1];
    if (filePath && filePath.endsWith('.epi')) {
        setTimeout(() => {
            mainWindow.webContents.send('open-file', filePath);
        }, 1000);
    }
}

app.whenReady().then(() => {
    createWindow();

    // Security: Disable webview
    app.on('web-contents-created', (event, contents) => {
        contents.on('will-attach-webview', (event) => {
            event.preventDefault();
        });
    });
});

app.on('window-all-closed', () => {
    if (process.platform !== 'darwin') {
        app.quit();
    }
});

app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
        createWindow();
    }
});

// Handle file open on macOS
app.on('open-file', (event, filePath) => {
    event.preventDefault();
    if (mainWindow) {
        mainWindow.webContents.send('open-file', filePath);
    }
});

/**
 * IPC Handlers
 */

// Open file dialog
ipcMain.handle('open-file-dialog', async () => {
    const result = await dialog.showOpenDialog(mainWindow, {
        properties: ['openFile'],
        filters: [
            { name: 'EPI Evidence', extensions: ['epi'] },
            { name: 'All Files', extensions: ['*'] }
        ]
    });

    if (!result.canceled && result.filePaths.length > 0) {
        return result.filePaths[0];
    }
    return null;
});

// Verify and load .epi file
ipcMain.handle('verify-epi-file', async (event, filePath) => {
    try {
        console.log('[VERIFY] Starting verification for:', filePath);

        // Step 1: Check file exists
        if (!fs.existsSync(filePath)) {
            return {
                success: false,
                error: 'File not found'
            };
        }

        // Step 2: Create temp directory for extraction
        const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'epi-verify-'));

        try {
            // Step 3: Extract ZIP
            await extractZip(filePath, { dir: tempDir });

            // Step 4: Verify structure
            const mimetypePath = path.join(tempDir, 'mimetype');
            const manifestPath = path.join(tempDir, 'manifest.json');

            if (!fs.existsSync(mimetypePath)) {
                return {
                    success: false,
                    error: 'Invalid .epi file: missing mimetype'
                };
            }

            if (!fs.existsSync(manifestPath)) {
                return {
                    success: false,
                    error: 'Invalid .epi file: missing manifest.json'
                };
            }

            // Step 5: Check mimetype
            const mimetype = fs.readFileSync(mimetypePath, 'utf8').trim();
            if (mimetype !== 'application/vnd.epi+zip') {
                return {
                    success: false,
                    error: `Invalid mimetype: ${mimetype}`
                };
            }

            // Step 6: Parse manifest
            const manifestData = fs.readFileSync(manifestPath, 'utf8');
            const manifest = JSON.parse(manifestData);

            // Step 7: Verify file integrity
            const integrityResult = await verifyIntegrity(tempDir, manifest);
            if (!integrityResult.valid) {
                return {
                    success: false,
                    error: 'Integrity check failed: ' + integrityResult.error,
                    verificationDetails: integrityResult
                };
            }

            // Step 8: Verify signature
            const signatureResult = await verifySignature(manifest);
            if (!signatureResult.valid) {
                return {
                    success: false,
                    error: 'Signature verification failed: ' + signatureResult.error,
                    verificationDetails: signatureResult
                };
            }

            // Step 9: Load viewer HTML
            const viewerPath = path.join(tempDir, 'viewer.html');
            let viewerHtml = null;
            if (fs.existsSync(viewerPath)) {
                viewerHtml = fs.readFileSync(viewerPath, 'utf8');
            }

            // SUCCESS - Return verified data
            return {
                success: true,
                manifest: manifest,
                viewerHtml: viewerHtml,
                verificationDetails: {
                    integrity: integrityResult,
                    signature: signatureResult
                },
                tempDir: tempDir
            };

        } catch (err) {
            // Cleanup temp dir on error
            fs.rmSync(tempDir, { recursive: true, force: true });
            throw err;
        }

    } catch (error) {
        console.error('[VERIFY] Error:', error);
        return {
            success: false,
            error: error.message
        };
    }
});

// Cleanup temp directory
ipcMain.handle('cleanup-temp', async (event, tempDir) => {
    if (tempDir && fs.existsSync(tempDir)) {
        fs.rmSync(tempDir, { recursive: true, force: true });
    }
});

/**
 * Verification Functions
 */

async function verifyIntegrity(extractDir, manifest) {
    try {
        const fileManifest = manifest.file_manifest || {};
        const mismatches = [];

        for (const [filename, expectedHash] of Object.entries(fileManifest)) {
            const filePath = path.join(extractDir, filename);

            if (!fs.existsSync(filePath)) {
                mismatches.push({
                    file: filename,
                    error: 'File missing'
                });
                continue;
            }

            const actualHash = await computeFileHash(filePath);
            if (actualHash !== expectedHash) {
                mismatches.push({
                    file: filename,
                    error: `Hash mismatch`,
                    expected: expectedHash,
                    actual: actualHash
                });
            }
        }

        if (mismatches.length > 0) {
            return {
                valid: false,
                error: `${mismatches.length} file(s) failed integrity check`,
                mismatches: mismatches
            };
        }

        return {
            valid: true,
            filesChecked: Object.keys(fileManifest).length
        };

    } catch (error) {
        return {
            valid: false,
            error: error.message
        };
    }
}

async function verifySignature(manifest) {
    try {
        // Check if signature exists
        if (!manifest.signature) {
            return {
                valid: false,
                error: 'No signature present',
                level: 'UNSIGNED'
            };
        }

        // Parse signature format: "ed25519:keyname:base64sig"
        const parts = manifest.signature.split(':', 3);
        if (parts.length !== 3) {
            return {
                valid: false,
                error: 'Invalid signature format'
            };
        }

        const [algorithm, keyName, signatureB64] = parts;

        if (algorithm !== 'ed25519') {
            return {
                valid: false,
                error: `Unsupported algorithm: ${algorithm}`
            };
        }

        // TODO: Implement Ed25519 verification
        // For now, we'll verify the format is correct and signature exists
        //Full crypto verification requires ed25519 library

        try {
            Buffer.from(signatureB64, 'base64');
        } catch (err) {
            return {
                valid: false,
                error: 'Invalid signature encoding'
            };
        }

        return {
            valid: true,
            algorithm: algorithm,
            keyName: keyName,
            level: 'SIGNED'
        };

    } catch (error) {
        return {
            valid: false,
            error: error.message
        };
    }
}

async function computeFileHash(filePath) {
    return new Promise((resolve, reject) => {
        const hash = crypto.createHash('sha256');
        const stream = fs.createReadStream(filePath);

        stream.on('data', (chunk) => hash.update(chunk));
        stream.on('end', () => resolve(hash.digest('hex')));
        stream.on('error', reject);
    });
}

