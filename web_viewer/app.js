'use strict';

const state = {
  cases: [],
  currentView: 'inbox',
  selectedCaseId: null,
  embeddedArtifactMode: false,
  activeCaseSection: 'audit-first-card',
  caseHighlights: {
    stepNumber: null,
    attachmentName: null,
  },
  attachmentPreviewCache: {},
  workspaceSetup: null,
  connectorProfiles: {},
  bridgeHealth: null,
  liveConnectorRecord: null,
  gatewayAccessToken: '',
  authSession: null,
  reviewerIdentity: '',
  filters: {
    search: '',
    trust: 'all',
    status: 'all',
    quickView: 'all',
    review: 'all',
    workflow: 'all',
  },
  policyEditors: {},
  sharedWorkspace: {
    connected: false,
    cases: [],
    workspaceFile: '',
    lastSyncAt: null,
  },
};

const POLICY_EDITOR_EMPTY_KEY = '__workspace__';
const SETUP_STORAGE_KEY = 'epi-decision-ops.setup.v1';
const GATEWAY_ACCESS_TOKEN_STORAGE_KEY = 'epi-decision-ops.gateway-token.v1';
const REVIEWER_IDENTITY_STORAGE_KEY = 'epi-decision-ops.reviewer.v1';
const REVIEW_ACTIONS = {
  dismissed: {
    buttonLabel: 'Approve decision',
    label: 'Approved decision',
    help: 'Use this when the recorded decision can proceed and your notes explain why.',
  },
  confirmed_fault: {
    buttonLabel: 'Reject decision',
    label: 'Rejected decision',
    help: 'Use this when the decision should not proceed and the issue needs to stay on record.',
  },
  skipped: {
    buttonLabel: 'Escalate / decide later',
    label: 'Escalated / decide later',
    help: 'Use this when another reviewer or more information is needed before a final decision.',
  },
};
const POLICY_RULE_TYPES = [
  { value: 'constraint_guard', label: 'Constraint guard' },
  { value: 'sequence_guard', label: 'Sequence guard' },
  { value: 'threshold_guard', label: 'Threshold guard' },
  { value: 'prohibition_guard', label: 'Prohibition guard' },
  { value: 'approval_guard', label: 'Approval rule' },
  { value: 'tool_permission_guard', label: 'Tool permission guard' },
];
const POLICY_SEVERITIES = ['critical', 'high', 'medium', 'low'];
const POLICY_MODES = ['detect', 'warn', 'block', 'require_approval', 'redact', 'quarantine', 'escalate'];
const POLICY_INTERVENTION_POINTS = ['input', 'prompt', 'model_request', 'model_response', 'tool_call', 'tool_response', 'memory_read', 'memory_write', 'decision', 'output', 'handoff', 'review'];
const CONNECTOR_LIVE_FIELDS = {
  zendesk: ['subdomain', 'email', 'api_token'],
  salesforce: ['instance_url', 'access_token'],
  servicenow: ['instance_url', 'username', 'password'],
  'internal-app': ['base_url'],
  'csv-export': ['csv_path', 'id_column'],
};
const SETUP_SYSTEMS = {
  zendesk: {
    label: 'Zendesk',
    application: 'zendesk',
    allowedToolsText: 'lookup_ticket, verify_customer, send_reply',
    deniedToolsText: 'delete_ticket',
  },
  salesforce: {
    label: 'Salesforce',
    application: 'salesforce',
    allowedToolsText: 'lookup_account, review_case, update_opportunity',
    deniedToolsText: 'delete_account',
  },
  servicenow: {
    label: 'ServiceNow',
    application: 'servicenow',
    allowedToolsText: 'lookup_record, verify_assignment, update_workflow',
    deniedToolsText: 'delete_incident',
  },
  'internal-app': {
    label: 'Internal app',
    application: 'internal-app',
    allowedToolsText: 'lookup_record, verify_input, route_case',
    deniedToolsText: 'delete_record',
  },
  'csv-export': {
    label: 'CSV or exported logs',
    application: 'csv-export',
    allowedToolsText: 'import_csv, validate_rows, lookup_record',
    deniedToolsText: 'drop_rows',
  },
};
const SETUP_WORKFLOWS = {
  'refund-approval': {
    label: 'Refund approvals',
    policyProfile: 'starter.refund-approval',
    approvalAction: 'approve_refund',
    finalAction: 'issue_refund',
    defaultRequiredStep: 'verify_identity',
    thresholdField: 'amount',
    thresholdValue: '500',
    includes: ['threshold_guard', 'approval_guard', 'sequence_guard', 'prohibition_guard'],
  },
  'loan-underwriting': {
    label: 'Loan underwriting',
    policyProfile: 'starter.loan-underwriting',
    approvalAction: 'approve_loan',
    finalAction: 'approve_loan',
    defaultRequiredStep: 'risk_assessment',
    thresholdField: 'amount',
    thresholdValue: '10000',
    includes: ['threshold_guard', 'approval_guard', 'constraint_guard', 'sequence_guard', 'prohibition_guard'],
  },
  'claims-review': {
    label: 'Claims review',
    policyProfile: 'starter.claims-review',
    approvalAction: 'approve_claim',
    finalAction: 'approve_claim',
    defaultRequiredStep: 'verify_claim',
    thresholdField: 'claim_amount',
    thresholdValue: '2500',
    includes: ['threshold_guard', 'approval_guard', 'sequence_guard', 'tool_permission_guard'],
  },
  'support-escalation': {
    label: 'Support escalations',
    policyProfile: 'starter.support-escalation',
    approvalAction: 'close_ticket',
    finalAction: 'resolve_ticket',
    defaultRequiredStep: 'verify_customer',
    thresholdField: '',
    thresholdValue: '',
    includes: ['approval_guard', 'sequence_guard', 'tool_permission_guard', 'prohibition_guard'],
  },
  'access-decision': {
    label: 'Access decisions',
    policyProfile: 'starter.access-decision',
    approvalAction: 'grant_access',
    finalAction: 'grant_access',
    defaultRequiredStep: 'verify_identity',
    thresholdField: '',
    thresholdValue: '',
    includes: ['approval_guard', 'sequence_guard', 'tool_permission_guard', 'prohibition_guard'],
  },
  'custom-approval': {
    label: 'Custom approvals',
    policyProfile: 'starter.custom-approval',
    approvalAction: 'approve_decision',
    finalAction: 'finalize_decision',
    defaultRequiredStep: 'verify_input',
    thresholdField: 'amount',
    thresholdValue: '1000',
    includes: ['threshold_guard', 'approval_guard', 'sequence_guard', 'prohibition_guard'],
  },
};
const CONNECTOR_FIELD_DEFS = {
  zendesk: [
    { key: 'subdomain', label: 'Zendesk subdomain', placeholder: 'mycompany', defaultValue: '' },
    { key: 'email', label: 'Zendesk email', placeholder: 'ops@example.com', defaultValue: '' },
    { key: 'api_token', label: 'Zendesk API token', placeholder: 'Paste token', defaultValue: '', secret: true },
  ],
  salesforce: [
    { key: 'instance_url', label: 'Salesforce instance URL', placeholder: 'https://your-org.my.salesforce.com', defaultValue: '' },
    { key: 'access_token', label: 'Salesforce access token', placeholder: 'Paste token', defaultValue: '', secret: true },
    { key: 'api_version', label: 'Salesforce API version', placeholder: 'v61.0', defaultValue: 'v61.0' },
  ],
  servicenow: [
    { key: 'instance_url', label: 'ServiceNow instance URL', placeholder: 'https://your-instance.service-now.com', defaultValue: '' },
    { key: 'username', label: 'ServiceNow username', placeholder: 'integration.user', defaultValue: '' },
    { key: 'password', label: 'ServiceNow password', placeholder: 'Paste password', defaultValue: '', secret: true },
  ],
  'internal-app': [
    { key: 'base_url', label: 'Internal app base URL', placeholder: 'https://internal.example.com', defaultValue: '' },
    { key: 'bearer_token', label: 'Bearer token', placeholder: 'Paste token', defaultValue: '', secret: true },
    { key: 'api_path', label: 'Default API path', placeholder: '/api/v1/decisions', defaultValue: '/api/v1/decisions' },
  ],
  'csv-export': [
    { key: 'csv_path', label: 'CSV file path', placeholder: 'source_export.csv', defaultValue: 'source_export.csv' },
    { key: 'id_column', label: 'ID column', placeholder: 'case_id', defaultValue: 'case_id' },
  ],
};

const elements = {};

document.addEventListener('DOMContentLoaded', () => {
  void initApp();
});

async function initApp() {
  captureElements();
  restoreGatewayAccessToken();
  restoreReviewerIdentity();
  bindEvents();
  applyInitialBridgeConfigFromQuery();
  restoreSavedSetupProfile(true);
  await loadPreloadedCases();
  renderApp();
  void autodetectConnectorBridge();
}

function applyInitialBridgeConfigFromQuery() {
  if (!elements.setupBridgeUrl) {
    return;
  }

  try {
    const params = new URLSearchParams(globalThis.location?.search || '');
    const bridgeUrl = normalizeBridgeUrl(params.get('bridgeUrl'));
    const accessToken = String(params.get('accessToken') || '').trim();
    let shouldRewriteUrl = false;
    if (bridgeUrl) {
      elements.setupBridgeUrl.value = bridgeUrl;
    }
    if (accessToken) {
      state.gatewayAccessToken = accessToken;
      if (elements.setupAccessToken) {
        elements.setupAccessToken.value = accessToken;
      }
      try {
        window.sessionStorage.setItem(GATEWAY_ACCESS_TOKEN_STORAGE_KEY, accessToken);
      } catch (_error) {
        // Ignore storage errors and keep the in-memory token for this tab.
      }
      params.delete('accessToken');
      shouldRewriteUrl = true;
    }
    if (shouldRewriteUrl && globalThis.history?.replaceState) {
      const nextSearch = params.toString();
      const nextUrl = `${globalThis.location.pathname}${nextSearch ? `?${nextSearch}` : ''}${globalThis.location.hash || ''}`;
      globalThis.history.replaceState({}, document.title, nextUrl);
    }
  } catch (_error) {
    // Ignore malformed query strings and keep the default bridge URL.
  }
}

function restoreGatewayAccessToken() {
  try {
    const stored = (window.sessionStorage.getItem(GATEWAY_ACCESS_TOKEN_STORAGE_KEY) || '').trim();
    state.gatewayAccessToken = stored;
    if (elements.setupAccessToken) {
      elements.setupAccessToken.value = stored;
    }
  } catch (_error) {
    state.gatewayAccessToken = '';
  }
}

function clearGatewayAccessToken({ render = true } = {}) {
  state.gatewayAccessToken = '';
  state.authSession = null;
  if (elements.setupAccessToken) {
    elements.setupAccessToken.value = '';
  }
  try {
    window.sessionStorage.removeItem(GATEWAY_ACCESS_TOKEN_STORAGE_KEY);
  } catch (_error) {
    // Ignore storage errors.
  }
  if (render) {
    renderSetupWizard();
  }
}

function saveGatewayAccessToken() {
  const value = (elements.setupAccessToken?.value || '').trim();
  state.gatewayAccessToken = value;
  state.authSession = null;
  try {
    if (value) {
      window.sessionStorage.setItem(GATEWAY_ACCESS_TOKEN_STORAGE_KEY, value);
    } else {
      window.sessionStorage.removeItem(GATEWAY_ACCESS_TOKEN_STORAGE_KEY);
    }
  } catch (_error) {
    // Ignore storage errors and keep the in-memory token for this tab.
  }
  renderSetupWizard();
}

async function refreshGatewayAuthSession() {
  const bridgeUrl = normalizeBridgeUrl(state.bridgeHealth?.url || elements.setupBridgeUrl?.value || '');
  if (!bridgeUrl || !state.gatewayAccessToken) {
    state.authSession = null;
    renderSetupWizard();
    return null;
  }

  try {
    const response = await bridgeFetch(`${bridgeUrl}/api/auth/session`);
    const payload = await response.json();
    if (!response.ok || !payload.ok || !payload.session) {
      if (response.status === 401 || response.status === 403) {
        clearGatewayAccessToken({ render: false });
      }
      throw new Error(payload.detail || payload.error || `Sign-in check failed with status ${response.status}`);
    }
    state.authSession = payload.session;
    renderSetupWizard();
    return state.authSession;
  } catch (_error) {
    renderSetupWizard();
    return null;
  }
}

function restoreReviewerIdentity() {
  try {
    const stored = (localStorage.getItem(REVIEWER_IDENTITY_STORAGE_KEY) || '').trim();
    state.reviewerIdentity = stored;
    if (elements.reviewerIdentity) {
      elements.reviewerIdentity.value = stored;
    }
  } catch (_error) {
    state.reviewerIdentity = '';
  }
}

function saveReviewerIdentity() {
  const value = (elements.reviewerIdentity?.value || '').trim();
  state.reviewerIdentity = value;
  try {
    if (value) {
      localStorage.setItem(REVIEWER_IDENTITY_STORAGE_KEY, value);
    } else {
      localStorage.removeItem(REVIEWER_IDENTITY_STORAGE_KEY);
    }
  } catch (_error) {
    // Ignore storage errors and keep the in-memory identity for this session.
  }
  const selected = getSelectedCase();
  if (!selected || !selected.review?.reviews?.length) {
    elements.reviewerName.value = value;
  }
  renderInbox();
}

function captureElements() {
  elements.fileInput = document.getElementById('file-input');
  elements.exampleCaseButton = document.getElementById('example-case-button');
  elements.addFilesButton = document.getElementById('add-files-button');
  elements.resetWorkspaceButton = document.getElementById('reset-workspace-button');
  elements.dropZone = document.getElementById('drop-zone');
  elements.dropZoneTitle = document.getElementById('drop-zone-title');
  elements.dropZoneCopy = document.getElementById('drop-zone-copy');
  elements.dropZoneAction = document.getElementById('drop-zone-action');
  elements.loadStatus = document.getElementById('load-status');
  elements.setupPanelDetails = document.getElementById('setup-panel-details');
  elements.setupReadyBadge = document.getElementById('setup-ready-badge');
  elements.setupSystem = document.getElementById('setup-system');
  elements.setupWorkflow = document.getElementById('setup-workflow');
  elements.setupReviewerRole = document.getElementById('setup-reviewer-role');
  elements.setupEnvironment = document.getElementById('setup-environment');
  elements.setupRequiredStep = document.getElementById('setup-required-step');
  elements.connectorFields = document.getElementById('connector-fields');
  elements.saveSetupProfileButton = document.getElementById('save-setup-profile-button');
  elements.loadSetupProfileButton = document.getElementById('load-setup-profile-button');
  elements.clearSetupProfileButton = document.getElementById('clear-setup-profile-button');
  elements.setupStorageNote = document.getElementById('setup-storage-note');
  elements.setupConnectionStatus = document.getElementById('setup-connection-status');
  elements.sharedAuthSection = document.getElementById('shared-auth-section');
  elements.sharedAuthStatus = document.getElementById('shared-auth-status');
  elements.sharedAuthCopy = document.getElementById('shared-auth-copy');
  elements.authUsername = document.getElementById('auth-username');
  elements.authPassword = document.getElementById('auth-password');
  elements.authLoginButton = document.getElementById('auth-login-button');
  elements.authLogoutButton = document.getElementById('auth-logout-button');
  elements.setupBridgeUrl = document.getElementById('setup-bridge-url');
  elements.setupAccessToken = document.getElementById('setup-access-token');
  elements.checkBridgeButton = document.getElementById('check-bridge-button');
  elements.fetchLiveRecordButton = document.getElementById('fetch-live-record-button');
  elements.setupLiveRecord = document.getElementById('setup-live-record');
  elements.setupWorkspaceButton = document.getElementById('setup-workspace-button');
  elements.downloadStarterPackButton = document.getElementById('download-starter-pack-button');
  elements.setupPreview = document.getElementById('setup-preview');
  elements.summaryStrip = document.getElementById('summary-strip');
  elements.summaryTotal = document.getElementById('summary-total');
  elements.summaryReview = document.getElementById('summary-review');
  elements.summaryTrusted = document.getElementById('summary-trusted');
  elements.summaryWorkflows = document.getElementById('summary-workflows');
  elements.guidedReviewPanel = document.getElementById('guided-review-panel');
  elements.guidedReviewTitle = document.getElementById('guided-review-title');
  elements.guidedReviewCopy = document.getElementById('guided-review-copy');
  elements.guidedReviewMeta = document.getElementById('guided-review-meta');
  elements.guidedReviewButton = document.getElementById('guided-review-button');
  elements.guidedWhyButton = document.getElementById('guided-why-button');
  elements.guidedQueueButton = document.getElementById('guided-queue-button');
  elements.guidedSampleButton = document.getElementById('guided-sample-button');
  elements.guidedExampleButton = document.getElementById('guided-example-button');
  elements.workspace = document.getElementById('workspace');
  elements.setupUtilityButton = document.getElementById('open-setup-utility-button');
  elements.rulesNavButton = document.getElementById('open-rules-utility-button');
  elements.reportsNavButton = document.getElementById('open-reports-utility-button');
  elements.caseSelector = document.getElementById('case-selector');
  elements.sharedWorkspaceStatus = document.getElementById('shared-workspace-status');
  elements.refreshSharedButton = document.getElementById('refresh-shared-button');
  elements.reviewerIdentity = document.getElementById('reviewer-identity');
  elements.searchInput = document.getElementById('search-input');
  elements.statusFilter = document.getElementById('status-filter');
  elements.quickViewFilter = document.getElementById('quick-view-filter');
  elements.trustFilter = document.getElementById('trust-filter');
  elements.reviewFilter = document.getElementById('review-filter');
  elements.workflowFilter = document.getElementById('workflow-filter');
  elements.caseList = document.getElementById('case-list');
  elements.emptyInbox = document.getElementById('empty-inbox');
  elements.noCaseSelected = document.getElementById('no-case-selected');
  elements.caseView = document.getElementById('case-view');
  elements.auditTrustBadge = document.getElementById('audit-trust-badge');
  elements.auditProofCopy = document.getElementById('audit-proof-copy');
  elements.auditSummaryGrid = document.getElementById('audit-summary-grid');
  elements.auditProofCommand = document.getElementById('audit-proof-command');
  elements.caseTitle = document.getElementById('case-title');
  elements.caseSubtitle = document.getElementById('case-subtitle');
  elements.caseSummaryCopy = document.getElementById('case-summary-copy');
  elements.caseOverviewNarrative = document.getElementById('case-overview-narrative');
  elements.caseOverviewSignals = document.getElementById('case-overview-signals');
  elements.caseWorkflowBadge = document.getElementById('case-workflow-badge');
  elements.caseSourceBadge = document.getElementById('case-source-badge');
  elements.caseImportBadge = document.getElementById('case-import-badge');
  elements.caseTrustBadge = document.getElementById('case-trust-badge');
  elements.caseRiskBadge = document.getElementById('case-risk-badge');
  elements.caseReviewBadge = document.getElementById('case-review-badge');
  elements.caseReviewSignatureBadge = document.getElementById('case-review-signature-badge');
  elements.caseAuditBadge = document.getElementById('case-audit-badge');
  elements.caseSectionNav = document.querySelector('.case-section-nav');
  elements.caseSnapshotTitle = document.getElementById('case-snapshot-title');
  elements.caseSnapshotCopy = document.getElementById('case-snapshot-copy');
  elements.caseSnapshotGrid = document.getElementById('case-snapshot-grid');
  elements.caseGuidanceTitle = document.getElementById('case-guidance-title');
  elements.caseGuidanceCopy = document.getElementById('case-guidance-copy');
  elements.caseGuidanceList = document.getElementById('case-guidance-list');
  elements.caseGuidanceReviewButton = document.getElementById('case-guidance-review-button');
  elements.caseGuidanceRulesButton = document.getElementById('case-guidance-rules-button');
  elements.caseGuidanceReportButton = document.getElementById('case-guidance-report-button');
  elements.caseSummaryGrid = document.getElementById('case-summary-grid');
  elements.caseEvidenceSummary = document.getElementById('case-evidence-summary');
  elements.casePolicyFlow = document.getElementById('case-policy-flow');
  elements.caseMappingCard = document.getElementById('case-mapping-card');
  elements.caseMappingSummary = document.getElementById('case-mapping-summary');
  elements.caseMappingGroups = document.getElementById('case-mapping-groups');
  elements.caseTrustCard = document.getElementById('case-trust-card');
  elements.caseTrustGrid = document.getElementById('case-trust-grid');
  elements.caseAttachmentsCard = document.getElementById('case-attachments-card');
  elements.caseAttachments = document.getElementById('case-attachments');
  elements.caseAttachmentPreview = document.getElementById('case-attachment-preview');
  elements.attachmentPreviewTitle = document.getElementById('attachment-preview-title');
  elements.attachmentPreviewMeta = document.getElementById('attachment-preview-meta');
  elements.attachmentPreviewBody = document.getElementById('attachment-preview-body');
  elements.caseAlerts = document.getElementById('case-alerts');
  elements.caseFindings = document.getElementById('case-findings');
  elements.caseTimeline = document.getElementById('case-timeline');
  elements.workflowForm = document.getElementById('workflow-form');
  elements.workflowAssignee = document.getElementById('workflow-assignee');
  elements.workflowDueAt = document.getElementById('workflow-due-at');
  elements.workflowStatus = document.getElementById('workflow-status');
  elements.workflowSaveStatus = document.getElementById('workflow-save-status');
  elements.caseComments = document.getElementById('case-comments');
  elements.commentForm = document.getElementById('comment-form');
  elements.commentBody = document.getElementById('comment-body');
  elements.commentSaveStatus = document.getElementById('comment-save-status');
  elements.reviewForm = document.getElementById('review-form');
  elements.reviewerName = document.getElementById('reviewer-name');
  elements.reviewOutcome = document.getElementById('review-outcome');
  elements.reviewNotes = document.getElementById('review-notes');
  elements.reviewSigningKey = document.getElementById('review-signing-key');
  elements.reviewApproveButton = document.getElementById('review-approve-button');
  elements.reviewRejectButton = document.getElementById('review-reject-button');
  elements.reviewEscalateButton = document.getElementById('review-escalate-button');
  elements.reviewActionHelp = document.getElementById('review-action-help');
  elements.reviewSaveStatus = document.getElementById('review-save-status');
  elements.downloadReviewedEpiButton = document.getElementById('download-reviewed-epi-button');
  elements.downloadReviewButton = document.getElementById('download-review-button');
  elements.downloadCaseReportButton = document.getElementById('download-case-report-button');
  elements.policySourceNote = document.getElementById('policy-source-note');
  elements.policyId = document.getElementById('policy-id');
  elements.policySystemName = document.getElementById('policy-system-name');
  elements.policySystemVersion = document.getElementById('policy-system-version');
  elements.policyVersion = document.getElementById('policy-version');
  elements.policyProfileId = document.getElementById('policy-profile-id');
  elements.policyScopeOrganization = document.getElementById('policy-scope-organization');
  elements.policyScopeTeam = document.getElementById('policy-scope-team');
  elements.policyScopeApplication = document.getElementById('policy-scope-application');
  elements.policyScopeWorkflow = document.getElementById('policy-scope-workflow');
  elements.policyScopeEnvironment = document.getElementById('policy-scope-environment');
  elements.policyRuleCountBadge = document.getElementById('policy-rule-count-badge');
  elements.policyApprovalCountBadge = document.getElementById('policy-approval-count-badge');
  elements.policyJsonPreview = document.getElementById('policy-json-preview');
  elements.resetPolicyButton = document.getElementById('reset-policy-button');
  elements.downloadPolicyButton = document.getElementById('download-policy-button');
  elements.downloadPolicySummaryButton = document.getElementById('download-policy-summary-button');
  elements.addRuleType = document.getElementById('add-rule-type');
  elements.addRuleButton = document.getElementById('add-rule-button');
  elements.policyRuleEditor = document.getElementById('policy-rule-editor');
  elements.reportType = document.getElementById('report-type');
  elements.reportScope = document.getElementById('report-scope');
  elements.reportPreview = document.getElementById('report-preview');
  elements.downloadReportText = document.getElementById('download-report-text');
  elements.downloadReportJson = document.getElementById('download-report-json');
  elements.downloadReportCsv = document.getElementById('download-report-csv');
}

function bindEvents() {
  elements.exampleCaseButton.addEventListener('click', () => {
    void loadExampleCase();
  });
  elements.addFilesButton.addEventListener('click', () => {
    if (!elements.addFilesButton.disabled) {
      elements.fileInput.click();
    }
  });
  elements.dropZone.addEventListener('click', () => {
    if (!elements.dropZone.classList.contains('disabled')) {
      elements.fileInput.click();
    }
  });
  elements.dropZone.addEventListener('keydown', (event) => {
    if (elements.dropZone.classList.contains('disabled')) {
      return;
    }
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      elements.fileInput.click();
    }
  });
  elements.fileInput.addEventListener('change', async (event) => {
    await handleFiles(event.target.files);
    elements.fileInput.value = '';
  });
  elements.resetWorkspaceButton.addEventListener('click', resetWorkspace);
  [
    elements.setupSystem,
    elements.setupWorkflow,
    elements.setupReviewerRole,
    elements.setupEnvironment,
    elements.setupRequiredStep,
    elements.setupBridgeUrl,
  ].forEach((input) => {
    input.addEventListener('input', renderSetupWizard);
    input.addEventListener('change', renderSetupWizard);
  });
  elements.setupAccessToken.addEventListener('input', saveGatewayAccessToken);
  elements.setupAccessToken.addEventListener('change', saveGatewayAccessToken);
  elements.authLoginButton.addEventListener('click', () => {
    void loginToSharedWorkspace();
  });
  elements.authLogoutButton.addEventListener('click', () => {
    void logoutFromSharedWorkspace();
  });
  elements.authPassword.addEventListener('keydown', (event) => {
    if (event.key === 'Enter') {
      event.preventDefault();
      void loginToSharedWorkspace();
    }
  });
  elements.connectorFields.addEventListener('input', handleConnectorFieldInput);
  elements.connectorFields.addEventListener('change', handleConnectorFieldInput);
  elements.saveSetupProfileButton.addEventListener('click', saveSetupProfile);
  elements.loadSetupProfileButton.addEventListener('click', () => restoreSavedSetupProfile(false));
  elements.clearSetupProfileButton.addEventListener('click', clearSavedSetupProfile);
  elements.checkBridgeButton.addEventListener('click', () => {
    void checkConnectorBridge();
  });
  elements.fetchLiveRecordButton.addEventListener('click', () => {
    void fetchLiveConnectorRecord();
  });
  elements.setupWorkspaceButton.addEventListener('click', applySetupWizard);
  elements.downloadStarterPackButton.addEventListener('click', downloadRecorderStarterPack);

  elements.dropZone.addEventListener('dragover', (event) => {
    if (elements.dropZone.classList.contains('disabled')) {
      return;
    }
    event.preventDefault();
    elements.dropZone.classList.add('dragover');
  });
  elements.dropZone.addEventListener('dragleave', () => {
    elements.dropZone.classList.remove('dragover');
  });
  elements.dropZone.addEventListener('drop', async (event) => {
    if (elements.dropZone.classList.contains('disabled')) {
      return;
    }
    event.preventDefault();
    elements.dropZone.classList.remove('dragover');
    await handleFiles(event.dataTransfer.files);
  });

  document.querySelectorAll('.nav-button').forEach((button) => {
    button.addEventListener('click', () => setView(button.dataset.view));
  });
  elements.setupUtilityButton.addEventListener('click', () => {
    scrollToSetupWizard();
  });
  elements.rulesNavButton.addEventListener('click', () => {
    setView('rules');
    elements.workspace.scrollIntoView({ behavior: 'smooth', block: 'start' });
  });
  elements.reportsNavButton.addEventListener('click', openReportsView);

  elements.searchInput.addEventListener('input', (event) => {
    state.filters.search = event.target.value.trim().toLowerCase();
    renderInbox();
    renderReportsView();
  });
  elements.reviewerIdentity.addEventListener('input', saveReviewerIdentity);
  elements.statusFilter.addEventListener('change', (event) => {
    state.filters.status = event.target.value;
    renderInbox();
    renderReportsView();
  });
  elements.quickViewFilter.addEventListener('change', (event) => {
    state.filters.quickView = event.target.value;
    renderInbox();
    renderReportsView();
  });
  elements.trustFilter.addEventListener('change', (event) => {
    state.filters.trust = event.target.value;
    renderInbox();
    renderReportsView();
  });
  elements.reviewFilter.addEventListener('change', (event) => {
    state.filters.review = event.target.value;
    renderInbox();
    renderReportsView();
  });
  elements.workflowFilter.addEventListener('change', (event) => {
    state.filters.workflow = event.target.value;
    renderInbox();
    renderReportsView();
  });

  elements.caseSelector.addEventListener('change', (event) => {
    selectCase(event.target.value);
  });

  elements.caseList.addEventListener('click', (event) => {
    const openButton = event.target.closest('[data-open-case]');
    if (!openButton) {
      return;
    }
    selectCase(openButton.dataset.openCase);
    setView('case');
  });
  elements.emptyInbox.addEventListener('click', (event) => {
    const exampleButton = event.target.closest('[data-open-example-case]');
    if (exampleButton) {
      void loadExampleCase();
      return;
    }
    const setupButton = event.target.closest('[data-scroll-setup]');
    if (setupButton) {
      scrollToSetupWizard();
    }
  });
  elements.caseGuidanceReviewButton.addEventListener('click', () => {
    void openCaseReviewForm();
  });
  elements.caseGuidanceRulesButton.addEventListener('click', () => {
    setView('rules');
    elements.workspace.scrollIntoView({ behavior: 'smooth', block: 'start' });
  });
  elements.caseGuidanceReportButton.addEventListener('click', openReportsView);
  elements.caseSectionNav.addEventListener('click', (event) => {
    const target = event.target.closest('[data-case-section-target]');
    if (!target) {
      return;
    }
    scrollToCaseSection(target.dataset.caseSectionTarget);
  });
  elements.caseView.addEventListener('click', (event) => {
    const sectionLink = event.target.closest('[data-case-section-target]');
    if (sectionLink && !sectionLink.closest('.case-section-nav')) {
      scrollToCaseSection(sectionLink.dataset.caseSectionTarget);
      return;
    }
    const stepLink = event.target.closest('[data-trace-step]');
    if (stepLink) {
      highlightCaseStep(Number(stepLink.dataset.traceStep || 0));
      return;
    }
    const attachmentFocus = event.target.closest('[data-attachment-focus]');
    if (attachmentFocus) {
      focusCaseAttachment(attachmentFocus.dataset.attachmentFocus);
      return;
    }
    const attachmentPreview = event.target.closest('[data-attachment-preview]');
    if (attachmentPreview) {
      void previewCaseAttachment(attachmentPreview.dataset.attachmentPreview);
      return;
    }
    const attachmentDownload = event.target.closest('[data-attachment-download]');
    if (attachmentDownload) {
      void downloadCaseAttachment(attachmentDownload.dataset.attachmentDownload);
    }
  });
  elements.refreshSharedButton.addEventListener('click', () => {
    void refreshSharedWorkspace(true);
  });
  elements.guidedReviewButton.addEventListener('click', () => {
    void startGuidedReview();
  });
  elements.guidedWhyButton.addEventListener('click', () => {
    openPriorityCaseReason();
  });
  elements.guidedQueueButton.addEventListener('click', () => {
    setView('inbox');
    elements.workspace.scrollIntoView({ behavior: 'smooth', block: 'start' });
  });
  elements.guidedSampleButton.addEventListener('click', () => {
    if (state.workspaceSetup) {
      void fetchLiveConnectorRecord();
      return;
    }
    scrollToSetupWizard();
  });
  elements.guidedExampleButton.addEventListener('click', () => {
    void loadExampleCase();
  });
  elements.workflowForm.addEventListener('submit', (event) => {
    event.preventDefault();
    void saveCaseWorkflow();
  });
  elements.commentForm.addEventListener('submit', (event) => {
    event.preventDefault();
    void saveCaseComment();
  });

  elements.reviewForm.addEventListener('submit', (event) => {
    event.preventDefault();
    const forcedOutcome = event.submitter?.dataset?.reviewAction || elements.reviewOutcome.value;
    void applyLocalReview(forcedOutcome);
  });
  elements.downloadReviewedEpiButton.addEventListener('click', downloadReviewedArtifact);
  elements.downloadReviewButton.addEventListener('click', downloadReviewRecord);
  elements.downloadCaseReportButton.addEventListener('click', downloadCaseSummary);

  [
    elements.policyId,
    elements.policySystemName,
    elements.policySystemVersion,
    elements.policyVersion,
    elements.policyProfileId,
    elements.policyScopeOrganization,
    elements.policyScopeTeam,
    elements.policyScopeApplication,
    elements.policyScopeWorkflow,
    elements.policyScopeEnvironment,
  ].forEach((input) => {
    input.addEventListener('input', syncPolicyMetadata);
    input.addEventListener('change', syncPolicyMetadata);
  });
  elements.resetPolicyButton.addEventListener('click', resetPolicyEditorFromCase);
  elements.downloadPolicyButton.addEventListener('click', downloadPolicyFile);
  elements.downloadPolicySummaryButton.addEventListener('click', downloadPolicySummary);
  elements.addRuleButton.addEventListener('click', addPolicyRule);
  elements.policyRuleEditor.addEventListener('input', handlePolicyRuleInput);
  elements.policyRuleEditor.addEventListener('change', handlePolicyRuleInput);
  elements.policyRuleEditor.addEventListener('click', handlePolicyRuleClick);

  [elements.reportType, elements.reportScope].forEach((input) => {
    input.addEventListener('change', renderReportsView);
  });
  elements.downloadReportText.addEventListener('click', () => downloadReport('text'));
  elements.downloadReportJson.addEventListener('click', () => downloadReport('json'));
  elements.downloadReportCsv.addEventListener('click', () => downloadReport('csv'));
}

async function handleFiles(fileList) {
  const files = Array.from(fileList || []).filter((file) => file.name.toLowerCase().endsWith('.epi'));
  if (!files.length) {
    setStatus('Choose one or more saved EPI case files to open here.', 'warning');
    return;
  }

  if (typeof JSZip === 'undefined') {
    setStatus('JSZip did not load, so the browser cannot read .epi files yet.', 'error');
    return;
  }

  setStatus(`Loading ${files.length} case file${files.length === 1 ? '' : 's'}...`, 'info');

  const loadedCases = [];
  const failures = [];

  for (const file of files) {
    try {
      const caseRecord = await parseEpiFile(file);
      loadedCases.push(caseRecord);
    } catch (error) {
      failures.push(`${file.name}: ${error.message}`);
    }
  }

  mergeCases(loadedCases);
  await publishCasesToSharedWorkspace(loadedCases);

  if (state.cases.length > 0 && !state.selectedCaseId) {
    state.selectedCaseId = state.cases[0].id;
  }

  renderApp();

  if (failures.length && loadedCases.length) {
    setStatus(`Loaded ${loadedCases.length} case file(s). Some files failed: ${failures.join(' | ')}`, 'warning');
  } else if (failures.length) {
    setStatus(`No case files loaded. ${failures.join(' | ')}`, 'error');
  } else {
    setStatus(`Loaded ${loadedCases.length} case file${loadedCases.length === 1 ? '' : 's'} into the queue.`, 'success');
  }
}

async function loadPreloadedCases() {
  const payloadTag = document.getElementById('epi-preloaded-cases');
  const legacyTag = document.getElementById('epi-data');
  const payloadText = payloadTag?.textContent?.trim() || '';
  const legacyText = legacyTag?.textContent?.trim() || '';

  if (!payloadText && !legacyText) {
    return;
  }

  try {
    let cases = [];
    let openedFromArtifact = false;
    let uiState = null;

    if (payloadText) {
      const payload = JSON.parse(payloadText);
      cases = Array.isArray(payload?.cases) ? payload.cases : [];
      uiState = payload?.ui || null;
    } else if (legacyText) {
      cases = [buildLegacyEmbeddedCasePayload(JSON.parse(legacyText))];
      openedFromArtifact = true;
    }

    if (!cases.length) {
      return;
    }

    const hydratedCases = [];
    for (const item of cases) {
      hydratedCases.push(await buildCaseRecord({
        sourceName: item.source_name || item.sourceName || 'case.epi',
        fileSize: item.file_size || item.fileSize || 0,
        archiveBytes: item.archive_base64 ? base64ToUint8Array(item.archive_base64) : null,
        manifest: item.manifest || {},
        steps: item.steps || [],
        analysis: item.analysis || null,
        policy: item.policy || null,
        policyEvaluation: item.policy_evaluation || item.policyEvaluation || null,
        review: item.review || null,
        environment: item.environment || null,
        stdout: item.stdout || null,
        stderr: item.stderr || null,
        integrity: item.integrity || null,
        signature: item.signature || null,
      }));
    }

    mergeCases(hydratedCases);
    applyPreloadedUiState(uiState);
    const shouldUseEmbeddedArtifactMode = openedFromArtifact || Boolean(uiState?.embeddedArtifactMode);
    if (hydratedCases.length) {
      state.selectedCaseId = hydratedCases[0].id;
      if ((!uiState || !uiState.view) && state.currentView === 'inbox') {
        state.currentView = 'case';
      }
      if (shouldUseEmbeddedArtifactMode) {
        state.currentView = 'case';
        configureEmbeddedArtifactMode();
        setStatus('Opened the packaged case file. A reviewed .epi download is ready, and source verification can be refreshed through epi view.', 'success');
      } else {
        const preloadCount = hydratedCases.length;
        const withArchiveBytes = hydratedCases.filter((caseRecord) => Boolean(caseRecord.archiveBytes)).length;
        const archiveMessage = withArchiveBytes === preloadCount
          ? 'A reviewed .epi download is ready.'
          : 'Some larger case files opened in review-only mode.';
        setStatus(`Opened ${preloadCount} case file${preloadCount === 1 ? '' : 's'} in the browser review workspace. ${archiveMessage}`, 'success');
      }
    }
  } catch (error) {
    setStatus(`Could not load the preopened case file: ${error.message}`, 'warning');
  }
}

async function parseEpiFile(file) {
  const artifactBytes = new Uint8Array(await file.arrayBuffer());
  const { containerFormat, payloadBytes } = await decodeEpiContainerBytes(artifactBytes);
  const zip = await JSZip.loadAsync(payloadBytes.slice(0));
  const artifactNames = Object.keys(zip.files)
    .filter((name) => !zip.files[name].dir)
    .sort();
  const manifestText = await readZipText(zip, 'manifest.json');
  const manifest = JSON.parse(manifestText);
  const steps = await readJsonl(zip, 'steps.jsonl');
  const analysis = await readOptionalJson(zip, 'analysis.json');
  const policy = await readOptionalJson(zip, 'policy.json');
  const policyEvaluation = await readOptionalJson(zip, 'policy_evaluation.json');
  const review = await readOptionalJson(zip, 'review.json');
  const environment = await readOptionalJson(zip, 'environment.json') || await readOptionalJson(zip, 'env.json');
  const mappingReport = await readOptionalJson(zip, 'artifacts/agt/mapping_report.json');
  const stdout = await readOptionalText(zip, 'stdout.log');
  const stderr = await readOptionalText(zip, 'stderr.log');

  const integrity = await checkIntegrity(zip, manifest);
  const signature = await verifySignature(manifest);

  return buildCaseRecord({
    sourceName: file.name,
    fileSize: file.size,
    archiveBytes: payloadBytes,
    containerFormat,
    manifest,
    steps,
    analysis,
    policy,
    policyEvaluation,
    review,
    environment,
    mappingReport,
    artifactNames,
    stdout,
    stderr,
    integrity,
    signature,
  });
}

async function buildCaseRecord(payload) {
  const manifest = payload.manifest || {};
  const steps = Array.isArray(payload.steps) ? payload.steps : [];
  const analysis = payload.analysis || null;
  const policy = payload.policy || null;
  const policyEvaluation = payload.policyEvaluation || null;
  const review = payload.review || null;
  const integrity = payload.integrity || {
    ok: true,
    checked: Object.keys(manifest.file_manifest || {}).length,
    mismatches: [],
  };
  const signature = payload.signature || {
    valid: false,
    reason: manifest.signature ? 'Signature was not rechecked in this view.' : 'No signer attached to this case file',
  };
  const sourceName = payload.sourceName || payload.source_name || 'case.epi';
  let archiveBytes = payload.archiveBytes || null;
  let containerFormat = payload.containerFormat || payload.container_format || null;
  if (archiveBytes && !containerFormat) {
    const decoded = await decodeEpiContainerBytes(archiveBytes);
    archiveBytes = decoded.payloadBytes;
    containerFormat = decoded.containerFormat;
  }
  const embeddedFiles = decodeEmbeddedFiles(payload.embeddedFiles || payload.files || null);
  const artifactNames = Array.isArray(payload.artifactNames)
    ? [...payload.artifactNames]
    : listEmbeddedArtifactNames(embeddedFiles);
  const mappingReport = payload.mappingReport || payload.mapping_report || readOptionalEmbeddedJson(embeddedFiles, 'artifacts/agt/mapping_report.json');
  const reviewSignature = await verifyReviewSignature(review);
  const reviewState = deriveReviewState(review, analysis, policyEvaluation, reviewSignature);
  const sourceTrustState = payload.sourceTrustState || payload.source_trust_state || null;
  const sharedWorkflow = payload.environment?.shared_workflow || {};
  const status = payload.status || sharedWorkflow.status || (reviewState.code === 'pending' ? 'unassigned' : 'resolved');
  const assignee = payload.assignee || sharedWorkflow.assignee || '';
  const dueAt = payload.due_at || payload.dueAt || sharedWorkflow.due_at || '';
  const commentCount = Number(payload.comment_count || payload.commentCount || sharedWorkflow.comment_count || 0);
  const lastCommentAt = payload.last_comment_at || payload.lastCommentAt || sharedWorkflow.last_comment_at || null;
  const comments = Array.isArray(payload.comments) ? payload.comments : [];
  const activity = Array.isArray(payload.activity) ? payload.activity : [];
  const trust = sourceTrustState || deriveTrustState(manifest, integrity, signature);
  const sourceProfile = deriveSourceProfile(manifest, analysis, mappingReport, artifactNames);
  const attachmentGroups = buildAttachmentGroups(artifactNames, sourceProfile);

  return {
    id: payload.id || createCaseId(sourceName, manifest),
    sourceName,
    fileSize: payload.fileSize || 0,
    archiveBytes,
    containerFormat: containerFormat || manifest.container_format || 'envelope-v2',
    embeddedFiles,
    manifest,
    steps,
    analysis,
    policy,
    policyEvaluation,
    review,
    environment: payload.environment || null,
    mappingReport,
    artifactNames,
    sourceProfile,
    attachmentGroups,
    stdout: payload.stdout || null,
    stderr: payload.stderr || null,
    sharedWorkspaceCase: Boolean(payload.sharedWorkspaceCase || payload.shared_workspace_case),
    backendCase: Boolean(payload.backendCase || payload.backend_case),
    sharedUpdatedAt: payload.sharedUpdatedAt || payload.shared_updated_at || null,
    integrity,
    signature,
    trust,
    decision: deriveDecisionSummary(manifest, steps, analysis),
    workflow: deriveWorkflowName(manifest, steps, sourceName),
    reviewSignature,
    reviewState,
    risk: deriveRiskState(analysis, policyEvaluation, integrity, reviewState),
    status,
    workflowState: deriveWorkflowState(status),
    assignee,
    dueAt,
    commentCount,
    lastCommentAt,
    comments,
    activity,
    traceability: buildTraceabilityIndex({
      steps,
      analysis,
      policy,
      review,
      mappingReport,
      attachmentGroups,
    }),
    isOverdue: Boolean(payload.is_overdue) || isCaseOverdue(dueAt, status),
    priorityOverride: payload.priority_override || payload.priorityOverride || null,
  };
}

function caseRichnessScore(caseRecord) {
  let score = 0;
  if (caseRecord.archiveBytes) {
    score += 120;
  }
  if (caseRecord.embeddedFiles && Object.keys(caseRecord.embeddedFiles).length) {
    score += 80;
  }
  score += (caseRecord.steps || []).length * 2;
  if (caseRecord.analysis) {
    score += 30;
  }
  if (caseRecord.policy) {
    score += 20;
  }
  if (caseRecord.environment) {
    score += 10;
  }
  if (caseRecord.sharedWorkspaceCase) {
    score -= 5;
  }
  return score;
}

function reviewTimestamp(review) {
  const latest = getLatestReviewEntry({ review });
  return latest?.timestamp || review?.reviewed_at || '';
}

function mergeCaseRecords(existing, incoming) {
  const existingScore = caseRichnessScore(existing);
  const incomingScore = caseRichnessScore(incoming);
  const preferred = incomingScore >= existingScore ? incoming : existing;
  const secondary = preferred === incoming ? existing : incoming;
  const merged = {
    ...preferred,
  };

  if (!merged.analysis && secondary.analysis) {
    merged.analysis = secondary.analysis;
  }
  if (!merged.policy && secondary.policy) {
    merged.policy = secondary.policy;
  }
  if (!merged.policyEvaluation && secondary.policyEvaluation) {
    merged.policyEvaluation = secondary.policyEvaluation;
  }
  if (!merged.mappingReport && secondary.mappingReport) {
    merged.mappingReport = secondary.mappingReport;
  }
  if (!merged.environment && secondary.environment) {
    merged.environment = secondary.environment;
  }
  if (!merged.stdout && secondary.stdout) {
    merged.stdout = secondary.stdout;
  }
  if (!merged.stderr && secondary.stderr) {
    merged.stderr = secondary.stderr;
  }
  if (!merged.archiveBytes && secondary.archiveBytes) {
    merged.archiveBytes = secondary.archiveBytes;
  }
  if ((!merged.embeddedFiles || !Object.keys(merged.embeddedFiles).length) && secondary.embeddedFiles) {
    merged.embeddedFiles = secondary.embeddedFiles;
  }
  if ((!merged.artifactNames || !merged.artifactNames.length) && secondary.artifactNames) {
    merged.artifactNames = secondary.artifactNames;
  }

  if (reviewTimestamp(secondary.review) > reviewTimestamp(merged.review)) {
    merged.review = secondary.review;
    merged.reviewSignature = secondary.reviewSignature;
    merged.reviewState = secondary.reviewState;
  }

  merged.sharedWorkspaceCase = Boolean(existing.sharedWorkspaceCase || incoming.sharedWorkspaceCase);
  merged.backendCase = Boolean(existing.backendCase || incoming.backendCase);
  merged.sharedUpdatedAt = incoming.sharedUpdatedAt || existing.sharedUpdatedAt || null;
  merged.status = incoming.status || existing.status;
  merged.workflowState = deriveWorkflowState(merged.status);
  merged.assignee = incoming.assignee || existing.assignee || '';
  merged.dueAt = incoming.dueAt || existing.dueAt || '';
  merged.commentCount = Number(incoming.commentCount || existing.commentCount || 0);
  merged.lastCommentAt = incoming.lastCommentAt || existing.lastCommentAt || null;
  merged.comments = Array.isArray(incoming.comments) && incoming.comments.length ? incoming.comments : (existing.comments || []);
  merged.activity = Array.isArray(incoming.activity) && incoming.activity.length ? incoming.activity : (existing.activity || []);
  merged.isOverdue = Boolean(incoming.isOverdue || existing.isOverdue || isCaseOverdue(merged.dueAt, merged.status));
  merged.priorityOverride = incoming.priorityOverride || existing.priorityOverride || null;
  if (!merged.trust && secondary.trust) {
    merged.trust = secondary.trust;
  }
  if (!merged.sourceProfile && secondary.sourceProfile) {
    merged.sourceProfile = secondary.sourceProfile;
  }
  if ((!merged.attachmentGroups || !merged.attachmentGroups.length) && secondary.attachmentGroups) {
    merged.attachmentGroups = secondary.attachmentGroups;
  }
  merged.risk = deriveRiskState(merged.analysis, merged.policyEvaluation, merged.integrity, merged.reviewState);
  merged.traceability = buildTraceabilityIndex({
    steps: merged.steps || [],
    analysis: merged.analysis,
    policy: merged.policy,
    review: merged.review,
    mappingReport: merged.mappingReport,
    attachmentGroups: merged.attachmentGroups,
  });
  return merged;
}

function buildLegacyEmbeddedCasePayload(payload) {
  const manifest = payload?.manifest || {};
  return {
    sourceName:
      manifest.workflow_name ||
      manifest.system_name ||
      manifest.workflow_id ||
      'case.epi',
    fileSize: 0,
    archiveBytes: null,
    manifest,
    steps: Array.isArray(payload?.steps) ? payload.steps : [],
    analysis: payload?.analysis || null,
    policy: payload?.policy || null,
    policyEvaluation: payload?.policy_evaluation || payload?.policyEvaluation || null,
    review: payload?.review || null,
    environment: payload?.environment || null,
    stdout: payload?.stdout || null,
    stderr: payload?.stderr || null,
    embeddedFiles: payload?.files || null,
    integrity: {
      ok: true,
      checked: Object.keys(manifest.file_manifest || {}).length,
      mismatches: [],
      pending: true,
    },
    signature: manifest.signature
      ? {
        valid: false,
        pending: true,
        reason: 'Open this case file through epi view to verify the signer and file integrity.',
      }
      : {
        valid: false,
        reason: 'No signer attached to this case file',
      },
  };
}

async function loadExampleCase() {
  const caseRecord = await buildCaseRecord(buildExampleCasePayload());
  mergeCases([caseRecord]);
  state.selectedCaseId = caseRecord.id;
  renderApp();
  setView('case');
  setStatus('Opened an example case so you can explore the review flow right away.', 'success');
}

function scrollToSetupWizard() {
  if (elements.setupPanelDetails) {
    elements.setupPanelDetails.open = true;
  }
  const setupPanel = document.querySelector('.setup-panel');
  setupPanel?.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function buildExampleCasePayload() {
  const manifest = {
    spec_version: '2.0',
    created_at: '2026-03-26T10:30:00Z',
    workflow_name: 'Refund approvals',
    system_name: 'Zendesk refund assistant',
    workflow_id: 'refund-approval-example',
    goal: 'Review a refund request safely before money is sent.',
    notes: 'Example case loaded from the browser.',
    file_manifest: {
      'manifest.json': 'example-manifest',
      'steps.jsonl': 'example-steps',
      'analysis.json': 'example-analysis',
      'policy.json': 'example-policy',
    },
  };

  return {
    sourceName: 'example_refund_case.epi',
    fileSize: 0,
    archiveBytes: null,
    manifest,
    steps: [
      {
        kind: 'session.start',
        timestamp: '2026-03-26T10:30:00Z',
        content: {
          workflow: 'Refund approvals',
        },
      },
      {
        kind: 'llm.request',
        timestamp: '2026-03-26T10:30:12Z',
        content: {
          model: 'gpt-5.4',
          messages: [
            {
              role: 'user',
              content: 'Review refund request 84721 and decide whether it can move forward.',
            },
          ],
        },
      },
      {
        kind: 'llm.response',
        timestamp: '2026-03-26T10:30:17Z',
        content: {
          choices: [
            {
              message: {
                content: 'The refund amount is above the auto-approval threshold and identity verification is still missing. Escalate this case for manager review.',
              },
            },
          ],
        },
      },
      {
        kind: 'agent.approval.request',
        timestamp: '2026-03-26T10:30:22Z',
        content: {
          action: 'approve_refund',
          reviewer: 'manager',
          reason: 'Refund amount exceeds the automatic approval limit.',
        },
      },
      {
        kind: 'agent.decision',
        timestamp: '2026-03-26T10:30:30Z',
        content: {
          decision: 'refund sent for review',
          confidence: 0.71,
          review_required: true,
          rationale: 'The request is high value and the required identity check was not completed.',
        },
      },
    ],
    analysis: {
      summary: 'A high-value refund was stopped for human review because identity verification was missing.',
      fault_detected: true,
      review_required: true,
      why_it_matters: 'A refund above the review threshold should not move forward without identity verification.',
      human_review: {
        status: 'pending',
      },
      primary_fault: {
        category: 'Missing check',
        fault_type: 'sequence_guard',
        step_number: 4,
        rule_id: 'R002',
        rule_name: 'Verify identity before refund',
        severity: 'critical',
        description: 'Identity verification did not happen before the refund decision.',
        why_it_matters: 'This refund exceeds the auto-approval limit and the customer identity check was not recorded.',
        plain_english: 'The system tried to move a high-value refund forward before the required identity check happened.',
      },
    },
    policy: {
      policy_format_version: '2.0',
      policy_id: 'zendesk-refunds-production',
      system_name: 'zendesk-refund-assistant',
      system_version: '1.0',
      policy_version: '2026-03-26',
      profile_id: 'finance.refund-agent',
      scope: {
        organization: 'Acme Support',
        team: 'refund-ops',
        application: 'zendesk',
        workflow: 'refund-approval',
        environment: 'production',
      },
      approval_policies: [
        {
          approval_id: 'refund-manager-approval',
          required_roles: ['manager'],
          minimum_approvers: 1,
          expires_after_minutes: null,
          reason_required: true,
          separation_of_duties: false,
        },
      ],
      rules: [
        {
          id: 'R001',
          name: 'Manager approval above threshold',
          severity: 'critical',
          description: 'Refunds above $500 require manager approval.',
          type: 'threshold_guard',
          mode: 'require_approval',
          applies_at: 'decision',
          threshold_field: 'amount',
          threshold_value: '500',
          required_action: 'human_approval',
        },
        {
          id: 'R002',
          name: 'Verify identity before refund',
          severity: 'critical',
          description: 'Identity must be verified before a refund can be finalized.',
          type: 'sequence_guard',
          required_before: 'issue_refund',
          must_call: 'verify_identity',
        },
      ],
    },
    policyEvaluation: {
      controls_evaluated: 4,
      controls_failed: 1,
      artifact_review_required: true,
    },
    review: null,
    environment: {
      source_system: 'Zendesk',
      region: 'us-east-1',
    },
    stdout: null,
    stderr: null,
    integrity: {
      ok: true,
      checked: 4,
      mismatches: [],
    },
    signature: {
      valid: false,
      reason: 'No signer is attached to this example case.',
    },
  };
}

function listEmbeddedArtifactNames(embeddedFiles) {
  if (!embeddedFiles || typeof embeddedFiles !== 'object') {
    return [];
  }
  return Object.keys(embeddedFiles).sort();
}

function readEmbeddedText(embeddedFiles, name) {
  if (!embeddedFiles || !embeddedFiles[name]) {
    return null;
  }
  try {
    return new TextDecoder().decode(embeddedFiles[name]);
  } catch (_error) {
    return null;
  }
}

function readOptionalEmbeddedJson(embeddedFiles, name) {
  const text = readEmbeddedText(embeddedFiles, name);
  if (!text) {
    return null;
  }
  try {
    return JSON.parse(text);
  } catch (_error) {
    return null;
  }
}

function deriveSourceProfile(manifest, analysis, mappingReport, artifactNames) {
  const tags = Array.isArray(manifest?.tags) ? manifest.tags.map((item) => String(item).toLowerCase()) : [];
  const artifactSet = new Set(Array.isArray(artifactNames) ? artifactNames : []);
  const analysisWarning = String(analysis?.warning || '').toLowerCase();
  const analysisMode = String(analysis?.mode || '').toLowerCase();
  const hasMappingReport = Boolean(mappingReport) || artifactSet.has('artifacts/agt/mapping_report.json');
  const looksLikeAgt =
    hasMappingReport ||
    tags.includes('agt') ||
    String(analysis?.source_system || '').toLowerCase() === 'agt' ||
    analysisMode === 'agt_import' ||
    analysisWarning.includes('agent governance toolkit');
  const hasRawAgtPayloads = Array.from(artifactSet).some((name) => name.startsWith('artifacts/agt/'));
  const synthesized = Boolean(mappingReport?.analysis?.synthesized || analysis?.synthesized);

  if (looksLikeAgt) {
    return {
      kind: 'agt-imported',
      label: 'AGT',
      sourceSystem: 'AGT',
      importMode: 'Imported via EPI',
      transformationAuditAvailable: hasMappingReport,
      rawSourceAvailable: hasRawAgtPayloads,
      synthesizedContentSummary: synthesized ? 'Synthesized analysis present' : 'Preserved raw evidence only',
      trustNarrative: synthesized ? 'Verified / Synthesized / Preserved raw' : 'Verified / Preserved raw',
    };
  }

  if (manifest?.source_system || manifest?.system_name || manifest?.workflow_name) {
    return {
      kind: 'epi-native',
      label: 'Native EPI',
      sourceSystem: manifest.source_system || manifest.system_name || 'EPI',
      importMode: 'Native EPI',
      transformationAuditAvailable: hasMappingReport,
      rawSourceAvailable: artifactSet.size > 0,
      synthesizedContentSummary: synthesized ? 'Synthesized analysis present' : 'Directly recorded evidence',
      trustNarrative: synthesized ? 'Verified / Synthesized' : 'Verified / Direct capture',
    };
  }

  return {
    kind: 'unknown',
    label: 'Unknown source',
    sourceSystem: 'Unknown',
    importMode: 'Portable EPI artifact',
    transformationAuditAvailable: hasMappingReport,
    rawSourceAvailable: artifactSet.size > 0,
    synthesizedContentSummary: synthesized ? 'Synthesized analysis present' : 'Portable case evidence',
    trustNarrative: synthesized ? 'Synthesized evidence present' : 'Portable case evidence',
  };
}

function buildAttachmentGroups(artifactNames, sourceProfile) {
  const groups = [
    { id: 'agt-source', label: 'AGT Source Data', items: [] },
    { id: 'epi-derived', label: 'EPI Derived Data', items: [] },
    { id: 'external-files', label: 'External Files', items: [] },
  ];

  (Array.isArray(artifactNames) ? artifactNames : [])
    .filter((name) => !['mimetype', 'viewer.html'].includes(name))
    .forEach((name) => {
      const item = {
        name,
        previewable: /\.(json|jsonl|txt|log|md)$/i.test(name),
      };
      if (name.startsWith('artifacts/agt/')) {
        groups[0].items.push(item);
      } else if (
        ['manifest.json', 'steps.jsonl', 'analysis.json', 'policy.json', 'policy_evaluation.json', 'review.json', 'environment.json', 'env.json', 'stdout.log', 'stderr.log'].includes(name) ||
        name.startsWith('artifacts/')
      ) {
        groups[1].items.push(item);
      } else {
        groups[2].items.push(item);
      }
    });

  return groups.filter((group) => {
    if (group.items.length) {
      return true;
    }
    return group.id !== 'agt-source' || sourceProfile?.kind === 'agt-imported';
  });
}

function buildTraceabilityIndex({ steps, analysis, policy, review, mappingReport, attachmentGroups }) {
  const latestReview = getLatestReviewEntry({ review });
  const primaryStepNumber = Number(analysis?.primary_fault?.step_number || 0) || null;
  const ruleId = analysis?.primary_fault?.rule_id || latestReview?.rule_id || null;
  const sourceAttachmentNames = (attachmentGroups || [])
    .flatMap((group) => group.items || [])
    .map((item) => item.name);
  const mappedAttachment =
    mappingReport?.field_handling?.preserved_raw?.[0]?.mapped_to ||
    mappingReport?.field_handling?.translated?.find((item) => String(item.mapped_to || '').startsWith('artifacts/'))?.mapped_to ||
    sourceAttachmentNames.find((name) => name.startsWith('artifacts/agt/')) ||
    null;

  return {
    primaryStepNumber,
    latestReviewStepNumber: Number(latestReview?.fault_step || 0) || primaryStepNumber,
    ruleId,
    mappedAttachment,
    sourceAttachmentNames,
    recognizedPolicySteps: Array.isArray(steps)
      ? steps
        .map((step, index) => ({ step, stepNumber: index + 1 }))
        .filter(({ step }) => ['policy.check', 'agent.decision', 'agent.approval.request', 'agent.approval.response'].includes(step.kind))
      : [],
    ruleCount: Array.isArray(policy?.rules) ? policy.rules.length : 0,
  };
}

function decodeEmbeddedFiles(entries) {
  if (!entries || typeof entries !== 'object') {
    return null;
  }

  const files = {};
  Object.entries(entries).forEach(([name, value]) => {
    if (typeof value === 'string' && value) {
      files[name] = base64ToUint8Array(value);
    }
  });

  return Object.keys(files).length ? files : null;
}

function mergeCases(newCases) {
  if (!newCases.length) {
    return;
  }

  const merged = new Map(state.cases.map((item) => [item.id, item]));
  newCases.forEach((item) => {
    const existing = merged.get(item.id);
    merged.set(item.id, existing ? mergeCaseRecords(existing, item) : item);
  });
  state.cases = Array.from(merged.values()).sort((left, right) => {
    return compareIsoDates(right.manifest.created_at, left.manifest.created_at);
  });

  if (!state.selectedCaseId && state.cases.length) {
    state.selectedCaseId = state.cases[0].id;
  }
}

function resetWorkspace() {
  state.cases = [];
  state.selectedCaseId = null;
  state.workspaceSetup = null;
  state.connectorProfiles = {};
  state.liveConnectorRecord = null;
  state.activeCaseSection = 'audit-first-card';
  state.caseHighlights = {
    stepNumber: null,
    attachmentName: null,
  };
  state.attachmentPreviewCache = {};
  state.policyEditors = {};
  state.currentView = 'inbox';
  state.filters = {
    search: '',
    trust: 'all',
    status: 'all',
    quickView: 'all',
    review: 'all',
    workflow: 'all',
  };
  elements.searchInput.value = '';
  elements.statusFilter.value = 'all';
  elements.quickViewFilter.value = 'all';
  elements.trustFilter.value = 'all';
  elements.reviewFilter.value = 'all';
  elements.workflowFilter.innerHTML = '<option value="all">All workflows</option>';
  elements.caseSelector.innerHTML = '';
  elements.reviewSaveStatus.textContent = '';
  resetSetupWizardForm();
  resetImportControls();
  renderApp();
  if (bridgeSupportsSharedWorkspace(state.bridgeHealth)) {
    void refreshSharedWorkspace(false);
  }
  setStatus('Started over. You can open saved cases or reuse a saved setup on this device.', 'info');
}

function configureEmbeddedArtifactMode() {
  state.embeddedArtifactMode = true;
  document.body.classList.add('embedded-artifact-mode');

  elements.addFilesButton.disabled = true;
  elements.dropZone.classList.add('disabled');
  elements.dropZone.setAttribute('aria-disabled', 'true');
  elements.dropZoneTitle.textContent = 'Embedded case file loaded';
  elements.dropZoneCopy.textContent = 'This packaged case review already contains the case record. Open this file again with epi view to add more .epi files.';
  elements.dropZoneAction.textContent = 'Embedded case file ready';
}

function resetImportControls() {
  state.embeddedArtifactMode = false;
  document.body.classList.remove('embedded-artifact-mode');
  elements.addFilesButton.disabled = false;
  elements.dropZone.classList.remove('disabled');
  elements.dropZone.removeAttribute('aria-disabled');
  elements.dropZoneTitle.textContent = 'Open local EPI cases';
  elements.dropZoneCopy.textContent = 'Drop `.epi` files here or choose them from your computer. Nothing is uploaded.';
  elements.dropZoneAction.textContent = 'Choose files';
}

function setView(viewName) {
  state.currentView = viewName;
  document.querySelectorAll('.nav-button').forEach((button) => {
    button.classList.toggle('active', button.dataset.view === viewName);
  });
  document.querySelectorAll('.view-panel').forEach((panel) => {
    panel.classList.toggle('active', panel.dataset.viewPanel === viewName);
  });
}

function setProgressiveNavigationState(hasSelectedCase) {
  [elements.rulesNavButton, elements.reportsNavButton].forEach((button) => {
    if (!button) {
      return;
    }
    button.disabled = !hasSelectedCase;
  });
  if (elements.caseSectionNav) {
    elements.caseSectionNav.hidden = !hasSelectedCase;
  }
  if (!hasSelectedCase && ['rules', 'reports'].includes(state.currentView)) {
    state.currentView = state.cases.length ? 'case' : 'inbox';
  }
}

function selectCase(caseId) {
  if (!caseId) {
    return;
  }
  state.selectedCaseId = caseId;
  state.activeCaseSection = 'audit-first-card';
  state.caseHighlights.stepNumber = null;
  state.caseHighlights.attachmentName = null;
  renderCaseView();
  renderRulesView();
  renderReportsView();
  elements.caseSelector.value = caseId;
}

function casePriorityScore(caseRecord) {
  const statusScore = {
    unassigned: 0,
    in_review: 1,
    assigned: 2,
    blocked: 3,
    resolved: 4,
  }[caseRecord.status] ?? 5;
  const reviewScore = {
    pending: 0,
    reviewed: 2,
    'not-required': 3,
  }[caseRecord.reviewState.code] ?? 4;
  const trustScore = {
    'do-not-use': -3,
    'verify-source': 0,
    'source-not-proven': 1,
    trusted: 2,
  }[caseRecord.trust.code] ?? 2;
  const riskScore = /high/i.test(caseRecord.risk.label)
    ? 0
    : /attention|review/i.test(caseRecord.risk.label)
      ? 1
      : 2;
  const overdueScore = caseRecord.isOverdue ? -2 : 0;

  return (statusScore * 10) + (reviewScore * 6) + (riskScore * 4) + trustScore + overdueScore;
}

function getPriorityCase(cases = state.cases) {
  if (!Array.isArray(cases) || !cases.length) {
    return null;
  }
  return [...cases].sort((left, right) => {
    const scoreDifference = casePriorityScore(left) - casePriorityScore(right);
    if (scoreDifference !== 0) {
      return scoreDifference;
    }
    return compareIsoDates(left.manifest.created_at, right.manifest.created_at);
  })[0];
}

function focusPriorityCase() {
  const priorityCase = getPriorityCase();
  if (!priorityCase) {
    return null;
  }
  selectCase(priorityCase.id);
  setView('case');
  elements.workspace.scrollIntoView({ behavior: 'smooth', block: 'start' });
  return priorityCase;
}

async function startGuidedReview() {
  const priorityCase = focusPriorityCase();
  if (!priorityCase) {
    if (state.workspaceSetup) {
      await fetchLiveConnectorRecord();
    } else {
      await loadExampleCase();
    }
    return;
  }
  await openCaseReviewForm();
}

function openPriorityCaseReason() {
  const priorityCase = focusPriorityCase();
  if (!priorityCase) {
    scrollToSetupWizard();
    return;
  }
  scrollToCaseSection('case-policy-card');
}

function scrollToCaseSection(sectionId) {
  setView('case');
  state.activeCaseSection = sectionId;
  document.querySelectorAll('.case-section-button').forEach((button) => {
    button.classList.toggle('active', button.dataset.caseSectionTarget === sectionId);
  });
  const section = document.getElementById(sectionId);
  if (!section) {
    return;
  }
  section.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function openReportsView() {
  setView('reports');
  elements.workspace.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function renderApp() {
  const hasCases = state.cases.length > 0;

  renderSetupWizard();
  renderSharedWorkspaceStatus();
  renderSummary();
  renderCaseSelector();
  renderWorkflowFilter();
  elements.searchInput.value = state.filters.search;
  elements.statusFilter.value = state.filters.status;
  elements.quickViewFilter.value = state.filters.quickView;
  elements.trustFilter.value = state.filters.trust;
  elements.reviewFilter.value = state.filters.review;
  elements.reviewerIdentity.value = state.reviewerIdentity;

  elements.summaryStrip.hidden = !hasCases;
  elements.workspace.hidden = !hasCases;
  elements.emptyInbox.hidden = true;
  elements.caseList.hidden = !hasCases;

  if (!hasCases) {
    setView('inbox');
  } else if (!getSelectedCase()) {
    const priorityCase = hasCases ? getPriorityCase(state.cases) : null;
    state.selectedCaseId = priorityCase ? priorityCase.id : null;
    if (priorityCase && state.currentView === 'inbox') {
      state.currentView = 'case';
    }
  }

  setProgressiveNavigationState(Boolean(getSelectedCase()));

  renderGuidedReviewPanel();
  renderInbox();
  renderCaseView();
  renderRulesView();
  renderReportsView();
  setView(state.currentView);
}

function applyPreloadedUiState(uiState) {
  if (!uiState || typeof uiState !== 'object') {
    return;
  }

  if (['inbox', 'case', 'rules', 'reports'].includes(uiState.view)) {
    state.currentView = uiState.view;
  }
  if (typeof uiState.embeddedArtifactMode === 'boolean') {
    state.embeddedArtifactMode = uiState.embeddedArtifactMode;
  }
}

function renderSummary() {
  const pendingReviews = state.cases.filter((caseRecord) => caseRecord.status !== 'resolved').length;
  const trustedCases = state.cases.filter((caseRecord) => caseRecord.trust.code === 'trusted').length;
  const workflowCount = new Set(state.cases.map((caseRecord) => caseRecord.workflow)).size;

  elements.summaryTotal.textContent = String(state.cases.length);
  elements.summaryReview.textContent = String(pendingReviews);
  elements.summaryTrusted.textContent = String(trustedCases);
  elements.summaryWorkflows.textContent = String(workflowCount);
}

function renderGuidedReviewPanel() {
  if (!state.cases.length) {
    elements.guidedReviewPanel.hidden = true;
    return;
  }
  const priorityCase = getPriorityCase();
  const pendingCount = state.cases.filter((caseRecord) => caseRecord.status !== 'resolved').length;
  const shouldShow = true;

  elements.guidedReviewPanel.hidden = !shouldShow;
  if (!shouldShow) {
    return;
  }

  if (priorityCase) {
    const dueText = priorityCase.dueAt ? `Due ${formatDueDate(priorityCase.dueAt)}` : 'No due date yet';
    const ownerText = priorityCase.assignee ? `Owner ${priorityCase.assignee}` : 'No owner yet';
    const openCountText = pendingCount > 1
      ? `${pendingCount} decisions still need attention.`
      : 'This is the main decision that needs attention right now.';
    elements.guidedReviewTitle.textContent = pendingCount > 1
      ? 'Start with this decision'
      : 'Review this decision next';
    elements.guidedReviewCopy.textContent = `${openCountText} ${priorityCase.decision.summary}`;
    elements.guidedReviewMeta.textContent = `${priorityCase.workflow} | ${priorityCase.workflowState.label} | ${ownerText} | ${dueText}`;
    elements.guidedReviewButton.textContent = 'Open this case';
    elements.guidedWhyButton.textContent = 'Show why';
    elements.guidedQueueButton.hidden = false;
    elements.guidedWhyButton.hidden = false;
    elements.guidedSampleButton.hidden = true;
    elements.guidedExampleButton.hidden = true;
    return;
  }

  const setup = state.workspaceSetup;
  const canFetchSample = Boolean(setup?.bridgeUrl);
  elements.guidedReviewTitle.textContent = 'Start with one decision';
  elements.guidedReviewCopy.textContent = setup
    ? `Your ${setup.systemLabel} ${setup.workflowLabel.toLowerCase()} setup is ready. Open one sample or saved case, then review it from start to finish.`
    : 'Open one example or saved case first. EPI becomes much easier once you can review a single decision end to end.';
  elements.guidedReviewMeta.textContent = setup
    ? `Next best move: ${canFetchSample ? 'try a safe sample' : 'open an example case'}`
    : 'Next best move: open an example case or connect a real system when you are ready.';
  elements.guidedReviewButton.textContent = canFetchSample ? 'Try a safe sample' : 'Open example case';
  elements.guidedWhyButton.hidden = true;
  elements.guidedQueueButton.hidden = true;
  elements.guidedSampleButton.hidden = !setup;
  elements.guidedExampleButton.hidden = false;
}

function renderSetupWizard() {
  renderConnectorFields(elements.setupSystem.value || 'zendesk');
  const draft = buildSetupDraftFromInputs();
  syncSetupBridgeState(draft);
  const setup = buildWorkspaceSetup(draft);
  const badgeLabel = state.workspaceSetup ? 'Ready to use' : 'Optional';
  const badgeTone = state.workspaceSetup ? 'success' : 'neutral';
  setBadge(elements.setupReadyBadge, badgeLabel, badgeTone);
  updateConnectionStatusBadge(setup);
  renderSharedAuthPanel(setup);
  elements.setupWorkspaceButton.textContent = state.workspaceSetup ? 'Update setup' : 'Save setup';
  elements.downloadStarterPackButton.disabled = !state.workspaceSetup;
  elements.checkBridgeButton.disabled = !setup.bridgeUrl;
  elements.fetchLiveRecordButton.disabled = !setup.bridgeUrl;
  elements.fetchLiveRecordButton.textContent = shouldUseMockPreview(setup) ? 'Try a safe sample' : 'Open live record';
  elements.setupPreview.innerHTML = buildSetupPreviewHtml(setup);
  renderLiveConnectorPreview(setup);
  updateSetupStorageUi();
}

function renderConnectorFields(system) {
  const defs = getConnectorFieldDefs(system);
  const profile = getConnectorProfile(system);

  elements.connectorFields.innerHTML = defs.map((field) => {
    const isWide = ['instance_url', 'base_url', 'api_path'].includes(field.key);
    return `
      <label${isWide ? ' class="setup-field-span"' : ''}>
        ${escapeHtml(field.label)}
        <input
          class="text-input"
          type="${field.secret ? 'password' : 'text'}"
          data-connector-field="${escapeHtml(field.key)}"
          value="${escapeHtml(profile[field.key] || '')}"
          placeholder="${escapeHtml(field.placeholder || '')}"
          autocomplete="off"
        >
      </label>
    `;
  }).join('');
}

function handleConnectorFieldInput(event) {
  const field = event.target?.dataset?.connectorField;
  if (!field) {
    return;
  }

  const system = elements.setupSystem.value || 'zendesk';
  const profile = getConnectorProfile(system);
  profile[field] = event.target.value;

  const draft = buildSetupDraftFromInputs();
  syncSetupBridgeState(draft);
  refreshPreparedWorkspaceSetup();
  const setup = buildWorkspaceSetup(draft);
  elements.setupPreview.innerHTML = buildSetupPreviewHtml(setup);
  renderLiveConnectorPreview(setup);
  updateSetupStorageUi();
}

function getConnectorFieldDefs(system) {
  return CONNECTOR_FIELD_DEFS[system] || [];
}

function buildDefaultConnectorProfile(system) {
  const profile = {};
  getConnectorFieldDefs(system).forEach((field) => {
    profile[field.key] = field.defaultValue || '';
  });
  return profile;
}

function getConnectorProfile(system) {
  if (!state.connectorProfiles[system]) {
    state.connectorProfiles[system] = buildDefaultConnectorProfile(system);
  }
  return state.connectorProfiles[system];
}

function compactConnectorProfile(profile, system, includeSecrets = true) {
  const compacted = {};
  getConnectorFieldDefs(system).forEach((field) => {
    const value = String(profile?.[field.key] || '').trim();
    if (!value) {
      return;
    }
    if (field.secret && !includeSecrets) {
      return;
    }
    compacted[field.key] = value;
  });
  return compacted;
}

function hasConfiguredLiveConnectorProfile(system, profile) {
  const requiredFields = CONNECTOR_LIVE_FIELDS[system] || [];
  return requiredFields.every((field) => String(profile?.[field] || '').trim());
}

function shouldUseMockPreview(setup) {
  return !hasConfiguredLiveConnectorProfile(setup.system, setup.connectorProfile || {});
}

function updateSetupStorageUi() {
  const hasSaved = hasSavedSetupProfile();
  const system = elements.setupSystem.value || 'zendesk';
  const configuredCount = Object.keys(compactConnectorProfile(getConnectorProfile(system), system, false)).length;

  elements.loadSetupProfileButton.disabled = !hasSaved;
  elements.clearSetupProfileButton.disabled = !hasSaved;
  elements.setupStorageNote.textContent = hasSaved
    ? `Saved on this device. ${configuredCount ? `${configuredCount} field${configuredCount === 1 ? '' : 's'} are ready for ${SETUP_SYSTEMS[system].label}.` : 'You can reuse this setup any time on this device.'} Secure keys are never saved here. Passwords and sign-in tokens stay only in this tab.`
    : 'EPI can remember this setup only in this browser on this device. Secure keys, passwords, and sign-in tokens stay only in the current session.';
}

function getSavedSetupProfile() {
  try {
    const raw = window.localStorage.getItem(SETUP_STORAGE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch (_error) {
    return null;
  }
}

function hasSavedSetupProfile() {
  return Boolean(getSavedSetupProfile());
}

function saveSetupProfile() {
  const payload = {
    version: 2,
    draft: buildSetupDraftFromInputs(),
    connector_profiles: Object.fromEntries(
      Object.keys(CONNECTOR_FIELD_DEFS).map((system) => [system, compactConnectorProfile(getConnectorProfile(system), system, false)]),
    ),
  };

  try {
    window.localStorage.setItem(SETUP_STORAGE_KEY, JSON.stringify(payload));
    updateSetupStorageUi();
    setStatus(`Saved your ${SETUP_SYSTEMS[payload.draft.system].label} setup on this device. Secure keys stay only in this session.`, 'success');
  } catch (error) {
    setStatus(`Could not save this setup on this device: ${error.message}`, 'warning');
  }
}

function restoreSavedSetupProfile(silent) {
  const saved = getSavedSetupProfile();
  if (!saved) {
    if (!silent) {
      setStatus('No saved setup was found on this device.', 'warning');
    }
    return false;
  }

  applySavedSetupProfile(saved);
  if (!silent) {
    renderApp();
    setView('rules');
    setStatus(`Loaded your saved ${SETUP_SYSTEMS[(saved.draft || {}).system || 'zendesk'].label} setup. Secure keys may need to be pasted again.`, 'success');
  }
  return true;
}

function applySavedSetupProfile(saved) {
  const draft = saved?.draft || {};
  const connectorProfiles = saved?.connector_profiles || {};

  elements.setupSystem.value = draft.system || 'zendesk';
  elements.setupWorkflow.value = draft.workflow || 'refund-approval';
  elements.setupReviewerRole.value = draft.reviewerRole || 'manager';
  elements.setupEnvironment.value = draft.environment || 'production';
  elements.setupRequiredStep.value = draft.requiredStep || '';
  elements.setupBridgeUrl.value = draft.bridgeUrl || 'http://127.0.0.1:8765';

  state.connectorProfiles = {};
  state.bridgeHealth = null;
  state.liveConnectorRecord = null;
  Object.keys(CONNECTOR_FIELD_DEFS).forEach((system) => {
    const defaults = buildDefaultConnectorProfile(system);
    const restored = connectorProfiles[system] || {};
    Object.keys(defaults).forEach((key) => {
      if (restored[key] != null) {
        defaults[key] = String(restored[key]);
      }
    });
    state.connectorProfiles[system] = defaults;
  });

  const setup = buildWorkspaceSetup(buildSetupDraftFromInputs());
  state.workspaceSetup = setup;
  state.policyEditors[POLICY_EDITOR_EMPTY_KEY] = createPolicyEditorFromSetup(setup);
}

function clearSavedSetupProfile() {
  try {
    window.localStorage.removeItem(SETUP_STORAGE_KEY);
  } catch (_error) {
    // Ignore local storage cleanup errors and continue clearing in-memory state.
  }
  updateSetupStorageUi();
  setStatus('Forgot the saved setup on this device.', 'info');
}

function normalizeBridgeUrl(value) {
  const trimmed = String(value || '').trim();
  if (!trimmed) {
    return '';
  }
  return trimmed.replace(/\/+$/, '');
}

function bridgeSessionReady(bridgeHealth) {
  return Boolean(bridgeHealth && (!bridgeHealth.authRequired || state.gatewayAccessToken));
}

function buildBridgeHeaders(extraHeaders = {}) {
  const headers = new Headers(extraHeaders);
  if (state.gatewayAccessToken) {
    headers.set('Authorization', `Bearer ${state.gatewayAccessToken}`);
  }
  return headers;
}

function bridgeFetch(url, options = {}) {
  const nextOptions = { ...options };
  nextOptions.headers = buildBridgeHeaders(options.headers || {});
  return fetch(url, nextOptions);
}

async function fetchBridgeHealthSnapshot(bridgeUrl) {
  const response = await bridgeFetch(`${bridgeUrl}/health`);
  const payload = await response.json();
  if (!response.ok || !payload.ok) {
    throw new Error(payload.error || `Health check failed with status ${response.status}`);
  }

  let readyPayload = {};
  try {
    const readyResponse = await bridgeFetch(`${bridgeUrl}/ready`);
    readyPayload = await readyResponse.json();
  } catch (_error) {
    readyPayload = {};
  }

  return {
    ok: true,
    url: bridgeUrl,
    service: payload.service,
    version: payload.version,
    capabilities: payload.capabilities || {},
    workspaceFile: payload.workspace_file || '',
    checkedAt: new Date().toISOString(),
    ready: readyPayload.ok !== undefined ? Boolean(readyPayload.ok) : Boolean(payload.ready),
    readyStatus: readyPayload.status || (payload.ready ? 'ready' : 'starting'),
    authRequired: Boolean(payload.auth_required),
    authMode: payload.auth_mode || readyPayload.auth_mode || 'disabled',
    localUserAuthEnabled: Boolean(payload.local_user_auth_enabled || readyPayload.local_user_auth_enabled),
    localUserCount: Number(payload.local_user_count || readyPayload.local_user_count || 0),
    retentionMode: payload.retention_mode || 'redacted_hashes',
    proxyFailureMode: payload.proxy_failure_mode || 'fail-open',
    replay: readyPayload.replay || payload.replay || null,
    projection: readyPayload.projection || payload.projection || null,
  };
}

function syncSetupBridgeState(draft) {
  const system = draft.system || 'zendesk';
  const bridgeUrl = normalizeBridgeUrl(draft.bridgeUrl);

  if (state.bridgeHealth && state.bridgeHealth.url !== bridgeUrl) {
    state.bridgeHealth = null;
  }

  if (state.liveConnectorRecord) {
    const matchesSystem = state.liveConnectorRecord.system === system;
    const matchesBridge = state.liveConnectorRecord.bridgeUrl === bridgeUrl;
    if (!matchesSystem || !matchesBridge) {
      state.liveConnectorRecord = null;
    }
  }
}

function refreshPreparedWorkspaceSetup() {
  if (!state.workspaceSetup) {
    return;
  }
  const draft = buildSetupDraftFromInputs();
  syncSetupBridgeState(draft);
  state.workspaceSetup = buildWorkspaceSetup(draft);
}

function getActiveBridgeHealth(bridgeUrl) {
  if (!state.bridgeHealth) {
    return null;
  }
  return state.bridgeHealth.url === normalizeBridgeUrl(bridgeUrl) ? state.bridgeHealth : null;
}

function getActiveLiveConnectorRecord(system, bridgeUrl) {
  if (!state.liveConnectorRecord) {
    return null;
  }
  const expectedBridgeUrl = normalizeBridgeUrl(bridgeUrl);
  return state.liveConnectorRecord.system === system && state.liveConnectorRecord.bridgeUrl === expectedBridgeUrl
    ? state.liveConnectorRecord
    : null;
}

function formatBridgeHealthLabel(bridgeHealth) {
  if (!bridgeHealth) {
    return 'Not checked';
  }
  if (!bridgeHealth.ok) {
    return 'Not connected';
  }
  if (bridgeHealth.authRequired && !state.gatewayAccessToken) {
    return 'Connected - token needed';
  }
  if (bridgeHealth.ready === false) {
    return 'Connected - replaying';
  }
  return 'Connected';
}

function bridgeSupportsSharedWorkspace(bridgeHealth) {
  return Boolean(bridgeHealth?.ok && bridgeHealth?.capabilities?.shared_workspace);
}

function formatLiveRecordLabel(liveConnectorRecord) {
  if (!liveConnectorRecord) {
    return 'Not loaded';
  }
  const recordId = liveConnectorRecord.record?.case_id || liveConnectorRecord.record?.ticket_id || liveConnectorRecord.record?.record_id || liveConnectorRecord.record?.sys_id;
  return recordId ? `Loaded (${recordId})` : 'Loaded';
}

function updateConnectionStatusBadge(setup) {
  let label = 'Connection not checked';
  let tone = 'neutral';

  if (setup.liveConnectorRecord) {
    label = 'Real record loaded';
    tone = 'success';
  } else if (setup.bridgeHealth?.ok) {
    label = formatBridgeHealthLabel(setup.bridgeHealth);
    if (setup.bridgeHealth.authRequired && state.authSession) {
      label = `Connected - signed in`;
    }
    tone = setup.bridgeHealth.authRequired && !state.gatewayAccessToken
      ? 'warning'
      : setup.bridgeHealth.ready === false
      ? 'warning'
      : 'success';
  } else if (setup.bridgeHealth && !setup.bridgeHealth.ok) {
    label = 'Not connected';
    tone = 'warning';
  }

  setBadge(elements.setupConnectionStatus, label, tone);
}

function renderSharedAuthPanel(setup) {
  if (!elements.sharedAuthSection || !elements.sharedAuthStatus || !elements.sharedAuthCopy) {
    return;
  }

  const bridgeHealth = setup.bridgeHealth;
  const localUserAuthEnabled = Boolean(bridgeHealth?.authRequired && bridgeHealth?.localUserAuthEnabled);
  elements.sharedAuthSection.hidden = !localUserAuthEnabled;
  if (!localUserAuthEnabled) {
    return;
  }

  if (!elements.authUsername.value) {
    elements.authUsername.value = state.authSession?.username || state.reviewerIdentity || '';
  }

  if (state.authSession) {
    const roleLabel = String(state.authSession.role || 'reviewer').replace('_', ' ');
    setBadge(elements.sharedAuthStatus, `Signed in as ${state.authSession.display_name || state.authSession.username}`, 'success');
    elements.sharedAuthCopy.textContent = `Signed in with ${roleLabel} access. EPI keeps this session only in the current browser tab.`;
    elements.authLoginButton.disabled = false;
    elements.authLogoutButton.disabled = false;
    elements.authPassword.disabled = false;
    elements.authUsername.disabled = false;
    return;
  }

  setBadge(elements.sharedAuthStatus, 'Sign in needed', 'warning');
  const userCountText = bridgeHealth?.localUserCount ? `${bridgeHealth.localUserCount} local user${bridgeHealth.localUserCount === 1 ? '' : 's'} ready.` : 'No local users were detected yet.';
  elements.sharedAuthCopy.textContent = `${userCountText} Sign in here to open the shared team workspace.`;
  elements.authLoginButton.disabled = !bridgeHealth?.ok;
  elements.authLogoutButton.disabled = !state.gatewayAccessToken;
  elements.authPassword.disabled = !bridgeHealth?.ok;
  elements.authUsername.disabled = !bridgeHealth?.ok;
}

function renderSharedWorkspaceStatus() {
  if (!elements.sharedWorkspaceStatus || !elements.refreshSharedButton) {
    return;
  }

  const bridgeHealth = state.bridgeHealth;
  if (!bridgeSupportsSharedWorkspace(bridgeHealth)) {
    setBadge(elements.sharedWorkspaceStatus, 'Local only', 'neutral');
    elements.refreshSharedButton.disabled = !bridgeHealth?.ok;
    return;
  }
  if (!bridgeSessionReady(bridgeHealth)) {
    setBadge(elements.sharedWorkspaceStatus, bridgeHealth?.localUserAuthEnabled ? 'Sign in needed' : 'Token needed', 'warning');
    elements.refreshSharedButton.disabled = false;
    return;
  }

  const caseCount = state.sharedWorkspace.cases.length;
  const prefix = state.authSession?.display_name || state.authSession?.username;
  const label = caseCount ? `${caseCount} team case${caseCount === 1 ? '' : 's'}${prefix ? ` · ${prefix}` : ''}` : prefix ? `Team sync on · ${prefix}` : 'Team sync on';
  setBadge(elements.sharedWorkspaceStatus, label, 'success');
  elements.refreshSharedButton.disabled = false;
}

async function loginToSharedWorkspace() {
  const bridgeUrl = normalizeBridgeUrl(elements.setupBridgeUrl?.value || state.bridgeHealth?.url || '');
  if (!bridgeUrl) {
    setStatus('Set the connection address first, then sign in.', 'warning');
    return;
  }

  const username = (elements.authUsername?.value || state.reviewerIdentity || '').trim();
  const password = (elements.authPassword?.value || '').trim();
  if (!username || !password) {
    setStatus('Enter your username/email and password first.', 'warning');
    return;
  }

  try {
    const response = await fetch(`${bridgeUrl}/api/auth/login`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ username, password }),
    });
    const payload = await response.json();
    if (!response.ok || !payload.ok || !payload.access_token) {
      throw new Error(payload.detail || payload.error || `Sign-in failed with status ${response.status}`);
    }

    state.gatewayAccessToken = String(payload.access_token).trim();
    state.authSession = payload.session || null;
    if (elements.setupAccessToken) {
      elements.setupAccessToken.value = state.gatewayAccessToken;
    }
    try {
      window.sessionStorage.setItem(GATEWAY_ACCESS_TOKEN_STORAGE_KEY, state.gatewayAccessToken);
    } catch (_error) {
      // Ignore storage errors and keep the in-memory token for this tab.
    }
    if (elements.authPassword) {
      elements.authPassword.value = '';
    }
    if (!state.reviewerIdentity) {
      elements.reviewerIdentity.value = username;
      saveReviewerIdentity();
    }

    state.bridgeHealth = await fetchBridgeHealthSnapshot(bridgeUrl);
    await refreshSharedWorkspace(false);
    renderApp();
    setStatus(`Signed in as ${state.authSession?.display_name || state.authSession?.username || username}.`, 'success');
  } catch (error) {
    setStatus(`Could not sign in yet: ${error.message}`, 'warning');
  }
}

async function logoutFromSharedWorkspace() {
  const bridgeUrl = normalizeBridgeUrl(state.bridgeHealth?.url || elements.setupBridgeUrl?.value || '');
  try {
    if (bridgeUrl && state.gatewayAccessToken) {
      await bridgeFetch(`${bridgeUrl}/api/auth/logout`, { method: 'POST' });
    }
  } catch (_error) {
    // Best-effort logout; local session cleanup still happens below.
  }

  clearGatewayAccessToken({ render: false });
  state.sharedWorkspace = {
    connected: false,
    cases: [],
    workspaceFile: '',
    lastSyncAt: null,
  };
  renderApp();
  setStatus('Signed out of the shared workspace for this browser tab.', 'info');
}

function renderLiveConnectorPreview(setup) {
  const liveConnectorRecord = setup.liveConnectorRecord;
  const bridgeHealth = setup.bridgeHealth;

  if (!liveConnectorRecord && !bridgeHealth) {
    elements.setupLiveRecord.hidden = true;
    elements.setupLiveRecord.innerHTML = '';
    return;
  }

  const bridgeRows = [
    `<dt>Status</dt><dd>${escapeHtml(formatBridgeHealthLabel(bridgeHealth))}</dd>`,
    `<dt>Address</dt><dd>${escapeHtml(setup.bridgeUrl || 'Not set')}</dd>`,
  ];
  if (bridgeHealth?.checkedAt) {
    bridgeRows.push(`<dt>Checked</dt><dd>${escapeHtml(formatDate(bridgeHealth.checkedAt))}</dd>`);
  }
  if (bridgeHealth) {
    bridgeRows.push(`<dt>Ready</dt><dd>${escapeHtml(bridgeHealth.readyStatus || (bridgeHealth.ready ? 'ready' : 'starting'))}</dd>`);
    bridgeRows.push(`<dt>Retention</dt><dd>${escapeHtml(bridgeHealth.retentionMode || 'redacted_hashes')}</dd>`);
    const authLabel = bridgeHealth.authRequired
      ? state.authSession
        ? `Signed in as ${state.authSession.display_name || state.authSession.username}`
        : state.gatewayAccessToken
        ? 'Token accepted in this tab'
        : bridgeHealth.localUserAuthEnabled
        ? 'Sign in required'
        : 'Token required'
      : 'Not required';
    bridgeRows.push(`<dt>Auth</dt><dd>${escapeHtml(authLabel)}</dd>`);
  }

  let recordSection = `
    <div>
      <p class="card-label">Real record</p>
      <p class="helper-copy">No real record has been loaded for this setup yet.</p>
    </div>
  `;
  if (liveConnectorRecord) {
    recordSection = `
      <div>
        <p class="card-label">Real record</p>
        <dl class="detail-grid">
          <dt>Loaded</dt><dd>${escapeHtml(formatDate(liveConnectorRecord.fetchedAt))}</dd>
          <dt>System</dt><dd>${escapeHtml(setup.systemLabel)}</dd>
          <dt>Record ID</dt><dd>${escapeHtml(liveConnectorRecord.caseInput?.case_id || liveConnectorRecord.caseInput?.record_id || liveConnectorRecord.caseInput?.ticket_id || 'Ready')}</dd>
          <dt>Source</dt><dd>${escapeHtml(liveConnectorRecord.record?.is_mock ? 'Safe sample from local bridge' : 'Live connector fetch')}</dd>
        </dl>
        ${liveConnectorRecord.record?.bridge_warning ? `<p class="helper-copy">${escapeHtml(liveConnectorRecord.record.bridge_warning)}</p>` : ''}
        <pre class="code-block compact-code">${escapeHtml(JSON.stringify(liveConnectorRecord.record, null, 2))}</pre>
      </div>
    `;
  }

  elements.setupLiveRecord.hidden = false;
  elements.setupLiveRecord.innerHTML = `
    <div class="setup-preview-grid">
      <div>
        <p class="card-label">Connection</p>
        <dl class="detail-grid">${bridgeRows.join('')}</dl>
      </div>
      ${recordSection}
    </div>
  `;
}

async function checkConnectorBridge() {
  const draft = buildSetupDraftFromInputs();
  syncSetupBridgeState(draft);
  const bridgeUrl = normalizeBridgeUrl(draft.bridgeUrl);
  if (!bridgeUrl) {
    setStatus('Open advanced settings if you need to change the connection address first.', 'warning');
    return;
  }

  try {
    state.bridgeHealth = await fetchBridgeHealthSnapshot(bridgeUrl);
    await refreshGatewayAuthSession();
    refreshPreparedWorkspaceSetup();
    renderSetupWizard();
    await refreshSharedWorkspace(false);
    await publishCasesToSharedWorkspace(state.cases);
    if (state.bridgeHealth.authRequired && !state.gatewayAccessToken) {
      setStatus(state.bridgeHealth.localUserAuthEnabled ? 'Connection is ready. Sign in to open shared team cases.' : 'Connection is ready. Add the access token in Advanced setup to open shared team cases.', 'warning');
    } else if (state.bridgeHealth.ready === false) {
      setStatus('Connection is up and replaying stored events. Shared cases will appear once it is ready.', 'warning');
    } else {
      setStatus('Connection is ready.', 'success');
    }
  } catch (error) {
    state.bridgeHealth = {
      ok: false,
      url: bridgeUrl,
      error: error.message || 'Could not reach the bridge',
      checkedAt: new Date().toISOString(),
    };
    state.sharedWorkspace = {
      connected: false,
      cases: [],
      workspaceFile: '',
      lastSyncAt: null,
    };
    refreshPreparedWorkspaceSetup();
    renderSetupWizard();
    setStatus(`Could not connect yet: ${error.message}`, 'warning');
  }
}

async function autodetectConnectorBridge() {
  const draft = buildSetupDraftFromInputs();
  syncSetupBridgeState(draft);
  const bridgeUrl = normalizeBridgeUrl(draft.bridgeUrl);
  if (!bridgeUrl || state.bridgeHealth?.ok) {
    return;
  }

  try {
    state.bridgeHealth = await fetchBridgeHealthSnapshot(bridgeUrl);
    await refreshGatewayAuthSession();
    refreshPreparedWorkspaceSetup();
    renderSetupWizard();
    await refreshSharedWorkspace(false);
    await publishCasesToSharedWorkspace(state.cases);
  } catch (_error) {
    // Silent on load. The explicit "Check local bridge" button gives actionable feedback.
  }
}

function buildBridgeFetchPayload(setup) {
  return {
    system: setup.system,
    connector_profile: {
      ...(setup.connectorProfile || {}),
      allow_mock_fallback: true,
    },
    case_input: {
      ...buildRecorderSampleInput(setup),
      allow_mock_fallback: true,
      preview_mode: shouldUseMockPreview(setup) ? 'sample' : 'live',
    },
  };
}

async function fetchLiveConnectorRecord() {
  const draft = buildSetupDraftFromInputs();
  syncSetupBridgeState(draft);
  const setup = buildWorkspaceSetup(draft);
  if (!setup.bridgeUrl) {
    setStatus('Open advanced settings if you need to change the connection address first.', 'warning');
    return;
  }

  try {
    const response = await bridgeFetch(`${setup.bridgeUrl}/api/fetch-record`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(buildBridgeFetchPayload(setup)),
    });
    const payload = await response.json();
    if (!response.ok || !payload.ok) {
      throw new Error(payload.error || `Fetch failed with status ${response.status}`);
    }

    state.bridgeHealth = {
      ok: true,
      url: setup.bridgeUrl,
      service: 'epi-connector-bridge',
      authRequired: Boolean(state.bridgeHealth?.authRequired),
      retentionMode: state.bridgeHealth?.retentionMode || 'redacted_hashes',
      ready: true,
      readyStatus: 'ready',
      checkedAt: new Date().toISOString(),
    };
    state.liveConnectorRecord = {
      system: setup.system,
      bridgeUrl: setup.bridgeUrl,
      fetchedAt: new Date().toISOString(),
      caseInput: buildRecorderSampleInput(setup),
      record: payload.record || {},
    };
    state.workspaceSetup = setup;
    state.policyEditors[POLICY_EDITOR_EMPTY_KEY] = createPolicyEditorFromSetup(setup);
    const caseRecord = await openLiveConnectorCasePreview(setup, state.liveConnectorRecord, payload.case || null);
    if (!caseRecord.backendCase) {
      await publishCaseToSharedWorkspace(caseRecord);
    }
    refreshPreparedWorkspaceSetup();
    renderSetupWizard();
    if (payload.record?.is_mock) {
      setStatus(`Opened a safe ${setup.systemLabel} sample so you can review the flow now. Add real connector details later if you want live records.`, 'success');
    } else {
      setStatus(`Opened a live ${setup.systemLabel} record as a case preview. You can review it now or use this setup in your system.`, 'success');
    }
  } catch (error) {
    state.liveConnectorRecord = null;
    refreshPreparedWorkspaceSetup();
    renderSetupWizard();
    setStatus(`Could not load a real ${setup.systemLabel} record yet: ${error.message}`, 'warning');
  }
}

async function openLiveConnectorCasePreview(setup, liveConnectorRecord, backendCasePayload) {
  const caseRecord = await buildCaseRecord(
    backendCasePayload || buildLiveConnectorCasePayload(setup, liveConnectorRecord),
  );
  mergeCases([caseRecord]);
  state.selectedCaseId = caseRecord.id;
  renderApp();
  setView('case');
  return caseRecord;
}

function buildLiveConnectorCasePayload(setup, liveConnectorRecord) {
  const fetchedAt = liveConnectorRecord.fetchedAt || new Date().toISOString();
  const record = liveConnectorRecord.record || {};
  const caseInput = liveConnectorRecord.caseInput || {};
  const recordId = deriveLiveRecordId(record, caseInput);
  const policyEditor = state.policyEditors[POLICY_EDITOR_EMPTY_KEY] || createPolicyEditorFromSetup(setup);
  const policyJson = buildExportablePolicyJson(policyEditor);
  const recordSummary = buildLiveRecordSummary(setup, record, caseInput, recordId);
  const sourceName = `live_${slugify(setup.system)}_${slugify(recordId || caseInput.case_id || 'record')}.epi`;

  return {
    sourceName,
    fileSize: 0,
    archiveBytes: null,
    manifest: {
      spec_version: '2.0',
      created_at: fetchedAt,
      workflow_name: setup.workflowLabel,
      system_name: setup.systemLabel,
      workflow_id: `${setup.workflow}-live-preview`,
      goal: `Review a live ${setup.workflowLabel.toLowerCase()} record before it is trusted.`,
      notes: recordSummary,
      file_manifest: {},
    },
    steps: [
      {
        kind: 'source.record.loaded',
        timestamp: fetchedAt,
        content: {
          system: setup.systemLabel,
          workflow: setup.workflowLabel,
          record_id: recordId || null,
          case_id: caseInput.case_id || null,
          preview_only: true,
          bridge_mode: record.bridge_mode || 'live',
        },
      },
      {
        kind: 'agent.decision',
        timestamp: fetchedAt,
        content: {
          decision: 'real record loaded for review',
          review_required: true,
          rationale: recordSummary,
        },
      },
    ],
    analysis: {
      summary: recordSummary,
      fault_detected: false,
      review_required: true,
      why_it_matters: 'A human should confirm that the live record, workflow rules, and system mapping look correct before this setup is trusted.',
      human_review: {
        status: 'pending',
      },
      secondary_flags: [
        {
          category: 'Setup check',
          fault_type: 'review_guard',
          description: 'This preview comes from the local connector bridge and should be checked before rollout.',
          why_it_matters: 'Use this case to confirm the source record shape, reviewer role, and starting rules.',
        },
      ],
    },
    policy: policyJson,
    policyEvaluation: {
      artifact_review_required: true,
      controls_evaluated: Array.isArray(policyJson.rules) ? policyJson.rules.length : 0,
      controls_failed: 0,
    },
    environment: {
      source_record: record,
      case_input: caseInput,
      preview_source: 'epi connect bridge',
    },
    integrity: {
      ok: true,
      checked: 0,
      mismatches: [],
    },
    signature: {
      valid: false,
      reason: 'Live record previews are unsigned until your system records a real .epi case.',
    },
  };
}

async function refreshSharedWorkspace(showStatus) {
  if (!bridgeSupportsSharedWorkspace(state.bridgeHealth)) {
    state.sharedWorkspace = {
      connected: false,
      cases: [],
      workspaceFile: '',
      lastSyncAt: null,
    };
    renderSharedWorkspaceStatus();
    return;
  }
  if (!bridgeSessionReady(state.bridgeHealth)) {
    state.sharedWorkspace = {
      connected: false,
      cases: [],
      workspaceFile: '',
      lastSyncAt: null,
    };
    renderSharedWorkspaceStatus();
    if (showStatus) {
      setStatus('Add the access token first, then refresh the shared inbox.', 'warning');
    }
    return;
  }

  try {
    let response = await bridgeFetch(`${state.bridgeHealth.url}/api/cases`);
    let payload = await response.json();
    if (response.ok && payload.ok) {
      payload = {
        ok: true,
        cases: Array.isArray(payload.cases) ? payload.cases : [],
        workspace_file: state.bridgeHealth.workspaceFile || '',
      };
    } else {
      response = await bridgeFetch(`${state.bridgeHealth.url}/api/workspace/state`);
      payload = await response.json();
    }
    if (!response.ok || !payload.ok) {
      throw new Error(payload.error || `Workspace sync failed with status ${response.status}`);
    }

    state.sharedWorkspace = {
      connected: true,
      cases: Array.isArray(payload.cases) ? payload.cases : [],
      workspaceFile: payload.workspace_file || state.bridgeHealth.workspaceFile || '',
      lastSyncAt: new Date().toISOString(),
    };
    await hydrateSharedWorkspaceCases(state.sharedWorkspace.cases);
    renderApp();
    renderSharedWorkspaceStatus();
    if (showStatus) {
      setStatus(`Refreshed ${state.sharedWorkspace.cases.length} shared case${state.sharedWorkspace.cases.length === 1 ? '' : 's'} from the team workspace.`, 'success');
    }
  } catch (error) {
    state.sharedWorkspace = {
      connected: false,
      cases: [],
      workspaceFile: '',
      lastSyncAt: null,
    };
    renderApp();
    renderSharedWorkspaceStatus();
    if (showStatus) {
      setStatus(`Could not refresh team cases yet: ${error.message}`, 'warning');
    }
  }
}

async function hydrateSharedWorkspaceCases(sharedCases) {
  if (!sharedCases.length) {
    return;
  }

  const hydrated = [];
  for (const item of sharedCases) {
    let payload = item;
    if (!item.manifest && state.bridgeHealth?.url && item.id) {
      try {
        const detailResponse = await bridgeFetch(`${state.bridgeHealth.url}/api/cases/${encodeURIComponent(item.id)}`);
        const detailPayload = await detailResponse.json();
        if (detailResponse.ok && detailPayload.ok && detailPayload.case) {
          payload = detailPayload.case;
        }
      } catch (_error) {
        payload = item;
      }
    }

    hydrated.push(await buildCaseRecord({
      id: payload.id || item.id,
      sourceName: payload.source_name || payload.sourceName || item.source_name || item.sourceName || 'shared-case.epi',
      fileSize: payload.file_size || payload.fileSize || item.file_size || item.fileSize || 0,
      manifest: payload.manifest || {},
      steps: payload.steps || [],
      analysis: payload.analysis || null,
      policy: payload.policy || null,
      policyEvaluation: payload.policy_evaluation || payload.policyEvaluation || null,
      mappingReport: payload.mapping_report || payload.mappingReport || null,
      review: payload.review || null,
      environment: payload.environment || null,
      stdout: payload.stdout || null,
      stderr: payload.stderr || null,
      artifactNames: payload.artifact_names || payload.artifactNames || [],
      integrity: payload.integrity || null,
      signature: payload.signature || null,
      sourceTrustState: payload.source_trust_state || payload.sourceTrustState || item.source_trust_state || item.sourceTrustState || null,
      sharedWorkspaceCase: true,
      backendCase: true,
      sharedUpdatedAt: payload.shared_updated_at || payload.sharedUpdatedAt || item.shared_updated_at || item.sharedUpdatedAt || null,
      status: payload.status || item.status || null,
      assignee: payload.assignee || item.assignee || '',
      due_at: payload.due_at || payload.dueAt || item.due_at || item.dueAt || '',
      priority_override: payload.priority_override || item.priority_override || null,
      comments: payload.comments || [],
      activity: payload.activity || [],
      comment_count: payload.comment_count || item.comment_count || 0,
      last_comment_at: payload.last_comment_at || item.last_comment_at || null,
      is_overdue: payload.is_overdue || item.is_overdue || false,
    }));
  }
  mergeCases(hydrated);
}

function buildSharedWorkspaceCaseExport(caseRecord) {
  return {
    id: caseRecord.id,
    source_name: caseRecord.sourceName,
    file_size: caseRecord.fileSize || 0,
    manifest: caseRecord.manifest,
    steps: caseRecord.steps,
    analysis: caseRecord.analysis,
    policy: caseRecord.policy,
    policy_evaluation: caseRecord.policyEvaluation,
    mapping_report: caseRecord.mappingReport,
    review: caseRecord.review,
    environment: caseRecord.environment,
    stdout: caseRecord.stdout,
    stderr: caseRecord.stderr,
    artifact_names: caseRecord.artifactNames,
    integrity: caseRecord.integrity,
    signature: caseRecord.signature,
    source_trust_state: caseRecord.trust,
    backend_case: caseRecord.backendCase,
    status: caseRecord.status,
    assignee: caseRecord.assignee,
    due_at: caseRecord.dueAt,
    priority_override: caseRecord.priorityOverride || null,
    comments: caseRecord.comments,
    activity: caseRecord.activity,
    comment_count: caseRecord.commentCount,
    last_comment_at: caseRecord.lastCommentAt,
  };
}

function isPublishableSharedCase(caseRecord) {
  return Boolean(caseRecord && !caseRecord.sharedWorkspaceCase && !String(caseRecord.sourceName || '').startsWith('example_'));
}

async function publishCaseToSharedWorkspace(caseRecord) {
  if (!isPublishableSharedCase(caseRecord) || !bridgeSupportsSharedWorkspace(state.bridgeHealth)) {
    return false;
  }

  try {
    const response = await bridgeFetch(`${state.bridgeHealth.url}/api/workspace/cases`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        case: buildSharedWorkspaceCaseExport(caseRecord),
      }),
    });
    const payload = await response.json();
    if (!response.ok || !payload.ok) {
      throw new Error(payload.error || `Workspace publish failed with status ${response.status}`);
    }
    return true;
  } catch (_error) {
    return false;
  }
}

async function publishCasesToSharedWorkspace(caseRecords) {
  for (const caseRecord of caseRecords) {
    await publishCaseToSharedWorkspace(caseRecord);
  }
}

function deriveLiveRecordId(record, caseInput) {
  return (
    record?.case_id ||
    record?.ticket_id ||
    record?.record_id ||
    record?.sys_id ||
    caseInput?.case_id ||
    caseInput?.ticket_id ||
    caseInput?.record_id ||
    caseInput?.sys_id ||
    ''
  );
}

function buildLiveRecordSummary(setup, record, caseInput, recordId) {
  const amountField = setup.workflowConfig.thresholdField;
  const amountValue = amountField ? record?.[amountField] ?? caseInput?.[amountField] : null;
  const amountText = amountValue != null && amountValue !== ''
    ? ` It includes ${sentenceCase(amountField)} ${amountValue}.`
    : '';
  const recordText = recordId ? ` Record ${recordId} is ready for review.` : ' A live source record is ready for review.';

  return `EPI loaded a live ${setup.systemLabel} record for ${setup.workflowLabel.toLowerCase()}.${recordText}${amountText} Check the rules and reviewer path before rollout.`;
}

function renderCaseSelector() {
  if (!state.cases.length) {
    elements.caseSelector.disabled = true;
    elements.caseSelector.innerHTML = state.workspaceSetup
      ? '<option value="">Workspace setup ready (no case file loaded yet)</option>'
      : '';
    return;
  }

  elements.caseSelector.disabled = false;
  elements.caseSelector.innerHTML = state.cases.map((caseRecord) => {
    return `<option value="${escapeHtml(caseRecord.id)}">${escapeHtml(caseRecord.decision.title)}</option>`;
  }).join('');

  if (state.selectedCaseId) {
    elements.caseSelector.value = state.selectedCaseId;
  }
}

function renderWorkflowFilter() {
  const options = ['<option value="all">All workflows</option>'];
  Array.from(new Set(state.cases.map((caseRecord) => caseRecord.workflow))).sort().forEach((workflow) => {
    options.push(`<option value="${escapeHtml(workflow)}">${escapeHtml(workflow)}</option>`);
  });
  elements.workflowFilter.innerHTML = options.join('');
  elements.workflowFilter.value = state.filters.workflow;
}

function renderInbox() {
  const cases = getFilteredCases();
  if (!state.cases.length) {
    elements.emptyInbox.hidden = false;
    elements.emptyInbox.innerHTML = buildEmptyInboxContent();
    elements.caseList.innerHTML = '';
    return;
  }

  elements.emptyInbox.hidden = cases.length > 0;
  elements.emptyInbox.innerHTML = `
    <h3>No cases match these filters</h3>
    <p>Adjust search or filters to bring cases back into the queue.</p>
  `;

  if (!cases.length) {
    elements.caseList.innerHTML = '';
    return;
  }

  elements.caseList.innerHTML = cases.map((caseRecord) => {
    const ownerBits = [];
    if (caseRecord.assignee) {
      ownerBits.push(`Owner: ${escapeHtml(caseRecord.assignee)}`);
    } else {
      ownerBits.push('Owner: Unassigned');
    }
    if (caseRecord.dueAt) {
      ownerBits.push(`Due: ${escapeHtml(formatDueDate(caseRecord.dueAt))}`);
    }
    if (caseRecord.isOverdue) {
      ownerBits.push('Overdue');
    }
    return `
      <article class="case-card">
        <div class="case-card-top">
          <div>
            <p class="case-meta">${escapeHtml(caseRecord.workflow)} | ${formatDate(caseRecord.manifest.created_at)} | ${escapeHtml(caseRecord.sourceProfile?.sourceSystem || caseRecord.sourceName)}</p>
            <h3>${escapeHtml(caseRecord.decision.title)}</h3>
            <p class="case-summary-copy">${escapeHtml(caseRecord.decision.summary)}</p>
            <p class="case-meta">${ownerBits.join(' | ')}</p>
          </div>
          <div class="badge-row">
            ${renderBadge(caseRecord.sourceProfile?.label || 'Case source', caseRecord.sourceProfile?.kind === 'agt-imported' ? 'warning' : 'neutral')}
            ${caseRecord.sharedWorkspaceCase ? renderBadge('Team case', 'neutral') : ''}
            ${renderBadge(caseRecord.workflowState.label, caseRecord.workflowState.tone)}
            ${renderBadge(caseRecord.trust.label, caseRecord.trust.tone)}
            ${renderBadge(caseRecord.risk.label, caseRecord.risk.tone)}
            ${renderBadge(caseRecord.reviewState.label, caseRecord.reviewState.tone)}
            ${renderBadge(caseRecord.reviewSignature.label, caseRecord.reviewSignature.tone)}
          </div>
        </div>
        <div class="case-card-footer">
          <span class="stack-copy">${escapeHtml(caseRecord.workflowState.detail)}</span>
          <button class="text-button" type="button" data-open-case="${escapeHtml(caseRecord.id)}">Open investigation</button>
        </div>
      </article>
    `;
  }).join('');
}

function renderCaseView() {
  const caseRecord = getSelectedCase();
  const hasCase = Boolean(caseRecord);
  elements.noCaseSelected.hidden = hasCase;
  elements.caseView.hidden = !hasCase;

  if (!caseRecord) {
    return;
  }

  elements.caseSelector.value = caseRecord.id;
  const analysisState = deriveAnalysisState(caseRecord.manifest, caseRecord.analysis);
  const guidance = buildCaseGuidance(caseRecord);
  const overview = buildOverviewPresentation(caseRecord, analysisState);
  const policyFlow = buildPolicyFlow(caseRecord);
  const evidenceSummary = buildEvidenceSummary(caseRecord, analysisState);
  const trustRows = buildTrustRows(caseRecord, analysisState);
  const trustAlerts = buildTrustAlerts(caseRecord, analysisState);
  const mappingView = buildTransformationAuditView(caseRecord);
  const attachmentView = buildAttachmentView(caseRecord);

  renderAuditFirstCard(caseRecord, analysisState, attachmentView);
  elements.caseSubtitle.textContent = `${caseRecord.workflow} | ${caseRecord.sourceProfile?.importMode || 'Portable EPI artifact'}`;
  elements.caseTitle.textContent = caseRecord.decision.title;
  elements.caseSummaryCopy.textContent = caseRecord.decision.summary;
  elements.caseOverviewNarrative.textContent = overview.narrative;
  const canDownloadReviewedArtifact = canBuildReviewedArtifact(caseRecord);
  elements.downloadReviewedEpiButton.disabled = !canDownloadReviewedArtifact;
  elements.downloadReviewedEpiButton.textContent = canDownloadReviewedArtifact
    ? 'Download reviewed case file (.epi)'
    : 'Reviewed case file unavailable';
  setBadge(elements.caseWorkflowBadge, caseRecord.workflowState.label, caseRecord.workflowState.tone);
  setBadge(
    elements.caseSourceBadge,
    `Source: ${caseRecord.sourceProfile?.sourceSystem || 'EPI'}`,
    caseRecord.sourceProfile?.kind === 'agt-imported' ? 'warning' : 'neutral',
  );
  setBadge(
    elements.caseImportBadge,
    caseRecord.sourceProfile?.importMode || 'Portable EPI artifact',
    caseRecord.sourceProfile?.kind === 'agt-imported' ? 'warning' : 'neutral',
  );
  setBadge(elements.caseTrustBadge, caseRecord.trust.label, caseRecord.trust.tone);
  setBadge(elements.caseRiskBadge, caseRecord.risk.label, caseRecord.risk.tone);
  setBadge(elements.caseReviewBadge, caseRecord.reviewState.label, caseRecord.reviewState.tone);
  setBadge(elements.caseReviewSignatureBadge, caseRecord.reviewSignature.label, caseRecord.reviewSignature.tone);
  setBadge(
    elements.caseAuditBadge,
    mappingView.visible ? 'Transformation audit available' : 'Direct evidence path',
    mappingView.visible ? 'warning' : 'neutral',
  );
  elements.caseOverviewSignals.innerHTML = overview.signals.map(renderCaseSignalItem).join('');
  renderCaseSnapshot(caseRecord, analysisState, guidance);

  elements.caseSummaryGrid.innerHTML = overview.summaryRows.map(([label, value]) => {
    return `<dt>${escapeHtml(label)}</dt><dd>${escapeHtml(value)}</dd>`;
  }).join('');

  elements.caseEvidenceSummary.innerHTML = evidenceSummary.map(renderStackItem).join('');
  elements.casePolicyFlow.innerHTML = policyFlow.map(renderStackItem).join('');
  elements.caseAlerts.innerHTML = trustAlerts.map(renderStackItem).join('');
  elements.caseTrustGrid.innerHTML = trustRows.map(([label, value]) => {
    return `<dt>${escapeHtml(label)}</dt><dd>${escapeHtml(value)}</dd>`;
  }).join('');
  elements.caseFindings.innerHTML = buildFindings(caseRecord).map(renderStackItem).join('');
  elements.caseTimeline.innerHTML = buildTimeline(caseRecord).map(renderTimelineItem).join('');
  renderTransformationAudit(caseRecord, mappingView);
  renderAttachmentGroups(caseRecord, attachmentView);
  renderCaseGuidance(guidance);
  renderWorkflowForm(caseRecord);
  renderComments(caseRecord);
  renderAttachmentPreview(caseRecord);
  setCaseSectionVisible('case-mapping-card', mappingView.visible);
  setCaseSectionVisible('case-attachments-card', attachmentView.visible);
  populateReviewForm(caseRecord);
  scrollToActiveCaseSectionIfNeeded();
}

function renderAuditFirstCard(caseRecord, analysisState, attachmentView) {
  setBadge(elements.auditTrustBadge, caseRecord.trust.label, caseRecord.trust.tone);
  elements.auditProofCopy.textContent = buildAuditProofCopy(caseRecord);
  elements.auditProofCommand.textContent = `epi verify ${quoteCliArg(caseRecord.sourceName || 'case.epi')}`;
  renderAuditSummaryGrid(buildAuditSummaryItems(caseRecord, analysisState, attachmentView));
}

function renderAuditSummaryGrid(items) {
  elements.auditSummaryGrid.replaceChildren(...items.map((item) => {
    const card = document.createElement('article');
    card.className = `audit-summary-item tone-panel-${item.tone || 'neutral'}`;

    const label = document.createElement('span');
    label.className = 'case-snapshot-label';
    label.textContent = item.label;

    const value = document.createElement('strong');
    value.textContent = item.value;

    const copy = document.createElement('p');
    copy.className = 'case-snapshot-copy';
    copy.textContent = item.copy;

    card.append(label, value, copy);
    return card;
  }));
}

function buildAuditProofCopy(caseRecord) {
  if (caseRecord.trust.code === 'do-not-use') {
    return 'Do not rely on this artifact until the original source is reverified from the .epi file.';
  }
  if (caseRecord.trust.code === 'trusted') {
    return 'This view can inspect the local artifact, but high-stakes review should verify the original .epi with the CLI or a known verifier.';
  }
  return 'Use this view to inspect evidence, then verify the original .epi before relying on it for audit or compliance review.';
}

function buildAuditSummaryItems(caseRecord, analysisState, attachmentView) {
  const stepCount = Array.isArray(caseRecord.steps) ? caseRecord.steps.length : 0;
  const protectedFileCount =
    Number(caseRecord.integrity?.checked || 0) ||
    Object.keys(caseRecord.manifest?.file_manifest || {}).length ||
    (Array.isArray(caseRecord.artifactNames) ? caseRecord.artifactNames.length : 0);
  const rawEvidenceCopy = attachmentView.visible
    ? 'Open raw files to inspect steps.jsonl, stdout/stderr, environment, analysis, and other sealed evidence.'
    : 'The manifest records protected file hashes. Raw-file preview is not available in this browser session.';
  const traceCopy = stepCount
    ? `${stepCount} recorded step${stepCount === 1 ? '' : 's'}. ${caseRecord.decision.summary}`
    : `Metadata-only case. ${caseRecord.decision.summary}`;

  return [
    {
      label: 'Trust verdict',
      value: caseRecord.trust.label,
      copy: caseRecord.trust.detail,
      tone: caseRecord.trust.tone,
    },
    {
      label: 'What happened',
      value: caseRecord.decision.outcome,
      copy: traceCopy,
      tone: 'neutral',
    },
    {
      label: 'Raw evidence',
      value: `${protectedFileCount} protected file${protectedFileCount === 1 ? '' : 's'}`,
      copy: rawEvidenceCopy,
      tone: 'neutral',
    },
    {
      label: 'Human review',
      value: caseRecord.reviewState.label,
      copy: `${caseRecord.reviewState.detail} ${analysisState.label}: ${analysisState.detail}`,
      tone: caseRecord.reviewState.tone,
    },
  ];
}

function quoteCliArg(value) {
  const text = String(value || 'case.epi');
  if (!/[\s"']/.test(text)) {
    return text;
  }
  return `"${text.replace(/"/g, '\\"')}"`;
}

function renderCaseGuidance(guidance) {
  elements.caseGuidanceTitle.textContent = guidance.title;
  elements.caseGuidanceCopy.textContent = guidance.copy;
  elements.caseGuidanceList.innerHTML = guidance.items.map(renderStackItem).join('');
  elements.caseGuidanceReviewButton.textContent = guidance.reviewButtonLabel;
}

function renderCaseSnapshot(caseRecord, analysisState, guidance) {
  const snapshot = buildCaseSnapshot(caseRecord, analysisState, guidance);
  elements.caseSnapshotTitle.textContent = snapshot.title;
  elements.caseSnapshotCopy.textContent = snapshot.copy;
  elements.caseSnapshotGrid.innerHTML = snapshot.items.map(renderCaseSnapshotItem).join('');
}

function renderWorkflowForm(caseRecord) {
  elements.workflowAssignee.value = caseRecord.assignee || '';
  elements.workflowDueAt.value = (caseRecord.dueAt || '').slice(0, 10);
  elements.workflowStatus.value = caseRecord.status || 'unassigned';
  elements.workflowSaveStatus.textContent = caseRecord.sharedWorkspaceCase
    ? `Current owner: ${caseRecord.assignee || 'Unassigned'}. ${caseRecord.isOverdue ? 'This case is overdue.' : caseRecord.workflowState.detail}`
    : 'Team workflow controls apply when this case is connected to the shared team workspace.';
}

function renderComments(caseRecord) {
  const comments = Array.isArray(caseRecord.comments) ? caseRecord.comments : [];
  elements.caseComments.innerHTML = comments.length
    ? comments.map((comment) => `
      <article class="stack-item">
        <h4>${escapeHtml(comment.author || 'Reviewer')}</h4>
        <p class="stack-copy">${escapeHtml(comment.body || '')}</p>
        <p class="helper-copy">${escapeHtml(formatDate(comment.created_at))}</p>
      </article>
    `).join('')
    : '<p class="helper-copy">No comments yet. Add context, handoff notes, or the next action here.</p>';
  elements.commentSaveStatus.textContent = state.reviewerIdentity
    ? `Comments will be posted as ${state.reviewerIdentity}.`
    : 'Add your name or email in the sidebar so comments and reviews show the right owner.';
}

function renderRulesView() {
  const editor = getActivePolicyEditor();
  const policy = editor.policy;

  elements.policyId.value = policy.policy_id || '';
  elements.policySystemName.value = policy.system_name || '';
  elements.policySystemVersion.value = policy.system_version || '';
  elements.policyVersion.value = policy.policy_version || '';
  elements.policyProfileId.value = policy.profile_id || '';
  elements.policyScopeOrganization.value = policy.scope.organization || '';
  elements.policyScopeTeam.value = policy.scope.team || '';
  elements.policyScopeApplication.value = policy.scope.application || '';
  elements.policyScopeWorkflow.value = policy.scope.workflow || '';
  elements.policyScopeEnvironment.value = policy.scope.environment || '';
  elements.policySourceNote.textContent = formatPolicySourceNote(editor);
  elements.policyRuleCountBadge.textContent = `${policy.rules.length} rule${policy.rules.length === 1 ? '' : 's'}`;
  elements.policyApprovalCountBadge.textContent = `${policy.approval_policies.length} approval polic${policy.approval_policies.length === 1 ? 'y' : 'ies'} carried forward`;
  elements.policyRuleEditor.innerHTML = renderPolicyRuleEditor(policy.rules);
  updatePolicyJsonPreview();
}

function renderReportsView() {
  const report = buildReportPayload(elements.reportType.value, elements.reportScope.value);
  elements.reportPreview.textContent = formatReportPreview(report);
}

function buildSetupDraftFromInputs() {
  return {
    system: elements.setupSystem.value || 'zendesk',
    workflow: elements.setupWorkflow.value || 'refund-approval',
    reviewerRole: (elements.setupReviewerRole.value || '').trim(),
    environment: elements.setupEnvironment.value || 'production',
    requiredStep: (elements.setupRequiredStep.value || '').trim(),
    bridgeUrl: normalizeBridgeUrl(elements.setupBridgeUrl.value || 'http://127.0.0.1:8765'),
  };
}

function buildWorkspaceSetup(draft) {
  const systemConfig = SETUP_SYSTEMS[draft.system] || SETUP_SYSTEMS.zendesk;
  const workflowConfig = SETUP_WORKFLOWS[draft.workflow] || SETUP_WORKFLOWS['refund-approval'];
  const reviewerRole = draft.reviewerRole || 'manager';
  const requiredStep = draft.requiredStep || workflowConfig.defaultRequiredStep;
  const environment = draft.environment || 'production';
  const systemName = slugifyPolicyId(`${systemConfig.application}-${workflowConfig.label}`);
  const policyId = slugifyPolicyId(`${systemName}-${environment}`);
  const approvalPolicyId = `${policyId}-approval`;
  const connectorProfile = compactConnectorProfile(getConnectorProfile(draft.system), draft.system, true);
  const activeLiveRecord = getActiveLiveConnectorRecord(draft.system, draft.bridgeUrl);
  const activeBridgeHealth = getActiveBridgeHealth(draft.bridgeUrl);

  return {
    system: draft.system,
    workflow: draft.workflow,
    environment,
    reviewerRole,
    requiredStep,
    bridgeUrl: draft.bridgeUrl,
    systemLabel: systemConfig.label,
    application: systemConfig.application,
    workflowLabel: workflowConfig.label,
    workflowConfig,
    systemConfig,
    systemName,
    policyId,
    approvalPolicyId,
    connectorProfile,
    bridgeHealth: activeBridgeHealth,
    liveConnectorRecord: activeLiveRecord,
    nextSteps: [
      `Check the starting rules for ${workflowConfig.label.toLowerCase()}.`,
      shouldUseMockPreview({ system: draft.system, connectorProfile })
        ? `Try a safe ${systemConfig.label} sample now, then add real connector details later.`
        : `Open a live ${systemConfig.label} record when you are ready.`,
      `Open saved EPI cases if you already have them.`,
      `Use this in my system when the setup looks right.`,
    ],
  };
}

function applySetupWizard() {
  const draft = buildSetupDraftFromInputs();
  syncSetupBridgeState(draft);
  const setup = buildWorkspaceSetup(draft);
  state.workspaceSetup = setup;
  state.selectedCaseId = null;
  state.policyEditors[POLICY_EDITOR_EMPTY_KEY] = createPolicyEditorFromSetup(setup);
  elements.setupRequiredStep.value = setup.requiredStep;
  state.currentView = 'inbox';
  renderApp();
  setStatus(
    `Workspace prepared for ${setup.systemLabel} ${setup.workflowLabel.toLowerCase()}. Start with one sample, live record, or saved case and review that first.`,
    'success',
  );
}

function createPolicyEditorFromSetup(setup) {
  const today = new Date().toISOString().slice(0, 10);
  return {
    sourceCaseId: null,
    sourceName: `${setup.systemLabel} ${setup.workflowLabel} workspace`,
    sourceHasPolicy: false,
    policy: {
      policy_format_version: '2.0',
      policy_id: setup.policyId,
      system_name: setup.systemName,
      system_version: '1.0',
      policy_version: today,
      profile_id: setup.workflowConfig.policyProfile,
      scope: {
        organization: '',
        team: '',
        application: setup.application,
        workflow: setup.workflow,
        environment: setup.environment,
      },
      approval_policies: [
        {
          approval_id: setup.approvalPolicyId,
          required_roles: [setup.reviewerRole],
          minimum_approvers: 1,
          expires_after_minutes: null,
          reason_required: true,
          separation_of_duties: false,
        },
      ],
      rules: buildSetupPolicyRules(setup),
    },
  };
}

function buildSetupPolicyRules(setup) {
  const rules = [];
  const workflowCase = { workflow: setup.workflowLabel };
  const ruleTypes = setup.workflowConfig.includes || [];

  ruleTypes.forEach((ruleType) => {
    const rule = createEmptyPolicyRule(ruleType, rules.length + 1, workflowCase);

    if (ruleType === 'threshold_guard') {
      rule.name = `${sentenceCase(setup.reviewerRole)} approval above ${setup.workflowConfig.thresholdValue || 'a threshold'}`;
      rule.description = `${sentenceCase(setup.reviewerRole)} review is required before ${setup.workflowLabel.toLowerCase()} above the configured threshold.`;
      rule.mode = 'require_approval';
      rule.applies_at = 'decision';
      rule.threshold_field = setup.workflowConfig.thresholdField || 'amount';
      rule.threshold_value = setup.workflowConfig.thresholdValue || '1000';
      rule.required_action = 'human_approval';
    } else if (ruleType === 'approval_guard') {
      rule.name = `${sentenceCase(setup.reviewerRole)} approval before final action`;
      rule.description = `${sentenceCase(setup.reviewerRole)} approval is required before ${setup.workflowLabel.toLowerCase()} can be finalized.`;
      rule.mode = 'require_approval';
      rule.approval_action = setup.workflowConfig.approvalAction;
      rule.approved_by = setup.reviewerRole;
      rule.approval_policy_ref = setup.approvalPolicyId;
    } else if (ruleType === 'sequence_guard') {
      rule.name = `${sentenceCase(setup.requiredStep)} before ${setup.workflowConfig.finalAction}`;
      rule.description = `${sentenceCase(setup.requiredStep)} must happen before the workflow reaches its final decision.`;
      rule.required_before = setup.workflowConfig.finalAction;
      rule.must_call = setup.requiredStep;
    } else if (ruleType === 'constraint_guard') {
      rule.name = 'Stay inside known limits';
      rule.description = 'The workflow must stay inside the known numeric limits before it can move forward.';
      rule.watch_for_text = setup.workflow === 'loan-underwriting'
        ? 'credit_limit, exposure_limit, available_balance'
        : 'claim_limit, reserve_amount';
      rule.violation_if = setup.workflow === 'loan-underwriting'
        ? 'approved_amount > watched_value'
        : 'claim_amount > watched_value';
    } else if (ruleType === 'tool_permission_guard') {
      rule.name = `Only approved ${setup.systemLabel} actions`;
      rule.description = `Only approved actions from ${setup.systemLabel} should be available in this workflow.`;
      rule.allowed_tools_text = setup.systemConfig.allowedToolsText;
      rule.denied_tools_text = setup.systemConfig.deniedToolsText;
      rule.mode = 'block';
      rule.applies_at = 'tool_call';
    } else if (ruleType === 'prohibition_guard') {
      rule.name = 'Never expose secrets or tokens';
      rule.description = 'Outputs must never contain secrets, tokens, or credential-like strings.';
      rule.applies_at = 'output';
    }

    rules.push(rule);
  });

  return rules;
}

function buildSetupPreviewHtml(setup) {
  const ruleChips = (setup.workflowConfig.includes || []).map((ruleType) => {
    return `<span class="pill-badge tone-neutral">${escapeHtml(ruleTypeLabel(ruleType))}</span>`;
  }).join('');

  const nextSteps = setup.nextSteps.map((step) => `<li>${escapeHtml(step)}</li>`).join('');
  const connectorFields = getConnectorFieldDefs(setup.system);
  const connectorRows = connectorFields.map((field) => {
    const rawValue = String(setup.connectorProfile[field.key] || '').trim();
    const value = field.secret
      ? (rawValue ? 'Saved locally' : 'Not set')
      : (rawValue || 'Not set');
    return `<dt>${escapeHtml(field.label)}</dt><dd>${escapeHtml(value)}</dd>`;
  }).join('');

  return `
    <div class="setup-preview-grid">
      <div>
        <p class="card-label">What EPI is preparing</p>
        <dl class="detail-grid">
          <dt>System</dt><dd>${escapeHtml(setup.systemLabel)}</dd>
          <dt>Workflow</dt><dd>${escapeHtml(setup.workflowLabel)}</dd>
          <dt>Reviewer</dt><dd>${escapeHtml(sentenceCase(setup.reviewerRole))}</dd>
          <dt>Required step</dt><dd>${escapeHtml(sentenceCase(setup.requiredStep))}</dd>
          <dt>Launch mode</dt><dd>${escapeHtml(shouldUseMockPreview(setup) ? 'Safe sample first' : 'Live record ready')}</dd>
          <dt>Environment</dt><dd>${escapeHtml(sentenceCase(setup.environment))}</dd>
        </dl>
      </div>
      <div>
        <p class="card-label">Starting rules</p>
        <div class="badge-row">${ruleChips}</div>
        <ul class="setup-next-steps">${nextSteps}</ul>
      </div>
      <div>
        <p class="card-label">Saved system details</p>
        <dl class="detail-grid">${connectorRows}</dl>
      </div>
      <div>
        <p class="card-label">Real record</p>
        <dl class="detail-grid">
          <dt>Connection</dt><dd>${escapeHtml(formatBridgeHealthLabel(setup.bridgeHealth))}</dd>
          <dt>Record</dt><dd>${escapeHtml(formatLiveRecordLabel(setup.liveConnectorRecord))}</dd>
          <dt>Team sync</dt><dd>${escapeHtml(bridgeSupportsSharedWorkspace(setup.bridgeHealth) ? 'Ready' : 'Local only')}</dd>
        </dl>
      </div>
    </div>
  `;
}

function buildEmptyInboxContent() {
  if (state.workspaceSetup) {
    return `
      <h3>Start with one decision</h3>
      <p>
        EPI is ready for ${escapeHtml(state.workspaceSetup.systemLabel)} ${escapeHtml(state.workspaceSetup.workflowLabel.toLowerCase())}.
        The easiest next move is to open one sample or saved case and review it end to end.
      </p>
      <div class="action-row empty-state-actions">
        <button class="secondary-button" type="button" data-open-example-case>Open example case</button>
        <button class="secondary-button" type="button" data-scroll-setup>Open setup</button>
      </div>
    `;
  }

  return `
    <h3>Open one decision first</h3>
    <p>Start with one example case, one saved \`.epi\` file, or the optional setup area. EPI is easiest to understand one decision at a time.</p>
    <div class="action-row empty-state-actions">
      <button class="secondary-button" type="button" data-open-example-case>Open example case</button>
      <button class="secondary-button" type="button" data-scroll-setup>Open setup</button>
    </div>
  `;
}

function resetSetupWizardForm() {
  elements.setupSystem.value = 'zendesk';
  elements.setupWorkflow.value = 'refund-approval';
  elements.setupReviewerRole.value = 'manager';
  elements.setupEnvironment.value = 'production';
  elements.setupRequiredStep.value = '';
  elements.setupBridgeUrl.value = 'http://127.0.0.1:8765';
}

function downloadRecorderStarterPack() {
  if (!state.workspaceSetup) {
    setStatus('Set up EPI first, then download the starter kit.', 'warning');
    return;
  }

  const setup = state.workspaceSetup;
  const liveConnectorRecord = getActiveLiveConnectorRecord(setup.system, setup.bridgeUrl);
  const editor = state.policyEditors[POLICY_EDITOR_EMPTY_KEY] || createPolicyEditorFromSetup(setup);
  const policyJson = buildExportablePolicyJson(editor);
  const archiveEntries = buildRecorderStarterFiles(setup, policyJson, liveConnectorRecord).map((entry) => ({
    name: entry.name,
    data: textToBytes(entry.content),
  }));
  const archiveBytes = createZipArchive(archiveEntries);
  downloadBlob(`${setup.policyId}_epi_recorder_starter.zip`, archiveBytes, 'application/zip');
  setStatus(
    `Downloaded a starter kit for ${setup.systemLabel} ${setup.workflowLabel.toLowerCase()}${liveConnectorRecord ? ' with a real record included' : ''}.`,
    'success',
  );
}

function buildRecorderStarterFiles(setup, policyJson, liveConnectorRecord) {
  const files = [
    {
      name: 'README.md',
      content: buildRecorderStarterReadme(setup, Boolean(liveConnectorRecord)),
    },
    {
      name: 'epi_policy.json',
      content: JSON.stringify(policyJson, null, 2),
    },
    {
      name: 'record_workflow.py',
      content: buildRecorderStarterScript(setup),
    },
    {
      name: 'connector_client.py',
      content: buildConnectorClientScript(setup),
    },
    {
      name: 'CONNECTOR_SETUP.md',
      content: buildConnectorSetupGuide(setup),
    },
    {
      name: 'sample_input.json',
      content: JSON.stringify(buildRecorderSampleInput(setup), null, 2),
    },
    {
      name: '.env.example',
      content: buildRecorderStarterEnvExample(setup),
    },
    {
      name: 'requirements.txt',
      content: buildRecorderStarterRequirements(setup),
    },
  ];

  if (liveConnectorRecord) {
    files.push({
      name: 'live_source_record.json',
      content: JSON.stringify(buildLiveSourceRecordExport(liveConnectorRecord), null, 2),
    });
  }

  return files;
}

function buildLiveSourceRecordExport(liveConnectorRecord) {
  return {
    fetched_at: liveConnectorRecord.fetchedAt,
    bridge_url: liveConnectorRecord.bridgeUrl,
    system: liveConnectorRecord.system,
    case_input: liveConnectorRecord.caseInput,
    record: liveConnectorRecord.record,
  };
}

function buildRecorderStarterReadme(setup, hasLiveRecord) {
  const workflowSlug = setup.workflow.replace(/-/g, '_');
  return [
    `# ${setup.systemLabel} ${setup.workflowLabel} starter`,
    '',
    'This starter pack was generated by the EPI Setup Wizard and is wired to the real `epi_recorder` runtime.',
    '',
    '## Files',
    '',
    '- `epi_policy.json`: the starter policy EPI will load during recording',
    '- `record_workflow.py`: a recorder-ready starter script that uses `record(...)` and `agent_run(...)`',
    '- `connector_client.py`: connector-aware helper functions for the selected source system',
    '- `CONNECTOR_SETUP.md`: how to fill in the credentials and identifiers for this connector',
    '- `sample_input.json`: sample decision input you can replace with your real system payload',
    '- `.env.example`: optional recording environment hints',
    ...(hasLiveRecord ? ['- `live_source_record.json`: a source record fetched through the local connector bridge and bundled for the first run'] : []),
    '',
    '## Run it',
    '',
    '```bash',
    'pip install -r requirements.txt',
    'python record_workflow.py',
    `epi view ${workflowSlug}_starter`,
    '```',
    '',
    'Expected result:',
    '',
    `- EPI records a ${setup.workflowLabel.toLowerCase()} flow into ./epi-recordings/${workflowSlug}_starter.epi`,
    '- The case file includes the local `epi_policy.json` rulebook',
    '- The browser review view opens a real case file that can be reviewed, verified, and exported',
    '',
    '## Replace the placeholders',
    '',
    `1. Fill in the connector environment values in \`.env.example\` and follow \`CONNECTOR_SETUP.md\`.`,
    `2. Adjust \`connector_client.py\` if your ${setup.systemLabel} fields or endpoints differ from the generated defaults.`,
    `3. Replace the placeholder reviewer step with your real ${setup.reviewerRole} approval path.`,
    '4. Replace the placeholder final decision with your real model, rules engine, or orchestration logic.',
    '5. Keep `epi_policy.json` beside the script so EPI embeds it during packing.',
    '',
    '## Why this is recorder-ready',
    '',
    '- Uses `from epi_recorder import record`',
    '- Uses `with epi.agent_run(...)` for structured decision evidence',
    '- Uses connector-aware helpers so real business-system fetches can be captured in the same run',
    ...(hasLiveRecord ? ['- Includes the last browser-fetched source record so the first run can start with real business context immediately'] : []),
    '- Produces a standard `.epi` case file EPI can view, verify, and review',
    '',
  ].join('\n');
}

function buildRecorderStarterScript(setup) {
  const workflowSlug = setup.workflow.replace(/-/g, '_');
  const workflowTitle = setup.workflowLabel;
  const sourceSystem = setup.systemLabel;
  const agentName = `${workflowSlug}_agent`;
  const primaryLookupTool = splitCommaList(setup.systemConfig.allowedToolsText)[0] || 'lookup_record';
  const requiredStep = toPythonIdentifier(setup.requiredStep || setup.workflowConfig.defaultRequiredStep);
  const approvalAction = setup.workflowConfig.approvalAction;

  return [
    'from __future__ import annotations',
    '',
    'import json',
    'from pathlib import Path',
    '',
    'from epi_recorder import record',
    'from connector_client import load_case_record, perform_required_check',
    '',
    `WORKFLOW_NAME = ${JSON.stringify(workflowTitle)}`,
    `OUTPUT_NAME = ${JSON.stringify(`${workflowSlug}_starter`)}`,
    `AGENT_NAME = ${JSON.stringify(agentName)}`,
    `SOURCE_SYSTEM = ${JSON.stringify(sourceSystem)}`,
    `SAMPLE_INPUT_PATH = Path(${JSON.stringify('sample_input.json')})`,
    `LIVE_SOURCE_RECORD_PATH = Path(${JSON.stringify('live_source_record.json')})`,
    '',
    '',
    'def load_case_input() -> dict:',
    "    return json.loads(SAMPLE_INPUT_PATH.read_text(encoding='utf-8'))",
    '',
    '',
    'def load_live_source_record() -> dict | None:',
    '    if not LIVE_SOURCE_RECORD_PATH.exists():',
    '        return None',
    "    payload = json.loads(LIVE_SOURCE_RECORD_PATH.read_text(encoding='utf-8'))",
    "    if isinstance(payload, dict) and 'record' in payload:",
    "        return payload['record']",
    '    return payload if isinstance(payload, dict) else None',
    '',
    '',
    'def main() -> None:',
    '    case_input = load_case_input()',
    '',
    `    with record(OUTPUT_NAME, workflow_name=${JSON.stringify(workflowTitle)}, goal=${JSON.stringify(`Capture a reviewable ${workflowTitle.toLowerCase()} decision record`)}) as epi:`,
    `        with epi.agent_run(AGENT_NAME, user_input=case_input, goal=${JSON.stringify(`Handle ${workflowTitle.toLowerCase()} safely and leave a defensible case file`)}) as agent:`,
    "            agent.plan('Load business context, complete the required checks, request approval when policy requires it, and record the final decision.')",
    `            agent.tool_call(${JSON.stringify(primaryLookupTool)}, {'source_system': SOURCE_SYSTEM, 'case_id': case_input.get('case_id')})`,
    '            source_record = load_live_source_record() or load_case_record(case_input)',
    `            agent.tool_result(${JSON.stringify(primaryLookupTool)}, source_record)`,
    '',
    `            agent.tool_call(${JSON.stringify(requiredStep)}, {'case_id': case_input.get('case_id')})`,
    '            required_check = perform_required_check(case_input, source_record)',
    `            agent.tool_result(${JSON.stringify(requiredStep)}, required_check)`,
    '',
    `            agent.approval_request(${JSON.stringify(approvalAction)}, reason=${JSON.stringify(`Starter workflow requires ${setup.reviewerRole} approval before the final action`)}, requested_by=AGENT_NAME)`,
    `            # Replace this placeholder with your real ${setup.reviewerRole} review queue or approval workflow.`,
    `            agent.approval_response(${JSON.stringify(approvalAction)}, approved=True, reviewer=${JSON.stringify(setup.reviewerRole)}, notes='Starter approval placeholder')`,
    '',
    `            agent.decision(${JSON.stringify(approvalAction)}, confidence=0.91, review_required=True, rationale=${JSON.stringify('Replace this placeholder with your real model or rules engine decision.')})`,
    '',
    "            epi.log_step('business.context', {",
    "                'source_system': SOURCE_SYSTEM,",
    `                'workflow': ${JSON.stringify(setup.workflow)},`,
    `                'environment': ${JSON.stringify(setup.environment)},`,
    `                'policy_id': ${JSON.stringify(setup.policyId)},`,
    "                'case_id': case_input.get('case_id'),",
    "                'connector_status': source_record.get('status'),",
    '            })',
    "            epi.log_step('business.outcome', {",
    `                'decision': ${JSON.stringify(approvalAction)},`,
    `                'reviewer_role': ${JSON.stringify(setup.reviewerRole)},`,
    "                'case_id': case_input.get('case_id'),",
    "                'notes': 'Replace this with your real post-decision payload.',",
    '            })',
    '',
    '',
    "if __name__ == '__main__':",
    '    main()',
    '',
  ].join('\n');
}

function buildRecorderSampleInput(setup) {
  const connectorProfile = setup.connectorProfile || {};
  const payload = {
    case_id: `${setup.workflow}-001`,
    source_system: setup.systemLabel,
    reviewer_role: setup.reviewerRole,
    notes: `Replace this sample with a real ${setup.workflowLabel.toLowerCase()} payload.`,
  };

  if (setup.system === 'zendesk') {
    payload.ticket_id = '12345';
    payload.requester_email = 'customer@example.com';
  } else if (setup.system === 'salesforce') {
    payload.record_id = '500000000000001';
    payload.object_name = 'Case';
  } else if (setup.system === 'servicenow') {
    payload.table = 'incident';
    payload.sys_id = '46d44b40db7f2010a8d75f48dc9619f4';
  } else if (setup.system === 'internal-app') {
    payload.record_id = 'approval-123';
    payload.api_path = connectorProfile.api_path || '/api/v1/decisions';
  } else if (setup.system === 'csv-export') {
    payload.csv_path = connectorProfile.csv_path || 'source_export.csv';
    payload.id_column = connectorProfile.id_column || 'case_id';
  }

  if (setup.workflowConfig.thresholdField) {
    payload[setup.workflowConfig.thresholdField] = Number(setup.workflowConfig.thresholdValue || 1000);
  }

  return payload;
}

function buildRecorderStarterEnvExample(setup) {
  const lines = [
    '# Optional EPI environment configuration',
    'EPI_RECORDINGS_DIR=epi-recordings',
    '# OPENAI_API_KEY=',
    '# ANTHROPIC_API_KEY=',
    '',
    buildConnectorEnvBlock(setup),
  ];
  return lines.join('\n');
}

function buildRecorderStarterRequirements(_setup) {
  return [
    'epi-recorder>=2.8.10',
    'requests>=2.32.0',
  ].join('\n') + '\n';
}

function buildConnectorEnvBlock(setup) {
  const connectorProfile = setup.connectorProfile || {};
  if (setup.system === 'zendesk') {
    return [
      '# Zendesk connector',
      `ZENDESK_SUBDOMAIN=${connectorProfile.subdomain || ''}`,
      `ZENDESK_EMAIL=${connectorProfile.email || ''}`,
      'ZENDESK_API_TOKEN=',
    ].join('\n');
  }

  if (setup.system === 'salesforce') {
    return [
      '# Salesforce connector',
      `SALESFORCE_INSTANCE_URL=${connectorProfile.instance_url || ''}`,
      'SALESFORCE_ACCESS_TOKEN=',
      `SALESFORCE_API_VERSION=${connectorProfile.api_version || 'v61.0'}`,
    ].join('\n');
  }

  if (setup.system === 'servicenow') {
    return [
      '# ServiceNow connector',
      `SERVICENOW_INSTANCE_URL=${connectorProfile.instance_url || ''}`,
      `SERVICENOW_USERNAME=${connectorProfile.username || ''}`,
      'SERVICENOW_PASSWORD=',
    ].join('\n');
  }

  if (setup.system === 'internal-app') {
    return [
      '# Internal app connector',
      `INTERNAL_APP_BASE_URL=${connectorProfile.base_url || ''}`,
      'INTERNAL_APP_BEARER_TOKEN=',
      `INTERNAL_APP_API_PATH=${connectorProfile.api_path || '/api/v1/decisions'}`,
    ].join('\n');
  }

  return [
    '# CSV connector',
    `CSV_PATH=${connectorProfile.csv_path || 'source_export.csv'}`,
    `CSV_ID_COLUMN=${connectorProfile.id_column || 'case_id'}`,
  ].join('\n');
}

function buildConnectorClientScript(setup) {
  if (setup.system === 'zendesk') {
    return buildZendeskConnectorScript(setup);
  }
  if (setup.system === 'salesforce') {
    return buildSalesforceConnectorScript(setup);
  }
  if (setup.system === 'servicenow') {
    return buildServiceNowConnectorScript(setup);
  }
  if (setup.system === 'internal-app') {
    return buildInternalAppConnectorScript(setup);
  }
  return buildCsvConnectorScript(setup);
}

function buildConnectorSetupGuide(setup) {
  const systemLine = `${setup.systemLabel} connector`;
  const steps = buildConnectorGuideSteps(setup);
  return [
    `# ${systemLine}`,
    '',
    `This starter pack was generated for ${setup.workflowLabel.toLowerCase()} in ${setup.systemLabel}.`,
    '',
    '## Before you run the recorder',
    '',
    ...steps.map((step, index) => `${index + 1}. ${step}`),
    `${steps.length + 1}. Optional: run \`epi connect serve\`, return to the Setup Wizard, and fetch one live source record so the starter pack includes \`live_source_record.json\`.`,
    '',
    '## Why this matters for EPI',
    '',
    '- The connector helper runs inside `record(...)`, so HTTP or file-access evidence can land in the same `.epi` case file.',
    '- The generated `record_workflow.py` still uses `agent_run(...)`, so reviewer actions, approvals, and decisions stay visible in one timeline.',
    '',
  ].join('\n');
}

function buildConnectorGuideSteps(setup) {
  if (setup.system === 'zendesk') {
    return [
      'Set `ZENDESK_SUBDOMAIN`, `ZENDESK_EMAIL`, and `ZENDESK_API_TOKEN` in `.env.example` or your shell.',
      'Replace `ticket_id` in `sample_input.json` with a real ticket number.',
      'Adjust `map_zendesk_ticket(...)` if your team needs extra fields in the recorded case file.',
    ];
  }
  if (setup.system === 'salesforce') {
    return [
      'Set `SALESFORCE_INSTANCE_URL` and `SALESFORCE_ACCESS_TOKEN`.',
      'Set `record_id` and `object_name` in `sample_input.json` for the Salesforce object you want to record.',
      'Adjust `map_salesforce_record(...)` if you want extra fields in the case context.',
    ];
  }
  if (setup.system === 'servicenow') {
    return [
      'Set `SERVICENOW_INSTANCE_URL`, `SERVICENOW_USERNAME`, and `SERVICENOW_PASSWORD`.',
      'Set `table` and `sys_id` in `sample_input.json` for the ServiceNow record you want to load.',
      'Adjust `map_servicenow_record(...)` if you need extra table-specific fields.',
    ];
  }
  if (setup.system === 'internal-app') {
    return [
      'Set `INTERNAL_APP_BASE_URL` and, if needed, `INTERNAL_APP_BEARER_TOKEN`.',
      'Set `api_path` and `record_id` in `sample_input.json`.',
      'Replace `map_internal_record(...)` with your organization-specific field mapping.',
    ];
  }
  return [
    'Place the exported CSV beside `record_workflow.py` or update `csv_path` in `sample_input.json`.',
    'Set `id_column` and `case_id` so the helper can find the right row.',
    'Adjust `map_csv_row(...)` if you need different recorded fields.',
  ];
}

function buildZendeskConnectorScript(setup) {
  return [
    'from __future__ import annotations',
    '',
    'import os',
    'from typing import Any',
    '',
    'import requests',
    '',
    '',
    'def load_case_record(case_input: dict[str, Any]) -> dict[str, Any]:',
    "    ticket_id = str(case_input.get('ticket_id') or case_input.get('case_id') or '').strip()",
    '    if not ticket_id:',
    "        raise ValueError('sample_input.json must include ticket_id or case_id for Zendesk')",
    '',
    "    subdomain = os.getenv('ZENDESK_SUBDOMAIN', '').strip()",
    "    email = os.getenv('ZENDESK_EMAIL', '').strip()",
    "    token = os.getenv('ZENDESK_API_TOKEN', '').strip()",
    '    if not (subdomain and email and token):',
    "        return {'status': 'placeholder', 'ticket_id': ticket_id, 'source_system': 'Zendesk', 'message': 'Set Zendesk environment variables to fetch a real ticket.'}",
    '',
    "    url = f'https://{subdomain}.zendesk.com/api/v2/tickets/{ticket_id}.json'",
    "    response = requests.get(url, auth=(f'{email}/token', token), timeout=30)",
    '    response.raise_for_status()',
    "    ticket = response.json().get('ticket', {})",
    '    return map_zendesk_ticket(ticket)',
    '',
    '',
    'def perform_required_check(case_input: dict[str, Any], source_record: dict[str, Any]) -> dict[str, Any]:',
    "    requester_email = case_input.get('requester_email') or source_record.get('requester_email')",
    "    return {'status': 'completed', 'check': " + JSON.stringify(setup.requiredStep) + ", 'requester_email_present': bool(requester_email)}",
    '',
    '',
    'def map_zendesk_ticket(ticket: dict[str, Any]) -> dict[str, Any]:',
    '    return {',
    "        'status': 'loaded',",
    "        'ticket_id': ticket.get('id'),",
    "        'subject': ticket.get('subject'),",
    "        'priority': ticket.get('priority'),",
    "        'requester_email': ticket.get('requester', {}).get('email') if isinstance(ticket.get('requester'), dict) else None,",
    "        'raw_status': ticket.get('status'),",
    "        'source_system': 'Zendesk',",
    '    }',
    '',
  ].join('\n');
}

function buildSalesforceConnectorScript(setup) {
  return [
    'from __future__ import annotations',
    '',
    'import os',
    'from typing import Any',
    '',
    'import requests',
    '',
    '',
    'def load_case_record(case_input: dict[str, Any]) -> dict[str, Any]:',
    "    record_id = str(case_input.get('record_id') or case_input.get('case_id') or '').strip()",
    "    object_name = str(case_input.get('object_name') or 'Case').strip()",
    '    if not record_id:',
    "        raise ValueError('sample_input.json must include record_id or case_id for Salesforce')",
    '',
    "    instance_url = os.getenv('SALESFORCE_INSTANCE_URL', '').rstrip('/')",
    "    access_token = os.getenv('SALESFORCE_ACCESS_TOKEN', '').strip()",
    "    api_version = os.getenv('SALESFORCE_API_VERSION', 'v61.0').strip()",
    '    if not (instance_url and access_token):',
    "        return {'status': 'placeholder', 'record_id': record_id, 'object_name': object_name, 'source_system': 'Salesforce', 'message': 'Set Salesforce environment variables to fetch a real record.'}",
    '',
    "    url = f'{instance_url}/services/data/{api_version}/sobjects/{object_name}/{record_id}'",
    "    response = requests.get(url, headers={'Authorization': f'Bearer {access_token}'}, timeout=30)",
    '    response.raise_for_status()',
    '    return map_salesforce_record(response.json(), object_name)',
    '',
    '',
    'def perform_required_check(case_input: dict[str, Any], source_record: dict[str, Any]) -> dict[str, Any]:',
    "    return {'status': 'completed', 'check': " + JSON.stringify(setup.requiredStep) + ", 'owner_present': bool(source_record.get('owner_id') or source_record.get('owner_name'))}",
    '',
    '',
    'def map_salesforce_record(record: dict[str, Any], object_name: str) -> dict[str, Any]:',
    '    return {',
    "        'status': 'loaded',",
    "        'record_id': record.get('Id'),",
    "        'object_name': object_name,",
    "        'subject': record.get('Subject') or record.get('Name'),",
    "        'priority': record.get('Priority'),",
    "        'owner_id': record.get('OwnerId'),",
    "        'source_system': 'Salesforce',",
    '    }',
    '',
  ].join('\n');
}

function buildServiceNowConnectorScript(setup) {
  return [
    'from __future__ import annotations',
    '',
    'import os',
    'from typing import Any',
    '',
    'import requests',
    '',
    '',
    'def load_case_record(case_input: dict[str, Any]) -> dict[str, Any]:',
    "    table = str(case_input.get('table') or 'incident').strip()",
    "    sys_id = str(case_input.get('sys_id') or case_input.get('case_id') or '').strip()",
    '    if not sys_id:',
    "        raise ValueError('sample_input.json must include sys_id or case_id for ServiceNow')",
    '',
    "    instance_url = os.getenv('SERVICENOW_INSTANCE_URL', '').rstrip('/')",
    "    username = os.getenv('SERVICENOW_USERNAME', '').strip()",
    "    password = os.getenv('SERVICENOW_PASSWORD', '').strip()",
    '    if not (instance_url and username and password):',
    "        return {'status': 'placeholder', 'sys_id': sys_id, 'table': table, 'source_system': 'ServiceNow', 'message': 'Set ServiceNow environment variables to fetch a real record.'}",
    '',
    "    url = f'{instance_url}/api/now/table/{table}/{sys_id}'",
    "    response = requests.get(url, auth=(username, password), timeout=30)",
    '    response.raise_for_status()',
    "    record = response.json().get('result', {})",
    '    return map_servicenow_record(record, table)',
    '',
    '',
    'def perform_required_check(case_input: dict[str, Any], source_record: dict[str, Any]) -> dict[str, Any]:',
    "    return {'status': 'completed', 'check': " + JSON.stringify(setup.requiredStep) + ", 'assignment_group_present': bool(source_record.get('assignment_group'))}",
    '',
    '',
    'def map_servicenow_record(record: dict[str, Any], table: str) -> dict[str, Any]:',
    '    return {',
    "        'status': 'loaded',",
    "        'sys_id': record.get('sys_id'),",
    "        'table': table,",
    "        'number': record.get('number'),",
    "        'short_description': record.get('short_description'),",
    "        'assignment_group': record.get('assignment_group'),",
    "        'source_system': 'ServiceNow',",
    '    }',
    '',
  ].join('\n');
}

function buildInternalAppConnectorScript(setup) {
  return [
    'from __future__ import annotations',
    '',
    'import os',
    'from typing import Any',
    '',
    'import requests',
    '',
    '',
    'def load_case_record(case_input: dict[str, Any]) -> dict[str, Any]:',
    "    record_id = str(case_input.get('record_id') or case_input.get('case_id') or '').strip()",
    "    api_path = str(case_input.get('api_path') or os.getenv('INTERNAL_APP_API_PATH') or '/api/v1/records').strip()",
    '    if not record_id:',
    "        raise ValueError('sample_input.json must include record_id or case_id for the internal app connector')",
    '',
    "    base_url = os.getenv('INTERNAL_APP_BASE_URL', '').rstrip('/')",
    "    bearer_token = os.getenv('INTERNAL_APP_BEARER_TOKEN', '').strip()",
    '    if not base_url:',
    "        return {'status': 'placeholder', 'record_id': record_id, 'api_path': api_path, 'source_system': 'Internal app', 'message': 'Set INTERNAL_APP_BASE_URL to fetch a real record.'}",
    '',
    "    headers = {'Accept': 'application/json'}",
    '    if bearer_token:',
    "        headers['Authorization'] = f'Bearer {bearer_token}'",
    "    url = f'{base_url}{api_path.rstrip('/')}/{record_id}'",
    '    response = requests.get(url, headers=headers, timeout=30)',
    '    response.raise_for_status()',
    '    return map_internal_record(response.json())',
    '',
    '',
    'def perform_required_check(case_input: dict[str, Any], source_record: dict[str, Any]) -> dict[str, Any]:',
    "    return {'status': 'completed', 'check': " + JSON.stringify(setup.requiredStep) + ", 'record_loaded': bool(source_record.get('record_id'))}",
    '',
    '',
    'def map_internal_record(record: dict[str, Any]) -> dict[str, Any]:',
    '    return {',
    "        'status': 'loaded',",
    "        'record_id': record.get('id') or record.get('record_id'),",
    "        'decision_state': record.get('status') or record.get('decision_state'),",
    "        'summary': record.get('summary') or record.get('title'),",
    "        'source_system': 'Internal app',",
    '    }',
    '',
  ].join('\n');
}

function buildCsvConnectorScript(setup) {
  return [
    'from __future__ import annotations',
    '',
    'import csv',
    'from pathlib import Path',
    'from typing import Any',
    'import os',
    '',
    '',
    'def load_case_record(case_input: dict[str, Any]) -> dict[str, Any]:',
    "    csv_path = Path(case_input.get('csv_path') or os.getenv('CSV_PATH') or 'source_export.csv')",
    "    id_column = str(case_input.get('id_column') or os.getenv('CSV_ID_COLUMN') or 'case_id')",
    "    case_id = str(case_input.get('case_id') or '').strip()",
    '    if not csv_path.exists():',
    "        return {'status': 'placeholder', 'csv_path': str(csv_path), 'source_system': 'CSV export', 'message': 'Place the export file beside record_workflow.py or update csv_path in sample_input.json.'}",
    '',
    "    with csv_path.open('r', encoding='utf-8', newline='') as handle:",
    '        reader = csv.DictReader(handle)',
    '        for row in reader:',
    "            if str(row.get(id_column, '')).strip() == case_id:",
    '                return map_csv_row(row)',
    '',
    "    raise ValueError(f'No row found for {case_id!r} using column {id_column!r}')",
    '',
    '',
    'def perform_required_check(case_input: dict[str, Any], source_record: dict[str, Any]) -> dict[str, Any]:',
    "    return {'status': 'completed', 'check': " + JSON.stringify(setup.requiredStep) + ", 'row_loaded': bool(source_record.get('case_id'))}",
    '',
    '',
    'def map_csv_row(row: dict[str, Any]) -> dict[str, Any]:',
    '    return {',
    "        'status': 'loaded',",
    "        'case_id': row.get('case_id') or row.get('id'),",
    "        'summary': row.get('summary') or row.get('title'),",
    "        'decision_state': row.get('status') or row.get('decision_state'),",
    "        'source_system': 'CSV export',",
    '    }',
    '',
  ].join('\n');
}

function toPythonIdentifier(value) {
  return String(value || '')
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '') || 'verify_input';
}

function getPolicyEditorKey() {
  return state.selectedCaseId || POLICY_EDITOR_EMPTY_KEY;
}

function getActivePolicyEditor() {
  const key = getPolicyEditorKey();
  if (!state.policyEditors[key]) {
    state.policyEditors[key] = !state.selectedCaseId && state.workspaceSetup
      ? createPolicyEditorFromSetup(state.workspaceSetup)
      : createPolicyEditorFromCase(getSelectedCase());
  }
  return state.policyEditors[key];
}

function createPolicyEditorFromCase(caseRecord) {
  const sourcePolicy = caseRecord?.policy || null;
  const workflowName = caseRecord?.workflow || 'decision-ops';
  const today = new Date().toISOString().slice(0, 10);

  return {
    sourceCaseId: caseRecord?.id || null,
    sourceName: caseRecord?.sourceName || null,
    sourceHasPolicy: Boolean(sourcePolicy),
    policy: {
      policy_format_version: sourcePolicy?.policy_format_version || '2.0',
      policy_id: sourcePolicy?.policy_id || slugifyPolicyId(workflowName),
      system_name: sourcePolicy?.system_name || workflowName,
      system_version: sourcePolicy?.system_version || '1.0',
      policy_version: sourcePolicy?.policy_version || today,
      profile_id: sourcePolicy?.profile_id || '',
      scope: {
        organization: sourcePolicy?.scope?.organization || '',
        team: sourcePolicy?.scope?.team || '',
        application: sourcePolicy?.scope?.application || '',
        workflow: sourcePolicy?.scope?.workflow || caseRecord?.workflow || '',
        environment: sourcePolicy?.scope?.environment || '',
      },
      approval_policies: normalizeApprovalPolicies(sourcePolicy?.approval_policies || []),
      rules: normalizePolicyRules(sourcePolicy?.rules || [], caseRecord),
    },
  };
}

function normalizeApprovalPolicies(policies) {
  if (!Array.isArray(policies)) {
    return [];
  }

  return policies.map((policy, index) => ({
    approval_id: policy?.approval_id || policy?.id || `approval-${index + 1}`,
    required_roles: Array.isArray(policy?.required_roles)
      ? policy.required_roles.filter(Boolean).map(String)
      : typeof policy?.required_roles === 'string' && policy.required_roles.trim()
        ? [policy.required_roles.trim()]
        : [],
    minimum_approvers: Number.isFinite(Number(policy?.minimum_approvers)) ? Number(policy.minimum_approvers) : 1,
    expires_after_minutes: policy?.expires_after_minutes != null && String(policy.expires_after_minutes).trim() !== ''
      ? Number(policy.expires_after_minutes)
      : null,
    reason_required: Boolean(policy?.reason_required),
    separation_of_duties: Boolean(policy?.separation_of_duties),
  }));
}

function normalizePolicyRules(rules, caseRecord) {
  if (!Array.isArray(rules) || !rules.length) {
    return [];
  }

  return rules.map((rule, index) => normalizePolicyRule(rule, index, caseRecord));
}

function normalizePolicyRule(rule, index, caseRecord) {
  const type = rule?.type || 'threshold_guard';
  const ruleId = rule?.id || nextPolicyRuleId(index + 1);
  return {
    id: String(ruleId),
    name: String(rule?.name || `${ruleTypeLabel(type)} ${index + 1}`),
    type,
    severity: rule?.severity || 'high',
    mode: rule?.mode || '',
    applies_at: Array.isArray(rule?.applies_at) ? String(rule.applies_at[0] || '') : String(rule?.applies_at || ''),
    description: String(rule?.description || ''),
    watch_for_text: Array.isArray(rule?.watch_for) ? rule.watch_for.join(', ') : String(rule?.watch_for || ''),
    violation_if: String(rule?.violation_if || ''),
    required_before: String(rule?.required_before || ''),
    must_call: String(rule?.must_call || ''),
    threshold_field: String(rule?.threshold_field || ''),
    threshold_value: rule?.threshold_value != null ? String(rule.threshold_value) : '',
    required_action: String(rule?.required_action || ''),
    prohibited_pattern: String(rule?.prohibited_pattern || rule?.pattern || ''),
    approval_action: String(rule?.approval_action || rule?.action || ''),
    approved_by: String(rule?.approved_by || ''),
    approval_policy_ref: String(rule?.approval_policy_ref || ''),
    allowed_tools_text: Array.isArray(rule?.allowed_tools) ? rule.allowed_tools.join(', ') : String(rule?.allowed_tools || ''),
    denied_tools_text: Array.isArray(rule?.denied_tools) ? rule.denied_tools.join(', ') : String(rule?.denied_tools || ''),
    workflow_hint: caseRecord?.workflow || '',
  };
}

function createEmptyPolicyRule(type, count, caseRecord) {
  const workflowName = caseRecord?.workflow || 'workflow';
  const base = normalizePolicyRule(
    {
      id: nextPolicyRuleId(count),
      name: `${ruleTypeLabel(type)} ${count}`,
      type,
      severity: type === 'approval_guard' ? 'critical' : 'high',
      mode: type === 'approval_guard' ? 'require_approval' : type === 'tool_permission_guard' ? 'block' : 'detect',
      applies_at: type === 'tool_permission_guard' ? 'tool_call' : 'decision',
      description: '',
    },
    count - 1,
    caseRecord,
  );

  if (type === 'threshold_guard') {
    base.name = 'Human approval above threshold';
    base.description = `Large ${workflowName} decisions require human review.`;
    base.threshold_field = 'amount';
    base.threshold_value = '1000';
    base.required_action = 'human_approval';
  } else if (type === 'approval_guard') {
    base.name = 'Manager approval before sensitive action';
    base.description = 'This action must have a matching human approval before execution.';
    base.approval_action = 'approve_decision';
    base.approved_by = 'manager';
  } else if (type === 'sequence_guard') {
    base.name = 'Required step before final action';
    base.description = 'A required verification step must happen before the final action.';
    base.required_before = 'final_action';
    base.must_call = 'verify_input';
  } else if (type === 'constraint_guard') {
    base.name = 'Stay within known limits';
    base.description = 'The workflow must not go above known limits.';
    base.watch_for_text = 'balance, limit';
    base.violation_if = 'decision_value > watched_value';
  } else if (type === 'prohibition_guard') {
    base.name = 'Never output secrets';
    base.description = 'The workflow must never output secret-like strings.';
    base.prohibited_pattern = 'sk-[A-Za-z0-9]+';
    base.applies_at = 'output';
  } else if (type === 'tool_permission_guard') {
    base.name = 'Only approved tools';
    base.description = 'Only approved tools may be used in this workflow.';
    base.allowed_tools_text = 'lookup_order, verify_identity';
    base.denied_tools_text = 'delete_customer';
  }

  return base;
}

function nextPolicyRuleId(count) {
  return `R${String(count).padStart(3, '0')}`;
}

function formatPolicySourceNote(editor) {
  if (editor.sourceHasPolicy && editor.sourceName) {
    const approvals = editor.policy.approval_policies.length
      ? ` ${editor.policy.approval_policies.length} approval polic${editor.policy.approval_policies.length === 1 ? 'y is' : 'ies are'} carried forward into exports.`
      : '';
    return `Editing the policy sealed into ${editor.sourceName}. Exporting here creates a fresh epi_policy.json for future runs and does not change the evidence already sealed in this case.${approvals}`;
  }

  return 'This case did not include policy.json. Start from the workflow details below, add business rules in plain language, and export a real epi_policy.json for future runs.';
}

function renderPolicyRuleEditor(rules) {
  if (!rules.length) {
    return `
      <div class="policy-rule-empty">
        <h3>No rules yet</h3>
        <p>Add the first control for this workflow. EPI will export a real policy file, not a one-off demo draft.</p>
      </div>
    `;
  }

  return rules.map((rule, index) => renderPolicyRuleCard(rule, index)).join('');
}

function renderPolicyRuleCard(rule, index) {
  return `
    <article class="policy-rule-card" data-rule-index="${index}">
      <div class="policy-rule-header">
        <div>
          <p class="card-label">${escapeHtml(rule.id || nextPolicyRuleId(index + 1))}</p>
          <h3>${escapeHtml(rule.name || ruleTypeLabel(rule.type))}</h3>
        </div>
        <button class="secondary-button" type="button" data-remove-rule="${index}">Remove rule</button>
      </div>

      <div class="policy-rule-grid">
        <label>
          Rule ID
          <input class="text-input" type="text" data-rule-index="${index}" data-rule-field="id" value="${escapeHtml(rule.id)}">
        </label>
        <label>
          Rule type
          <select class="text-input" data-rule-index="${index}" data-rule-field="type">
            ${renderSelectOptions(POLICY_RULE_TYPES, rule.type)}
          </select>
        </label>
        <label class="policy-field-span">
          Rule name
          <input class="text-input" type="text" data-rule-index="${index}" data-rule-field="name" value="${escapeHtml(rule.name)}" placeholder="Manager approval before refund">
        </label>
        <label class="policy-field-span">
          Business description
          <textarea class="text-area" rows="3" data-rule-index="${index}" data-rule-field="description" placeholder="Describe this rule in normal business language.">${escapeHtml(rule.description)}</textarea>
        </label>
        <label>
          Severity
          <select class="text-input" data-rule-index="${index}" data-rule-field="severity">
            ${renderSelectOptions(POLICY_SEVERITIES.map((value) => ({ value, label: sentenceCase(value) })), rule.severity)}
          </select>
        </label>
        <label>
          EPI response
          <select class="text-input" data-rule-index="${index}" data-rule-field="mode">
            ${renderSelectOptions([{ value: '', label: 'Use default behavior' }].concat(POLICY_MODES.map((value) => ({ value, label: sentenceCase(value) }))), rule.mode)}
          </select>
        </label>
        <label>
          Intervention point
          <select class="text-input" data-rule-index="${index}" data-rule-field="applies_at">
            ${renderSelectOptions([{ value: '', label: 'Use workflow default' }].concat(POLICY_INTERVENTION_POINTS.map((value) => ({ value, label: sentenceCase(value) }))), rule.applies_at)}
          </select>
        </label>
        <div class="policy-field-wide"></div>
        ${renderPolicyRuleFields(rule, index)}
      </div>

      <div class="policy-rule-summary">
        <strong>Plain-English rule summary</strong>
        <span class="stack-copy">${escapeHtml(buildPolicyRuleSummary(rule))}</span>
      </div>
    </article>
  `;
}

function renderPolicyRuleFields(rule, index) {
  if (rule.type === 'constraint_guard') {
    return `
      <label>
        Watch these fields
        <input class="text-input" type="text" data-rule-index="${index}" data-rule-field="watch_for_text" value="${escapeHtml(rule.watch_for_text)}" placeholder="balance, credit_limit, exposure_limit">
      </label>
      <label>
        Violation if
        <input class="text-input" type="text" data-rule-index="${index}" data-rule-field="violation_if" value="${escapeHtml(rule.violation_if)}" placeholder="approved_amount > watched_value">
      </label>
    `;
  }

  if (rule.type === 'sequence_guard') {
    return `
      <label>
        Final action that must wait
        <input class="text-input" type="text" data-rule-index="${index}" data-rule-field="required_before" value="${escapeHtml(rule.required_before)}" placeholder="refund">
      </label>
      <label>
        Required earlier step
        <input class="text-input" type="text" data-rule-index="${index}" data-rule-field="must_call" value="${escapeHtml(rule.must_call)}" placeholder="verify_identity">
      </label>
    `;
  }

  if (rule.type === 'threshold_guard') {
    return `
      <label>
        Numeric field
        <input class="text-input" type="text" data-rule-index="${index}" data-rule-field="threshold_field" value="${escapeHtml(rule.threshold_field)}" placeholder="amount">
      </label>
      <label>
        Threshold value
        <input class="text-input" type="number" step="any" data-rule-index="${index}" data-rule-field="threshold_value" value="${escapeHtml(rule.threshold_value)}" placeholder="1000">
      </label>
      <label class="policy-field-span">
        Required action after threshold
        <input class="text-input" type="text" data-rule-index="${index}" data-rule-field="required_action" value="${escapeHtml(rule.required_action)}" placeholder="human_approval">
      </label>
    `;
  }

  if (rule.type === 'prohibition_guard') {
    return `
      <label class="policy-field-span">
        Pattern that must never appear
        <input class="text-input" type="text" data-rule-index="${index}" data-rule-field="prohibited_pattern" value="${escapeHtml(rule.prohibited_pattern)}" placeholder="sk-[A-Za-z0-9]+">
      </label>
    `;
  }

  if (rule.type === 'approval_guard') {
    return `
      <label>
        Action requiring approval
        <input class="text-input" type="text" data-rule-index="${index}" data-rule-field="approval_action" value="${escapeHtml(rule.approval_action)}" placeholder="approve_refund">
      </label>
      <label>
        Approved by
        <input class="text-input" type="text" data-rule-index="${index}" data-rule-field="approved_by" value="${escapeHtml(rule.approved_by)}" placeholder="manager">
      </label>
      <label class="policy-field-span">
        Approval policy reference
        <input class="text-input" type="text" data-rule-index="${index}" data-rule-field="approval_policy_ref" value="${escapeHtml(rule.approval_policy_ref)}" placeholder="manager-refund-approval">
      </label>
    `;
  }

  if (rule.type === 'tool_permission_guard') {
    return `
      <label>
        Allowed tools
        <input class="text-input" type="text" data-rule-index="${index}" data-rule-field="allowed_tools_text" value="${escapeHtml(rule.allowed_tools_text)}" placeholder="lookup_order, verify_identity">
      </label>
      <label>
        Denied tools
        <input class="text-input" type="text" data-rule-index="${index}" data-rule-field="denied_tools_text" value="${escapeHtml(rule.denied_tools_text)}" placeholder="delete_customer, export_ledger">
      </label>
    `;
  }

  return '';
}

function renderSelectOptions(options, selectedValue) {
  return options.map((option) => {
    const value = typeof option === 'string' ? option : option.value;
    const label = typeof option === 'string' ? sentenceCase(option) : option.label;
    const selected = String(selectedValue || '') === String(value) ? ' selected' : '';
    return `<option value="${escapeHtml(value)}"${selected}>${escapeHtml(label)}</option>`;
  }).join('');
}

function buildPolicyRuleSummary(rule) {
  if (rule.type === 'constraint_guard') {
    return `${rule.name || 'Constraint guard'} watches ${rule.watch_for_text || 'important fields'} and flags a violation when ${rule.violation_if || 'the decision breaks a known limit'}.`;
  }
  if (rule.type === 'sequence_guard') {
    return `${rule.name || 'Sequence guard'} requires ${rule.must_call || 'a required step'} before ${rule.required_before || 'the final action'}.`;
  }
  if (rule.type === 'threshold_guard') {
    return `${rule.name || 'Threshold guard'} requires ${rule.required_action || 'human approval'} when ${rule.threshold_field || 'a numeric field'} goes above ${rule.threshold_value || 'the threshold'}.`;
  }
  if (rule.type === 'prohibition_guard') {
    return `${rule.name || 'Prohibition guard'} blocks output that matches ${rule.prohibited_pattern || 'a forbidden pattern'}.`;
  }
  if (rule.type === 'approval_guard') {
    return `${rule.name || 'Approval rule'} requires ${rule.approved_by || 'the reviewer'} to approve ${rule.approval_action || 'a sensitive action'} before it executes.`;
  }
  if (rule.type === 'tool_permission_guard') {
    return `${rule.name || 'Tool permission guard'} allows ${rule.allowed_tools_text || 'approved tools only'} and denies ${rule.denied_tools_text || 'restricted tools'}.`;
  }
  return rule.description || 'Rule summary unavailable.';
}

function syncPolicyMetadata() {
  const editor = getActivePolicyEditor();
  editor.policy.policy_id = elements.policyId.value.trim();
  editor.policy.system_name = elements.policySystemName.value.trim();
  editor.policy.system_version = elements.policySystemVersion.value.trim();
  editor.policy.policy_version = elements.policyVersion.value.trim();
  editor.policy.profile_id = elements.policyProfileId.value.trim();
  editor.policy.scope.organization = elements.policyScopeOrganization.value.trim();
  editor.policy.scope.team = elements.policyScopeTeam.value.trim();
  editor.policy.scope.application = elements.policyScopeApplication.value.trim();
  editor.policy.scope.workflow = elements.policyScopeWorkflow.value.trim();
  editor.policy.scope.environment = elements.policyScopeEnvironment.value.trim();
  updatePolicyJsonPreview();
}

function handlePolicyRuleInput(event) {
  const field = event.target?.dataset?.ruleField;
  const index = Number.parseInt(event.target?.dataset?.ruleIndex || '', 10);
  if (!field || Number.isNaN(index)) {
    return;
  }

  const editor = getActivePolicyEditor();
  const rule = editor.policy.rules[index];
  if (!rule) {
    return;
  }

  rule[field] = event.target.value;
  updatePolicyJsonPreview();

  if (field === 'type' || field === 'id' || field === 'name' || event.type === 'change') {
    renderRulesView();
  }
}

function handlePolicyRuleClick(event) {
  const removeButton = event.target.closest('[data-remove-rule]');
  if (!removeButton) {
    return;
  }

  const index = Number.parseInt(removeButton.dataset.removeRule, 10);
  if (Number.isNaN(index)) {
    return;
  }

  const editor = getActivePolicyEditor();
  editor.policy.rules.splice(index, 1);
  renderRulesView();
}

function addPolicyRule() {
  const editor = getActivePolicyEditor();
  editor.policy.rules.push(createEmptyPolicyRule(elements.addRuleType.value, editor.policy.rules.length + 1, getSelectedCase()));
  renderRulesView();
}

function resetPolicyEditorFromCase() {
  state.policyEditors[getPolicyEditorKey()] = createPolicyEditorFromCase(getSelectedCase());
  renderRulesView();
}

function updatePolicyJsonPreview() {
  elements.policyJsonPreview.textContent = JSON.stringify(buildExportablePolicyJson(getActivePolicyEditor()), null, 2);
}

function buildExportablePolicyJson(editor) {
  const policy = editor.policy;
  const systemName = policy.system_name || getSelectedCase()?.workflow || 'decision-ops';
  const payload = {
    policy_format_version: policy.policy_format_version || '2.0',
    policy_id: policy.policy_id || slugifyPolicyId(systemName),
    system_name: systemName,
    system_version: policy.system_version || '1.0',
    policy_version: policy.policy_version || new Date().toISOString().slice(0, 10),
    profile_id: policy.profile_id || undefined,
    scope: compactScope(policy.scope),
    approval_policies: policy.approval_policies.length ? policy.approval_policies.map((approval) => compactObject({
      approval_id: approval.approval_id,
      required_roles: approval.required_roles.length ? approval.required_roles : undefined,
      minimum_approvers: approval.minimum_approvers,
      expires_after_minutes: approval.expires_after_minutes,
      reason_required: approval.reason_required || undefined,
      separation_of_duties: approval.separation_of_duties || undefined,
    })) : undefined,
    rules: policy.rules.map(sanitizePolicyRule),
  };

  const cleaned = compactObject(payload);
  cleaned.rules = payload.rules;
  return cleaned;
}

function sanitizePolicyRule(rule) {
  const payload = {
    id: rule.id || nextPolicyRuleId(1),
    name: rule.name || ruleTypeLabel(rule.type),
    severity: rule.severity || 'high',
    description: rule.description || buildPolicyRuleSummary(rule),
    type: rule.type,
    mode: rule.mode || undefined,
    applies_at: rule.applies_at || undefined,
  };

  if (rule.type === 'constraint_guard') {
    payload.watch_for = splitCommaList(rule.watch_for_text);
    payload.violation_if = rule.violation_if || undefined;
  } else if (rule.type === 'sequence_guard') {
    payload.required_before = rule.required_before || undefined;
    payload.must_call = rule.must_call || undefined;
  } else if (rule.type === 'threshold_guard') {
    payload.threshold_field = rule.threshold_field || undefined;
    payload.threshold_value = rule.threshold_value !== '' && !Number.isNaN(Number(rule.threshold_value))
      ? Number(rule.threshold_value)
      : undefined;
    payload.required_action = rule.required_action || undefined;
  } else if (rule.type === 'prohibition_guard') {
    payload.prohibited_pattern = rule.prohibited_pattern || undefined;
  } else if (rule.type === 'approval_guard') {
    payload.approval_action = rule.approval_action || undefined;
    payload.approved_by = rule.approved_by || undefined;
    payload.approval_policy_ref = rule.approval_policy_ref || undefined;
  } else if (rule.type === 'tool_permission_guard') {
    payload.allowed_tools = splitCommaList(rule.allowed_tools_text);
    payload.denied_tools = splitCommaList(rule.denied_tools_text);
  }

  return compactObject(payload);
}

function compactScope(scope) {
  const cleaned = compactObject(scope || {});
  return Object.keys(cleaned).length ? cleaned : undefined;
}

function compactObject(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return value;
  }

  const result = {};
  Object.entries(value).forEach(([key, item]) => {
    if (item == null) {
      return;
    }
    if (typeof item === 'string' && !item.trim()) {
      return;
    }
    if (Array.isArray(item) && !item.length) {
      return;
    }
    result[key] = item;
  });
  return result;
}

function splitCommaList(value) {
  return String(value || '')
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean);
}

function ruleTypeLabel(value) {
  const match = POLICY_RULE_TYPES.find((item) => item.value === value);
  if (match) {
    return match.label;
  }
  return sentenceCase(String(value || 'rule').replace(/_/g, ' '));
}

function downloadPolicyFile() {
  const policyJson = buildExportablePolicyJson(getActivePolicyEditor());
  downloadBlob('epi_policy.json', JSON.stringify(policyJson, null, 2), 'application/json');
}

function downloadPolicySummary() {
  const editor = getActivePolicyEditor();
  const caseRecord = getSelectedCase();
  const policyJson = buildExportablePolicyJson(editor);
  const lines = [
    `Policy ID: ${policyJson.policy_id}`,
    `System: ${policyJson.system_name} (${policyJson.system_version})`,
    `Policy version: ${policyJson.policy_version}`,
    `Rules: ${policyJson.rules.length}`,
    `Approval policies carried forward: ${(policyJson.approval_policies || []).length}`,
    '',
    caseRecord
      ? `Selected case: ${caseRecord.decision.title}`
      : 'No case selected.',
    '',
    'Rule summaries',
    ...policyJson.rules.map((rule, index) => `${index + 1}. ${rule.name} [${rule.type}] - ${rule.description}`),
  ];
  downloadBlob('epi_policy_summary.txt', lines.join('\n'), 'text/plain;charset=utf-8');
}

function slugifyPolicyId(value) {
  return String(value || 'epi-policy')
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '') || 'epi-policy';
}

function populateReviewForm(caseRecord) {
  const existingReview = getLatestReviewEntry(caseRecord);
  const canDownloadReviewedArtifact = canBuildReviewedArtifact(caseRecord);
  const defaultOutcome = caseRecord.analysis?.primary_fault || caseRecord.analysis?.fault_detected || caseRecord.reviewState.code === 'pending'
    ? 'confirmed_fault'
    : 'dismissed';
  elements.reviewerName.value = existingReview?.reviewer || caseRecord.review?.reviewed_by || state.reviewerIdentity || '';
  setSelectedReviewOutcome(existingReview?.outcome || defaultOutcome);
  elements.reviewNotes.value = existingReview?.notes || '';
  elements.reviewSaveStatus.textContent = existingReview
    ? `Latest review notes on file: ${mapReviewOutcome(existingReview.outcome)}${caseRecord.review?.review_signature ? ' (signed)' : ''}`
      : caseRecord.backendCase
      ? 'Saving here updates the shared case. Downloading a reviewed .epi exports a portable reviewed case file from the team workspace.'
      : canDownloadReviewedArtifact
      ? 'Your changes stay local until you download the reviewed case or review notes.'
      : 'Your changes stay local in this browser session. Open the original .epi file if you want to download a reviewed case.';
}

function setSelectedReviewOutcome(outcome) {
  const nextOutcome = REVIEW_ACTIONS[outcome] ? outcome : 'dismissed';
  elements.reviewOutcome.value = nextOutcome;
  [
    elements.reviewApproveButton,
    elements.reviewRejectButton,
    elements.reviewEscalateButton,
  ].forEach((button) => {
    if (!button) {
      return;
    }
    const selected = button.dataset.reviewAction === nextOutcome;
    button.classList.toggle('is-selected', selected);
    button.classList.toggle('primary-button', selected);
    button.classList.toggle('secondary-button', !selected);
  });
  if (elements.reviewActionHelp) {
    elements.reviewActionHelp.textContent = REVIEW_ACTIONS[nextOutcome].help;
  }
}

async function saveReviewToBackend(caseRecord, reviewRecord) {
  if (!caseRecord?.backendCase || !state.bridgeHealth?.url) {
    return null;
  }

  const response = await bridgeFetch(`${state.bridgeHealth.url}/api/cases/${encodeURIComponent(caseRecord.id)}/reviews`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(reviewRecord),
  });
  const payload = await response.json();
  if (!response.ok || !payload.ok || !payload.case) {
    throw new Error(payload.detail || payload.error || `Review save failed with status ${response.status}`);
  }

  const updatedCase = await buildCaseRecord(payload.case);
  mergeCases([updatedCase]);
  state.selectedCaseId = updatedCase.id;
  renderApp();
  setView('case');
  return updatedCase;
}

async function saveCaseWorkflow() {
  const caseRecord = getSelectedCase();
  if (!caseRecord) {
    return;
  }
  if (!caseRecord.backendCase || !state.bridgeHealth?.url) {
    elements.workflowSaveStatus.textContent = 'Workflow updates are available for shared team cases.';
    return;
  }

  const payload = {
    assignee: (elements.workflowAssignee.value || '').trim() || null,
    due_at: (elements.workflowDueAt.value || '').trim() || null,
    status: elements.workflowStatus.value || caseRecord.status || 'unassigned',
    updated_by: state.reviewerIdentity || (elements.reviewerName.value || '').trim() || 'reviewer',
    reason: 'Workflow updated in case review',
  };

  try {
    const response = await bridgeFetch(`${state.bridgeHealth.url}/api/cases/${encodeURIComponent(caseRecord.id)}`, {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    });
    const data = await response.json();
    if (!response.ok || !data.ok || !data.case) {
      throw new Error(data.detail || data.error || `Workflow save failed with status ${response.status}`);
    }
    const updatedCase = await buildCaseRecord(data.case);
    mergeCases([updatedCase]);
    state.selectedCaseId = updatedCase.id;
    elements.workflowSaveStatus.textContent = `Saved workflow state: ${updatedCase.workflowState.label}.`;
    renderApp();
    setView('case');
  } catch (error) {
    elements.workflowSaveStatus.textContent = `Could not save workflow: ${error.message}`;
  }
}

async function saveCaseComment() {
  const caseRecord = getSelectedCase();
  if (!caseRecord) {
    return;
  }
  if (!caseRecord.backendCase || !state.bridgeHealth?.url) {
    elements.commentSaveStatus.textContent = 'Comments are available for shared team cases.';
    return;
  }

  const body = (elements.commentBody.value || '').trim();
  if (!body) {
    elements.commentSaveStatus.textContent = 'Write a short comment before saving.';
    return;
  }

  try {
    const response = await bridgeFetch(`${state.bridgeHealth.url}/api/cases/${encodeURIComponent(caseRecord.id)}/comments`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        author: state.reviewerIdentity || (elements.reviewerName.value || '').trim() || 'reviewer',
        body,
      }),
    });
    const data = await response.json();
    if (!response.ok || !data.ok || !data.case) {
      throw new Error(data.detail || data.error || `Comment save failed with status ${response.status}`);
    }
    const updatedCase = await buildCaseRecord(data.case);
    mergeCases([updatedCase]);
    state.selectedCaseId = updatedCase.id;
    elements.commentBody.value = '';
    elements.commentSaveStatus.textContent = 'Comment added to the shared case.';
    renderApp();
    setView('case');
  } catch (error) {
    elements.commentSaveStatus.textContent = `Could not save comment: ${error.message}`;
  }
}

async function ensureCaseInReview(caseRecord) {
  if (!caseRecord?.backendCase || !state.bridgeHealth?.url) {
    return caseRecord;
  }
  if (caseRecord.status === 'in_review') {
    return caseRecord;
  }
  const response = await bridgeFetch(`${state.bridgeHealth.url}/api/cases/${encodeURIComponent(caseRecord.id)}`, {
    method: 'PATCH',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      status: 'in_review',
      updated_by: state.reviewerIdentity || (elements.reviewerName.value || '').trim() || 'reviewer',
      reason: 'Review started in case review',
    }),
  });
  const payload = await response.json();
  if (!response.ok || !payload.ok || !payload.case) {
    throw new Error(payload.detail || payload.error || `Could not start review (status ${response.status})`);
  }
  const updatedCase = await buildCaseRecord(payload.case);
  mergeCases([updatedCase]);
  state.selectedCaseId = updatedCase.id;
  renderApp();
  return updatedCase;
}

async function applyLocalReview(forcedOutcome) {
  const caseRecord = getSelectedCase();
  if (!caseRecord) {
    return;
  }

  try {
    if (forcedOutcome) {
      setSelectedReviewOutcome(forcedOutcome);
    }
    const reviewRecord = await buildPreparedReviewRecord(caseRecord);
    const actionLabel = mapReviewOutcome(reviewRecord.reviews?.[0]?.outcome);
    if (caseRecord.backendCase) {
      await saveReviewToBackend(caseRecord, reviewRecord);
      elements.reviewSaveStatus.textContent = `${actionLabel} saved to the shared team case for ${reviewRecord.reviewed_by || 'this reviewer'} at ${formatDate(reviewRecord.reviewed_at)}.${reviewRecord.review_signature ? ' Signed review ready.' : ' Review notes saved.'}`;
    } else {
      caseRecord.review = reviewRecord;
      caseRecord.reviewSignature = await verifyReviewSignature(reviewRecord);
      caseRecord.reviewState = deriveReviewState(reviewRecord, caseRecord.analysis, caseRecord.policyEvaluation, caseRecord.reviewSignature);
      caseRecord.status = workflowStatusForReviewOutcome(reviewRecord.reviews?.[0]?.outcome, caseRecord.status);
      caseRecord.workflowState = deriveWorkflowState(caseRecord.status);
      const sharedSaved = await publishCaseToSharedWorkspace(caseRecord);
      elements.reviewSaveStatus.textContent = `${actionLabel} saved locally for ${reviewRecord.reviewed_by || 'this reviewer'} at ${formatDate(reviewRecord.reviewed_at)}.${reviewRecord.review_signature ? ' Signed review ready.' : ' Download the reviewed case file when you are ready.'}`;
      if (sharedSaved) {
        elements.reviewSaveStatus.textContent += ' Shared workspace updated.';
      }
    }
    renderInbox();
    renderCaseView();
    renderReportsView();
  } catch (error) {
    elements.reviewSaveStatus.textContent = `Could not prepare review: ${error.message}`;
  }
}

async function downloadReviewRecord() {
  const caseRecord = getSelectedCase();
  if (!caseRecord) {
    return;
  }
  try {
    const reviewRecord = await buildPreparedReviewRecord(caseRecord);
    if (caseRecord.backendCase) {
      await saveReviewToBackend(caseRecord, reviewRecord);
    } else {
      caseRecord.review = reviewRecord;
      caseRecord.reviewSignature = await verifyReviewSignature(reviewRecord);
      caseRecord.reviewState = deriveReviewState(reviewRecord, caseRecord.analysis, caseRecord.policyEvaluation, caseRecord.reviewSignature);
      caseRecord.status = workflowStatusForReviewOutcome(reviewRecord.reviews?.[0]?.outcome, caseRecord.status);
      caseRecord.workflowState = deriveWorkflowState(caseRecord.status);
      await publishCaseToSharedWorkspace(caseRecord);
      renderInbox();
      renderCaseView();
      renderReportsView();
    }

    const filename = caseRecord.sourceName.replace(/\.epi$/i, '') + '-review.json';
    downloadBlob(filename, JSON.stringify(reviewRecord, null, 2), 'application/json');
    elements.reviewSaveStatus.textContent = `Downloaded ${filename}.${reviewRecord.review_signature ? ' The review notes file is signed.' : ' The review notes file is unsigned.'}`;
  } catch (error) {
    elements.reviewSaveStatus.textContent = `Could not export review notes: ${error.message}`;
  }
}

function downloadCaseSummary() {
  const caseRecord = getSelectedCase();
  if (!caseRecord) {
    return;
  }
  const filename = caseRecord.sourceName.replace(/\.epi$/i, '') + '-case-summary.txt';
  downloadBlob(filename, buildCaseSummary(caseRecord), 'text/plain;charset=utf-8');
}

async function downloadReviewedArtifact() {
  const caseRecord = getSelectedCase();
  if (!caseRecord) {
    return;
  }

  if (!canBuildReviewedArtifact(caseRecord)) {
    elements.reviewSaveStatus.textContent = 'This browser session does not have enough case file data to rebuild a reviewed .epi yet.';
    return;
  }

  try {
    const reviewRecord = await buildPreparedReviewRecord(caseRecord);
    if (caseRecord.backendCase) {
      await saveReviewToBackend(caseRecord, reviewRecord);
      elements.reviewSaveStatus.textContent = 'Preparing reviewed .epi file...';
      const response = await bridgeFetch(`${state.bridgeHealth.url}/api/cases/${encodeURIComponent(caseRecord.id)}/export`, {
        method: 'POST',
      });
      if (!response.ok) {
        throw new Error(`Export failed with status ${response.status}`);
      }
      const blob = await response.blob();
      const filename = caseRecord.sourceName.replace(/\.epi$/i, '') + '-reviewed.epi';
      downloadBlob(filename, blob, 'application/vnd.epi');
      elements.reviewSaveStatus.textContent = `Downloaded ${filename}.${reviewRecord.review_signature ? ' The embedded review notes are signed.' : ' The embedded review notes are unsigned.'} The shared case remains available in the inbox.`;
    } else {
      caseRecord.review = reviewRecord;
      caseRecord.reviewSignature = await verifyReviewSignature(reviewRecord);
      caseRecord.reviewState = deriveReviewState(reviewRecord, caseRecord.analysis, caseRecord.policyEvaluation, caseRecord.reviewSignature);
      caseRecord.status = workflowStatusForReviewOutcome(reviewRecord.reviews?.[0]?.outcome, caseRecord.status);
      caseRecord.workflowState = deriveWorkflowState(caseRecord.status);
      await publishCaseToSharedWorkspace(caseRecord);

      renderInbox();
      renderCaseView();
      renderReportsView();

      elements.reviewSaveStatus.textContent = 'Preparing reviewed .epi file...';
      const archiveBytes = await buildReviewedArtifactBytes(caseRecord, reviewRecord);
      const filename = caseRecord.sourceName.replace(/\.epi$/i, '') + '-reviewed.epi';
      downloadBlob(filename, archiveBytes, 'application/vnd.epi');
      elements.reviewSaveStatus.textContent = `Downloaded ${filename}.${reviewRecord.review_signature ? ' The embedded review notes are signed.' : ' The embedded review notes are unsigned.'} The original case file is unchanged.`;
    }
  } catch (error) {
    elements.reviewSaveStatus.textContent = `Could not create reviewed .epi: ${error.message}`;
  }
}

async function buildPreparedReviewRecord(caseRecord) {
  const reviewRecord = buildReviewDraft(caseRecord);
  const signingKeyText = elements.reviewSigningKey.value.trim();
  if (!signingKeyText) {
    return reviewRecord;
  }
  return signReviewRecord(reviewRecord, signingKeyText);
}

async function signReviewRecord(reviewRecord, signingKeyText) {
  if (!globalThis.crypto?.subtle) {
    throw new Error('Browser cryptography is not available.');
  }

  if (!globalThis.noble?.getPublicKey && !globalThis.noble?.getPublicKeyAsync) {
    throw new Error('Browser public-key helper is not available.');
  }

  const pkcs8Bytes = parsePkcs8PrivateKey(signingKeyText);
  const seedBytes = extractEd25519SeedFromPkcs8(pkcs8Bytes);
  const privateKey = await crypto.subtle.importKey(
    'pkcs8',
    pkcs8Bytes,
    'Ed25519',
    false,
    ['sign'],
  );

  const payloadBytes = new TextEncoder().encode(buildReviewSigningPayload(reviewRecord));
  const hashBytes = await sha256Bytes(payloadBytes);
  const signatureBuffer = await crypto.subtle.sign('Ed25519', privateKey, hashBytes);
  const signatureHex = noble.etc.bytesToHex(new Uint8Array(signatureBuffer));

  const publicKeyBytes = globalThis.noble.getPublicKey
    ? globalThis.noble.getPublicKey(seedBytes)
    : await globalThis.noble.getPublicKeyAsync(seedBytes);
  const publicKeyHex = noble.etc.bytesToHex(publicKeyBytes);

  return {
    ...reviewRecord,
    review_signature: `ed25519:${publicKeyHex}:${signatureHex}`,
  };
}

async function buildReviewedArtifactBytes(caseRecord, reviewRecord) {
  const entries = [];

  entries.push({
    name: 'mimetype',
    data: textToBytes('application/vnd.epi+zip'),
  });

  const sourceEntries = await collectArtifactSourceEntries(caseRecord);
  sourceEntries.forEach((entry) => entries.push(entry));

  const viewerHtml = buildEmbeddedViewerHtml(caseRecord, reviewRecord, sourceEntries);
  entries.push({
    name: 'review.json',
    data: textToBytes(JSON.stringify(reviewRecord, null, 2)),
  });
  entries.push({
    name: 'viewer.html',
    data: textToBytes(viewerHtml),
  });
  entries.push({
    name: 'manifest.json',
    data: textToBytes(JSON.stringify({
      ...caseRecord.manifest,
      container_format: 'envelope-v2',
    }, null, 2)),
  });

  const payloadBytes = createZipArchive(entries);
  return wrapZipPayloadAsEnvelope(payloadBytes);
}

async function collectArtifactSourceEntries(caseRecord) {
  const entries = [];

  if (caseRecord.archiveBytes) {
    if (typeof JSZip === 'undefined') {
      throw new Error('The browser ZIP helper is unavailable for this preloaded case file.');
    }

    const sourceZip = await JSZip.loadAsync(caseRecord.archiveBytes.slice(0));
    const sourceNames = Object.keys(sourceZip.files)
      .filter((name) => !sourceZip.files[name].dir)
      .filter((name) => !['mimetype', 'manifest.json', 'viewer.html', 'review.json'].includes(name));

    sourceNames.sort();
    for (const name of sourceNames) {
      const entry = sourceZip.file(name);
      if (!entry) {
        continue;
      }
      entries.push({
        name,
        data: await entry.async('uint8array'),
      });
    }
    return entries;
  }

  if (caseRecord.embeddedFiles && Object.keys(caseRecord.embeddedFiles).length) {
    Object.keys(caseRecord.embeddedFiles)
      .filter((name) => !['mimetype', 'manifest.json', 'viewer.html', 'review.json'].includes(name))
      .sort()
      .forEach((name) => {
        entries.push({
          name,
          data: caseRecord.embeddedFiles[name].slice(0),
        });
      });
    return entries;
  }

  throw new Error('This browser session does not include enough case file data to rebuild the reviewed .epi.');
}

function buildEmbeddedViewerHtml(caseRecord, reviewRecord, sourceEntries) {
  let html = '<!DOCTYPE html>\n' + document.documentElement.outerHTML;
  const payload = {
    manifest: caseRecord.manifest,
    steps: caseRecord.steps,
    analysis: caseRecord.analysis,
    policy: caseRecord.policy,
    policy_evaluation: caseRecord.policyEvaluation,
    review: reviewRecord,
    environment: caseRecord.environment,
    stdout: caseRecord.stdout,
    stderr: caseRecord.stderr,
    files: encodeEmbeddedFiles(sourceEntries),
  };
  const dataTag = `<script id="epi-data" type="application/json">${htmlSafeJson(payload, 2)}</script>`;

  html = html.replace(/<script id="epi-preloaded-cases" type="application\/json">[\s\S]*?<\/script>\s*/u, '');
  if (/<script id="epi-data" type="application\/json">[\s\S]*?<\/script>/u.test(html)) {
    html = html.replace(/<script id="epi-data" type="application\/json">[\s\S]*?<\/script>/u, dataTag);
  } else if (html.includes('<script id="epi-view-context" type="application/json">')) {
    html = html.replace('<script id="epi-view-context" type="application/json">', `${dataTag}\n<script id="epi-view-context" type="application/json">`);
  } else if (html.includes('</head>')) {
    html = html.replace('</head>', `${dataTag}\n</head>`);
  }

  return html.replace(/<script src="https:\/\/cdn\.jsdelivr\.net\/npm\/jszip@3\.10\.1\/dist\/jszip\.min\.js"><\/script>\s*/u, '');
}

function encodeEmbeddedFiles(entries) {
  const files = {};
  entries.forEach((entry) => {
    files[entry.name] = uint8ArrayToBase64(entry.data);
  });
  return files;
}

function buildReportPayload(reportType, reportScope) {
  const cases = resolveReportCases(reportScope);
  return {
    generated_at: new Date().toISOString(),
    report_type: reportType,
    scope: reportScope,
    counts: {
      total_cases: cases.length,
      trusted_cases: cases.filter((caseRecord) => caseRecord.trust.code === 'trusted').length,
      pending_review: cases.filter((caseRecord) => caseRecord.reviewState.code === 'pending').length,
      do_not_use: cases.filter((caseRecord) => caseRecord.trust.code === 'do-not-use').length,
    },
    cases: cases.map((caseRecord) => ({
      title: caseRecord.decision.title,
      workflow: caseRecord.workflow,
      created_at: caseRecord.manifest.created_at || null,
      trust: caseRecord.trust.label,
      risk: caseRecord.risk.label,
      review: caseRecord.reviewState.label,
      outcome: caseRecord.decision.outcome,
      file: caseRecord.sourceName,
    })),
  };
}

function formatReportPreview(report) {
  const lines = [
    `Report type: ${report.report_type}`,
    `Scope: ${report.scope}`,
    `Generated: ${formatDate(report.generated_at)}`,
    '',
    `Cases: ${report.counts.total_cases}`,
    `Trusted: ${report.counts.trusted_cases}`,
    `Pending review: ${report.counts.pending_review}`,
    `Do not use: ${report.counts.do_not_use}`,
    '',
  ];

  if (!report.cases.length) {
    lines.push('No cases available for this report scope.');
    return lines.join('\n');
  }

  report.cases.slice(0, 8).forEach((item, index) => {
    lines.push(`${index + 1}. ${item.title}`);
    lines.push(`   Workflow: ${item.workflow}`);
    lines.push(`   Trust: ${item.trust}`);
    lines.push(`   Review: ${item.review}`);
    lines.push(`   Outcome: ${item.outcome}`);
  });

  if (report.cases.length > 8) {
    lines.push('');
    lines.push(`Plus ${report.cases.length - 8} more case(s). Download the report for the full list.`);
  }

  return lines.join('\n');
}

function downloadReport(format) {
  const report = buildReportPayload(elements.reportType.value, elements.reportScope.value);
  const baseName = `epi-${report.report_type}-report`;

  if (format === 'json') {
    downloadBlob(`${baseName}.json`, JSON.stringify(report, null, 2), 'application/json');
    return;
  }

  if (format === 'csv') {
    const rows = [
      ['title', 'workflow', 'created_at', 'trust', 'risk', 'review', 'outcome', 'file'],
      ...report.cases.map((item) => [
        item.title,
        item.workflow,
        item.created_at || '',
        item.trust,
        item.risk,
        item.review,
        item.outcome,
        item.file,
      ]),
    ];
    downloadBlob(`${baseName}.csv`, rows.map((row) => row.map(toCsvCell).join(',')).join('\n'), 'text/csv;charset=utf-8');
    return;
  }

  downloadBlob(`${baseName}.txt`, formatReportPreview(report), 'text/plain;charset=utf-8');
}

async function readJsonl(zip, name) {
  const text = await readOptionalText(zip, name);
  if (!text) {
    return [];
  }
  return text.split(/\r?\n/).filter(Boolean).map((line) => {
    return JSON.parse(line);
  });
}

async function readZipText(zip, name) {
  const entry = zip.file(name);
  if (!entry) {
    throw new Error(`${name} is missing from this .epi file.`);
  }
  return entry.async('string');
}

async function readOptionalText(zip, name) {
  const entry = zip.file(name);
  if (!entry) {
    return null;
  }
  return entry.async('string');
}

async function readOptionalJson(zip, name) {
  const text = await readOptionalText(zip, name);
  if (!text) {
    return null;
  }
  try {
    return JSON.parse(text);
  } catch (_error) {
    return null;
  }
}

async function checkIntegrity(zip, manifest) {
  const fileManifest = manifest.file_manifest || {};
  const mismatches = [];

  for (const [filename, expectedHash] of Object.entries(fileManifest)) {
    const entry = zip.file(filename);
    if (!entry) {
      mismatches.push(`${filename} missing`);
      continue;
    }

    const buffer = await entry.async('arraybuffer');
    const actualHash = await sha256Hex(buffer);
    if (actualHash !== expectedHash) {
      mismatches.push(filename);
    }
  }

  return {
    ok: mismatches.length === 0,
    checked: Object.keys(fileManifest).length,
    mismatches,
  };
}

async function verifySignature(manifest) {
  if (!manifest.signature) {
    return { valid: false, reason: 'No signer attached to this case file' };
  }

  if (typeof verifyManifestSignature !== 'function') {
    return { valid: false, reason: 'Browser signature verifier unavailable' };
  }

  try {
    return await verifyManifestSignature(manifest);
  } catch (error) {
    return { valid: false, reason: error.message };
  }
}

async function verifyReviewSignature(review) {
  if (!review) {
    return {
      code: 'no-review',
      label: 'No review saved',
      tone: 'neutral',
      detail: 'This case file does not include saved review notes yet.',
    };
  }

  if (!review.review_signature) {
    return {
      code: 'unsigned-review',
      label: 'Unsigned review',
      tone: 'warning',
      detail: 'A review is attached, but it does not carry a cryptographic signature.',
    };
  }

  if (!globalThis.noble?.verifyAsync) {
    return {
      code: 'unsigned-review',
      label: 'Review not checked',
      tone: 'warning',
      detail: 'The browser review verifier is unavailable.',
    };
  }

  const parts = String(review.review_signature).split(':');
  if (parts.length !== 3 || parts[0] !== 'ed25519') {
    return {
      code: 'bad-review-signature',
      label: 'Bad review signature',
      tone: 'danger',
      detail: 'The attached review signature is not in the expected Ed25519 format.',
    };
  }

  try {
    const publicKeyBytes = noble.etc.hexToBytes(parts[1]);
    const signatureBytes = decodeSignatureBytes(parts[2]);
    const payloadBytes = new TextEncoder().encode(buildReviewSigningPayload(review));
    const hashBytes = await sha256Bytes(payloadBytes);
    const isValid = await noble.verifyAsync(signatureBytes, hashBytes, publicKeyBytes);

    if (isValid) {
      return {
        code: 'signed-review',
        label: 'Signed review',
        tone: 'success',
        detail: 'The attached review signature verifies against the review contents.',
      };
    }

    return {
      code: 'bad-review-signature',
      label: 'Bad review signature',
      tone: 'danger',
      detail: 'The attached review signature does not match the review contents.',
    };
  } catch (error) {
    return {
      code: 'bad-review-signature',
      label: 'Bad review signature',
      tone: 'danger',
      detail: `The review signature could not be verified: ${error.message}`,
    };
  }
}

async function sha256Hex(buffer) {
  const hash = await crypto.subtle.digest('SHA-256', buffer);
  return Array.from(new Uint8Array(hash))
    .map((byte) => byte.toString(16).padStart(2, '0'))
    .join('');
}

async function sha256Bytes(bufferLike) {
  const hash = await crypto.subtle.digest('SHA-256', bufferLike);
  return new Uint8Array(hash);
}

function deriveTrustState(manifest, integrity, signature) {
  if (!integrity.ok) {
    return {
      code: 'do-not-use',
      label: 'Tampered / do not use',
      tone: 'danger',
      detail: `Integrity failed for ${integrity.mismatches.join(', ')}.`,
    };
  }

  if (integrity.pending || signature.pending) {
    if (manifest.signature) {
      return {
        code: 'verify-source',
        label: 'Verify source',
        tone: 'warning',
        detail: signature.reason || 'Open this case through epi view to verify the signer and file integrity.',
      };
    }

    return {
      code: 'source-not-proven',
      label: 'Unsigned but intact',
      tone: 'warning',
      detail: `This packaged case view can show the decision record, but it did not recheck the ${integrity.checked} protected file(s) on this device.`,
    };
  }

  if (signature.valid) {
    return {
      code: 'trusted',
      label: 'Verified',
      tone: 'success',
      detail: `Record has not been modified. All ${integrity.checked} protected file(s) matched and the signer verified.`,
    };
  }

  if (manifest.signature) {
    return {
      code: 'source-not-proven',
      label: 'Unsigned but intact',
      tone: 'warning',
      detail: `The protected files match, but the signer could not be confirmed: ${signature.reason}.`,
    };
  }

  return {
    code: 'source-not-proven',
    label: 'Unsigned but intact',
    tone: 'warning',
    detail: `The protected files match, but no signer is attached to this case file.`,
  };
}

function analysisHeadline(analysis) {
  if (!analysis) {
    return '';
  }
  if (typeof analysis.summary === 'string' && analysis.summary.trim()) {
    return analysis.summary;
  }
  if (analysis.summary && typeof analysis.summary === 'object') {
    return analysis.summary.headline || analysis.summary.primary_category || '';
  }
  return '';
}

function deriveAnalysisState(manifest, analysis) {
  const status = String(manifest?.analysis_status || '').trim().toLowerCase();
  const error = String(manifest?.analysis_error || '').trim();
  if (status === 'complete') {
    return {
      code: 'complete',
      label: 'Automated policy check complete',
      tone: 'success',
      detail: analysisHeadline(analysis) || 'Automated checks ran and the results were sealed into this case file.',
    };
  }
  if (status === 'error') {
    return {
      code: 'error',
      label: 'Automated policy check failed',
      tone: 'danger',
      detail: error || 'Automated checks failed before the artifact was sealed.',
    };
  }
  if (status === 'skipped') {
    return {
      code: 'skipped',
      label: 'Automated policy check not run',
      tone: 'warning',
      detail: 'No policy check result was recorded for this case file.',
    };
  }
  return {
    code: 'unknown',
    label: 'Automated policy check not recorded',
    tone: 'neutral',
    detail: 'This artifact does not record whether automated checks ran.',
  };
}

function businessDecisionLabel(value) {
  const raw = String(value || '').trim().toLowerCase();
  if (!raw) {
    return 'Decision captured';
  }
  if (raw.includes('deny') || raw.includes('declin')) {
    return 'Denied';
  }
  if (raw.includes('approve') || raw.includes('pay') || raw.includes('accept')) {
    return 'Approved';
  }
  if (raw.includes('escalat') || raw.includes('review')) {
    return 'Escalated';
  }
  return sentenceCase(raw);
}

function deriveDecisionSummary(manifest, steps, analysis) {
  const lastDecisionStep = [...steps].reverse().find((step) => {
    return ['agent.decision', 'agent.approval.response', 'llm.response', 'session.end'].includes(step.kind);
  });

  const rawOutcome =
    lastDecisionStep?.content?.decision ||
    lastDecisionStep?.content?.action ||
    lastDecisionStep?.content?.result ||
    (typeof lastDecisionStep?.content?.approved === 'boolean'
      ? (lastDecisionStep.content.approved ? 'approved' : 'rejected')
      : null) ||
    analysisHeadline(analysis) ||
    manifest.goal ||
    'Decision captured';

  const workflowName = manifest.system_name || manifest.workflow_name || manifest.workflow_id || 'workflow';

  return {
    title: businessDecisionLabel(String(rawOutcome)),
    outcome: businessDecisionLabel(String(rawOutcome)),
    summary: analysisHeadline(analysis) || manifest.notes || manifest.goal || `EPI captured the decision path for this ${workflowName}.`,
  };
}

function deriveWorkflowName(manifest, steps, fallback) {
  return (
    manifest.workflow_name ||
    manifest.system_name ||
    steps.find((step) => step.kind === 'session.start')?.content?.workflow ||
    stripExtension(fallback)
  );
}

function deriveWorkflowState(status) {
  switch (String(status || '').trim()) {
    case 'assigned':
      return {
        code: 'assigned',
        label: 'Assigned',
        tone: 'neutral',
        detail: 'A reviewer owns this case, but the review is not in progress yet.',
      };
    case 'in_review':
      return {
        code: 'in_review',
        label: 'In review',
        tone: 'warning',
        detail: 'A reviewer is actively working this case.',
      };
    case 'blocked':
      return {
        code: 'blocked',
        label: 'Blocked',
        tone: 'danger',
        detail: 'This case is waiting on more context or a later decision.',
      };
    case 'resolved':
      return {
        code: 'resolved',
        label: 'Resolved',
        tone: 'success',
        detail: 'The team workflow for this case is complete.',
      };
    case 'unassigned':
    default:
      return {
        code: 'unassigned',
        label: 'Unassigned',
        tone: 'warning',
        detail: 'This case still needs an owner.',
      };
  }
}

function isCaseOverdue(dueAt, status) {
  if (!dueAt || status === 'resolved') {
    return false;
  }
  const dateText = String(dueAt).trim().slice(0, 10);
  if (!dateText) {
    return false;
  }
  const today = new Date().toISOString().slice(0, 10);
  return dateText < today;
}

function formatDueDate(dueAt) {
  if (!dueAt) {
    return 'No due date';
  }
  if (String(dueAt).trim().length === 10) {
    return dueAt;
  }
  return formatDate(dueAt);
}

function workflowStatusForReviewOutcome(outcome, fallback) {
  if (outcome === 'confirmed_fault' || outcome === 'dismissed') {
    return 'resolved';
  }
  if (outcome === 'skipped') {
    return 'blocked';
  }
  return fallback || 'resolved';
}

function deriveReviewState(review, analysis, policyEvaluation, reviewSignature) {
  const latestReview = getLatestReviewEntry({ review });
  if (latestReview) {
    const signatureState = reviewSignature?.detail || (review?.review_signature ? 'Signed review attached.' : 'Unsigned review attached.');
    return {
      code: 'reviewed',
      label: mapReviewOutcome(latestReview.outcome),
      tone: reviewSignature?.code === 'bad-review-signature' ? 'danger' : 'success',
      detail: `Reviewed by ${latestReview.reviewer || review?.reviewed_by || 'reviewer'} on ${formatDate(latestReview.timestamp || review?.reviewed_at)}. ${signatureState}`,
    };
  }

  const pending = Boolean(
    analysis?.human_review?.status === 'pending' ||
    analysis?.review_required ||
    policyEvaluation?.artifact_review_required
  );

  if (pending) {
    return {
      code: 'pending',
      label: 'Pending review',
      tone: 'warning',
      detail: 'A human decision is still needed before this case should be relied on.',
    };
  }

  return {
    code: 'not-required',
    label: 'No review required',
    tone: 'neutral',
    detail: 'No pending review signal was found in this case file.',
  };
}

function deriveRiskState(analysis, policyEvaluation, integrity, reviewState) {
  if (!integrity.ok) {
    return {
      label: 'Critical risk',
      tone: 'danger',
      detail: 'The record was changed after sealing, so the decision should be treated as unsafe.',
    };
  }

  if (analysis?.primary_fault || analysis?.fault_detected) {
    return {
      label: 'High risk',
      tone: 'danger',
      detail: analysis?.why_it_matters || 'EPI detected a primary fault that needs a human decision.',
    };
  }

  if ((analysis?.secondary_flags || []).length || policyEvaluation?.controls_failed) {
    return {
      label: 'Needs attention',
      tone: 'warning',
      detail: 'This case triggered policy or analysis signals that should be reviewed.',
    };
  }

  if (reviewState.code === 'pending') {
    return {
      label: 'Needs review',
      tone: 'warning',
      detail: 'No high fault was found, but the workflow still expects a human decision.',
    };
  }

  return {
    label: 'Low risk',
    tone: 'success',
    detail: 'No active fault or pending review signal was found in this case file.',
  };
}

function buildCaseSnapshot(caseRecord, analysisState, guidance) {
  const hasSteps = Array.isArray(caseRecord.steps) ? caseRecord.steps.length : 0;
  const activityCount = Array.isArray(caseRecord.activity) ? caseRecord.activity.length : 0;
  const evidenceLine = hasSteps
    ? `${hasSteps} recorded step${hasSteps === 1 ? '' : 's'}${activityCount ? ` and ${activityCount} team update${activityCount === 1 ? '' : 's'}` : ''}.`
    : 'Metadata-only case record.';
  const containerLine = caseRecord.containerFormat === 'envelope-v2'
    ? 'Envelope container with sealed payload.'
    : 'Legacy ZIP case container.';

  if (caseRecord.trust.code === 'do-not-use') {
    return {
      title: 'Pause before using this case',
      copy: 'The record failed integrity checks. Confirm the source before relying on the decision or any attached review notes.',
      items: [
        {
          label: 'Decision',
          value: caseRecord.decision.outcome,
          copy: caseRecord.decision.summary,
          tone: 'neutral',
        },
        {
          label: 'Trust',
          value: caseRecord.trust.label,
          copy: caseRecord.trust.detail,
          tone: caseRecord.trust.tone,
        },
        {
          label: 'Risk',
          value: caseRecord.risk.label,
          copy: caseRecord.risk.detail,
          tone: caseRecord.risk.tone,
        },
        {
          label: 'Next step',
          value: guidance.reviewButtonLabel,
          copy: guidance.copy,
          tone: 'danger',
        },
        {
          label: 'Evidence trail',
          value: evidenceLine,
          copy: containerLine,
          tone: 'neutral',
        },
      ],
    };
  }

  if (caseRecord.reviewState.code === 'pending') {
    return {
      title: 'You can understand this case in under a minute',
      copy: 'Start with these five signals, then jump straight to findings, timeline, or the review form when you are ready to decide.',
      items: [
        {
          label: 'Decision',
          value: caseRecord.decision.outcome,
          copy: caseRecord.decision.summary,
          tone: 'neutral',
        },
        {
          label: 'Why it matters',
          value: caseRecord.risk.label,
          copy: caseRecord.risk.detail,
          tone: caseRecord.risk.tone,
        },
        {
          label: 'Human review',
          value: caseRecord.reviewState.label,
          copy: caseRecord.reviewState.detail,
          tone: caseRecord.reviewState.tone,
        },
        {
          label: 'Trust',
          value: caseRecord.trust.label,
          copy: caseRecord.trust.detail,
          tone: caseRecord.trust.tone,
        },
        {
          label: 'Evidence trail',
          value: evidenceLine,
          copy: `${analysisState.label}. ${containerLine}`,
          tone: 'neutral',
        },
      ],
    };
  }

  if (caseRecord.reviewState.code === 'reviewed') {
    return {
      title: 'This decision already has a saved human outcome',
      copy: 'Use the cards below to confirm the trust state, check the final review note, and update the record only if something changed.',
      items: [
        {
          label: 'Decision',
          value: caseRecord.decision.outcome,
          copy: caseRecord.decision.summary,
          tone: 'neutral',
        },
        {
          label: 'Saved review',
          value: caseRecord.reviewState.label,
          copy: caseRecord.reviewState.detail,
          tone: caseRecord.reviewState.tone,
        },
        {
          label: 'Trust',
          value: caseRecord.trust.label,
          copy: caseRecord.trust.detail,
          tone: caseRecord.trust.tone,
        },
        {
          label: 'Automation',
          value: analysisState.label,
          copy: analysisState.detail,
          tone: analysisState.tone,
        },
        {
          label: 'Evidence trail',
          value: evidenceLine,
          copy: containerLine,
          tone: 'neutral',
        },
      ],
    };
  }

  return {
    title: 'Read the essentials first, then decide where to go deeper',
    copy: 'This case is already organized for review. Use the quick jumps if you want to go straight to findings, timeline, or exports.',
    items: [
      {
        label: 'Decision',
        value: caseRecord.decision.outcome,
        copy: caseRecord.decision.summary,
        tone: 'neutral',
      },
      {
        label: 'Trust',
        value: caseRecord.trust.label,
        copy: caseRecord.trust.detail,
        tone: caseRecord.trust.tone,
      },
      {
        label: 'Risk',
        value: caseRecord.risk.label,
        copy: caseRecord.risk.detail,
        tone: caseRecord.risk.tone,
      },
      {
        label: 'Next step',
        value: guidance.reviewButtonLabel,
        copy: guidance.copy,
        tone: caseRecord.reviewState.tone,
      },
      {
        label: 'Evidence trail',
        value: evidenceLine,
        copy: `${analysisState.label}. ${containerLine}`,
        tone: 'neutral',
      },
    ],
  };
}

function buildOverviewPresentation(caseRecord, analysisState) {
  const reason = deriveDecisionReason(caseRecord);
  const confidence = deriveDecisionConfidence(caseRecord);
  const sourceLine = caseRecord.sourceProfile?.kind === 'agt-imported'
    ? `${caseRecord.sourceProfile.sourceSystem} -> EPI import`
    : (caseRecord.sourceProfile?.sourceSystem || 'Native EPI');
  const narrativeParts = [
    `${caseRecord.decision.outcome} is the recorded outcome for this ${caseRecord.workflow.toLowerCase()} case.`,
    reason,
    caseRecord.reviewState.code === 'pending'
      ? 'Human action is still required before the case should be relied on.'
      : 'A human decision is already attached or no extra review was requested.',
    caseRecord.trust.code === 'do-not-use'
      ? 'Do not trust this file until the original source is reverified.'
      : 'The file can be inspected locally and its trust state is shown below.',
  ];

  return {
    narrative: narrativeParts.join(' '),
    signals: [
      {
        label: 'Decision',
        value: caseRecord.decision.outcome,
        copy: caseRecord.decision.summary,
        tone: 'neutral',
      },
      {
        label: 'Reason',
        value: reason,
        copy: caseRecord.risk.detail,
        tone: caseRecord.risk.tone,
      },
      {
        label: 'Confidence',
        value: confidence,
        copy: analysisState.detail,
        tone: analysisState.tone,
      },
      {
        label: 'Review',
        value: caseRecord.reviewState.label,
        copy: caseRecord.reviewState.detail,
        tone: caseRecord.reviewState.tone,
      },
      {
        label: 'Trust',
        value: caseRecord.trust.label,
        copy: caseRecord.trust.detail,
        tone: caseRecord.trust.tone,
      },
      {
        label: 'Source',
        value: sourceLine,
        copy: caseRecord.sourceProfile?.transformationAuditAvailable
          ? 'Transformation audit available.'
          : 'Direct case evidence path.',
        tone: caseRecord.sourceProfile?.kind === 'agt-imported' ? 'warning' : 'neutral',
      },
    ],
    summaryRows: [
      ['Decision', caseRecord.decision.outcome],
      ['Source system', caseRecord.sourceProfile?.sourceSystem || 'EPI'],
      ['Import mode', caseRecord.sourceProfile?.importMode || 'Portable EPI artifact'],
      ['Trust state', caseRecord.trust.label],
      ['Policy result', summarizePolicyResult(caseRecord)],
      ['Review state', caseRecord.reviewState.label],
      ['Risk / severity', caseRecord.risk.label],
      ['Confidence', confidence],
      ['Created', formatDate(caseRecord.manifest.created_at)],
      ['Case file', caseRecord.sourceName],
      ['Workflow', caseRecord.workflow],
      ['Signed by', deriveSignerLabel(caseRecord.manifest)],
    ],
  };
}

function deriveDecisionReason(caseRecord) {
  const directReason =
    caseRecord.analysis?.primary_fault?.plain_english ||
    caseRecord.analysis?.primary_fault?.why_it_matters ||
    caseRecord.analysis?.summary?.headline ||
    (typeof caseRecord.analysis?.summary === 'string' ? caseRecord.analysis.summary : '');
  if (directReason) {
    return directReason;
  }
  if (caseRecord.policyEvaluation?.controls_failed) {
    return `Policy checks reported ${caseRecord.policyEvaluation.controls_failed} failed control${caseRecord.policyEvaluation.controls_failed === 1 ? '' : 's'}.`;
  }
  return 'No explicit policy explanation was attached to this case.';
}

function deriveDecisionConfidence(caseRecord) {
  const lastDecisionStep = [...(caseRecord.steps || [])].reverse().find((step) => step.kind === 'agent.decision');
  const raw = lastDecisionStep?.content?.confidence ?? caseRecord.analysis?.confidence ?? null;
  if (typeof raw === 'number') {
    if (raw >= 0.8) {
      return 'High';
    }
    if (raw >= 0.55) {
      return 'Medium';
    }
    return 'Low';
  }
  const normalized = String(raw || '').trim();
  return normalized ? sentenceCase(normalized) : 'Not recorded';
}

function summarizePolicyResult(caseRecord) {
  if (caseRecord.analysis?.primary_fault?.rule_name) {
    return caseRecord.analysis.primary_fault.rule_name;
  }
  if (caseRecord.policyEvaluation?.controls_failed) {
    return `${caseRecord.policyEvaluation.controls_failed} failed control${caseRecord.policyEvaluation.controls_failed === 1 ? '' : 's'}`;
  }
  if (caseRecord.policyEvaluation?.controls_evaluated) {
    return 'Policy evaluated with no failed controls';
  }
  return 'No policy result attached';
}

function buildEvidenceSummary(caseRecord, analysisState) {
  const items = [
    {
      eyebrow: 'Evidence trail',
      title: `${caseRecord.steps.length} recorded step${caseRecord.steps.length === 1 ? '' : 's'}`,
      copy: caseRecord.steps.length
        ? 'Open the timeline below to trace the sequence from input through decision and review.'
        : 'This artifact does not include a detailed step log, so the case relies on summary metadata and attached files.',
      tone: 'neutral',
    },
    {
      eyebrow: 'Execution context',
      title: caseRecord.environment?.source_system || caseRecord.environment?.runtime || caseRecord.workflow,
      copy: caseRecord.environment
        ? truncate(JSON.stringify(caseRecord.environment), 180)
        : 'No environment block was attached to this case.',
      tone: 'neutral',
    },
    {
      eyebrow: 'Automation',
      title: analysisState.label,
      copy: analysisState.detail,
      tone: analysisState.tone,
    },
  ];

  if (caseRecord.traceability?.primaryStepNumber) {
    items[0].actions = [
      {
        label: `Jump to step ${caseRecord.traceability.primaryStepNumber}`,
        attribute: 'data-trace-step',
        value: String(caseRecord.traceability.primaryStepNumber),
      },
    ];
  }
  return items;
}

function buildPolicyFlow(caseRecord) {
  const items = [];
  const primaryFault = caseRecord.analysis?.primary_fault || null;
  const reviewLinkStep = caseRecord.traceability?.latestReviewStepNumber || caseRecord.traceability?.primaryStepNumber || null;

  items.push({
    eyebrow: 'Policy result',
    title: summarizePolicyResult(caseRecord),
    copy: caseRecord.policyEvaluation
      ? `Controls evaluated: ${caseRecord.policyEvaluation.controls_evaluated || 0}. Failed: ${caseRecord.policyEvaluation.controls_failed || 0}.`
      : 'No separate policy evaluation file was attached to this case.',
    tone: caseRecord.policyEvaluation?.controls_failed ? 'warning' : 'neutral',
  });

  if (primaryFault) {
    items.push({
      eyebrow: 'Why it fired',
      title: primaryFault.rule_name || primaryFault.rule_id || 'Primary policy fault',
      copy: summarizeFault(primaryFault),
      tone: severityToTone(primaryFault.severity),
      actions: primaryFault.step_number
        ? [
          {
            label: `Show evidence step ${primaryFault.step_number}`,
            attribute: 'data-trace-step',
            value: String(primaryFault.step_number),
          },
        ]
        : [],
    });
  }

  items.push({
    eyebrow: 'Decision',
    title: caseRecord.decision.outcome,
    copy: caseRecord.decision.summary,
    tone: 'neutral',
    actions: reviewLinkStep
      ? [
        {
          label: `Trace to step ${reviewLinkStep}`,
          attribute: 'data-trace-step',
          value: String(reviewLinkStep),
        },
      ]
      : [],
  });

  items.push({
    eyebrow: 'Review',
    title: caseRecord.reviewState.label,
    copy: caseRecord.reviewState.detail,
    tone: caseRecord.reviewState.tone,
    actions: [
      {
        label: 'Open review section',
        attribute: 'data-case-section-target',
        value: 'case-review-card',
      },
    ],
  });

  if (caseRecord.sourceProfile?.kind === 'agt-imported') {
    items.unshift({
      eyebrow: 'Source system',
      title: 'AGT imported into EPI',
      copy: `${caseRecord.sourceProfile.trustNarrative}. Transformation audit available for imported evidence.`,
      tone: 'warning',
      actions: [
        {
          label: 'Open mapping',
          attribute: 'data-case-section-target',
          value: 'case-mapping-card',
        },
      ],
    });
  }

  return items;
}

function buildTrustRows(caseRecord, analysisState) {
  return [
    ['Trust state', caseRecord.trust.label],
    ['Integrity', caseRecord.integrity.ok ? `Checked ${caseRecord.integrity.checked} protected file(s)` : `Mismatch in ${caseRecord.integrity.mismatches.join(', ')}`],
    ['Manifest signer', deriveSignerLabel(caseRecord.manifest)],
    ['Review signature', caseRecord.reviewSignature.label],
    ['Container format', caseRecord.containerFormat || 'Unknown'],
    ['Automation state', analysisState.label],
  ];
}

function buildTrustAlerts(caseRecord, analysisState) {
  const items = [
    {
      eyebrow: 'Integrity',
      title: caseRecord.trust.label,
      copy: caseRecord.trust.detail,
      tone: caseRecord.trust.tone,
    },
    {
      eyebrow: 'Automation',
      title: analysisState.label,
      copy: analysisState.detail,
      tone: analysisState.tone,
    },
    {
      eyebrow: 'Review signature',
      title: caseRecord.reviewSignature.label,
      copy: caseRecord.reviewSignature.detail,
      tone: caseRecord.reviewSignature.tone,
    },
  ];

  if (caseRecord.sourceProfile?.kind === 'agt-imported' && (caseRecord.mappingReport?.analysis?.synthesized || caseRecord.analysis?.synthesized)) {
    items.push({
      eyebrow: 'Synthesized analysis',
      title: 'Synthesized',
      copy: caseRecord.mappingReport?.analysis?.warning || caseRecord.analysis?.warning || 'This analysis was synthesized during import from AGT evidence.',
      tone: 'warning',
    });
  }

  return items;
}

function buildTransformationAuditView(caseRecord) {
  const report = caseRecord.mappingReport;
  const visible = Boolean(caseRecord.sourceProfile?.transformationAuditAvailable && report);
  if (!visible) {
    return {
      visible: false,
      summary: [],
      groups: [],
    };
  }

  const summary = [];
  const sourceSummary = report.source_summary || {};
  const stepTransformation = report.step_transformation || {};
  const analysisInfo = report.analysis || {};

  if (sourceSummary.has_audit_logs) {
    summary.push({
      eyebrow: 'Mapping',
      title: 'audit_logs -> steps.jsonl',
      copy: `${sourceSummary.section_counts?.audit_logs || 0} audit log entr${sourceSummary.section_counts?.audit_logs === 1 ? 'y' : 'ies'} were imported into the EPI evidence trail.`,
      tone: 'neutral',
    });
  }
  if (sourceSummary.has_compliance_report) {
    summary.push({
      eyebrow: 'Policy',
      title: 'ComplianceReport -> policy_evaluation.json',
      copy: 'Compliance findings were preserved as EPI policy evaluation output.',
      tone: 'warning',
    });
  }
  if (sourceSummary.has_policy_document) {
    summary.push({
      eyebrow: 'Policy',
      title: 'PolicyDocument -> policy.json',
      copy: 'The imported AGT policy document is available as a native EPI policy file.',
      tone: 'neutral',
    });
  }
  summary.push({
    eyebrow: 'Transformation',
    title: 'Raw payload preservation',
    copy: caseRecord.sourceProfile?.rawSourceAvailable
      ? 'Raw AGT payloads are preserved under attachments.'
      : 'No raw AGT payloads were embedded in this browser session.',
    tone: caseRecord.sourceProfile?.rawSourceAvailable ? 'success' : 'warning',
  });
  summary.push({
    eyebrow: 'Dedupe',
    title: `Duplicates removed: ${stepTransformation.duplicates_removed || 0}`,
    copy: `Strategy: ${sentenceCase(stepTransformation.dedupe_strategy || 'not recorded')}. Ambiguous conflicts: ${stepTransformation.ambiguous_conflicts || 0}.`,
    tone: (stepTransformation.ambiguous_conflicts || 0) > 0 ? 'warning' : 'neutral',
  });
  if (analysisInfo.synthesized) {
    summary.push({
      eyebrow: 'Analysis',
      title: 'Synthesized',
      copy: analysisInfo.warning || 'Analysis was synthesized from AGT evidence during import.',
      tone: 'warning',
    });
  }

  const fieldHandling = report.field_handling || {};
  const groups = [
    ['exact', 'Exact'],
    ['translated', 'Translated'],
    ['derived', 'Derived'],
    ['synthesized', 'Synthesized'],
    ['preserved_raw', 'Preserved raw'],
    ['dropped', 'Dropped'],
    ['unclassified', 'Unclassified'],
  ].map(([key, label]) => ({
    key,
    label,
    items: Array.isArray(fieldHandling[key]) ? fieldHandling[key] : [],
  })).filter((group) => group.items.length > 0);

  return { visible, summary, groups };
}

function buildAttachmentView(caseRecord) {
  const groups = Array.isArray(caseRecord.attachmentGroups) ? caseRecord.attachmentGroups : [];
  return {
    visible: groups.some((group) => Array.isArray(group.items) && group.items.length > 0),
    groups,
  };
}

function renderCaseSignalItem(item) {
  return `
    <article class="case-snapshot-item tone-panel-${escapeHtml(item.tone || 'neutral')}">
      <span class="case-snapshot-label">${escapeHtml(item.label)}</span>
      <strong class="case-snapshot-value">${escapeHtml(item.value)}</strong>
      <p class="case-snapshot-copy">${escapeHtml(item.copy)}</p>
    </article>
  `;
}

function renderTransformationAudit(caseRecord, mappingView) {
  if (!mappingView.visible) {
    elements.caseMappingSummary.innerHTML = `
      <article class="stack-item tone-panel-neutral">
        <p class="stack-copy">No transformation audit was attached to this case. Native EPI recordings stay readable without imported-source provenance.</p>
      </article>
    `;
    elements.caseMappingGroups.innerHTML = '';
    return;
  }

  elements.caseMappingSummary.innerHTML = mappingView.summary.map(renderStackItem).join('');
  elements.caseMappingGroups.innerHTML = mappingView.groups.map((group) => {
    const items = group.items.slice(0, 10).map((item) => renderMappingRow(item, caseRecord)).join('');
    return `
      <section class="mapping-group">
        <div class="mapping-group-header">
          <div>
            <p class="card-label">${escapeHtml(group.label)}</p>
            <h4>${escapeHtml(group.items.length)} mapped field${group.items.length === 1 ? '' : 's'}</h4>
          </div>
          ${renderBadge(group.label, group.key === 'dropped' || group.key === 'unclassified' ? 'warning' : group.key === 'synthesized' ? 'warning' : 'neutral')}
        </div>
        ${items}
      </section>
    `;
  }).join('');
}

function renderMappingRow(item, caseRecord) {
  const mappedTo = item.mapped_to || 'Not recorded';
  const actions = [];
  if (String(mappedTo).startsWith('artifacts/')) {
    actions.push({
      label: 'Open raw source',
      attribute: 'data-attachment-focus',
      value: mappedTo,
    });
  } else if (caseRecord.traceability?.primaryStepNumber) {
    actions.push({
      label: `Jump to step ${caseRecord.traceability.primaryStepNumber}`,
      attribute: 'data-trace-step',
      value: String(caseRecord.traceability.primaryStepNumber),
    });
  }
  return `
    <article class="mapping-row">
      <div class="mapping-pair">
        <strong>${escapeHtml(item.section || 'Source section')} -> ${escapeHtml(item.field || 'field')}</strong>
        <span class="mapping-arrow">${escapeHtml(mappedTo)}</span>
      </div>
      <p class="stack-copy">${escapeHtml(item.notes || `Count: ${item.count || 0}`)}</p>
      ${renderInlineActions(actions)}
    </article>
  `;
}

function renderAttachmentGroups(caseRecord, attachmentView) {
  if (!attachmentView.visible) {
    elements.caseAttachments.innerHTML = `
      <article class="attachment-group tone-panel-neutral">
        <p class="stack-copy">No extra attachments are available in this browser session.</p>
      </article>
    `;
    return;
  }

  elements.caseAttachments.innerHTML = attachmentView.groups.map((group) => {
    const items = group.items.map((item) => {
      const isHighlighted = state.caseHighlights.attachmentName === item.name;
      const actions = [];
      if (item.previewable) {
        actions.push({
          label: 'Preview',
          attribute: 'data-attachment-preview',
          value: item.name,
        });
      }
      actions.push({
        label: 'Download',
        attribute: 'data-attachment-download',
        value: item.name,
      });
      return `
        <article class="attachment-item ${isHighlighted ? 'is-highlighted' : ''}">
          <strong>${escapeHtml(item.name)}</strong>
          <p class="stack-copy">${escapeHtml(item.previewable ? 'Previewable locally as text or JSON.' : 'Binary or structured attachment. Download to inspect further.')}</p>
          ${renderInlineActions(actions)}
        </article>
      `;
    }).join('');

    return `
      <section class="attachment-group">
        <div class="attachment-group-header">
          <div>
            <p class="card-label">${escapeHtml(group.label)}</p>
            <h4>${escapeHtml(group.items.length)} attachment${group.items.length === 1 ? '' : 's'}</h4>
          </div>
        </div>
        ${items || '<p class="helper-copy">No attachments in this group.</p>'}
      </section>
    `;
  }).join('');
}

function renderAttachmentPreview(caseRecord) {
  const preview = state.attachmentPreviewCache[caseRecord.id] || null;
  if (!preview) {
    elements.attachmentPreviewTitle.textContent = 'No attachment selected';
    elements.attachmentPreviewMeta.textContent = 'Select a JSON or text attachment to preview it locally, or download any attachment without leaving the browser.';
    elements.attachmentPreviewBody.textContent = '';
    return;
  }
  elements.attachmentPreviewTitle.textContent = preview.name;
  elements.attachmentPreviewMeta.textContent = preview.meta;
  elements.attachmentPreviewBody.textContent = preview.content;
}

function setCaseSectionVisible(sectionId, visible) {
  const panel = document.getElementById(sectionId);
  if (panel) {
    panel.hidden = !visible;
  }
  const navButton = elements.caseSectionNav?.querySelector(`[data-case-section-target="${sectionId}"]`);
  if (navButton) {
    navButton.hidden = !visible;
  }
  if (!visible && state.activeCaseSection === sectionId) {
    state.activeCaseSection = 'audit-first-card';
  }
}

function scrollToActiveCaseSectionIfNeeded() {
  document.querySelectorAll('.case-section-button').forEach((button) => {
    if (button.hidden) {
      return;
    }
    button.classList.toggle('active', button.dataset.caseSectionTarget === state.activeCaseSection);
  });
}

function highlightCaseStep(stepNumber) {
  if (!stepNumber) {
    return;
  }
  state.caseHighlights.stepNumber = stepNumber;
  state.activeCaseSection = 'case-evidence-card';
  renderCaseView();
  scrollToCaseSection('case-evidence-card');
}

function focusCaseAttachment(name) {
  if (!name) {
    return;
  }
  state.caseHighlights.attachmentName = name;
  state.activeCaseSection = 'case-attachments-card';
  renderCaseView();
  scrollToCaseSection('case-attachments-card');
}

async function previewCaseAttachment(name) {
  const caseRecord = getSelectedCase();
  if (!caseRecord || !name) {
    return;
  }
  const bytes = await readCaseAttachmentBytes(caseRecord, name);
  const previewText = decodePreviewText(bytes);
  state.attachmentPreviewCache[caseRecord.id] = {
    name,
    meta: `${name} | ${previewText.truncated ? 'Preview truncated for local reading.' : 'Full local preview.'}`,
    content: previewText.content,
  };
  focusCaseAttachment(name);
}

async function downloadCaseAttachment(name) {
  const caseRecord = getSelectedCase();
  if (!caseRecord || !name) {
    return;
  }
  const bytes = await readCaseAttachmentBytes(caseRecord, name);
  downloadBlob(name.split('/').pop() || name, bytes, guessMimeType(name));
}

async function readCaseAttachmentBytes(caseRecord, name) {
  if (caseRecord.embeddedFiles?.[name]) {
    return caseRecord.embeddedFiles[name].slice(0);
  }
  if (caseRecord.archiveBytes) {
    const zip = await JSZip.loadAsync(caseRecord.archiveBytes.slice(0));
    const entry = zip.file(name);
    if (!entry) {
      throw new Error(`${name} is not available in this browser session.`);
    }
    return await entry.async('uint8array');
  }
  throw new Error('This browser session does not include that attachment.');
}

function decodePreviewText(bytes) {
  try {
    const text = new TextDecoder().decode(bytes);
    const truncated = text.length > 4000;
    return {
      content: truncated ? `${text.slice(0, 4000)}\n\n...` : text,
      truncated,
    };
  } catch (_error) {
    return {
      content: 'Preview unavailable for this attachment type.',
      truncated: false,
    };
  }
}

function guessMimeType(name) {
  if (/\.json$/i.test(name)) {
    return 'application/json';
  }
  if (/\.jsonl$/i.test(name) || /\.log$/i.test(name) || /\.txt$/i.test(name) || /\.md$/i.test(name)) {
    return 'text/plain;charset=utf-8';
  }
  return 'application/octet-stream';
}

function buildGuidanceItems(tone, items) {
  const sequenceLabels = ['Start here', 'Then', 'Finish with'];
  return items.map((item, index) => ({
    ...item,
    tone: item.tone || tone,
    eyebrow: item.eyebrow || sequenceLabels[index] || 'Next',
  }));
}

function severityToTone(value) {
  const text = String(value || '').trim().toLowerCase();
  if (['critical', 'high'].includes(text)) {
    return 'danger';
  }
  if (text === 'medium') {
    return 'warning';
  }
  return 'neutral';
}

function buildFaultBadges(fault) {
  const badges = [];
  if (fault?.severity) {
    badges.push({
      label: sentenceCase(fault.severity),
      tone: severityToTone(fault.severity),
    });
  }
  if (fault?.rule_id) {
    badges.push({
      label: `Rule ${fault.rule_id}`,
      tone: 'neutral',
    });
  }
  if (fault?.step_number != null) {
    badges.push({
      label: `Step ${fault.step_number}`,
      tone: 'neutral',
    });
  }
  return badges;
}

function buildRuleBadges(rule) {
  const badges = [];
  if (rule?.mode) {
    badges.push({
      label: sentenceCase(rule.mode),
      tone: rule.mode === 'block' ? 'danger' : rule.mode === 'require_approval' ? 'warning' : 'neutral',
    });
  }
  if (rule?.applies_at) {
    badges.push({
      label: sentenceCase(rule.applies_at),
      tone: 'neutral',
    });
  }
  return badges;
}

function buildFindings(caseRecord) {
  const findings = [];

  if (caseRecord.analysis?.primary_fault) {
    findings.push({
      eyebrow: 'Highest priority',
      title: 'Primary fault',
      copy: summarizeFault(caseRecord.analysis.primary_fault),
      meta: 'Read this before making the human decision.',
      tone: 'danger',
      badges: buildFaultBadges(caseRecord.analysis.primary_fault),
      actions: caseRecord.analysis.primary_fault.step_number
        ? [
          {
            label: `Show step ${caseRecord.analysis.primary_fault.step_number}`,
            attribute: 'data-trace-step',
            value: String(caseRecord.analysis.primary_fault.step_number),
          },
        ]
        : [],
    });
  }

  (caseRecord.analysis?.secondary_flags || []).forEach((flag, index) => {
    findings.push({
      eyebrow: 'Supporting signal',
      title: `Secondary flag ${index + 1}`,
      copy: summarizeFault(flag),
      meta: 'Additional context that may change the review outcome.',
      tone: 'warning',
      badges: buildFaultBadges(flag),
      actions: flag.step_number
        ? [
          {
            label: `Show step ${flag.step_number}`,
            attribute: 'data-trace-step',
            value: String(flag.step_number),
          },
        ]
        : [],
    });
  });

  if (caseRecord.policyEvaluation) {
    const evaluated = caseRecord.policyEvaluation.controls_evaluated || 0;
    const failed = caseRecord.policyEvaluation.controls_failed || 0;
    findings.push({
      eyebrow: 'Policy evaluation',
      title: 'Rules evaluation',
      copy: `Rules checked: ${evaluated}. Rules failed: ${failed}.`,
      meta: `${evaluated} checked / ${failed} failed`,
      tone: failed ? 'warning' : 'success',
      badges: [
        {
          label: failed ? 'Needs follow-up' : 'No rule failures',
          tone: failed ? 'warning' : 'success',
        },
      ],
    });
  }

  const rules = Array.isArray(caseRecord.policy?.rules) ? caseRecord.policy.rules : [];
  rules.slice(0, 4).forEach((rule) => {
    findings.push({
      eyebrow: 'Active rule',
      title: rule.name || rule.id || 'Rule',
      copy: rule.description || `Mode: ${rule.mode || 'review'}. Applies at: ${rule.applies_at || 'decision'}.`,
      meta: rule.id ? `Rule ID: ${rule.id}` : null,
      tone: 'neutral',
      badges: buildRuleBadges(rule),
    });
  });

  if (caseRecord.review?.reviews?.length) {
    const latest = getLatestReviewEntry(caseRecord);
    findings.push({
      eyebrow: 'Latest review',
      title: 'Latest review note',
      copy: latest?.notes || 'Review notes are attached to this case.',
      meta: latest?.timestamp ? `Saved ${formatDate(latest.timestamp)}` : 'Review attached to this case.',
      tone: 'success',
      actions: latest?.fault_step
        ? [
          {
            label: `Trace review to step ${latest.fault_step}`,
            attribute: 'data-trace-step',
            value: String(latest.fault_step),
          },
        ]
        : [],
    });
  }

  if (!findings.length) {
    findings.push({
      eyebrow: 'Evidence note',
      title: 'No explicit findings',
      copy: 'This case file does not include analysis details or rule findings, so the case view focuses on trust, decision context, and timeline.',
      tone: 'neutral',
    });
  }

  return findings;
}

function buildCaseGuidance(caseRecord) {
  if (caseRecord.trust.code === 'do-not-use') {
    return {
      title: 'Stop here and verify the original case',
      copy: 'This record failed integrity checks, so it should not be used for decision-making until the source is verified.',
      reviewButtonLabel: 'Add review note',
      items: buildGuidanceItems('danger', [
        {
          title: 'Treat this case as unsafe',
          copy: 'Do not rely on the decision record until the original file is checked and reopened from a trusted source.',
        },
        {
          title: 'Capture what went wrong',
          copy: 'Use the review form to note who found the issue and what should happen next.',
        },
        {
          title: 'Share a report if needed',
          copy: 'Open the decision record exports if you need to hand this case to another team or keep an incident record.',
        },
      ]),
    };
  }

  if (caseRecord.workflowState.code === 'unassigned') {
    return {
      title: 'Assign this case before work starts',
      copy: 'This case still needs an owner. Assign it, set a due date if needed, and then start the review.',
      reviewButtonLabel: 'Start review',
      items: buildGuidanceItems('warning', [
        {
          title: 'Choose the reviewer',
          copy: 'Use the Team Workflow card to assign ownership so the case is not lost in the queue.',
        },
        {
          title: 'Set the review in motion',
          copy: 'Starting the review moves the workflow to In review and makes the case easier to track.',
        },
        {
          title: 'Capture context in comments',
          copy: 'Add a quick note if another team needs to know why this case was escalated.',
        },
      ]),
    };
  }

  if (caseRecord.reviewState.code === 'pending') {
    return {
      title: 'A human decision is still needed',
      copy: 'This case has been stopped for review. Read the finding, record the outcome, and save the reviewed case when you are done.',
      reviewButtonLabel: 'Start review',
      items: buildGuidanceItems('warning', [
        {
          title: 'Read the risk and findings first',
          copy: 'Check the finding summary below to understand why this case was flagged before you make a decision.',
        },
        {
          title: 'Record the human outcome',
          copy: 'Use the review workspace to confirm the issue, dismiss it, or decide later with notes.',
        },
        {
          title: 'Save a defensible record',
          copy: 'Download the reviewed case or the decision summary so the final decision has a clear audit trail.',
        },
      ]),
    };
  }

  if (caseRecord.reviewState.code === 'reviewed') {
    return {
      title: 'This case already has a human review',
      copy: 'You can update the review, check the rules that shaped the case, or export the decision record for sharing.',
      reviewButtonLabel: 'Update review',
      items: buildGuidanceItems('success', [
        {
          title: 'Confirm the final record',
          copy: 'Check the latest review note and signature status to make sure the saved outcome still looks right.',
        },
        {
          title: 'Tighten rules if this repeats',
          copy: 'Open the Rules view if similar cases should be caught earlier or routed differently.',
        },
        {
          title: 'Share the result',
          copy: 'Open the decision record exports or download the reviewed case if someone else needs the final record.',
        },
      ]),
    };
  }

  return {
    title: 'This case looks ready to understand and share',
    copy: 'No urgent review signal is active right now, but you can still inspect the case, tighten the rules, or export the decision record.',
    reviewButtonLabel: 'Add note',
    items: buildGuidanceItems('neutral', [
      {
        title: 'Check the summary and timeline',
        copy: 'Review the decision summary and timeline to confirm the case matches what you expected.',
      },
      {
        title: 'Open the rules if you want stricter controls',
        copy: 'The Rules view lets you tighten approvals, thresholds, and required checks for future decisions.',
      },
      {
        title: 'Keep or share the record',
        copy: 'Open the decision record exports if you want a portable summary for audit, operations, or management.',
      },
    ]),
  };
}

function buildTimeline(caseRecord) {
  const visibleSteps = caseRecord.steps.filter((step) => !['session.start', 'session.end'].includes(step.kind));
  const stepItems = visibleSteps.slice(0, 24).map((step, index) => ({
    title: stepLabel(step.kind),
    time: formatDate(step.timestamp),
    sortTime: step.timestamp,
    copy: summarizeStep(step, index),
    kicker: `Step ${index + 1}`,
    tone: timelineToneForKind(step.kind),
    badges: buildTimelineBadges(step.kind, step.content || {}),
    highlighted: state.caseHighlights.stepNumber === index + 1,
    actions: buildTimelineActions(step, index + 1, caseRecord),
  }));
  const activityItems = (Array.isArray(caseRecord.activity) ? caseRecord.activity : []).map((item) => ({
    title: item.title || sentenceCase(String(item.kind || 'activity').replace(/_/g, ' ')),
    time: formatDate(item.created_at),
    sortTime: item.created_at,
    copy: item.copy || 'Team workflow updated.',
    kicker: 'Workflow update',
    tone: 'neutral',
    badges: [
      {
        label: sentenceCase(String(item.kind || 'activity').replace(/_/g, ' ')),
        tone: 'neutral',
      },
    ],
  }));

  const combined = [...stepItems, ...activityItems].sort((left, right) => compareIsoDates(left.sortTime, right.sortTime));
  if (!combined.length) {
    return [
      {
        title: 'No detailed step timeline',
        time: formatDate(caseRecord.manifest.created_at),
        sortTime: caseRecord.manifest.created_at,
        copy: 'This case file contains metadata and supporting files, but no detailed recorded steps.',
        kicker: 'Timeline note',
        tone: 'neutral',
        badges: [],
      },
    ];
  }
  return combined.map(({ sortTime, ...item }) => item);
}

function buildTimelineActions(step, stepNumber, caseRecord) {
  const actions = [];
  const ruleId = step.content?.matched_rule || step.content?.rule_id || null;
  if (ruleId) {
    actions.push({
      label: `Rule ${ruleId}`,
      attribute: 'data-case-section-target',
      value: 'case-policy-card',
    });
  }
  if (caseRecord.sourceProfile?.kind === 'agt-imported' && step.content?.source_ref?.section) {
    const attachmentName = `artifacts/agt/${step.content.source_ref.section}.json`;
    if (caseRecord.traceability?.sourceAttachmentNames?.includes(attachmentName)) {
      actions.push({
        label: 'Open raw source',
        attribute: 'data-attachment-focus',
        value: attachmentName,
      });
    }
  }
  return actions;
}

function timelineToneForKind(kind) {
  const text = String(kind || '').trim().toLowerCase();
  if (text.includes('error') || text === 'agent.run.error') {
    return 'danger';
  }
  if (text === 'agent.approval.request' || text === 'policy.check') {
    return 'warning';
  }
  if (['agent.approval.response', 'agent.decision', 'agent.run.end'].includes(text)) {
    return 'success';
  }
  return 'neutral';
}

function buildTimelineBadges(kind, content) {
  const badges = [
    {
      label: sentenceCase(String(kind || '').replace(/\./g, ' ')),
      tone: 'neutral',
    },
  ];

  if (content?.tool) {
    badges.push({
      label: `Tool: ${content.tool}`,
      tone: 'neutral',
    });
  } else if (content?.model) {
    badges.push({
      label: `Model: ${content.model}`,
      tone: 'neutral',
    });
  } else if (content?.reviewer) {
    badges.push({
      label: `Reviewer: ${content.reviewer}`,
      tone: 'neutral',
    });
  }

  if (typeof content?.approved === 'boolean') {
    badges.push({
      label: content.approved ? 'Approved' : 'Rejected',
      tone: content.approved ? 'success' : 'danger',
    });
  }

  return badges.slice(0, 3);
}

function buildReviewDraft(caseRecord) {
  const reviewer = elements.reviewerName.value.trim() || 'reviewer';
  const outcome = elements.reviewOutcome.value;
  const notes = elements.reviewNotes.value.trim();
  const focusFault = caseRecord.analysis?.primary_fault || caseRecord.analysis?.secondary_flags?.[0] || {};
  const timestamp = new Date().toISOString();

  return {
    review_version: '1.0.0',
    reviewed_by: reviewer,
    reviewed_at: timestamp,
    reviews: [
      {
        fault_step: focusFault.step_number || null,
        rule_id: focusFault.rule_id || null,
        fault_type: focusFault.fault_type || null,
        outcome,
        notes,
        reviewer,
        timestamp,
      },
    ],
    review_signature: null,
  };
}

function buildReviewSigningPayload(reviewRecord) {
  return canonicalJson({
    review_version: reviewRecord.review_version,
    reviewed_by: reviewRecord.reviewed_by,
    reviewed_at: reviewRecord.reviewed_at,
    reviews: reviewRecord.reviews,
  });
}

function canonicalJson(value) {
  if (value === null) {
    return 'null';
  }
  if (typeof value === 'string') {
    return JSON.stringify(value);
  }
  if (typeof value !== 'object') {
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) {
    return '[' + value.map((item) => canonicalJson(item)).join(',') + ']';
  }

  const keys = Object.keys(value).sort();
  return '{' + keys.map((key) => `${JSON.stringify(key)}:${canonicalJson(value[key])}`).join(',') + '}';
}

function parsePkcs8PrivateKey(signingKeyText) {
  if (/BEGIN ENCRYPTED PRIVATE KEY/.test(signingKeyText)) {
    throw new Error('Encrypted private keys are not supported in the browser. Use an unencrypted EPI .key file.');
  }

  const pemMatch = signingKeyText.match(/-----BEGIN PRIVATE KEY-----([\s\S]+?)-----END PRIVATE KEY-----/);
  if (pemMatch) {
    return base64ToUint8Array(pemMatch[1]);
  }

  if (/^[A-Za-z0-9+/=\s]+$/.test(signingKeyText)) {
    return base64ToUint8Array(signingKeyText);
  }

  throw new Error('Paste an unencrypted Ed25519 PKCS#8 private key in PEM format.');
}

function extractEd25519SeedFromPkcs8(pkcs8Bytes) {
  for (let index = pkcs8Bytes.length - 34; index >= 0; index -= 1) {
    if (pkcs8Bytes[index] === 0x04 && pkcs8Bytes[index + 1] === 0x20) {
      return pkcs8Bytes.slice(index + 2, index + 34);
    }
  }

  throw new Error('Could not extract the Ed25519 private key seed from this PKCS#8 key.');
}

const CRC32_TABLE = (() => {
  const table = new Uint32Array(256);
  for (let index = 0; index < 256; index += 1) {
    let value = index;
    for (let bit = 0; bit < 8; bit += 1) {
      value = (value & 1) ? (0xedb88320 ^ (value >>> 1)) : (value >>> 1);
    }
    table[index] = value >>> 0;
  }
  return table;
})();

function canBuildReviewedArtifact(caseRecord) {
  return Boolean(
    caseRecord?.backendCase ||
    caseRecord?.archiveBytes ||
    (caseRecord?.embeddedFiles && Object.keys(caseRecord.embeddedFiles).length)
  );
}

const EPI_ENVELOPE_MAGIC_BYTES = new Uint8Array([0x45, 0x50, 0x49, 0x31]);
const EPI_ENVELOPE_VERSION = 1;
const EPI_PAYLOAD_FORMAT_ZIP_V1 = 0x01;
const EPI_ENVELOPE_HEADER_SIZE = 64;

function textToBytes(value) {
  return new TextEncoder().encode(String(value));
}

function htmlSafeJson(value, indent) {
  return JSON.stringify(value, null, indent)
    .replace(/&/g, '\\u0026')
    .replace(/</g, '\\u003c')
    .replace(/>/g, '\\u003e')
    .replace(/\u2028/g, '\\u2028')
    .replace(/\u2029/g, '\\u2029');
}

function uint8ArrayToBase64(bytes) {
  let binary = '';
  const chunkSize = 0x8000;
  for (let index = 0; index < bytes.length; index += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(index, index + chunkSize));
  }
  return btoa(binary);
}

function bytesEqual(left, right) {
  if (!left || !right || left.length !== right.length) {
    return false;
  }
  for (let index = 0; index < left.length; index += 1) {
    if (left[index] !== right[index]) {
      return false;
    }
  }
  return true;
}

function readUint64LE(view, offset) {
  const low = view.getUint32(offset, true);
  const high = view.getUint32(offset + 4, true);
  return (high * 0x100000000) + low;
}

function writeUint64LE(view, offset, value) {
  if (!Number.isSafeInteger(value) || value < 0) {
    throw new Error('EPI payload length must be a non-negative safe integer.');
  }
  const low = value >>> 0;
  const high = Math.floor(value / 0x100000000) >>> 0;
  view.setUint32(offset, low, true);
  view.setUint32(offset + 4, high, true);
}

async function decodeEpiContainerBytes(inputBytes) {
  const bytes = inputBytes instanceof Uint8Array ? inputBytes : new Uint8Array(inputBytes || []);
  if (bytes.length < 4 || !bytesEqual(bytes.subarray(0, 4), EPI_ENVELOPE_MAGIC_BYTES)) {
    return {
      containerFormat: 'legacy-zip',
      payloadBytes: bytes.slice(0),
    };
  }
  if (bytes.length < EPI_ENVELOPE_HEADER_SIZE) {
    throw new Error('EPI envelope is too small to contain a valid header.');
  }

  const headerView = new DataView(bytes.buffer, bytes.byteOffset, EPI_ENVELOPE_HEADER_SIZE);
  const version = headerView.getUint8(4);
  const payloadFormat = headerView.getUint8(5);
  const reservedFlags = headerView.getUint16(6, true);
  const payloadLength = readUint64LE(headerView, 8);
  const payloadHash = bytes.slice(16, 48);
  const reservedTail = bytes.slice(48, 64);

  if (version !== EPI_ENVELOPE_VERSION) {
    throw new Error(`Unsupported EPI envelope version: ${version}`);
  }
  if (payloadFormat !== EPI_PAYLOAD_FORMAT_ZIP_V1) {
    throw new Error(`Unsupported EPI payload format: ${payloadFormat}`);
  }
  if (reservedFlags !== 0) {
    throw new Error('Invalid EPI envelope header: reserved flags must be zero.');
  }
  if (!reservedTail.every((value) => value === 0)) {
    throw new Error('Invalid EPI envelope header: reserved bytes must be zero.');
  }
  if (!Number.isSafeInteger(payloadLength) || payloadLength <= 0) {
    throw new Error('Invalid EPI envelope payload length.');
  }
  if ((EPI_ENVELOPE_HEADER_SIZE + payloadLength) !== bytes.length) {
    throw new Error('Invalid EPI envelope payload length.');
  }

  const payloadBytes = bytes.slice(EPI_ENVELOPE_HEADER_SIZE);
  const actualHash = await sha256Bytes(payloadBytes);
  if (!bytesEqual(actualHash, payloadHash)) {
    throw new Error('EPI envelope payload hash mismatch.');
  }

  return {
    containerFormat: 'envelope-v2',
    payloadBytes,
  };
}

async function wrapZipPayloadAsEnvelope(payloadBytes) {
  const payload = payloadBytes instanceof Uint8Array ? payloadBytes : new Uint8Array(payloadBytes || []);
  const header = new Uint8Array(EPI_ENVELOPE_HEADER_SIZE);
  header.set(EPI_ENVELOPE_MAGIC_BYTES, 0);
  const headerView = new DataView(header.buffer);
  headerView.setUint8(4, EPI_ENVELOPE_VERSION);
  headerView.setUint8(5, EPI_PAYLOAD_FORMAT_ZIP_V1);
  headerView.setUint16(6, 0, true);
  writeUint64LE(headerView, 8, payload.length);
  header.set(await sha256Bytes(payload), 16);
  return concatUint8Arrays([header, payload]);
}

function createZipArchive(entries) {
  const now = toDosDateTime(new Date());
  const localParts = [];
  const centralParts = [];
  let offset = 0;
  let centralSize = 0;

  entries.forEach((entry) => {
    const nameBytes = textToBytes(entry.name);
    const data = entry.data instanceof Uint8Array ? entry.data : new Uint8Array(entry.data || []);
    const crc = crc32(data);

    const localHeader = new Uint8Array(30 + nameBytes.length);
    const localView = new DataView(localHeader.buffer);
    localView.setUint32(0, 0x04034b50, true);
    localView.setUint16(4, 20, true);
    localView.setUint16(6, 0, true);
    localView.setUint16(8, 0, true);
    localView.setUint16(10, now.time, true);
    localView.setUint16(12, now.date, true);
    localView.setUint32(14, crc, true);
    localView.setUint32(18, data.length, true);
    localView.setUint32(22, data.length, true);
    localView.setUint16(26, nameBytes.length, true);
    localView.setUint16(28, 0, true);
    localHeader.set(nameBytes, 30);
    localParts.push(localHeader, data);

    const centralHeader = new Uint8Array(46 + nameBytes.length);
    const centralView = new DataView(centralHeader.buffer);
    centralView.setUint32(0, 0x02014b50, true);
    centralView.setUint16(4, 20, true);
    centralView.setUint16(6, 20, true);
    centralView.setUint16(8, 0, true);
    centralView.setUint16(10, 0, true);
    centralView.setUint16(12, now.time, true);
    centralView.setUint16(14, now.date, true);
    centralView.setUint32(16, crc, true);
    centralView.setUint32(20, data.length, true);
    centralView.setUint32(24, data.length, true);
    centralView.setUint16(28, nameBytes.length, true);
    centralView.setUint16(30, 0, true);
    centralView.setUint16(32, 0, true);
    centralView.setUint16(34, 0, true);
    centralView.setUint16(36, 0, true);
    centralView.setUint32(38, 0, true);
    centralView.setUint32(42, offset, true);
    centralHeader.set(nameBytes, 46);
    centralParts.push(centralHeader);

    offset += localHeader.length + data.length;
    centralSize += centralHeader.length;
  });

  const end = new Uint8Array(22);
  const endView = new DataView(end.buffer);
  endView.setUint32(0, 0x06054b50, true);
  endView.setUint16(4, 0, true);
  endView.setUint16(6, 0, true);
  endView.setUint16(8, entries.length, true);
  endView.setUint16(10, entries.length, true);
  endView.setUint32(12, centralSize, true);
  endView.setUint32(16, offset, true);
  endView.setUint16(20, 0, true);

  return concatUint8Arrays([...localParts, ...centralParts, end]);
}

function concatUint8Arrays(parts) {
  const totalLength = parts.reduce((sum, part) => sum + part.length, 0);
  const merged = new Uint8Array(totalLength);
  let offset = 0;
  parts.forEach((part) => {
    merged.set(part, offset);
    offset += part.length;
  });
  return merged;
}

function crc32(bytes) {
  let crc = 0xffffffff;
  for (let index = 0; index < bytes.length; index += 1) {
    crc = CRC32_TABLE[(crc ^ bytes[index]) & 0xff] ^ (crc >>> 8);
  }
  return (crc ^ 0xffffffff) >>> 0;
}

function toDosDateTime(date) {
  const year = Math.max(date.getFullYear(), 1980);
  return {
    date: ((year - 1980) << 9) | ((date.getMonth() + 1) << 5) | date.getDate(),
    time: (date.getHours() << 11) | (date.getMinutes() << 5) | Math.floor(date.getSeconds() / 2),
  };
}

function base64ToUint8Array(value) {
  const cleaned = value.replace(/-----[^-]+-----/g, '').replace(/\s+/g, '');
  try {
    const binary = atob(cleaned);
    const bytes = new Uint8Array(binary.length);
    for (let index = 0; index < binary.length; index += 1) {
      bytes[index] = binary.charCodeAt(index);
    }
    return bytes;
  } catch (_error) {
    throw new Error('The signing key could not be decoded. Make sure the full PEM key was pasted.');
  }
}

function decodeSignatureBytes(signatureValue) {
  try {
    return noble.etc.hexToBytes(signatureValue);
  } catch (_hexError) {
    return base64ToUint8Array(signatureValue);
  }
}

function buildCaseSummary(caseRecord) {
  const analysisState = deriveAnalysisState(caseRecord.manifest, caseRecord.analysis);
  return [
    'EPI DECISION SUMMARY',
    '====================',
    `Case: ${caseRecord.decision.title}`,
    `Workflow: ${caseRecord.workflow}`,
    `Review status: ${caseRecord.workflowState.label}`,
    `Assignee: ${caseRecord.assignee || 'Unassigned'}`,
    `Due date: ${formatDueDate(caseRecord.dueAt)}`,
    `Created: ${formatDate(caseRecord.manifest.created_at)}`,
    `Record integrity: ${caseRecord.trust.label}`,
    `Automated policy check: ${analysisState.label}`,
    `Risk: ${caseRecord.risk.label}`,
    `Human review: ${caseRecord.reviewState.label}`,
    `Signer: ${deriveSignerLabel(caseRecord.manifest)}`,
    '',
    'CASE OVERVIEW',
    caseRecord.decision.summary,
    '',
    'KEY DECISION STEPS',
    ...buildTimeline(caseRecord).map((item, index) => `${index + 1}. ${item.title} (${item.time}) - ${item.copy}`),
    '',
    'FINDINGS AND RULES',
    ...buildFindings(caseRecord).map((item) => `- ${item.title}: ${item.copy}`),
  ].join('\n');
}

function resolveReportCases(scope) {
  if (scope === 'selected') {
    const selected = getSelectedCase();
    return selected ? [selected] : [];
  }
  if (scope === 'filtered') {
    return getFilteredCases();
  }
  return [...state.cases];
}

function getFilteredCases() {
  return state.cases.filter((caseRecord) => {
    const haystack = [
      caseRecord.decision.title,
      caseRecord.decision.summary,
      caseRecord.workflow,
      caseRecord.sourceName,
      caseRecord.assignee || '',
      caseRecord.manifest.notes || '',
    ].join(' ').toLowerCase();

    const matchesSearch = !state.filters.search || haystack.includes(state.filters.search);
    const matchesStatus = state.filters.status === 'all' || caseRecord.status === state.filters.status;
    const matchesQuickView =
      state.filters.quickView === 'all' ||
      (state.filters.quickView === 'mine' && Boolean(state.reviewerIdentity) && caseRecord.assignee === state.reviewerIdentity) ||
      (state.filters.quickView === 'overdue' && caseRecord.isOverdue);
    const matchesTrust = state.filters.trust === 'all' || caseRecord.trust.code === state.filters.trust;
    const matchesReview =
      state.filters.review === 'all' ||
      (state.filters.review === 'reviewed'
        ? caseRecord.reviewState.code === 'reviewed'
        : caseRecord.reviewState.code === state.filters.review);
    const matchesWorkflow = state.filters.workflow === 'all' || caseRecord.workflow === state.filters.workflow;

    return matchesSearch && matchesStatus && matchesQuickView && matchesTrust && matchesReview && matchesWorkflow;
  });
}

function getSelectedCase() {
  return state.cases.find((caseRecord) => caseRecord.id === state.selectedCaseId) || null;
}

function renderBadge(label, tone) {
  return `<span class="pill-badge tone-${tone}">${escapeHtml(label)}</span>`;
}

function setBadge(element, label, tone) {
  element.className = `pill-badge tone-${tone}`;
  element.textContent = label;
}

function renderBadgeRow(badges) {
  if (!Array.isArray(badges) || !badges.length) {
    return '';
  }
  const content = badges.map((badge) => {
    return `<span class="pill-badge tone-${escapeHtml(badge.tone || 'neutral')}">${escapeHtml(badge.label)}</span>`;
  }).join('');
  return `<div class="badge-row">${content}</div>`;
}

function renderCaseSnapshotItem(item) {
  const tone = item.tone || 'neutral';
  return `
    <article class="case-snapshot-item tone-panel-${escapeHtml(tone)}">
      <span class="case-snapshot-label">${escapeHtml(item.label)}</span>
      <strong class="case-snapshot-value">${escapeHtml(item.value)}</strong>
      <p class="case-snapshot-copy">${escapeHtml(item.copy)}</p>
    </article>
  `;
}

function renderInlineActions(actions) {
  if (!Array.isArray(actions) || !actions.length) {
    return '';
  }
  return `
    <div class="mapping-row-actions">
      ${actions.map((action) => {
        const attribute = escapeHtml(action.attribute || '');
        const value = escapeHtml(action.value || '');
        const label = escapeHtml(action.label || 'Open');
        return `<button class="text-button inline-button" type="button" ${attribute}="${value}">${label}</button>`;
      }).join('')}
    </div>
  `;
}

function renderStackItem(item) {
  const tone = item.tone || 'neutral';
  const eyebrow = item.eyebrow ? `<p class="stack-eyebrow">${escapeHtml(item.eyebrow)}</p>` : '';
  const meta = item.meta ? `<p class="stack-meta">${escapeHtml(item.meta)}</p>` : '';
  const badges = renderBadgeRow(item.badges);
  const actions = renderInlineActions(item.actions);
  return `
    <article class="stack-item tone-panel-${escapeHtml(tone)} ${item.highlighted ? 'is-highlighted' : ''}">
      ${eyebrow}
      <h4>${escapeHtml(item.title)}</h4>
      <p class="stack-copy">${escapeHtml(item.copy)}</p>
      ${meta}
      ${badges}
      ${actions}
    </article>
  `;
}

function renderTimelineItem(item) {
  const tone = item.tone || 'neutral';
  const kicker = item.kicker ? `<span class="timeline-kicker">${escapeHtml(item.kicker)}</span>` : '';
  const badges = renderBadgeRow(item.badges);
  const actions = renderInlineActions(item.actions);
  return `
    <article class="timeline-item tone-panel-${escapeHtml(tone)} ${item.highlighted ? 'is-highlighted' : ''}">
      <div class="timeline-top">
        <div class="timeline-heading">
          ${kicker}
          <strong class="timeline-kind">${escapeHtml(item.title)}</strong>
        </div>
        <span class="timeline-meta">${escapeHtml(item.time)}</span>
      </div>
      ${badges}
      <div class="timeline-content">${escapeHtml(item.copy)}</div>
      ${actions}
    </article>
  `;
}

function setStatus(message, tone) {
  elements.loadStatus.className = `status-banner ${tone}`;
  elements.loadStatus.textContent = message;
}

function createCaseId(sourceName, manifest) {
  return [
    manifest.workflow_id || 'workflow',
    manifest.created_at || sourceName,
    sourceName,
  ].join('::');
}

function deriveSignerLabel(manifest) {
  if (!manifest.signature) {
    return 'No signer';
  }
  const parts = String(manifest.signature).split(':');
  return parts[1] || 'Attached signer';
}

function getLatestReviewEntry(caseRecord) {
  const reviews = caseRecord?.review?.reviews;
  return Array.isArray(reviews) && reviews.length ? reviews[reviews.length - 1] : null;
}

function summarizeFault(fault) {
  const category = fault.category || fault.fault_type || 'Finding';
  const step = fault.step_number != null ? ` at step ${fault.step_number}` : '';
  const detail = fault.why_it_matters || fault.description || fault.details || 'Needs human attention.';
  return `${category}${step}. ${detail}`;
}

function stepLabel(kind) {
  const mapping = {
    'tool.call': 'Business check started',
    'tool.response': 'Business check completed',
    'llm.request': 'AI was consulted',
    'llm.response': 'AI response recorded',
    'agent.approval.request': 'Human approval requested',
    'agent.approval.response': 'Human approval recorded',
    'agent.decision': 'Final decision recorded',
    'agent.run.end': 'Workflow completed',
  };
  return mapping[kind] || sentenceCase(String(kind).replace(/\./g, ' '));
}

async function openCaseReviewForm() {
  let caseRecord = getSelectedCase();
  if (!caseRecord) {
    return;
  }

  try {
    caseRecord = await ensureCaseInReview(caseRecord);
  } catch (error) {
    elements.reviewSaveStatus.textContent = `Could not start the review workflow: ${error.message}`;
  }

  elements.reviewForm.scrollIntoView({ behavior: 'smooth', block: 'start' });
  if (elements.reviewerName.value.trim()) {
    elements.reviewNotes.focus();
  } else {
    elements.reviewerName.focus();
  }
}

function summarizeStep(step, index) {
  const content = step.content || {};
  if (step.kind === 'source.record.loaded') {
    const recordId = content.record_id || content.case_id || 'the source record';
    return `Loaded ${recordId} from ${content.system || 'the source system'} as a review preview.`;
  }
  if (step.kind === 'llm.request') {
    return `AI was consulted using ${content.model || 'the configured model'} before the final decision was recorded.`;
  }
  if (step.kind === 'llm.response') {
    const firstChoice = Array.isArray(content.choices) ? content.choices[0] : null;
    const responseText = firstChoice?.message?.content || 'Model returned a response.';
    return truncate(responseText, 220);
  }
  if (step.kind === 'agent.approval.request') {
    return `Requested approval for ${content.action || 'the next action'}.`;
  }
  if (step.kind === 'agent.approval.response') {
    return `${content.reviewer || 'Reviewer'} ${content.approved ? 'approved' : 'did not approve'} ${content.action || 'the requested action'}.`;
  }
  if (step.kind === 'agent.decision') {
    return `Final decision recorded: ${businessDecisionLabel(content.decision || content.result || 'decision captured')}.`;
  }
  return truncate(JSON.stringify(content || {}, null, 2) || `Step ${index + 1}`, 220);
}

function downloadBlob(filename, content, mimeType) {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function formatDate(value) {
  if (!value) {
    return 'Not provided';
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return String(value);
  }
  return date.toLocaleString();
}

function compareIsoDates(left, right) {
  const leftTime = Date.parse(left || 0);
  const rightTime = Date.parse(right || 0);
  return leftTime - rightTime;
}

function stripExtension(filename) {
  return filename.replace(/\.[^.]+$/, '');
}

function sentenceCase(value) {
  const text = String(value || '').replace(/[_-]+/g, ' ').trim();
  if (!text) {
    return 'Decision captured';
  }
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function truncate(value, maxLength) {
  const text = String(value || '');
  if (text.length <= maxLength) {
    return text;
  }
  return text.slice(0, maxLength - 1) + '...';
}

function slugify(value) {
  return String(value || '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '');
}

function toCsvCell(value) {
  const text = String(value ?? '');
  return `"${text.replace(/"/g, '""')}"`;
}

function mapReviewOutcome(outcome) {
  return REVIEW_ACTIONS[outcome]?.label || 'Reviewed';
}

function escapeHtml(value) {
  if (value == null) {
    return '';
  }
  const div = document.createElement('div');
  div.textContent = String(value);
  return div.innerHTML;
}
