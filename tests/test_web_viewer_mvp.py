from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_web_viewer_shell_has_case_investigation_navigation():
    html = _read("web_viewer/index.html")

    assert "EPI Case Investigation" in html
    assert "Open local EPI cases" in html
    assert "Case investigation" in html
    assert "Evidence" in html
    assert 'id="epi-view-context"' in html
    assert 'id="file-input"' in html
    assert 'id="drop-zone"' in html
    assert 'class="page-shell"' in html


def test_web_viewer_app_supports_source_aware_case_investigation():
    js = _read("web_viewer/app.js")

    assert "function initApp" in js
    assert "function renderCaseView" in js
    assert "function deriveTrustState" in js
    assert "function deriveDecisionSummary" in js
    assert "function buildTrustRows" in js
    assert "function renderApp" in js
    assert "Tampered" in js


def test_web_viewer_readme_describes_case_investigation_model():
    readme = _read("web_viewer/README.md")

    assert "EPI Case Investigation Viewer" in readme
    assert "case-first" in readme
    assert "Overview" in readme
    assert "Evidence" in readme
    assert "Policy" in readme
    assert "Review" in readme
    assert "Mapping" in readme
    assert "Trust" in readme
    assert "Attachments" in readme
