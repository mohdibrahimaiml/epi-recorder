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
const { verifyManifestSignature } = require('./lib/verification.cjs');

let mainWindow;
const EPI_ENVELOPE_MAGIC = Buffer.from('EPI1', 'ascii');
const EPI_ENVELOPE_VERSION = 1;
const EPI_PAYLOAD_FORMAT_ZIP_V1 = 0x01;
const EPI_ENVELOPE_HEADER_SIZE = 64;

function resolveInitialEpiArg(argv = process.argv) {
    for (const arg of argv.slice(1)) {
        if (typeof arg === 'string' && arg.toLowerCase().endsWith('.epi')) {
            return path.resolve(arg);
        }
    }
    return null;
}

function readUInt64LE(buffer, offset) {
    const low = buffer.readUInt32LE(offset);
    const high = buffer.readUInt32LE(offset + 4);
    return (BigInt(high) << 32n) | BigInt(low);
}

function detectEnvelope(filePath) {
    const fd = fs.openSync(filePath, 'r');
    try {
        const header = Buffer.alloc(EPI_ENVELOPE_HEADER_SIZE);
        const bytesRead = fs.readSync(fd, header, 0, EPI_ENVELOPE_HEADER_SIZE, 0);
        if (bytesRead < 4) {
            return null;
        }
        if (!header.subarray(0, 4).equals(EPI_ENVELOPE_MAGIC)) {
            return null;
        }
        if (bytesRead < EPI_ENVELOPE_HEADER_SIZE) {
            throw new Error('EPI envelope is too small to contain a valid header');
        }

        const version = header.readUInt8(4);
        const payloadFormat = header.readUInt8(5);
        const reservedFlags = header.readUInt16LE(6);
        const payloadLength = readUInt64LE(header, 8);
        const payloadSha256 = header.subarray(16, 48);
        const reservedTail = header.subarray(48, 64);

        if (version !== EPI_ENVELOPE_VERSION) {
            throw new Error(`Unsupported EPI envelope version: ${version}`);
        }
        if (payloadFormat !== EPI_PAYLOAD_FORMAT_ZIP_V1) {
            throw new Error(`Unsupported EPI payload format: ${payloadFormat}`);
        }
        if (reservedFlags !== 0) {
            throw new Error('Invalid EPI envelope header: reserved flags must be zero');
        }
        if (!reservedTail.equals(Buffer.alloc(reservedTail.length))) {
            throw new Error('Invalid EPI envelope header: reserved bytes must be zero');
        }

        const stats = fs.statSync(filePath);
        const expectedSize = BigInt(EPI_ENVELOPE_HEADER_SIZE) + payloadLength;
        if (payloadLength <= 0n || expectedSize !== BigInt(stats.size)) {
            throw new Error('Invalid EPI envelope payload length');
        }

        return {
            payloadLength,
            payloadSha256,
        };
    } finally {
        fs.closeSync(fd);
    }
}

function extractEpiPayload(filePath, outputPath) {
    const envelope = detectEnvelope(filePath);
    if (!envelope) {
        return filePath;
    }

    const hash = crypto.createHash('sha256');
    const readStream = fs.createReadStream(filePath, { start: EPI_ENVELOPE_HEADER_SIZE });
    const writeStream = fs.createWriteStream(outputPath);

    return new Promise((resolve, reject) => {
        readStream.on('data', (chunk) => hash.update(chunk));
        readStream.on('error', reject);
        writeStream.on('error', reject);
        writeStream.on('finish', () => {
            const actualSize = fs.statSync(outputPath).size;
            if (BigInt(actualSize) !== envelope.payloadLength) {
                reject(new Error('Unexpected payload length while extracting EPI envelope'));
                return;
            }
            const actualHash = hash.digest();
            if (!actualHash.equals(envelope.payloadSha256)) {
                reject(new Error('EPI envelope payload hash mismatch'));
                return;
            }
            resolve(outputPath);
        });
        readStream.pipe(writeStream);
    });
}

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
    const filePath = resolveInitialEpiArg();
    if (filePath) {
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
            // Step 3: Extract the inner ZIP payload from either legacy or envelope containers
            const payloadPath = path.join(tempDir, 'payload.zip');
            const extractedPayload = await extractEpiPayload(filePath, payloadPath);
            await extractZip(extractedPayload, { dir: tempDir });

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
    return verifyManifestSignature(manifest);
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


 
