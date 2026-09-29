"""Smoke-test the viewer JS to prevent boot-crash regressions.
These run fast and on every test run — no browser needed.

Single implementation: all structural checks live in
epi_core.viewer_assets (validate_app_js_source / js_brace_errors /
node_check_js). This file imports them — no duplicated slicing logic that
can drift from the pack-time validator.
"""
import json
import shutil
from pathlib import Path

import pytest

from epi_core.viewer_assets import (
    _validate_app_js,
    js_brace_errors,
    node_check_js,
    validate_app_js_source,
)

REPO = Path(__file__).resolve().parent.parent


# Balanced fixture containing the exact pattern that broke the old
# "function "-slicing validator: anonymous callbacks inside the checked code.
BALANCED_WITH_ANONYMOUS_CALLBACKS = """function renderIntegrity(caseData) {
  const fo = caseData.items || [];
  const titles = fo.slice(0, 5).map(function (e) { return (e.id || '') + ': ' + (e.reason || ''); }).join(' | ');
  const filtered = fo.filter(function (r) { return r && r.ok; });
  const s = "a { brace in a string }";
  const t = `outer ${inner({a: 1})} done`;
  // a { brace in a comment }
  /* another { brace } */
  if (filtered.length > 0) {
    return titles;
  }
  return '';
}
"""

UNBALANCED_FIXTURE = """function renderIntegrity(caseData) {
  const fo = caseData.items || [];
  if (fo.length > 0) {
    return fo;
  }
"""


class TestViewerJSValidation:
    """app.js must pass structural checks on every test run."""

    def test_app_js_passes_validation(self):
        """The canonical web_viewer/app.js must validate."""
        js = (REPO / "web_viewer" / "app.js").read_text(encoding="utf-8")
        _validate_app_js(js)

    def test_app_js_has_no_bracedrift(self):
        """Canonical app.js is brace-balanced under the shared scanner."""
        js = (REPO / "web_viewer" / "app.js").read_text(encoding="utf-8")
        assert js_brace_errors(js) == []

    def test_no_syntax_bombs(self):
        """Patterns known to break boot must not exist."""
        js = (REPO / "web_viewer" / "app.js").read_text(encoding="utf-8")
        assert "delete manifest.signature" not in js, (
            "delete manifest.signature destroys Sign & Seal integrity"
        )

    def test_anonymous_callbacks_do_not_break_validation(self):
        """Regression: anonymous `function (` callbacks must not corrupt the
        brace check (the old slicer cut the body at the callback and reported
        a phantom mismatch that broke all sealing)."""
        assert js_brace_errors(BALANCED_WITH_ANONYMOUS_CALLBACKS) == []

    def test_unbalanced_fixture_fails(self):
        """The scanner must catch a genuinely unbalanced function."""
        assert js_brace_errors(UNBALANCED_FIXTURE) != []

    def test_node_check_agrees_with_scanner(self):
        """Real grammar backstop: node --check passes the canonical file and
        the balanced fixture, and rejects the unbalanced one."""
        if shutil.which("node") is None:
            pytest.skip("node not installed")
        js = (REPO / "web_viewer" / "app.js").read_text(encoding="utf-8")
        assert node_check_js(js) == []
        assert node_check_js(BALANCED_WITH_ANONYMOUS_CALLBACKS) == []
        assert node_check_js(UNBALANCED_FIXTURE) != []

    def test_node_check_survives_thread_start_mock(self):
        """node_check_js must not depend on threading: pack-time validation
        runs inside suites that patch threading.Thread.start, and Windows
        pipe-draining spawns reader threads — DEVNULL avoids pipes entirely."""
        if shutil.which("node") is None:
            pytest.skip("node not installed")
        from unittest.mock import patch

        with patch("threading.Thread.start", return_value=None):
            assert node_check_js("var x = 1;") == []
            assert node_check_js("var x = ;") != []

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
