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
    assert "INTEGRITY FAIL" in js or "FAIL" in js


def test_web_viewer_self_checks_crypto_offline():
    """§1 Trust & Integrity must run noble-ed25519 self-check without epi view."""
    js = _read("web_viewer/app.js")
    crypto = _read("epi_viewer_static/crypto.js")
    html = _read("web_viewer/index.html")

    assert "async function selfVerifyEmbeddedCase" in js
    assert "verifyManifestSignature" in js
    assert "OPEN VIA EPI VIEW TO VERIFY" not in js
    assert "globalThis.verifyManifestSignature" in crypto
    assert "noble-ed25519" in crypto
    assert "verify-cmd-hint" in html
    assert "epilabs.org/verify" in html
    assert "integrity_scope" in js or "scope === 'partial'" in js or 'scope === "partial"' in js
    assert "renderTrustPlainSummary" in js
    assert "trust-plain-summary" in html
    assert "authority-ladder" in html
    assert "Advanced details" in html
    assert "epi keys trust" in html or "keys trust" in html


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
