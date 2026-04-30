from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_web_viewer_shell_has_case_investigation_navigation():
    html = _read("web_viewer/viewer.html")

    assert "EPI_FORENSIC" in html
    assert "Official_Forensic_Record" in html
    assert "Governance" in html
    assert "Evidence_Log" in html
    assert 'id="epi-view-context"' in html
    assert 'id="forensic-index"' in html
    assert 'id="evidence-trace"' in html
    assert 'id="env-section"' in html


def test_web_viewer_app_supports_source_aware_case_investigation():
    js = _read("web_viewer/viewer.js")

    assert "async function initialize" in js
    assert "function deriveDecision" in js
    assert "function computeTrust" in js
    assert "function buildCausalGraph" in js
    assert "function extractFaults" in js
    assert "function renderDocument" in js
    assert "tampered" in js


def test_web_viewer_readme_describes_case_investigation_model():
    readme = _read("web_viewer/README.md")

    assert "Forensic Truth Engine" in readme
    assert "Official_Forensic_Record" in readme
    assert "0.0 Summary" in readme
    assert "1.0 Governance" in readme
    assert "2.0 Evidence_Log" in readme
    assert "3.0 Appendix" in readme
