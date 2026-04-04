from pathlib import Path

import pytest


SITE_ROOT = Path(__file__).resolve().parents[1] / "epi-official-site"


def _require_site_repo() -> None:
    if not SITE_ROOT.exists():
        pytest.skip("epi-official-site is not present in this checkout")


def test_verify_page_uses_shared_verify_core():
    _require_site_repo()
    html = (SITE_ROOT / "verify.html").read_text(encoding="utf-8")
    assert "epi-verify-core.js" in html
    assert "analyzeArtifactBlob" in html


def test_hosted_cases_page_uses_trusted_renderer_only():
    _require_site_repo()
    html = (SITE_ROOT / "cases" / "index.html").read_text(encoding="utf-8")
    assert "epi-verify-core.js" in html
    assert "allowEmbeddedViewer: false" in html
    assert "viewer.html" not in html
    assert "openEmbeddedViewerHtml" not in html


def test_service_worker_caches_cases_page_and_verify_core():
    _require_site_repo()
    sw = (SITE_ROOT / "sw.js").read_text(encoding="utf-8")
    assert "./cases/" in sw
    assert "./js/epi-verify-core.js" in sw
