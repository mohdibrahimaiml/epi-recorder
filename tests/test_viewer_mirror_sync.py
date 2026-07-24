"""CI guard: local web_viewer and crypto packages stay consistent.

Hosted multi-case Decision Ops (website/viewer + root viewer/) was removed.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_web_viewer_model_a_not_model_b():
    js = (ROOT / "web_viewer" / "app.js").read_text(encoding="utf-8")
    # Model A markers
    assert "epiBuildSignedReviewRecord" in js
    assert "epiBuildArtifactBinding" in js
    fn = js.split("async function buildReviewedArtifactBytes")[1].split(
        "async function downloadReviewedArtifact"
    )[0]
    assert "epiSignManifest" not in fn


def test_hosted_decision_ops_viewer_removed():
    """Public Decision Ops surface must stay gone."""
    assert not (ROOT / "viewer").exists()
    assert not (ROOT / "website" / "viewer").exists()
    # Old URLs should redirect via static stub / _redirects, not serve an app
    stub = (ROOT / "website" / "viewer.html").read_text(encoding="utf-8")
    assert "/verify/" in stub
    assert "Decision Ops" in stub  # only as removal notice
