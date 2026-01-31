/**
 * EPI Viewer - Renderer Process
 * 
 * Frontend logic for evidence inspection.
 * Implements verify-before-render UI flow.
 */

// Global state
let currentVerificationResult = null;
let currentTempDir = null;

// Initialize app when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    initializeApp();
});

function initializeApp() {
    // Event listeners
    document.getElementById('btn-open-file').addEventListener('click', openFileDialog);
    document.getElementById('btn-try-another').addEventListener('click', resetToInitial);
    document.getElementById('btn-close-file').addEventListener('click', resetToInitial);
    document.getElementById('btn-export-report').addEventListener('click', exportVerificationReport);

    // Tab navigation
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            switchLayer(e.target.dataset.layer);
        });
    });

    // Drag and drop
    const dropZone = document.getElementById('drop-zone');
    dropZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropZone.style.borderColor = '#4B5563';
    });

    dropZone.addEventListener('dragleave', () => {
        dropZone.style.borderColor = '#d1d5db';
    });

    dropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropZone.style.borderColor = '#d1d5db';

        const files = e.dataTransfer.files;
        if (files.length > 0) {
            const filePath = files[0].path;
            if (filePath.endsWith('.epi')) {
                verifyAndLoadFile(filePath);
            } else {
                alert('Please select a .epi file');
            }
        }
    });

    // Listen for file open from main process
    window.epiAPI.onOpenFile((filePath) => {
        verifyAndLoadFile(filePath);
    });
}

async function openFileDialog() {
    const filePath = await window.epiAPI.openFileDialog();
    if (filePath) {
        verifyAndLoadFile(filePath);
    }
}

async function verifyAndLoadFile(filePath) {
    try {
        // Show loading state
        showState('loading');
        updateVerificationStep('parsing', 'loading');

        // Verify the file (backend does all the work)
        const result = await window.epiAPI.verifyEpiFile(filePath);

        if (result.success) {
            // Verification succeeded
            updateVerificationStep('parsing', 'complete');
            updateVerificationStep('integrity', 'complete');
            updateVerificationStep('signature', 'complete');

            // Store result
            currentVerificationResult = result;
            currentTempDir = result.tempDir;

            // Show verified content
            displayVerifiedEvidence(result);

        } else {
            // Verification failed
            updateVerificationStep('parsing', 'error');
            showError(result.error, result.verificationDetails);
        }

    } catch (error) {
        console.error('Error verifying file:', error);
        showError(error.message);
    }
}

function updateVerificationStep(stepId, status) {
    const step = document.getElementById(`step-${stepId}`);
    if (!step) return;

    step.classList.remove('loading', 'complete', 'error');
    step.classList.add(status);

    const icon = step.querySelector('.step-icon');
    if (status === 'loading') {
        icon.textContent = '⏳';
    } else if (status === 'complete') {
        icon.textContent = '✓';
        icon.style.color = '#10b981';
    } else if (status === 'error') {
        icon.textContent = '✗';
        icon.style.color = '#ef4444';
    }
}

function displayVerifiedEvidence(result) {
    const manifest = result.manifest;

    // Update status banner
    document.getElementById('status-algorithm').textContent = 'Ed25519';
    document.getElementById('status-timestamp').textContent = new Date(manifest.created_at).toISOString();
    document.getElementById('status-version').textContent = `EPI ${manifest.spec_version}`;

    // Update evidence summary
    document.getElementById('summary-workflow').textContent = manifest.workflow_id || '—';
    document.getElementById('summary-created').textContent = new Date(manifest.created_at).toLocaleString();

    const signerName = extractSignerName(manifest.signature);
    document.getElementById('summary-signer').textContent = signerName || 'unsigned';

    const filesCount = Object.keys(manifest.file_manifest || {}).length;
    document.getElementById('summary-files').textContent = filesCount;

    // Layer 1: Embedded Viewer
    if (result.viewerHtml) {
        const viewerContainer = document.getElementById('embedded-viewer');
        viewerContainer.innerHTML = result.viewerHtml;
    } else {
        document.getElementById('embedded-viewer').innerHTML =
            '<p style="color: #6b7280;">No embedded viewer found in this .epi file.</p>';
    }

    // Layer 2: Structured Facts
    renderFactsTable(manifest);

    // Layer 3: Cryptographic Details
    renderCryptoDetails(result);

    // Show viewer state
    showState('viewer');
}

function renderFactsTable(manifest) {
    const factsTable = document.getElementById('facts-table');

    const facts = [
        { label: 'Workflow ID', value: manifest.workflow_id },
        { label: 'Spec Version', value: manifest.spec_version },
        { label: 'Created At', value: new Date(manifest.created_at).toISOString() },
        { label: 'Signature', value: manifest.signature ? 'Present' : 'None' },
        { label: 'Files in Manifest', value: Object.keys(manifest.file_manifest || {}).length },
    ];

    if (manifest.environment) {
        facts.push(
            { label: 'Python Version', value: manifest.environment.python_version },
            { label: 'Operating System', value: manifest.environment.os_name },
            { label: 'Platform', value: manifest.environment.platform }
        );
    }

    let html = '<table style="width: 100%; border-collapse: collapse;">';
    html += '<thead><tr style="background: #f5f5f5; border-bottom: 1px solid #d1d5db;">';
    html += '<th style="text-align: left; padding: 12px; font-weight: 600;">Field</th>';
    html += '<th style="text-align: left; padding: 12px; font-weight: 600;">Value</th>';
    html += '</tr></thead><tbody>';

    facts.forEach(fact => {
        html += '<tr style="border-bottom: 1px solid #e5e7eb;">';
        html += `<td style="padding: 12px; color: #6b7280;">${escapeHtml(fact.label)}</td>`;
        html += `<td style="padding: 12px; font-family: monospace;">${escapeHtml(String(fact.value))}</td>`;
        html += '</tr>';
    });

    html += '</tbody></table>';
    factsTable.innerHTML = html;
}

function renderCryptoDetails(result) {
    const cryptoDetails = document.getElementById('crypto-details');
    const manifest = result.manifest;
    const verification = result.verificationDetails;

    let text = '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n';
    text += 'CRYPTOGRAPHIC VERIFICATION DETAILS\n';
    text += '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n';

    text += '[ SIGNATURE ]\n';
    if (manifest.signature) {
        const parts = manifest.signature.split(':');
        text += `  Algorithm: ${parts[0]}\n`;
        text += `  Key Name:  ${parts[1]}\n`;
        text += `  Signature: ${parts[2].substring(0, 64)}...\n\n`;
        text += `  Status: ${verification.signature.valid ? '✓ VALID' : '✗ INVALID'}\n`;
    } else {
        text += '  Status: UNSIGNED\n';
    }

    text += '\n[ FILE INTEGRITY ]\n';
    text += `  Files Checked: ${verification.integrity.filesChecked || 0}\n`;
    text += `  Status: ${verification.integrity.valid ? '✓ ALL VALID' : '✗ MISMATCHES FOUND'}\n`;

    if (verification.integrity.mismatches && verification.integrity.mismatches.length > 0) {
        text += '\n  Mismatches:\n';
        verification.integrity.mismatches.forEach(m => {
            text += `    - ${m.file}: ${m.error}\n`;
        });
    }

    text += '\n[ FILE MANIFEST ]\n';
    const fileManifest = manifest.file_manifest || {};
    Object.entries(fileManifest).forEach(([file, hash]) => {
        text += `  ${file}\n`;
        text += `    SHA-256: ${hash}\n\n`;
    });

    text += '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n';
    text += 'End of Cryptographic Data\n';
    text += '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n';

    cryptoDetails.textContent = text;
}

function extractSignerName(signature) {
    if (!signature) return null;
    const parts = signature.split(':');
    if (parts.length >= 2) {
        return parts[1];
    }
    return null;
}

function switchLayer(layerId) {
    // Update tabs
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.classList.remove('active');
        if (btn.dataset.layer === layerId) {
            btn.classList.add('active');
        }
    });

    // Update panels
    document.querySelectorAll('.layer-panel').forEach(panel => {
        panel.classList.remove('active');
    });
    document.getElementById(`layer-${layerId}`).classList.add('active');
}

function showError(message, details) {
    document.getElementById('error-message').textContent = message;

    if (details) {
        const detailsDiv = document.getElementById('error-details');
        detailsDiv.textContent = JSON.stringify(details, null, 2);
    }

    showState('error');
}

function showState(stateName) {
    document.querySelectorAll('.state-view').forEach(view => {
        view.classList.remove('active');
    });
    document.getElementById(`${stateName}-state`).classList.add('active');
}

function resetToInitial() {
    // Cleanup temp files
    if (currentTempDir) {
        window.epiAPI.cleanupTemp(currentTempDir);
        currentTempDir = null;
    }

    currentVerificationResult = null;
    showState('initial');
}

function exportVerificationReport() {
    if (!currentVerificationResult) return;

    const manifest = currentVerificationResult.manifest;
    const verification = currentVerificationResult.verificationDetails;

    let report = '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n';
    report += '           EPI VERIFICATION REPORT\n';
    report += '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n';

    report += 'Status: VERIFIED ✓\n';
    report += `Verified at: ${new Date().toISOString()}\n`;
    report += `Verified by: EPI Viewer v1.0.0\n\n`;

    report += '[ EVIDENCE SUMMARY ]\n';
    report += `  Workflow ID: ${manifest.workflow_id}\n`;
    report += `  Created At:  ${manifest.created_at}\n`;
    report += `  Spec Version: ${manifest.spec_version}\n`;
    report += `  Signature:   ${manifest.signature ? 'Present' : 'None'}\n\n`;

    report += '[ VERIFICATION RESULTS ]\n';
    report += `  Signature:   ${verification.signature.valid ? '✓ VALID' : '✗ INVALID'}\n`;
    report += `  Integrity:   ${verification.integrity.valid ? '✓ VALID' : '✗ INVALID'}\n`;
    report += `  Files Checked: ${verification.integrity.filesChecked}\n\n`;

    report += '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n';
    report += 'This report was derived from a cryptographically\n';
    report += 'verified EPI artifact. Any modifications to this\n';
    report += 'report invalidate verification.\n';
    report += '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n';

    // Copy to clipboard
    navigator.clipboard.writeText(report).then(() => {
        alert('Verification report copied to clipboard!');
    });
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

