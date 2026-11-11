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
    # A release branch may be version-bumped before the wheel is uploaded; in
    # that state the banner must say so rather than claim it is already live.
    assert ("on PyPI" in home) or ("PyPI publish pending" in home)


def test_no_polyglot_by_default_claim():
    for name in ("index.html", "how-it-works.html"):
        text = _read(name)
        assert "is a valid HTML+ZIP polyglot binary" not in text, name
        assert "is a self-contained HTML+ZIP polyglot binary" not in text, name
        assert "data-only" in text.lower(), name

def test_sample_is_labelled_without_promising_a_pass():
    """The homepage sells the record; the verify page keeps the honest signer caveat."""
    home = _read("index.html")
    verify = _read("verify/index.html")
    assert "Decision Record" in home
    assert "epi demo" in home
    assert "DECISION: PASS" not in home
    # The technical caveat stays where the technical check lives.
    assert "signer unknown" in verify


def test_sample_files_exist():
    assert (SITE / "assets" / "sample.epi").is_file()
    assert (SITE / "assets" / "demo" / "decision-example.epi").is_file()

