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
