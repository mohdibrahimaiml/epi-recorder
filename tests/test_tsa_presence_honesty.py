"""TSA honesty after offline validation (WP1a). No format/header changes.

New truth:
- The browser viewers never validate: they say "not validated" and name
  `epi verify` as the only place validation happens.
- epi_cli/verify.py validates new-scheme tokens offline; only legacy tokens
  (sealed before imprints) and unevaluated reports keep presence-only words.
- epi_core/checkpoints.py fails tampered checkpoint tokens and warns on
  unknown roots; it no longer calls live tokens "presence only".
- Public site copy names `epi verify` as the place validation happens.
"""

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
        assert "epi verify" in text, f"{p} must name epi verify as the validation place"


def test_cli_validates_new_scheme_tokens():
    text = (ROOT / "epi_cli" / "verify.py").read_text(encoding="utf-8")
    assert "sealed by key" in text
    assert "no later than" in text
    assert "CONTENTS-ONLY" in text
    assert "imprint_mismatch" in text
    assert "timestamp_verified" in text
    assert "legacy token" in text
    assert "imprint not recomputable" in text


def test_checkpoint_tokens_are_checked_not_presence_only():
    text = (ROOT / "epi_core" / "checkpoints.py").read_text(encoding="utf-8")
    assert "CHECKPOINT TIMESTAMP INVALID" in text
    assert "token presence only, not validated" not in text


def test_marketing_names_epi_verify_for_validation():
    for p in [
        ROOT / "website" / "index.html",
        ROOT / "website" / "enterprise.html",
        ROOT / "website" / "trust.html",
    ]:
        text = p.read_text(encoding="utf-8")
        assert "epi verify" in text, p
