from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_web_viewer_shell_has_forensic_navigation():
    html = _read("web_viewer/index.html")

    assert "EPI Forensic Artifact Viewer" in html
    assert "Audit_Index" in html
    assert "Evidence" in html
    assert 'id="epi-view-context"' in html
    assert 'id="forensic-index"' in html
    assert 'id="document-root"' in html
    assert 'id="integrity-status"' in html
    assert 'id="evidence-trace"' in html


def test_web_viewer_app_supports_forensic_rendering():
    js = _read("web_viewer/app.js")

    assert "function init" in js
    assert "function renderHeader" in js
    assert "function renderIntegrity" in js
    assert "function renderVerdict" in js
    assert "function renderEvidence" in js
    assert "function renderAttestation" in js
    assert "COMPROMISED" in js


def test_web_viewer_readme_describes_forensic_model():
    readme = _read("web_viewer/README.md")

    assert "EPI Forensic Artifact Viewer" in readme
    assert "forensic" in readme.lower()
    assert "Overview" in readme
    assert "Evidence" in readme
    assert "Policy" in readme
    assert "Review" in readme
    assert "Mapping" in readme
    assert "Trust" in readme
    assert "Attachments" in readme
