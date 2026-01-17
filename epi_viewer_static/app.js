/**
 * EPI Viewer - Static JavaScript Application
 * 
 * Renders .epi workflow timeline with zero code execution.
 * All data is loaded from embedded JSON.
 */

// Load embedded data
function loadEPIData() {
    const dataScript = document.getElementById('epi-data');
    if (!dataScript) {
        console.error('EPI data not found');
        return null;
    }
    try {
        return JSON.parse(dataScript.textContent);
    } catch (e) {
        console.error('Failed to parse EPI data:', e);
        return null;
    }
}

// Render trust badge
async function renderTrustBadge(manifest) {
    const badge = document.getElementById('trust-badge');
    if (!badge) return;

    // Initial state: checking
    badge.innerHTML = `
        <div class="trust-badge inline-flex items-center px-3 py-1 rounded-full text-sm font-medium bg-gray-100 text-gray-600">
            <svg class="animate-spin -ml-1 mr-2 h-4 w-4 text-gray-600" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
            </svg>
            Verifying...
        </div>
    `;

    // Check verification logic availability
    if (typeof window.verifyManifestSignature !== 'function') {
        renderBadgeResult(false, 'Missing crypto lib', manifest.signature != null);
        return;
    }

    try {
        const result = await window.verifyManifestSignature(manifest);
        console.log("Verification Result:", result);
        renderBadgeResult(result.valid, result.reason, manifest.signature != null);
    } catch (e) {
        console.error("Verification error:", e);
        renderBadgeResult(false, e.message, manifest.signature != null);
    }
}

function renderBadgeResult(isValid, reason, hasSignature) {
    const badge = document.getElementById('trust-badge');
    let badgeHTML;

    if (isValid) {
        badgeHTML = `
            <div class="trust-badge inline-flex items-center px-3 py-1 rounded-full text-sm font-medium bg-green-100 text-green-800" title="Cryptographically Verified">
                <svg class="w-4 h-4 mr-1" fill="currentColor" viewBox="0 0 20 20">
                    <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"/>
                </svg>
                Verified
            </div>
        `;
    } else if (!hasSignature) {
        badgeHTML = `
            <div class="trust-badge inline-flex items-center px-3 py-1 rounded-full text-sm font-medium bg-yellow-100 text-yellow-800">
                 Unsigned
            </div>
        `;
    } else {
        // Has signature but INVALID
        badgeHTML = `
            <div class="trust-badge inline-flex items-center px-3 py-1 rounded-full text-sm font-medium bg-red-100 text-red-800" title="Hash Mismatch: ${reason}">
                <svg class="w-4 h-4 mr-1" fill="currentColor" viewBox="0 0 20 20">
                    <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd"/>
                </svg>
                TAMPERED
            </div>
        `;
    }
    badge.innerHTML = badgeHTML;
}

// Render metadata section
function renderMetadata(manifest) {
    // Create metadata section container
    const metadataSection = document.createElement('div');
    metadataSection.className = 'bg-blue-50 rounded-lg p-4 mb-6';
    metadataSection.innerHTML = '<h3 class="text-lg font-semibold text-gray-900 mb-3">Recording Metadata</h3>';

    const metadataContent = document.createElement('div');
    metadataContent.className = 'space-y-3';

    // Goal
    if (manifest.goal) {
        const goalDiv = document.createElement('div');
        goalDiv.innerHTML = `
            <div class="text-gray-500 text-xs uppercase tracking-wide">Goal</div>
            <div class="mt-1">${escapeHTML(manifest.goal)}</div>
        `;
        metadataContent.appendChild(goalDiv);
    }

    // Notes
    if (manifest.notes) {
        const notesDiv = document.createElement('div');
        notesDiv.innerHTML = `
            <div class="text-gray-500 text-xs uppercase tracking-wide">Notes</div>
            <div class="mt-1">${escapeHTML(manifest.notes)}</div>
        `;
        metadataContent.appendChild(notesDiv);
    }

    // Metrics
    if (manifest.metrics && Object.keys(manifest.metrics).length > 0) {
        const metricsDiv = document.createElement('div');
        let metricsHtml = '<div class="text-gray-500 text-xs uppercase tracking-wide">Metrics</div><div class="mt-1 flex flex-wrap gap-2">';
        for (const [key, value] of Object.entries(manifest.metrics)) {
            metricsHtml += `<span class="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-purple-100 text-purple-800">${escapeHTML(key)}=${escapeHTML(String(value))}</span>`;
        }
        metricsHtml += '</div>';
        metricsDiv.innerHTML = metricsHtml;
        metadataContent.appendChild(metricsDiv);
    }

    // Approved by
    if (manifest.approved_by) {
        const approvedDiv = document.createElement('div');
        approvedDiv.innerHTML = `
            <div class="text-gray-500 text-xs uppercase tracking-wide">Approved By</div>
            <div class="mt-1">${escapeHTML(manifest.approved_by)}</div>
        `;
        metadataContent.appendChild(approvedDiv);
    }

    // Tags
    if (manifest.tags && manifest.tags.length > 0) {
        const tagsDiv = document.createElement('div');
        let tagsHtml = '<div class="text-gray-500 text-xs uppercase tracking-wide">Tags</div><div class="mt-1 flex flex-wrap gap-2">';
        for (const tag of manifest.tags) {
            tagsHtml += `<span class="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-green-100 text-green-800">${escapeHTML(tag)}</span>`;
        }
        tagsHtml += '</div>';
        tagsDiv.innerHTML = tagsHtml;
        metadataContent.appendChild(tagsDiv);
    }

    // Only add metadata section if there's content to show
    if (metadataContent.children.length > 0) {
        metadataSection.appendChild(metadataContent);
        // Insert at the top of main content
        const mainContent = document.querySelector('main');
        if (mainContent && mainContent.firstChild) {
            mainContent.insertBefore(metadataSection, mainContent.firstChild);
        }
    }
}

// Render manifest summary
function renderManifest(manifest) {
    const summary = document.getElementById('manifest-summary');
    if (!summary) return;

    const created = new Date(manifest.created_at).toLocaleString();
    const filesCount = Object.keys(manifest.file_manifest || {}).length;

    summary.innerHTML = `
        <div>
            <div class="text-gray-500 text-xs uppercase tracking-wide">Workflow ID</div>
            <div class="font-mono text-xs mt-1 break-all">${manifest.workflow_id}</div>
        </div>
        <div>
            <div class="text-gray-500 text-xs uppercase tracking-wide">Created</div>
            <div class="mt-1">${created}</div>
        </div>
        <div>
            <div class="text-gray-500 text-xs uppercase tracking-wide">Command</div>
            <div class="font-mono text-xs mt-1 break-all bg-gray-50 p-2 rounded">${manifest.cli_command || 'N/A'}</div>
        </div>
        <div>
            <div class="text-gray-500 text-xs uppercase tracking-wide">Files</div>
            <div class="mt-1">${filesCount} captured</div>
        </div>
        <div>
            <div class="text-gray-500 text-xs uppercase tracking-wide">Spec Version</div>
            <div class="mt-1 font-mono text-xs">${manifest.spec_version}</div>
        </div>
    `;
}

// Render a single step based on its kind
function renderStep(step) {
    const { index, timestamp, kind, content } = step;
    const time = new Date(timestamp).toLocaleTimeString();

    // Common wrapper
    const wrapper = document.createElement('div');
    wrapper.className = 'step-card px-6 py-4';

    // Header
    const header = document.createElement('div');
    header.className = 'flex items-center justify-between mb-2';
    header.innerHTML = `
        <div class="flex items-center space-x-2">
            <span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-blue-100 text-blue-800">
                #${index}
            </span>
            <span class="text-sm font-medium text-gray-900">${kind}</span>
        </div>
        <span class="text-xs text-gray-500">${time}</span>
    `;
    wrapper.appendChild(header);

    // Content based on kind
    const contentDiv = document.createElement('div');
    contentDiv.className = 'mt-3';

    if (kind === 'llm.request') {
        contentDiv.innerHTML = renderLLMRequest(content);
    } else if (kind === 'llm.response') {
        contentDiv.innerHTML = renderLLMResponse(content);
    } else if (kind === 'security.redaction') {
        contentDiv.innerHTML = renderRedaction(content);
    } else {
        // Generic JSON display
        contentDiv.innerHTML = `<pre class="text-xs bg-gray-50 p-3 rounded overflow-auto">${JSON.stringify(content, null, 2)}</pre>`;
    }

    wrapper.appendChild(contentDiv);
    return wrapper;
}

// Render LLM request
function renderLLMRequest(content) {
    const messages = content.messages || [];
    let html = `
        <div class="text-xs text-gray-600 mb-2">
            <span class="font-medium">${content.provider}</span> • 
            <span class="font-mono">${content.model}</span>
        </div>
    `;

    // Render messages as chat bubbles
    if (messages.length > 0) {
        html += '<div class="space-y-2">';
        for (const msg of messages) {
            const isUser = msg.role === 'user';
            const bgColor = isUser ? 'bg-blue-100' : 'bg-gray-100';
            const textColor = isUser ? 'text-blue-900' : 'text-gray-900';
            const align = isUser ? 'ml-auto' : 'mr-auto';

            html += `
                <div class="chat-bubble ${align} ${bgColor} ${textColor} rounded-lg px-4 py-2 text-sm">
                    <div class="text-xs font-medium mb-1 uppercase">${msg.role}</div>
                    <div class="whitespace-pre-wrap">${escapeHTML(msg.content)}</div>
                </div>
            `;
        }
        html += '</div>';
    }

    return html;
}

// Render LLM response
function renderLLMResponse(content) {
    const choices = content.choices || [];
    let html = `
        <div class="text-xs text-gray-600 mb-2">
            <span class="font-medium">${content.provider}</span> • 
            <span class="font-mono">${content.model}</span>
        </div>
    `;

    // Render response messages
    if (choices.length > 0) {
        html += '<div class="space-y-2">';
        for (const choice of choices) {
            html += `
                <div class="chat-bubble mr-auto bg-green-100 text-green-900 rounded-lg px-4 py-2 text-sm">
                    <div class="text-xs font-medium mb-1 uppercase">Assistant</div>
                    <div class="whitespace-pre-wrap">${escapeHTML(choice.message.content)}</div>
                    ${choice.finish_reason ? `<div class="text-xs text-green-700 mt-2">• ${choice.finish_reason}</div>` : ''}
                </div>
            `;
        }
        html += '</div>';
    }

    // Usage stats
    if (content.usage) {
        html += `
            <div class="mt-3 text-xs text-gray-600 flex items-center space-x-4">
                <span>📊 ${content.usage.total_tokens} tokens</span>
                <span>⚡ ${content.latency_seconds}s</span>
            </div>
        `;
    }

    return html;
}

// Render redaction event
function renderRedaction(content) {
    return `
        <div class="bg-yellow-50 border border-yellow-200 rounded-lg p-3 text-sm">
            <div class="flex items-center text-yellow-800">
                <svg class="w-5 h-5 mr-2" fill="currentColor" viewBox="0 0 20 20">
                    <path fill-rule="evenodd" d="M5 9V7a5 5 0 0110 0v2a2 2 0 012 2v5a2 2 0 01-2 2H5a2 2 0 01-2-2v-5a2 2 0 012-2zm8-2v2H7V7a3 3 0 016 0z" clip-rule="evenodd"/>
                </svg>
                <span class="font-medium">Secrets Redacted</span>
            </div>
            <div class="mt-2 text-yellow-700">
                ${content.count} sensitive value(s) removed from <span class="font-mono text-xs">${content.target_step}</span>
            </div>
        </div>
    `;
}

// Escape HTML to prevent XSS
function escapeHTML(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

// Render timeline
function renderTimeline(steps) {
    const timeline = document.getElementById('timeline');
    if (!timeline) return;

    if (steps.length === 0) {
        timeline.innerHTML = `
            <div class="px-6 py-12 text-center text-gray-500">
                No steps recorded
            </div>
        `;
        return;
    }

    timeline.innerHTML = '';
    for (const step of steps) {
        timeline.appendChild(renderStep(step));
    }
}

// Initialize viewer
async function init() {
    const data = loadEPIData();
    if (!data) {
        document.body.innerHTML = `
            <div class="min-h-screen flex items-center justify-center">
                <div class="text-center">
                    <h1 class="text-2xl font-bold text-red-600 mb-2">Failed to load EPI data</h1>
                    <p class="text-gray-600">The embedded data could not be parsed.</p>
                </div>
            </div>
        `;
        return;
    }

    await renderTrustBadge(data.manifest);
    renderMetadata(data.manifest);  // New metadata section
    renderManifest(data.manifest);
    renderTimeline(data.steps);
}

// Run on load
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
} else {
    init();
}