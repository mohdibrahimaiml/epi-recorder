"""Smoke-test the viewer JS to prevent boot-crash regressions.
These run fast and on every test run — no browser needed.
"""
import json
from pathlib import Path

from epi_core.viewer_assets import _validate_app_js

REPO = Path(__file__).resolve().parent.parent


class TestViewerJSValidation:
    """app.js must pass structural checks on every test run."""

    def test_app_js_passes_validation(self):
        """The canonical web_viewer/app.js must validate."""
        js = (REPO / "web_viewer" / "app.js").read_text(encoding="utf-8")
        _validate_app_js(js)

    def test_app_js_has_no_bracedrift(self):
        """Every function in app.js must have balanced braces."""
        js = (REPO / "web_viewer" / "app.js").read_text(encoding="utf-8")
        for func in [
            "buildReviewedArtifactBytes",
            "buildReviewedFromOriginal",
            "summarizeStep",
            "renderVerdict",
            "renderAnalysis",
            "renderGovernance",
            "renderIntegrity",
            "renderAttestation",
        ]:
            idx = js.find(f"function {func}")
            if idx < 0:
                idx = js.find(f"async function {func}")
            if idx < 0:
                continue
            next_func = len(js)
            for marker in ["function ", "async function "]:
                pos = js.find(marker, idx + len(func) + 20)
                if pos > 0 and pos < next_func:
                    next_func = pos
            body = js[idx:next_func]
            opens = body.count("{")
            closes = body.count("}")
            assert opens == closes, (
                f"Brace drift in {func}(): {opens} open, {closes} close"
            )

    def test_no_syntax_bombs(self):
        """Patterns known to break boot must not exist."""
        js = (REPO / "web_viewer" / "app.js").read_text(encoding="utf-8")
        assert "delete manifest.signature" not in js, (
            "delete manifest.signature destroys Sign & Seal integrity"
        )

    def test_viewer_copies_stay_in_sync(self):
        """site/ and website/ copies must be identical to canonical."""
        canonical = (REPO / "web_viewer" / "app.js").read_text(encoding="utf-8")
        for copy_path in ("site/viewer/app.js", "website/viewer/app.js"):
            copy = (REPO / copy_path).read_text(encoding="utf-8")
            assert copy == canonical, (
                f"{copy_path} has diverged from web_viewer/app.js "
                f"({len(copy)} vs {len(canonical)} bytes). "
                f"Run: python scripts/sync_viewer_mirrors.py"
            )
