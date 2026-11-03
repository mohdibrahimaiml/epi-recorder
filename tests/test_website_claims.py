"""The live site must not claim what the product does not do."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SITE = REPO_ROOT / "website"


def _read(rel: str) -> str:
    return (SITE / rel).read_text(encoding="utf-8")


def test_no_insurability_claim():
    banned = ("makes ai agents insurable", "insurable and auditable")
    offenders = [
        str(p.relative_to(REPO_ROOT))
        for p in SITE.rglob("*.html")
        if any(phrase in p.read_text(encoding="utf-8").lower() for phrase in banned)
    ]
    assert not offenders, offenders


def test_footer_matches_the_published_version():
    home = _read("index.html")
    assert "publish pending" not in home
    assert "on PyPI" in home


def test_no_polyglot_by_default_claim():
    for name in ("index.html", "how-it-works.html"):
        text = _read(name)
        assert "is a valid HTML+ZIP polyglot binary" not in text, name
        assert "is a self-contained HTML+ZIP polyglot binary" not in text, name
        assert "data-only" in text.lower(), name

def test_sample_is_labelled_integrity_only():
    """The demo sample must not imply a PASS: its signer is not pinned."""
    home = _read("index.html")
    verify = _read("verify/index.html")
    assert "signer unknown" in home
    assert "signer unknown" in verify
    # The honest PASS path is the local demo, not the downloadable sample.
    assert "epi demo" in home


def test_sample_files_exist():
    assert (SITE / "assets" / "sample.epi").is_file()
    assert (SITE / "assets" / "demo" / "decision-example.epi").is_file()

