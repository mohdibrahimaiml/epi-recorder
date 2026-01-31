/**
 * EPI Viewer - Preload Script
 * 
 * Secure bridge between main process and renderer.
 * Exposes only necessary APIs using contextBridge.
 */

const { contextBridge, ipcRenderer } = require('electron');

// Expose secure API to renderer
contextBridge.exposeInMainWorld('epiAPI', {
    // Open file dialog
    openFileDialog: () => ipcRenderer.invoke('open-file-dialog'),

    // Verify .epi file
    verifyEpiFile: (filePath) => ipcRenderer.invoke('verify-epi-file', filePath),

    // Cleanup temporary files
    cleanupTemp: (tempDir) => ipcRenderer.invoke('cleanup-temp', tempDir),

    // Listen for file open events
    onOpenFile: (callback) => {
        ipcRenderer.on('open-file', (event, filePath) => callback(filePath));
    }
});

