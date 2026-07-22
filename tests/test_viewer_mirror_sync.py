"""CI guard: deploy mirrors of multi-case viewer must match viewer/ source."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

MIRRORS = [
    ROOT / "website" / "viewer" / "app.js",
    ROOT / "website" / "viewer" / "crypto.js",
]


def test_website_viewer_matches_source_viewer():
    src_app = (ROOT / "viewer" / "app.js").read_bytes()
    src_crypto = (ROOT / "viewer" / "crypto.js").read_bytes()
    assert (ROOT / "website" / "viewer" / "app.js").read_bytes() == src_app
    assert (ROOT / "website" / "viewer" / "crypto.js").read_bytes() == src_crypto


def test_crypto_js_synced_between_packages():
    a = (ROOT / "epi_viewer_static" / "crypto.js").read_bytes()
    b = (ROOT / "viewer" / "crypto.js").read_bytes()
    assert a == b


def test_web_viewer_model_a_not_model_b():
    js = (ROOT / "web_viewer" / "app.js").read_text(encoding="utf-8")
    # Model A markers
    assert "epiBuildSignedReviewRecord" in js
    assert "epiBuildArtifactBinding" in js
    fn = js.split("async function buildReviewedArtifactBytes")[1].split(
        "async function downloadReviewedArtifact"
    )[0]
    assert "epiSignManifest" not in fn
