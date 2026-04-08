from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_web_viewer_shell_has_case_investigation_navigation():
    html = _read("web_viewer/index.html")

    assert "EPI Case Investigation" in html
    assert "Queue" in html
    assert "Case investigation" in html
    assert "Connect a source when you are ready" in html
    assert "Export recorder starter" in html
    assert "Overview" in html
    assert "Evidence" in html
    assert "Policy" in html
    assert "Review" in html
    assert "Mapping" in html
    assert "Trust" in html
    assert "Attachments" in html
    assert "Transformation audit" in html
    assert "Inspect raw source files and derived artifacts" in html
    assert 'id="epi-view-context"' in html
    assert 'id="open-setup-utility-button"' in html
    assert 'id="open-rules-utility-button"' in html
    assert 'id="open-reports-utility-button"' in html
    assert 'id="case-overview-signals"' in html
    assert 'id="case-overview-narrative"' in html
    assert 'id="case-source-badge"' in html
    assert 'id="case-import-badge"' in html
    assert 'id="case-audit-badge"' in html
    assert 'id="case-policy-flow"' in html
    assert 'id="case-mapping-summary"' in html
    assert 'id="case-mapping-groups"' in html
    assert 'id="case-trust-grid"' in html
    assert 'id="case-attachments"' in html
    assert 'id="attachment-preview-body"' in html
    assert "../epi_viewer_static/crypto.js" in html
    assert "app.js" in html
    assert "styles.css" in html


def test_web_viewer_app_supports_source_aware_case_investigation():
    js = _read("web_viewer/app.js")

    assert "async function parseEpiFile" in js
    assert "async function buildCaseRecord" in js
    assert "function deriveSourceProfile" in js
    assert "function buildAttachmentGroups" in js
    assert "function buildTraceabilityIndex" in js
    assert "function buildOverviewPresentation" in js
    assert "function buildPolicyFlow" in js
    assert "function buildEvidenceSummary" in js
    assert "function buildTrustRows" in js
    assert "function buildTrustAlerts" in js
    assert "function buildTransformationAuditView" in js
    assert "function renderTransformationAudit" in js
    assert "function renderAttachmentGroups" in js
    assert "function renderAttachmentPreview" in js
    assert "async function previewCaseAttachment" in js
    assert "async function downloadCaseAttachment" in js
    assert "function highlightCaseStep" in js
    assert "function focusCaseAttachment" in js
    assert "function renderCaseView" in js
    assert "function renderInbox" in js
    assert "function renderRulesView" in js
    assert "function renderReportsView" in js
    assert "artifacts/agt/mapping_report.json" in js
    assert "Transformation audit available" in js
    assert "AGT imported into EPI" in js
    assert "Unsigned but intact" in js
    assert "Tampered / do not use" in js
    assert "function renderInlineActions" in js
    assert "function buildTimelineActions" in js
    assert "function buildEmptyInboxContent" in js
    assert "function buildRecorderStarterFiles" in js
    assert "function buildSharedWorkspaceCaseExport" in js


def test_web_viewer_readme_describes_case_investigation_model():
    readme = _read("web_viewer/README.md")

    assert "case-first" in readme
    assert "Queue" in readme
    assert "Case" in readme
    assert "Overview" in readme
    assert "Evidence" in readme
    assert "Policy" in readme
    assert "Review" in readme
    assert "Mapping" in readme
    assert "Trust" in readme
    assert "Attachments" in readme
    assert "Source system: AGT" in readme
    assert "Import mode: EPI" in readme
    assert "transformation audit" in readme.lower()
    assert "Everything stays local to the browser" in readme
    assert "one `.epi` file" in readme
    assert "offline/local review" in readme
    assert "epi connect serve" in readme
