from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_web_viewer_shell_has_decision_ops_navigation():
    html = _read("web_viewer/index.html")

    assert "EPI Decision Ops" in html
    assert "Inbox" in html
    assert "Case" in html
    assert "Rules" in html
    assert "Reports" in html
    assert "Start with one decision, see why it matters, and record the human outcome." in html
    assert "../epi_viewer_static/crypto.js" in html
    assert "app.js" in html
    assert "styles.css" in html
    assert 'id="example-case-button"' in html
    assert 'id="epi-view-context"' in html
    assert 'id="drop-zone-title"' in html
    assert 'id="drop-zone-copy"' in html
    assert 'id="drop-zone-action"' in html
    assert "Quick Setup" in html
    assert 'id="setup-system"' in html
    assert 'id="setup-workflow"' in html
    assert "Pick a system and a decision type" in html
    assert 'class="setup-grid setup-grid-primary"' in html
    assert 'id="setup-reviewer-role"' in html
    assert 'id="setup-required-step"' in html
    assert 'id="connector-fields"' in html
    assert 'id="save-setup-profile-button"' in html
    assert 'id="load-setup-profile-button"' in html
    assert 'id="clear-setup-profile-button"' in html
    assert 'id="setup-storage-note"' in html
    assert 'id="setup-connection-status"' in html
    assert 'id="shared-auth-section"' in html
    assert 'id="shared-auth-status"' in html
    assert 'id="auth-username"' in html
    assert 'id="auth-password"' in html
    assert 'id="auth-login-button"' in html
    assert 'id="auth-logout-button"' in html
    assert 'id="setup-bridge-url"' in html
    assert 'id="check-bridge-button"' in html
    assert 'id="fetch-live-record-button"' in html
    assert "Try a safe sample" in html
    assert 'id="setup-live-record"' in html
    assert 'id="setup-workspace-button"' in html
    assert 'id="download-starter-pack-button"' in html
    assert "Use this in my system" in html
    assert "Advanced setup options" in html
    assert 'id="setup-preview"' in html
    assert 'id="guided-review-panel"' in html
    assert 'id="guided-review-title"' in html
    assert 'id="guided-review-copy"' in html
    assert 'id="guided-review-meta"' in html
    assert 'id="guided-review-button"' in html
    assert 'id="guided-why-button"' in html
    assert 'id="guided-queue-button"' in html
    assert 'id="guided-sample-button"' in html
    assert 'id="guided-example-button"' in html
    assert "Start Here" in html
    assert "Review this decision" in html
    assert 'id="shared-workspace-status"' in html
    assert 'id="refresh-shared-button"' in html
    assert 'id="reviewer-identity"' in html
    assert "My name/email" in html
    assert 'id="status-filter"' in html
    assert 'id="quick-view-filter"' in html
    assert "All workflow statuses" in html
    assert "Mine" in html
    assert "Overdue" in html
    assert "Zendesk" in html
    assert "Salesforce" in html
    assert "ServiceNow" in html
    assert 'id="case-workflow-badge"' in html
    assert "Team Workflow" in html
    assert 'id="workflow-form"' in html
    assert 'id="workflow-assignee"' in html
    assert 'id="workflow-due-at"' in html
    assert 'id="workflow-status"' in html
    assert 'id="save-workflow-button"' in html
    assert "Comments" in html
    assert 'id="case-comments"' in html
    assert 'id="comment-form"' in html
    assert 'id="comment-body"' in html
    assert 'id="save-comment-button"' in html
    assert "Download reviewed .epi" in html
    assert "Optional signing key" in html
    assert "case-review-signature-badge" in html
    assert 'id="case-guidance-title"' in html
    assert 'id="case-guidance-copy"' in html
    assert 'id="case-guidance-list"' in html
    assert 'id="case-guidance-review-button"' in html
    assert 'id="case-guidance-rules-button"' in html
    assert 'id="case-guidance-report-button"' in html
    assert "Verify source" in html
    assert 'id="policy-id"' in html
    assert 'id="policy-system-name"' in html
    assert 'id="policy-json-preview"' in html
    assert 'id="policy-rule-editor"' in html
    assert "Download epi_policy.json" in html
    assert "Turn business controls into enforceable EPI rules" in html


def test_web_viewer_app_supports_local_review_and_reports():
    js = _read("web_viewer/app.js")

    assert "async function parseEpiFile" in js
    assert "async function loadPreloadedCases" in js
    assert "async function buildCaseRecord" in js
    assert "function buildLegacyEmbeddedCasePayload" in js
    assert "function renderInbox" in js
    assert "function renderCaseView" in js
    assert "function renderCaseGuidance" in js
    assert "function getPriorityCase" in js
    assert "function startGuidedReview" in js
    assert "function openPriorityCaseReason" in js
    assert "function renderGuidedReviewPanel" in js
    assert "function renderWorkflowForm" in js
    assert "function renderComments" in js
    assert "async function loadExampleCase" in js
    assert "function buildExampleCasePayload" in js
    assert "function buildCaseGuidance" in js
    assert "function deriveWorkflowState" in js
    assert "function workflowStatusForReviewOutcome" in js
    assert "function deriveTrustState" in js
    assert "function downloadReviewRecord" in js
    assert "async function downloadReviewedArtifact" in js
    assert "async function buildReviewedArtifactBytes" in js
    assert "async function collectArtifactSourceEntries" in js
    assert "function buildEmbeddedViewerHtml" in js
    assert "function canBuildReviewedArtifact" in js
    assert "function createZipArchive" in js
    assert "function configureEmbeddedArtifactMode" in js
    assert "function resetImportControls" in js
    assert "function renderSetupWizard" in js
    assert "function renderConnectorFields" in js
    assert "function handleConnectorFieldInput" in js
    assert "function saveSetupProfile" in js
    assert "function restoreSavedSetupProfile" in js
    assert "function clearSavedSetupProfile" in js
    assert "function hasConfiguredLiveConnectorProfile" in js
    assert "function shouldUseMockPreview" in js
    assert "function normalizeBridgeUrl" in js
    assert "function checkConnectorBridge" in js
    assert "function autodetectConnectorBridge" in js
    assert "function restoreReviewerIdentity" in js
    assert "function saveReviewerIdentity" in js
    assert "async function refreshGatewayAuthSession" in js
    assert "async function loginToSharedWorkspace" in js
    assert "async function logoutFromSharedWorkspace" in js
    assert "function renderSharedAuthPanel" in js
    assert "function bridgeSupportsSharedWorkspace" in js
    assert "function renderSharedWorkspaceStatus" in js
    assert "function buildBridgeFetchPayload" in js
    assert "function fetchLiveConnectorRecord" in js
    assert "async function openLiveConnectorCasePreview" in js
    assert "function buildLiveConnectorCasePayload" in js
    assert "function deriveLiveRecordId" in js
    assert "function buildLiveRecordSummary" in js
    assert "async function refreshSharedWorkspace" in js
    assert "async function hydrateSharedWorkspaceCases" in js
    assert "function buildSharedWorkspaceCaseExport" in js
    assert "async function publishCaseToSharedWorkspace" in js
    assert "function mergeCaseRecords" in js
    assert "function renderLiveConnectorPreview" in js
    assert "function buildLiveSourceRecordExport" in js
    assert "function applySetupWizard" in js
    assert "function createPolicyEditorFromSetup" in js
    assert "function buildSetupPolicyRules" in js
    assert "function buildSetupPreviewHtml" in js
    assert "function buildEmptyInboxContent" in js
    assert "function downloadRecorderStarterPack" in js
    assert "function buildRecorderStarterFiles" in js
    assert "function buildRecorderStarterScript" in js
    assert "function buildRecorderStarterReadme" in js
    assert "function buildRecorderSampleInput" in js
    assert "function buildConnectorClientScript" in js
    assert "function buildConnectorSetupGuide" in js
    assert "function buildZendeskConnectorScript" in js
    assert "function buildSalesforceConnectorScript" in js
    assert "function buildServiceNowConnectorScript" in js
    assert "function buildInternalAppConnectorScript" in js
    assert "function buildCsvConnectorScript" in js
    assert "from epi_recorder import record" in js
    assert "with epi.agent_run" in js
    assert "connector_client.py" in js
    assert "CONNECTOR_SETUP.md" in js
    assert "live_source_record.json" in js
    assert "requests>=2.32.0" in js
    assert "epi-decision-ops.setup.v1" in js
    assert "localStorage" in js
    assert "function getActivePolicyEditor" in js
    assert "function createPolicyEditorFromCase" in js
    assert "function normalizePolicyRules" in js
    assert "function addPolicyRule" in js
    assert "function buildExportablePolicyJson" in js
    assert "function sanitizePolicyRule" in js
    assert "function downloadPolicyFile" in js
    assert "function downloadPolicySummary" in js
    assert "function ruleTypeLabel" in js
    assert "async function signReviewRecord" in js
    assert "async function verifyReviewSignature" in js
    assert "function parsePkcs8PrivateKey" in js
    assert "function decodeSignatureBytes" in js
    assert "function buildReviewSigningPayload" in js
    assert "function openCaseReviewForm" in js
    assert "async function saveCaseWorkflow" in js
    assert "async function saveCaseComment" in js
    assert "async function ensureCaseInReview" in js
    assert "function scrollToSetupWizard" in js
    assert "function downloadReport" in js
    assert "verifyManifestSignature" in js
    assert "document.getElementById('epi-data')" in js
    assert "Verify source" in js
    assert "Opened the packaged Decision Ops case file. Reviewed .epi download is ready" in js
    assert "epi_policy.json" in js
    assert "Opened an example case so you can explore the review flow right away." in js
    assert "Opened a live" in js
    assert "Secure keys stay only in this session." in js
    assert "source.record.loaded" in js
    assert "allow_mock_fallback" in js
    assert "Team case" in js
    assert "Comments will be posted as" in js


def test_web_viewer_readme_describes_nontechnical_workflow():
    readme = _read("web_viewer/README.md")

    assert "Decision Ops dashboard" in readme
    assert "one-click example case" in readme
    assert "Setup Wizard" in readme
    assert "safe sample" in readme.lower()
    assert "guided next steps" in readme
    assert "recorder starter export" in readme
    assert "Zendesk, Salesforce, ServiceNow, internal apps, and CSV-based workflows" in readme
    assert "stored only in this browser" in readme.lower()
    assert "secret keys stay only in the current session" in readme.lower()
    assert "Inbox" in readme
    assert "Case" in readme
    assert "Rules" in readme
    assert "Reports" in readme
    assert "reviewed `.epi`" in readme
    assert "browser signing" in readme
    assert "bad signature" in readme
    assert "Everything stays local to the browser" in readme
    assert "packaged `viewer.html`" in readme
    assert "embedded `epi-data`" in readme
    assert "offline" in readme.lower()
    assert "valid `epi_policy.json`" in readme
    assert "epi connect serve" in readme
    assert "epi connect open" in readme
    assert "live source record" in readme.lower()
    assert "case preview" in readme.lower()
    assert "shared" in readme.lower()
