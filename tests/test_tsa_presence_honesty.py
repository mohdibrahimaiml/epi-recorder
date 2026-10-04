"""Item 5: TSA presence-only honesty. No format/header changes."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_viewer_does_not_claim_timestamped():
    for p in [
        ROOT / "website" / "viewer" / "app.js",
        ROOT / "web_viewer" / "app.js",
    ]:
        text = p.read_text(encoding="utf-8")
        assert "timestamped" not in text, f"{p} still claims timestamped"
        assert "not validated" in text


def test_checkpoint_mismatch_is_presence_only():
    text = (ROOT / "epi_core" / "checkpoints.py").read_text(encoding="utf-8")
    assert "independently timestamped record" not in text
    assert "not validated" in text


def test_marketing_qualifies_rfc3161():
    for p in [
        ROOT / "website" / "index.html",
        ROOT / "website" / "enterprise.html",
        ROOT / "website" / "trust.html",
    ]:
        text = p.read_text(encoding="utf-8")
        assert "signature not validated" in text or "not validated" in text, p
